"""Weekly update for the store manager: figures computed by code, wording optionally by AI.

    python -m inventory.summary                 # last full week, code-written summary
    python -m inventory.summary --gemini        # also ask Gemini to write it, then verify every figure
"""
import argparse
import json
import re
from datetime import date, timedelta

from .ask import AIError, call_gemini
from .db import connect_readonly

LEVEL = 0.95


def last_full_week(conn):
    """The latest Monday-to-Sunday week that the data fully covers, with at least five trading days."""
    last = date.fromisoformat(conn.execute("SELECT MAX(date) FROM trading_days").fetchone()[0])
    monday = last - timedelta(days=last.weekday())
    if monday + timedelta(days=6) > last:
        monday -= timedelta(days=7)
    while True:
        n = conn.execute("SELECT COUNT(*) FROM trading_days WHERE date BETWEEN ? AND ?",
                         (monday.isoformat(), (monday + timedelta(days=6)).isoformat())).fetchone()[0]
        if n >= 5:
            return monday
        monday -= timedelta(days=7)


def week_facts(conn, monday=None):
    monday = monday or last_full_week(conn)
    start, end = monday.isoformat(), (monday + timedelta(days=6)).isoformat()
    prev_start, prev_end = (monday - timedelta(days=7)).isoformat(), (monday - timedelta(days=1)).isoformat()
    totals = "SELECT COALESCE(SUM(units + bulk_units), 0), COALESCE(SUM(revenue + bulk_revenue), 0) FROM daily_sales WHERE date BETWEEN ? AND ?"
    units, revenue = conn.execute(totals, (start, end)).fetchone()
    prev_units, prev_revenue = conn.execute(totals, (prev_start, prev_end)).fetchone()
    top = conn.execute("""SELECT s.product_code, p.description, SUM(s.units + s.bulk_units) AS u
                          FROM daily_sales s JOIN products p USING (product_code)
                          WHERE s.date BETWEEN ? AND ? GROUP BY s.product_code ORDER BY u DESC, s.product_code LIMIT 3""",
                       (start, end)).fetchall()
    stockouts = conn.execute("""SELECT COUNT(*), COALESCE(SUM(lost), 0), COUNT(DISTINCT product_code)
                                FROM simulation_daily WHERE service_level = ? AND date BETWEEN ? AND ? AND lost > 0""",
                             (LEVEL, start, end)).fetchone()
    week_last_day = conn.execute("SELECT MAX(date) FROM trading_days WHERE date BETWEEN ? AND ?", (start, end)).fetchone()[0]
    below = conn.execute("""SELECT d.product_code, p.description, d.on_hand, pol.reorder_point, d.on_order
                            FROM simulation_daily d JOIN policy pol ON pol.product_code = d.product_code
                              AND pol.service_level = d.service_level
                            JOIN products p ON p.product_code = d.product_code
                            WHERE d.service_level = ? AND d.date = ? AND d.on_hand <= pol.reorder_point
                            ORDER BY pol.reorder_point - d.on_hand DESC""", (LEVEL, week_last_day)).fetchall()
    change = lambda now, before: round(100 * (now - before) / before, 1) if before else None
    return {
        "week_start": start, "week_end": end, "service_level": LEVEL,
        "units": int(units), "revenue": round(revenue), "units_change_pct": change(units, prev_units),
        "revenue_change_pct": change(revenue, prev_revenue), "prior_week_units": int(prev_units),
        "prior_week_revenue": round(prev_revenue),
        "top_sellers": [{"product_code": c, "description": d, "units": int(u)} for c, d, u in top],
        "stockout_product_days": stockouts[0], "lost_units": int(stockouts[1]), "products_with_stockouts": stockouts[2],
        "below_reorder_point_count": len(below),
        "below_reorder_point": [{"product_code": c, "description": d, "on_hand": int(h), "reorder_point": int(r),
                                 "on_order": int(o)} for c, d, h, r, o in below[:5]],
        "note": "Sales are real (UCI Online Retail II). Stock positions come from the simulated 95% policy.",
    }


def _pct(x):
    return "no change data" if x is None else f"{'up' if x >= 0 else 'down'} {abs(x):.1f}%"


def written_summary(f):
    """Always available: every figure comes straight from the facts."""
    lines = [f"Week of {f['week_start']} to {f['week_end']}: {f['units']:,} units sold for £{f['revenue']:,} "
             f"(units {_pct(f['units_change_pct'])}, revenue {_pct(f['revenue_change_pct'])} on the week before)."]
    if f["top_sellers"]:
        lines.append("Top sellers: " + "; ".join(f"{t['description']} ({t['units']:,} units)" for t in f["top_sellers"]) + ".")
    if f["stockout_product_days"]:
        lines.append(f"Stockouts: {f['products_with_stockouts']} products ran out on {f['stockout_product_days']} "
                     f"product-days, losing {f['lost_units']:,} units of sales.")
    else:
        lines.append("No stockouts this week.")
    if f["below_reorder_point_count"]:
        names = ", ".join(b["description"] for b in f["below_reorder_point"][:3])
        lines.append(f"{f['below_reorder_point_count']} products are at or below their reorder point, led by {names}. "
                     "Check that their replenishment orders are on the way.")
    return " ".join(lines)


def _allowed(f):
    """Every number the facts contain, as it might be written: 1234, 1,234, 12.5, dates, product codes."""
    allowed = set()
    def walk(x):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            for v in (x, abs(x)):                 # "down 22.5%" is stored as -22.5
                allowed.add(round(float(v), 1))
                allowed.add(float(round(v)))
        elif isinstance(x, str):
            for n in re.findall(r"\d+(?:\.\d+)?", x):
                allowed.add(round(float(n), 1))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(f)
    for d in (f["week_start"], f["week_end"]):
        y, m, day = map(int, d.split("-"))
        allowed |= {float(y), float(m), float(day)}
    allowed |= {float(len(f["top_sellers"])), float(len(f["below_reorder_point"]))}
    return allowed


def check_summary(text, f):
    """Reject an AI summary that states any figure the verified facts do not contain."""
    if not isinstance(text, str) or not (40 <= len(text.strip()) <= 2000):
        raise ValueError("summary missing or the wrong length")
    found = [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]
    allowed = _allowed(f)
    bad = sorted({n for n in found if round(n, 1) not in allowed})
    if bad:
        raise ValueError(f"figures not in the verified facts: {bad}")
    return text.strip()


def gemini_summary(f, opener=None):
    prompt = ("Write a short weekly update (under 120 words) for a store manager from these verified facts. "
              "Use only these facts. Do not calculate new numbers, estimate, or round differently. "
              "End with one practical next step. Facts: " + json.dumps(f))
    text = call_gemini(prompt, json_output=False, opener=opener)
    try:
        return check_summary(text, f)
    except ValueError as exc:
        raise AIError(f"The AI summary was rejected: {exc}. Use the code-written summary instead.") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--week", help="Monday of the week to summarise, YYYY-MM-DD (default: last full week)")
    parser.add_argument("--gemini", action="store_true")
    args = parser.parse_args(argv)
    conn = connect_readonly()
    f = week_facts(conn, date.fromisoformat(args.week) if args.week else None)
    print("Code-written summary:\n" + written_summary(f))
    if args.gemini:
        try:
            print("\nAI-written summary (every figure checked against the facts):\n" + gemini_summary(f))
        except AIError as exc:
            print(f"\n{exc}")


if __name__ == "__main__":
    main()
