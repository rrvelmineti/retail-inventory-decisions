"""Turn the public UCI Online Retail II workbook into small, clean analysis tables.

Source: Chen, D. (2019). Online Retail II [Dataset]. UCI Machine Learning Repository.
https://doi.org/10.24432/C5CG6D  Licence: CC BY 4.0.

Run:  python -m inventory.prepare path/to/online_retail_II.xlsx
"""
import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
TOP_PRODUCTS = 50
PRODUCT_CODE = r"^\d{5}[A-Z]{0,2}$"     # real products; excludes POST, DOT, M, BANK CHARGES, gift vouchers...
BULK_MIN_UNITS = 500                     # a single line this large, and far above normal, is a bulk order
BULK_PERCENTILE = 0.995


def load_workbook(path):
    sheets = pd.read_excel(path, sheet_name=None,
                           dtype={"Invoice": str, "StockCode": str, "Description": str, "Country": str})
    return pd.concat(sheets.values(), ignore_index=True)


def clean(raw):
    """Return order lines that represent real product sales, plus a log of what was removed."""
    df = raw.copy()
    df["code"] = df["StockCode"].str.upper().str.strip()
    df["Invoice"] = df["Invoice"].astype(str)
    log = {"raw_lines": len(df)}
    is_cancel = df["Invoice"].str.startswith("C")
    cancels = df[is_cancel & df["Customer ID"].notna()]
    df = df[~is_cancel]
    log["cancellation_lines"] = int(is_cancel.sum())
    keep = (df["Quantity"] > 0) & (df["Price"] > 0)
    log["zero_or_negative_lines"] = int((~keep).sum())
    df = df[keep]
    is_product = df["code"].str.match(PRODUCT_CODE)
    log["non_product_lines"] = int((~is_product).sum())
    df = df[is_product].copy()

    # A cancellation leaves the original line in place. Remove one original line per cancellation,
    # matched on customer, product and quantity, taking the most recent ones first.
    key = lambda d: d["Customer ID"].astype("Int64").astype(str) + "|" + d["code"] + "|" + d["Quantity"].abs().astype(int).astype(str)
    n_cancel = key(cancels).value_counts()
    df["key"] = key(df).where(df["Customer ID"].notna())
    df = df.sort_values("InvoiceDate")
    df["recent_rank"] = df.groupby("key").cumcount(ascending=False)
    cancelled = df["key"].notna() & (df["recent_rank"] < df["key"].map(n_cancel).fillna(0))
    log["cancelled_original_lines"] = int(cancelled.sum())
    df = df[~cancelled].drop(columns=["key", "recent_rank"])

    # Flag one-off wholesale lines; they are still sales but are not used to size everyday stock.
    threshold = df.groupby("code")["Quantity"].transform(lambda q: q.quantile(BULK_PERCENTILE))
    df["bulk_order"] = (df["Quantity"] >= BULK_MIN_UNITS) & (df["Quantity"] > threshold)
    log["bulk_order_lines"] = int(df["bulk_order"].sum())
    df["date"] = df["InvoiceDate"].dt.normalize()
    df["revenue"] = df["Quantity"] * df["Price"]
    log["clean_lines"] = len(df)
    return df, log


def build_tables(lines, top=TOP_PRODUCTS):
    """Pick consistently sold products and build daily demand on every trading day."""
    trading_days = pd.DataFrame({"date": sorted(lines["date"].unique())})
    y2010 = lines[lines["date"].dt.year == 2010]
    y2011 = lines[lines["date"].dt.year == 2011]
    active_2010 = y2010.groupby("code")["date"].nunique()
    sold_2011 = set(y2011["code"])
    eligible = active_2010[(active_2010 >= 150) & active_2010.index.isin(sold_2011)].index
    regular = y2010[~y2010["bulk_order"] & y2010["code"].isin(eligible)]
    chosen = regular.groupby("code")["Quantity"].sum().sort_values(ascending=False).head(top).index

    sel = lines[lines["code"].isin(chosen)]
    names = (sel.groupby(["code", "Description"]).size().reset_index(name="n")
             .sort_values("n", ascending=False).drop_duplicates("code").set_index("code")["Description"])
    products = pd.DataFrame({
        "product_code": chosen,
        "description": [" ".join(str(names.get(c, "")).split()).title() for c in chosen],
        "median_price": [round(sel.loc[sel["code"] == c, "Price"].median(), 2) for c in chosen],
    })
    grid = pd.MultiIndex.from_product([chosen, trading_days["date"]], names=["product_code", "date"]).to_frame(index=False)
    def daily(frame, name):
        return frame.groupby(["code", "date"]).agg(**{f"{name}units": ("Quantity", "sum"), f"{name}revenue": ("revenue", "sum")})
    reg = daily(sel[~sel["bulk_order"]], "")
    bulk = daily(sel[sel["bulk_order"]], "bulk_")
    sales = grid.merge(reg, left_on=["product_code", "date"], right_index=True, how="left") \
                .merge(bulk, left_on=["product_code", "date"], right_index=True, how="left").fillna(0)
    for col in ("units", "bulk_units"):
        sales[col] = sales[col].astype(int)
    for col in ("revenue", "bulk_revenue"):
        sales[col] = sales[col].round(2)
    trading_days["weekday"] = trading_days["date"].dt.day_name()
    trading_days["month"] = trading_days["date"].dt.strftime("%Y-%m")
    return products, sales, trading_days


def write(products, sales, trading_days, log, out=PROCESSED):
    out.mkdir(parents=True, exist_ok=True)
    products.to_csv(out / "products.csv", index=False)
    sales.assign(date=sales["date"].dt.strftime("%Y-%m-%d")).to_csv(out / "daily_sales.csv", index=False)
    trading_days.assign(date=trading_days["date"].dt.strftime("%Y-%m-%d")).to_csv(out / "trading_days.csv", index=False)
    pd.Series(log).to_frame("lines").to_csv(out / "cleaning_log.csv", index_label="step")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("xlsx", type=Path, help="online_retail_II.xlsx downloaded from UCI")
    args = parser.parse_args(argv)
    lines, log = clean(load_workbook(args.xlsx))
    products, sales, days = build_tables(lines)
    write(products, sales, days, log)
    for step, n in log.items():
        print(f"{step:28} {n:>10,}")
    print(f"Wrote {len(products)} products and {len(sales):,} product-days to {PROCESSED.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
