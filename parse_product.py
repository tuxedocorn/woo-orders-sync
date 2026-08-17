import re
from datetime import datetime

MONTH_ABBR = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}

# Listings that describe a general farm pickup / promo item rather than a
# specific scheduled pickup slot -- these are legitimate products, just a
# different (older/simpler) naming convention with no fixed date to extract.
GENERIC_FARM_MARKERS = [
    "pick up at the shed",
    "fresh box of olathe sweet",
    "truck tour:",
    "fundraiser:",
    "support the farm",
    "local delivery:",  # fallback if the specific Local Delivery pattern below doesn't match
]


def _normalize_mojibake(s: str) -> str:
    """Fixes common encoding corruption where en-dash (–) shows up as 'â' due to
    a UTF-8/Latin-1 mismatch somewhere in the WooCommerce/WordPress pipeline."""
    return s.replace("â€“", "–").replace("â€”", "–").replace("â", "–")


def _resolve_year(month: int, day: int, reference_date: datetime):
    """No year in the source string, so assume current year unless that would
    put the date more than 60 days in the past (handles Dec -> Jan rollover)."""
    year = reference_date.year
    try:
        candidate = datetime(year, month, day)
    except ValueError:
        return None
    if (reference_date - candidate).days > 60:
        candidate = datetime(year + 1, month, day)
    return candidate.strftime("%Y-%m-%d")


def _parse_date_token(date_str: str, reference_date: datetime):
    """Accepts 'M/D' (e.g. 8/19) or abbreviated/full month name + day (e.g. 'Aug 19', 'August 19')."""
    date_str = date_str.strip()

    m = re.match(r"^(\d{1,2})/(\d{1,2})$", date_str)
    if m:
        return _resolve_year(int(m.group(1)), int(m.group(2)), reference_date)

    m = re.match(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2})$", date_str)
    if m:
        mon_key = m.group(1).lower()[:3]
        if mon_key in MONTH_ABBR:
            return _resolve_year(MONTH_ABBR[mon_key], int(m.group(2)), reference_date)

    return None


def _blank_result(raw_name: str) -> dict:
    return {
        "raw_name": raw_name, "product": None, "size": None, "city": None,
        "state": None, "location_note": None, "pickup_date": None,
        "start_time": None, "end_time": None, "parse_ok": False,
        "parse_error": None, "category": None,
    }


def parse_product_name(name: str, reference_date: datetime = None) -> dict:
    if reference_date is None:
        reference_date = datetime.now()

    result = _blank_result(name)
    clean_name = _normalize_mojibake(name)

    # ---- Pattern A: scheduled pickup slot ----
    # {Product} – {Box Size} – {City}, {ST} [(note)] - {Date} @ {Start} - {End}
    parts = [p.strip() for p in re.split(r"\s*–\s*", clean_name)]
    if len(parts) >= 3:
        location_block = "–".join(parts[2:])
        pattern = re.compile(
            r"^(?P<city>[^,]+),\s*(?P<state>[A-Za-z]{2})\s*"
            r"(?:\((?P<note>[^)]*)\)\s*)?"
            r"-\s*(?P<date>[A-Za-z]{3,9}\.?\s*\d{1,2}|\d{1,2}/\d{1,2})\s*@\s*"
            r"(?P<start>\d{1,2}:\d{2}\s*(?:[AaPp][Mm])?)\s*-\s*"
            r"(?P<end>\d{1,2}:\d{2}\s*[AaPp][Mm])\s*$"
        )
        m = pattern.match(location_block)
        if m:
            pickup_date = _parse_date_token(m.group("date"), reference_date)
            if pickup_date is not None:
                result["product"] = parts[0]
                result["size"] = parts[1]
                result["city"] = m.group("city").strip()
                result["state"] = m.group("state").strip().upper()
                result["location_note"] = m.group("note")
                result["pickup_date"] = pickup_date

                start_raw = m.group("start").strip()
                end_raw = m.group("end").strip().upper().replace(" ", "")
                if not re.search(r"[AaPp][Mm]", start_raw):
                    meridiem = re.search(r"[AaPp][Mm]", m.group("end")).group(0).upper()
                    start_raw = f"{start_raw} {meridiem}"
                result["start_time"] = start_raw.upper().replace(" ", "")
                result["end_time"] = end_raw
                result["parse_ok"] = True
                result["category"] = "scheduled_pickup"
                return result

    # ---- Pattern B: onion bag / variant format ----
    # {Product} – {Variant description} (Pickup in {City}, {ST}) - {Variant}
    if len(parts) == 2:
        onion_pattern = re.compile(
            r"^(?P<desc>.+?)\s*\(Pickup in (?P<city>[^,]+),\s*(?P<state>[A-Za-z]{2})\)\s*-\s*(?P<variant>.+)$"
        )
        m = onion_pattern.match(parts[1])
        if m:
            result["product"] = parts[0]
            result["size"] = m.group("variant").strip()
            result["city"] = m.group("city").strip()
            result["state"] = m.group("state").strip().upper()
            result["parse_ok"] = True
            result["category"] = "farm_pickup_no_schedule"
            return result

    # ---- Pattern C: "Local Delivery: Month Day, Year - ... - City, ST" ----
    # Note: the prefix ".*" is greedy (not ".*?") on purpose -- most of these
    # descriptions contain several " - " separated segments but only ONE comma
    # in the whole string (right before the state), so a non-greedy prefix
    # would stop at the first hyphen and swallow the whole middle description
    # into the city field. Greedy + backtracking correctly finds the LAST
    # " - City, ST" segment at the end instead.
    local_delivery_pattern = re.compile(
        r"^Local Delivery:\s*(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2}),?\s*(?P<year>\d{4})"
        r".*-\s*(?P<city>[^,]+),\s*(?P<state>[A-Za-z]{2})\d*\s*$"
    )
    m = local_delivery_pattern.match(clean_name)
    if m:
        mon_key = m.group("month").lower()[:3]
        if mon_key in MONTH_ABBR:
            try:
                pickup_date = datetime(
                    int(m.group("year")), MONTH_ABBR[mon_key], int(m.group("day"))
                ).strftime("%Y-%m-%d")
            except ValueError:
                pickup_date = None
            result["product"] = "Local Delivery - Sweet Corn"
            result["city"] = m.group("city").strip()
            result["state"] = m.group("state").strip().upper()
            result["pickup_date"] = pickup_date
            result["parse_ok"] = True
            result["category"] = "local_delivery"
            return result

    # ---- Pattern D: generic farm-pickup / promo listings with no fixed schedule ----
    lowered = clean_name.lower()
    if any(marker in lowered for marker in GENERIC_FARM_MARKERS):
        result["product"] = clean_name
        if "olathe" in lowered:
            result["city"] = "Olathe"
            result["state"] = "CO"
        result["parse_ok"] = True
        result["category"] = "farm_pickup_no_schedule"
        return result

    # ---- Nothing matched: genuine parse failure ----
    if len(parts) < 3:
        result["parse_error"] = f"Expected 3 en-dash-separated parts, got {len(parts)}"
    else:
        result["parse_error"] = f"Location/date block did not match any known pattern: '{parts[-1]}'"
    return result
