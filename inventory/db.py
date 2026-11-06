"""Load the processed CSVs into a SQLite database and describe its schema for people and for AI."""
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
DB_PATH = ROOT / "data" / "retail.db"

TABLES = {
    "products": "products.csv",
    "trading_days": "trading_days.csv",
    "daily_sales": "daily_sales.csv",
    "policy": "policy.csv",
    "simulation_daily": "simulation_daily.csv",
    "simulation_summary": "simulation_summary.csv",
    "reorder_status": "reorder_status.csv",
}

# This text is the only thing about the data that is sent to an AI model: names and meanings, no rows.
SCHEMA = """\
SQLite database for a UK online gift retailer. 50 regularly sold products. Dates are TEXT 'YYYY-MM-DD'.
Real sales: 2009-12-01 to 2011-12-09 (UCI Online Retail II). Stock levels and lead times are simulated.

products(product_code TEXT PRIMARY KEY, description TEXT, median_price REAL)  -- selling price in GBP
trading_days(date TEXT PRIMARY KEY, weekday TEXT, month TEXT)  -- one row per day the shop traded; month is 'YYYY-MM'
daily_sales(product_code TEXT, date TEXT, units INTEGER, revenue REAL, bulk_units INTEGER, bulk_revenue REAL)
  -- one row per product per trading day, zero when nothing sold. units/revenue are regular sales;
  -- bulk_units/bulk_revenue are one-off wholesale orders, kept separate. Total sales = units + bulk_units.
policy(product_code TEXT, service_level REAL, avg_daily REAL, sd_daily REAL, lead_time_days INTEGER, z REAL,
       unit_cost REAL, safety_stock INTEGER, reorder_point INTEGER, order_qty INTEGER)
  -- reorder policy set from 2010 regular demand; service_level is one of 0.8, 0.9, 0.95, 0.98, 0.99
simulation_daily(product_code TEXT, service_level REAL, date TEXT, demand INTEGER, sold INTEGER, lost INTEGER,
                 on_hand INTEGER, on_order INTEGER, ordered INTEGER)
  -- day-by-day 2011 backtest of each policy on real regular demand; lost > 0 means a stockout that day
simulation_summary(product_code TEXT, service_level REAL, days INTEGER, demand_units INTEGER, sold_units INTEGER,
                   lost_units INTEGER, stockout_days INTEGER, fill_rate REAL, avg_on_hand REAL,
                   avg_stock_value REAL, holding_cost REAL, lost_margin REAL, orders_placed INTEGER)
  -- 2011 totals per product and service level; money in GBP
reorder_status(product_code TEXT, date TEXT, on_hand INTEGER, on_order INTEGER, position INTEGER,
               reorder_point INTEGER, safety_stock INTEGER, order_qty INTEGER, below_reorder_point INTEGER)
  -- position of each product on the last day of data (2011-12-09) at the 0.95 service level; 1 = true
"""


def build(path=DB_PATH):
    path = Path(path)
    if path.exists():
        path.unlink()
    with sqlite3.connect(path) as conn:
        for table, file in TABLES.items():
            frame = pd.read_csv(PROCESSED / file, dtype={"product_code": str})
            if "below_reorder_point" in frame:
                frame["below_reorder_point"] = frame["below_reorder_point"].astype(int)
            frame.to_sql(table, conn, index=False)
        conn.execute("CREATE INDEX sales_by_product ON daily_sales(product_code, date)")
        conn.execute("CREATE INDEX sim_by_product ON simulation_daily(product_code, service_level, date)")
    return path


def connect_readonly(path=DB_PATH):
    """Open the database so that no query can change it."""
    path = Path(path).resolve()
    if not path.exists():
        build(path)
    # as_uri() gives file:///C:/... on Windows and file:///home/... on Linux, with spaces encoded.
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")
    return conn


if __name__ == "__main__":
    print(f"Built {build()}")
