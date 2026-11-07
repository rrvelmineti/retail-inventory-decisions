"""Reorder points from past demand, then a backtest on later demand.

Reorder point = average daily demand x lead time + safety stock
Safety stock  = z (from the service level) x daily demand std dev x sqrt(lead time)

Policies are set from 2010 demand only, then tested day by day on real 2011 demand,
so the test never sees the data it was tuned on.

The business assumptions (cost share, holding rate, lead times, service levels) come from
config/client_settings.json and are checked before the run. See inventory/settings.py.

Run:  python -m inventory.policy
"""
import zlib
from math import sqrt
from pathlib import Path
from statistics import NormalDist

import pandas as pd

from .settings import Settings, SettingsError, load as load_settings

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

# Defaults, matching config/client_settings.json. The dataset has sales only, so these are a modelled
# scenario, stated openly. Runs read the client's settings file; these remain for reference and tests.
SERVICE_LEVELS = (0.80, 0.90, 0.95, 0.98, 0.99)
DEFAULT_LEVEL = 0.95
UNIT_COST_SHARE = 0.60          # unit cost as a share of the median selling price
HOLDING_RATE_YEAR = 0.25        # yearly cost of holding stock, as a share of its value
TRADING_DAYS_YEAR = 302         # this retailer trades about six days a week
ORDER_COVER_DAYS = 24           # each replenishment order covers about four weeks of demand
LEAD_TIME_RANGE = (5, 20)       # supplier lead time in trading days, fixed per product
TRAIN_YEAR, TEST_YEAR = 2010, 2011


def lead_time(code):
    """A stable, product-specific lead time so results are reproducible."""
    low, high = LEAD_TIME_RANGE
    return low + zlib.crc32(code.encode()) % (high - low + 1)


def build_policies(products, sales, levels=None, train_year=TRAIN_YEAR, settings=None):
    settings = settings or Settings()
    levels = settings.service_levels if levels is None else levels
    train = sales[pd.to_datetime(sales["date"]).dt.year == train_year]
    stats = train.groupby("product_code")["units"].agg(avg_daily="mean", sd_daily="std")
    rows = []
    for p in products.itertuples():
        avg, sd = stats.loc[p.product_code, "avg_daily"], stats.loc[p.product_code, "sd_daily"]
        lt = settings.lead_time(p.product_code)
        for level in levels:
            z = NormalDist().inv_cdf(level)
            safety = z * sd * sqrt(lt)
            rows.append({
                "product_code": p.product_code, "service_level": level, "avg_daily": round(avg, 2),
                "sd_daily": round(sd, 2), "lead_time_days": lt, "z": round(z, 3),
                "unit_cost": round(p.median_price * settings.unit_cost_share, 2),
                "safety_stock": round(safety), "reorder_point": round(avg * lt + safety),
                "order_qty": max(1, round(avg * settings.order_cover_days)),
            })
    return pd.DataFrame(rows)


def simulate(policy, demand):
    """Run one product under one policy over the test days.

    Each day: receive due orders, serve demand from stock (unmet demand is lost),
    then reorder whenever stock on hand plus stock on order is at or below the reorder point.
    """
    rop, q, lt = int(policy.reorder_point), int(policy.order_qty), int(policy.lead_time_days)
    on_hand, pipeline, rows = rop + q, {}, []
    for i, (date, d) in enumerate(demand.itertuples(index=False)):
        on_hand += pipeline.pop(i, 0)
        sold = min(on_hand, d)
        lost = d - sold
        on_hand -= sold
        on_order = sum(pipeline.values())
        ordered = 0
        while on_hand + on_order + ordered <= rop:
            ordered += q
        if ordered:
            pipeline[i + lt] = pipeline.get(i + lt, 0) + ordered
        rows.append((date, d, sold, lost, on_hand, on_order + ordered, ordered))
    return pd.DataFrame(rows, columns=["date", "demand", "sold", "lost", "on_hand", "on_order", "ordered"])


