import re
from datetime import datetime

def parse_product_name(name: str, reference_date: datetime = None):
    """
    Parses product names like:
    'Olathe Sweet Sweet Corn – 1 Box (2 Dozen Ears) – Thornton, CO - 8/19 @ 10:00 - 11:30 AM'
    'Olathe Sweet Sweet Corn – 1 Box (2 Dozen Ears) – Westminster, CO (Tuesday) - 9/8 @ 10:00 AM - 11:30 AM'
    """
    if reference_date is None:
        reference_date = datetime.now()

    result = {
        "raw_name": name,
        "product": None,
        "size": None,
        "city": None,
        "state": None,
        "weekday_label": None,
        "pickup_date": None,
        "start_time": None,
        "end_time": None,
        "parse_ok": False,
        "parse_error": None,
    }

    # Split on en-dash "–" (with surrounding spaces)
    parts = [p.strip() for p in re.split(r"\s*–\s*", name)]
    if len(parts) < 3:
        result["parse_error"] = f"Expected 3 en-dash-separated parts, got {len(parts)}"
        return result

    result["product"] = parts[0]
    result["size"] = parts[1]
    location_block = "–".join(parts[2:])  # in case there's a 4th part with another –

    # Location block pattern:
    # City, ST (optional (Weekday)) - M/D @ START [AM/PM] - END AM/PM
    pattern = re.compile(
        r"^(?P<city>[^,]+),\s*(?P<state>[A-Za-z]{2})\s*"
        r"(?:\((?P<weekday>[A-Za-z]+)\)\s*)?"
        r"-\s*(?P<date>\d{1,2}/\d{1,2})\s*@\s*"
        r"(?P<start>\d{1,2}:\d{2}\s*(?:[AaPp][Mm])?)\s*-\s*"
        r"(?P<end>\d{1,2}:\d{2}\s*[AaPp][Mm])\s*$"
    )
    m = pattern.match(location_block)
    if not m:
        result["parse_error"] = f"Location/date block did not match pattern: '{location_block}'"
        return result

    result["city"] = m.group("city").strip()
    result["state"] = m.group("state").strip().upper()
    result["weekday_label"] = m.group("weekday")

    # Resolve date (no year in source) -> infer year, roll to next year if date already passed
    month, day = (int(x) for x in m.group("date").split("/"))
    year = reference_date.year
    try:
        candidate = datetime(year, month, day)
    except ValueError as e:
        result["parse_error"] = f"Invalid date {month}/{day}: {e}"
        return result

    # If the date is more than ~60 days in the past, assume it's next year (year rollover, e.g. Dec->Jan)
    if (reference_date - candidate).days > 60:
        candidate = datetime(year + 1, month, day)

    result["pickup_date"] = candidate.strftime("%Y-%m-%d")

    # Resolve start time; if start has no AM/PM, inherit from end
    start_raw = m.group("start").strip()
    end_raw = m.group("end").strip().upper().replace(" ", "")
    if not re.search(r"[AaPp][Mm]", start_raw):
        # borrow meridiem from end
        meridiem = re.search(r"[AaPp][Mm]", m.group("end")).group(0).upper()
        start_raw = f"{start_raw} {meridiem}"
    start_raw = start_raw.upper().replace(" ", "")

    result["start_time"] = start_raw
    result["end_time"] = end_raw
    result["parse_ok"] = True
    return result


if __name__ == "__main__":
    test_names = [
        "Olathe Sweet Sweet Corn – 1 Box (2 Dozen Ears) – Thornton, CO - 8/19 @ 10:00 - 11:30 AM",
        "Olathe Sweet Sweet Corn – 1 Box (2 Dozen Ears) – Westminster, CO (Tuesday) - 9/8 @ 10:00 AM - 11:30 AM",
        "Olathe Sweet Sweet Corn – 1 Box (2 Dozen Ears) – Westminster, CO (Tuesday) - 8/18 @ 10:00 AM - 11:30 AM",
    ]
    ref = datetime(2026, 8, 17)  # "today" per conversation
    for n in test_names:
        r = parse_product_name(n, reference_date=ref)
        print(r)
        print()
