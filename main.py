"""
Woo Orders -> Smartsheet sync.

Fetches open (pending/processing/on-hold) WooCommerce orders, parses each
line item's product name for pickup date/location/box size, and upserts
into the 'Woo Pickup Orders' Smartsheet.

Env vars required:
  WOO_SITE_URL             e.g. https://tuxedocorn.com
  WOO_CONSUMER_KEY
  WOO_CONSUMER_SECRET
  SMARTSHEET_ACCESS_TOKEN
"""
from datetime import datetime

# Load credentials from .env BEFORE importing the other modules, since they
# read os.environ[...] at import time. Harmless no-op on GitHub Actions
# (where secrets are already real env vars and no .env file exists).
from dotenv import load_dotenv
load_dotenv()

from woo_client import fetch_open_orders, flatten_order_line_items
from parse_product import parse_product_name
from smartsheet_sync import upsert_rows


def main():
    print("Fetching open WooCommerce orders...")
    orders = fetch_open_orders()
    print(f"  Found {len(orders)} open orders")

    line_items = []
    for order in orders:
        line_items.extend(flatten_order_line_items(order))
    print(f"  {len(line_items)} total line items")

    reference_date = datetime.now()
    parsed_rows = []
    parse_failures = 0
    category_counts = {}

    for li in line_items:
        parsed = parse_product_name(li["product_name"], reference_date=reference_date)
        if not parsed["parse_ok"]:
            parse_failures += 1
        else:
            category_counts[parsed["category"]] = category_counts.get(parsed["category"], 0) + 1

        parsed_rows.append({
            **li,
            "product": parsed["product"],
            "size": parsed["size"],
            "city": parsed["city"],
            "state": parsed["state"],
            "pickup_date": parsed["pickup_date"],
            "start_time": parsed["start_time"],
            "end_time": parsed["end_time"],
            "parse_ok": parsed["parse_ok"],
            "parse_error": parsed["parse_error"],
            "category": parsed["category"],
            "location_note": parsed["location_note"],
            "order_line_key": f"{li['order_id']}-{li['line_item_id']}",
        })

    print("  Category breakdown:")
    for cat, count in sorted(category_counts.items()):
        print(f"    {cat}: {count}")
    if parse_failures:
        print(f"  WARNING: {parse_failures} product name(s) genuinely failed to parse — "
              f"check 'Parse Error' column in Smartsheet for details")

    print("Syncing to Smartsheet...")
    result = upsert_rows(parsed_rows)
    print(f"  Added {result['added']} rows, updated {result['updated']} rows")


if __name__ == "__main__":
    main()
