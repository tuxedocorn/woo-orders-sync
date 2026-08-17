"""
WooCommerce REST API client — fetches orders that still need fulfillment.
Docs: https://woocommerce.github.io/woocommerce-rest-api-docs/#orders
"""
import os
import requests
from typing import List, Dict

WOO_SITE_URL = os.environ["WOO_SITE_URL"].rstrip("/")  # e.g. https://tuxedocorn.com
WOO_CONSUMER_KEY = os.environ["WOO_CONSUMER_KEY"]
WOO_CONSUMER_SECRET = os.environ["WOO_CONSUMER_SECRET"]

ORDERS_ENDPOINT = f"{WOO_SITE_URL}/wp-json/wc/v3/orders"

# Statuses that represent orders still needing fulfillment / pickup
OPEN_STATUSES = ["pending", "processing", "on-hold"]


def fetch_open_orders() -> List[Dict]:
    """
    Fetches all orders in OPEN_STATUSES, paginating through the WooCommerce API.
    Returns a flat list of raw order dicts (each with a 'line_items' array).
    """
    all_orders = []
    page = 1
    per_page = 100

    while True:
        resp = requests.get(
            ORDERS_ENDPOINT,
            auth=(WOO_CONSUMER_KEY, WOO_CONSUMER_SECRET),
            params={
                "status": ",".join(OPEN_STATUSES),
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
