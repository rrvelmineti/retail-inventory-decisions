"""Make the synthetic sales export used to demonstrate client onboarding.

A new retailer's export looks nothing like the platform's format: different column names, UK dates
with times, returns as negative quantities, and the usual typing and export mistakes. This script
writes such a file with known, planted problems, and an answer key, so the onboarding checks can be
scored exactly.

    python examples/client/make_export.py

Products, descriptions and typical prices come from data/processed/products.csv. Every order line
is invented. The output is deterministic.
"""
import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HEADER = ["Order No", "Order Date", "SKU", "Item Name", "Qty", "Unit Price (GBP)", "Cust #", "Ship Country"]
ROWS = 600
COUNTRIES = ["United Kingdom"] * 8 + ["France", "Germany", "EIRE", "Netherlands"]

# Planted problems: (kind, how many). Blocking problems stop the row from loading; warnings load.
BLOCKING = [("missing_sku", 3), ("bad_date", 3), ("qty_not_number", 3), ("qty_fraction", 2),
            ("qty_zero", 2), ("price_negative", 2), ("price_missing", 2)]
WARNINGS = [("return", 4), ("duplicate", 3)]


def main():
    rng = random.Random(7)
    with (ROOT / "data" / "processed" / "products.csv").open(encoding="utf-8") as f:
        products = list(csv.DictReader(f))[:25]
    start = datetime(2012, 1, 2, 8, 0)
    rows, seen = [], set()
    order, line_in_order = 600100, 0
    for _ in range(ROWS):
        if line_in_order == 0 or rng.random() < 0.3:
            order += 1
            when = start + timedelta(days=rng.randrange(60), minutes=rng.randrange(600))
            cust, country = str(rng.randrange(12000, 18000)), rng.choice(COUNTRIES)
        line_in_order += 1
        while True:      # only planted duplicates may repeat a line exactly
            p = rng.choice(products)
            price = round(float(p["median_price"]) * rng.choice([0.9, 1, 1, 1, 1.1]), 2)
            row = [str(order), when.strftime("%d/%m/%Y %H:%M"), p["product_code"], p["description"],
                   str(rng.choice([1, 2, 3, 4, 6, 6, 12, 12, 24])), f"{price:.2f}", cust, country]
            if tuple(row) not in seen:
                break
        seen.add(tuple(row))
        rows.append(row)

    planted = []
    candidates = list(range(len(rows)))
    rng.shuffle(candidates)
    picks = iter(candidates)
    for kind, n in BLOCKING + WARNINGS:
        for _ in range(n):
            i = next(picks)
            r = rows[i]
            if kind == "missing_sku":
                r[2] = ""
            elif kind == "bad_date":
                r[1] = rng.choice(["31/02/2012 10:15", "2012-13-05", "next Tuesday"])
            elif kind == "qty_not_number":
                r[4] = rng.choice(["ten", "1O", "n/a"])
            elif kind == "qty_fraction":
                r[4] = "2.5"
            elif kind == "qty_zero":
                r[4] = "0"
            elif kind == "price_negative":
                r[5] = "-" + r[5]
            elif kind == "price_missing":
                r[5] = ""
            elif kind == "return":
                r[4] = "-" + r[4]
            planted.append({"kind": kind, "row_index": i})
    # Duplicates are exact copies of a line, inserted straight after it, as a double export would do.
    dup_rows = sorted((p["row_index"] for p in planted if p["kind"] == "duplicate"), reverse=True)
    for i in dup_rows:
        rows.insert(i + 1, list(rows[i]))
    # Line numbers in the file: header is line 1, so data row index i is line i + 2 after the inserts.
    index_to_line = {}
    shift = 0
    dup_set = set(dup_rows)
    for i in range(len(rows) - len(dup_rows)):
        index_to_line[i] = i + 2 + shift
        if i in dup_set:
            shift += 1
    key = [{"kind": p["kind"], "line": index_to_line[p["row_index"]] + (1 if p["kind"] == "duplicate" else 0)}
           for p in planted]

    with (HERE / "sales_export.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)
    (HERE / "answer_key.json").write_text(json.dumps({
        "about": "Planted problems in sales_export.csv. Line numbers count the header as line 1. "
                 "For duplicates, the line is the second copy.",
        "mapping": {"invoice": "Order No", "invoice_date": "Order Date", "product_code": "SKU",
                    "description": "Item Name", "quantity": "Qty", "unit_price": "Unit Price (GBP)",
                    "customer_id": "Cust #", "country": "Ship Country"},
        "date_format": "%d/%m/%Y %H:%M",
        "rows": len(rows),
        "blocking": sorted((k for k in key if k["kind"] not in dict(WARNINGS)), key=lambda k: k["line"]),
        "warnings": sorted((k for k in key if k["kind"] in dict(WARNINGS)), key=lambda k: k["line"]),
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} rows to {HERE / 'sales_export.csv'} with {len(key)} planted problems")


if __name__ == "__main__":
    main()