def run_backtest(products, sales, policies, test_year=TEST_YEAR, settings=None):
    settings = settings or Settings()
    test = sales[pd.to_datetime(sales["date"]).dt.year == test_year]
    daily_rate = settings.holding_rate_year / settings.trading_days_year
    sims, summary = [], []
    for pol in policies.itertuples():
        demand = test.loc[test["product_code"] == pol.product_code, ["date", "units"]]
        sim = simulate(pol, demand)
        sim.insert(0, "service_level", pol.service_level)
        sim.insert(0, "product_code", pol.product_code)
        sims.append(sim)
        holding = (sim["on_hand"] * pol.unit_cost * daily_rate).sum()
        summary.append({
            "product_code": pol.product_code, "service_level": pol.service_level,
            "days": len(sim), "demand_units": int(sim["demand"].sum()), "sold_units": int(sim["sold"].sum()),
            "lost_units": int(sim["lost"].sum()), "stockout_days": int((sim["lost"] > 0).sum()),
            "fill_rate": round(sim["sold"].sum() / max(sim["demand"].sum(), 1), 4),
            "avg_on_hand": round(sim["on_hand"].mean(), 1),
            "avg_stock_value": round(sim["on_hand"].mean() * pol.unit_cost, 2),
            "holding_cost": round(holding, 2),
            "lost_margin": round(sim["lost"].sum() * (pol.unit_cost / settings.unit_cost_share - pol.unit_cost), 2),
            "orders_placed": int((sim["ordered"] > 0).sum()),
        })
    return pd.concat(sims, ignore_index=True), pd.DataFrame(summary)


def tradeoff(summary):
    """One row per service level: the stockout versus holding-cost trade-off across all products."""
    t = summary.groupby("service_level").agg(
        demand_units=("demand_units", "sum"), lost_units=("lost_units", "sum"),
        stockout_days=("stockout_days", "sum"), product_days=("days", "sum"),
        avg_stock_value=("avg_stock_value", "sum"), holding_cost=("holding_cost", "sum"),
        lost_margin=("lost_margin", "sum")).reset_index()
    t["fill_rate"] = (1 - t["lost_units"] / t["demand_units"]).round(4)
    t["stockout_day_share"] = (t["stockout_days"] / t["product_days"]).round(4)
    t["total_cost"] = t["holding_cost"] + t["lost_margin"]
    money = ["avg_stock_value", "holding_cost", "lost_margin", "total_cost"]
    t[money] = t[money].round(2)
    return t


def reorder_status(policies, sims, level=None):
    """Where each product stands on the last day of the data, under the chosen service level."""
    level = DEFAULT_LEVEL if level is None else level
    last = sims[sims["service_level"] == level].groupby("product_code").tail(1)
    pol = policies[policies["service_level"] == level][["product_code", "reorder_point", "order_qty", "safety_stock"]]
    s = last.merge(pol, on="product_code")
    s["position"] = s["on_hand"] + s["on_order"]
    s["below_reorder_point"] = s["on_hand"] <= s["reorder_point"]
    return s[["product_code", "date", "on_hand", "on_order", "position", "reorder_point",
              "safety_stock", "order_qty", "below_reorder_point"]]


def main(settings_path=None):
    products = pd.read_csv(PROCESSED / "products.csv", dtype={"product_code": str})
    sales = pd.read_csv(PROCESSED / "daily_sales.csv", dtype={"product_code": str})
    try:
        settings = load_settings(settings_path or ROOT / "config" / "client_settings.json",
                                 known_products=set(products["product_code"]))
    except SettingsError as exc:
        raise SystemExit(f"{exc}\nNothing was run. Fix the settings file and try again.") from None
    if not settings.signed_off:
        print("Note: client settings are not yet signed off by the store manager and finance.\n")
    policies = build_policies(products, sales, settings=settings)
    sims, summary = run_backtest(products, sales, policies, settings=settings)
    t = tradeoff(summary)
    status = reorder_status(policies, sims, settings.default_service_level)
    policies.to_csv(PROCESSED / "policy.csv", index=False)
    sims.to_csv(PROCESSED / "simulation_daily.csv", index=False)
    summary.to_csv(PROCESSED / "simulation_summary.csv", index=False)
    t.to_csv(PROCESSED / "tradeoff.csv", index=False)
    status.to_csv(PROCESSED / "reorder_status.csv", index=False)
    print(t[["service_level", "fill_rate", "stockout_days", "lost_units", "avg_stock_value",
             "holding_cost", "lost_margin", "total_cost"]].to_string(index=False))
    print(f"\n{int(status['below_reorder_point'].sum())} of {len(status)} products are at or below their "
          f"reorder point on {status['date'].iloc[0]} at the {settings.default_service_level:.0%} service level.")


if __name__ == "__main__":
    main()
