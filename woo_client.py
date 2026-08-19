"""
WooCommerce REST API client — fetches ALL orders (any status) placed since
the season start, so Smartsheet reports can filter by status as needed
rather than the script deciding what counts as "open."
Docs: https://woocommerce.github.io/woocommerce-rest-api-docs/#orders
"""
import os
import requests
from typing import List, Dict

WOO_SITE_URL = os.environ["WOO_SITE_URL"].rstrip("/")  # e.g. https://tuxedocorn.com
WOO_CONSUMER_KEY = os.environ["WOO_CONSUMER_KEY"]
WOO_CONSUMER_SECRET = os.environ["WOO_CONSUMER_SECRET"]

ORDERS_ENDPOINT = f"{WOO_SITE_URL}/wp-json/wc/v3/orders"

# Only pull orders from this season onward (pre-sales started April 1, 2026).
# Change this each season, or move to an env var if you want it configurable
# without editing code.
SEASON_START = "2026-04-01T00:00:00"


def fetch_open_orders() -> List[Dict]:
    """
    Fetches ALL orders (status='any', which WooCommerce interprets as every
    status except 'trash') placed on or after SEASON_START, paginating
    through the WooCommerce API. Returns a flat list of raw order dicts
    (each with a 'line_items' array).

    Function name kept as fetch_open_orders for compatibility with main.py;
    despite the name it no longer filters by status -- filtering now happens
    in Smartsheet, using the 'Order Status' column this pulls in per row.
    """
    all_orders = []
    page = 1
    per_page = 100

    while True:
        resp = requests.get(
            ORDERS_ENDPOINT,
            auth=(WOO_CONSUMER_KEY, WOO_CONSUMER_SECRET),
            params={
                "status": "any",
                "after": SEASON_START,
                "per_page": per_page,
                "page": page,
                "orderby": "date",
                "order": "asc",
            },
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"WooCommerce API returned status {resp.status_code}")
            print(f"Response headers: {dict(resp.headers)}")
            print(f"Response body (first 1000 chars):\n{resp.text[:1000]}")
            resp.raise_for_status()

        try:
            batch = resp.json()
        except ValueError:
            print(f"WooCommerce API did not return JSON. Status: {resp.status_code}")
            print(f"Content-Type: {resp.headers.get('Content-Type')}")
            print(f"Response body (first 1000 chars):\n{resp.text[:1000]}")
            raise
        if not batch:
            break
        all_orders.extend(batch)

        total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
        if page >= total_pages:
            break
        page += 1

    return all_orders


def flatten_order_line_items(order: Dict) -> List[Dict]:
    """
    Turns one WooCommerce order into a list of line-item-level dicts,
    since pickup date/location live on the PRODUCT NAME of each line item,
    not the order as a whole.
    """
    customer_name = f"{order.get('billing', {}).get('first_name', '')} {order.get('billing', {}).get('last_name', '')}".strip()
    customer_email = order.get("billing", {}).get("email", "")
    order_date = order.get("date_created", "")[:10]  # YYYY-MM-DD

    rows = []
    for li in order.get("line_items", []):
        rows.append({
            "order_id": order["id"],
            "order_number": order.get("number", str(order["id"])),
            "order_status": order.get("status", ""),
            "order_date": order_date,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "line_item_id": li["id"],
            "product_name": li.get("name", ""),
            "quantity": li.get("quantity", 0),
            "line_total": li.get("total", ""),
        })
    return rows
