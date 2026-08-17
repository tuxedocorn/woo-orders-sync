"""
Upserts parsed WooCommerce pickup-order line items into the
'Woo Pickup Orders' Smartsheet, keyed on Order Line Key (order_id-line_item_id)
so re-runs update existing rows instead of duplicating them.
"""
import os
import requests
from datetime import datetime, timezone
from typing import Dict, List

SMARTSHEET_TOKEN = os.environ["SMARTSHEET_ACCESS_TOKEN"]
SHEET_ID = 2023490038222724  # Woo Pickup Orders, in Sweet Corn 2026 workspace

BASE_URL = f"https://api.smartsheet.com/2.0/sheets/{SHEET_ID}"
HEADERS = {
    "Authorization": f"Bearer {SMARTSHEET_TOKEN}",
    "Content-Type": "application/json",
}

# Column IDs (from sheet creation) — column titles must match the sheet exactly
COLS = {
    "Order Number": 899570186096516,
    "Order Status": 5403169813467012,
    "Order Date": 3151369999781764,
    "Customer Name": 7654969627152260,
    "Customer Email": 2025470092939140,
    "Product": 6529069720309636,
    "Box Size": 4277269906624388,
    "Pickup City": 8780869533994884,
    "Pickup State": 195882744319876,
    "Pickup Date": 4699482371690372,
    "Pickup Start Time": 2447682558005124,
    "Pickup End Time": 6951282185375620,
    "Quantity": 1321782651162500,
    "Line Item Total": 5825382278532996,
    "Raw Product Name": 3573582464847748,
    "Parse OK": 8077182092218244,
    "Parse Error": 758832697741188,
    "Order Line Key": 5262432325111684,
    "Last Synced": 3010632511426436,
}


def _cell(col_title: str, value):
    return {"columnId": COLS[col_title], "value": value}


def get_existing_rows() -> Dict[str, int]:
    """Returns {order_line_key: row_id} for all rows currently on the sheet."""
    resp = requests.get(BASE_URL, headers=HEADERS, params={"include": "objectValue"}, timeout=30)
    resp.raise_for_status()
    sheet = resp.json()

    key_col_id = COLS["Order Line Key"]
    existing = {}
    for row in sheet.get("rows", []):
        for cell in row.get("cells", []):
            if cell.get("columnId") == key_col_id and cell.get("value"):
                existing[str(cell["value"])] = row["id"]
    return existing


def build_row_cells(parsed_row: Dict) -> List[Dict]:
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return [
        _cell("Order Number", parsed_row["order_number"]),
        _cell("Order Status", parsed_row["order_status"]),
        _cell("Order Date", parsed_row["order_date"]),
        _cell("Customer Name", parsed_row["customer_name"]),
        _cell("Customer Email", parsed_row["customer_email"]),
        _cell("Product", parsed_row.get("product")),
        _cell("Box Size", parsed_row.get("size")),
        _cell("Pickup City", parsed_row.get("city")),
        _cell("Pickup State", parsed_row.get("state")),
        _cell("Pickup Date", parsed_row.get("pickup_date")),
        _cell("Pickup Start Time", parsed_row.get("start_time")),
        _cell("Pickup End Time", parsed_row.get("end_time")),
        _cell("Quantity", parsed_row["quantity"]),
        _cell("Line Item Total", parsed_row["line_total"]),
        _cell("Raw Product Name", parsed_row["product_name"]),
        _cell("Parse OK", bool(parsed_row.get("parse_ok"))),
        _cell("Parse Error", parsed_row.get("parse_error")),
        _cell("Order Line Key", parsed_row["order_line_key"]),
        _cell("Last Synced", now_iso),
    ]


def upsert_rows(parsed_rows: List[Dict]):
    """
    Splits parsed_rows into updates (existing Order Line Key) and adds (new),
    then sends batched PUT/POST calls to the Smartsheet API.
    """
    existing = get_existing_rows()

    rows_to_add = []
    rows_to_update = []

    for pr in parsed_rows:
        cells = build_row_cells(pr)
        key = pr["order_line_key"]
        if key in existing:
            rows_to_update.append({"id": existing[key], "cells": cells})
        else:
            rows_to_add.append({"cells": cells, "toBottom": True})

    if rows_to_add:
        for i in range(0, len(rows_to_add), 400):  # Smartsheet batch limit
            chunk = rows_to_add[i:i + 400]
            resp = requests.post(f"{BASE_URL}/rows", headers=HEADERS, json=chunk, timeout=60)
            resp.raise_for_status()

    if rows_to_update:
        for i in range(0, len(rows_to_update), 400):
            chunk = rows_to_update[i:i + 400]
            resp = requests.put(f"{BASE_URL}/rows", headers=HEADERS, json=chunk, timeout=60)
            resp.raise_for_status()

    return {"added": len(rows_to_add), "updated": len(rows_to_update)}
