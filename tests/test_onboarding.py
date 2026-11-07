"""Client data onboarding, client settings and the finance view. Offline; no AI calls."""
import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import pandas as pd

from inventory import finance, onboard, settings
from inventory.policy import build_policies, run_backtest, tradeoff
from inventory.prepare import clean

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "client"
KEY = json.loads((EXAMPLE / "answer_key.json").read_text())
SETTINGS = json.loads((ROOT / "config" / "client_settings.json").read_text())


def export(rows, header=("Order No", "Order Date", "SKU", "Item Name", "Qty", "Unit Price (GBP)")):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    w.writerows(rows)
    return out.getvalue().encode()


GOOD = ["5001", "03/01/2012 09:15", "22197", "Small Popcorn Holder", "12", "0.85"]


class OnboardingSampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = onboard.onboard((EXAMPLE / "sales_export.csv").read_bytes(), date_format=KEY["date_format"])

    def test_every_column_is_mapped_by_name(self):
        self.assertEqual(self.result["mapping"], KEY["mapping"])
        self.assertEqual(self.result["unmapped_columns"], [])

    def test_every_planted_blocking_problem_is_rejected_and_nothing_else(self):
        rejected = {f["line"] for f in self.result["findings"] if f["severity"] == onboard.BLOCKING}
        self.assertEqual(rejected, {p["line"] for p in KEY["blocking"]})

    def test_every_planted_warning_is_flagged_and_loaded(self):
        warned = {f["line"] for f in self.result["findings"] if f["severity"] == onboard.WARNING}
        self.assertEqual(warned, {p["line"] for p in KEY["warnings"]})
        self.assertEqual(self.result["returns"], 4)
        self.assertEqual(self.result["loaded"], KEY["rows"] - len(KEY["blocking"]))

    def test_too_many_rejects_means_not_ready(self):
        self.assertEqual(self.result["decision"], "Not ready")              # 17 of 603 is 2.8% > 1%
        relaxed = onboard.onboard((EXAMPLE / "sales_export.csv").read_bytes(), date_format=KEY["date_format"],
                                  max_reject_share=0.05)
        self.assertEqual(relaxed["decision"], "Ready to load")

    def test_clean_rows_pass_the_platforms_own_cleaning_step(self):
        df = pd.DataFrame(self.result["clean"])
        df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
        df["Customer ID"] = pd.to_numeric(df["Customer ID"])
        lines, log = clean(df)
        self.assertEqual(log["raw_lines"], self.result["loaded"])
        self.assertEqual(log["cancellation_lines"], 4)                      # returns arrive as C-invoices
        self.assertEqual(log["clean_lines"], self.result["loaded"] - 4)

    def test_outputs_are_written_and_the_mapping_can_be_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            with redirect_stdout(io.StringIO()):
                code = onboard.main([str(EXAMPLE / "sales_export.csv"), "--out", str(out)])
            self.assertEqual(code, 2)
            self.assertEqual({p.name for p in out.iterdir()}, {"clean.csv", "rejected.csv", "mapping.json", "report.md"})
            with (out / "rejected.csv").open(encoding="utf-8") as f:
                self.assertEqual(len({r["line"] for r in csv.DictReader(f)}), 17)
            self.assertIn("**Decision: Not ready**", (out / "report.md").read_text())
            with redirect_stdout(io.StringIO()):
                again = onboard.main([str(EXAMPLE / "sales_export.csv"), "--mapping", str(out / "mapping.json"),
                                      "--out", str(Path(tmp) / "again"), "--max-reject-share", "0.05"])
            self.assertEqual(again, 0)


class OnboardingRuleTests(unittest.TestCase):
    def run_rows(self, rows, **kw):
        return onboard.onboard(export(rows), **kw)

    def test_unknown_headings_are_left_for_the_analyst(self):
        r = onboard.onboard(export([GOOD], header=("Ref", "When", "SKU", "Item Name", "Qty", "Unit Price (GBP)")))
        self.assertEqual(r["decision"], "Not ready")
        self.assertEqual(r["missing_required"], ["invoice", "invoice_date"])
        fixed = onboard.onboard(export([GOOD], header=("Ref", "When", "SKU", "Item Name", "Qty", "Unit Price (GBP)")),
                                mapping={"invoice": "Ref", "invoice_date": "When"})
        self.assertEqual((fixed["decision"], fixed["loaded"]), ("Ready to load", 1))

    def test_a_heading_matching_two_fields_is_not_guessed(self):
        m = onboard.suggest_mapping(["Order No", "Order Date", "Date", "SKU", "Qty", "Price"])
        self.assertNotIn("invoice_date", m)                 # "Order Date" and "Date" both mean the date

    def test_dates_must_match_the_agreed_format(self):
        us = ["5001", "01/13/2012 09:15", "22197", "x", "1", "1.00"]
        self.assertEqual(self.run_rows([us])["rejected"], 1)                       # month 13 in UK format
        self.assertEqual(self.run_rows([us], date_format="%m/%d/%Y %H:%M")["rejected"], 0)
        self.assertEqual(self.run_rows([["5001", "03/01/2012", "22197", "x", "1", "1.00"]])["rejected"], 0)  # no time

    def test_bad_values_are_rejected_with_reasons(self):
        rows = [GOOD[:4] + ["2.5", "1.00"], GOOD[:4] + ["ten", "1.00"], GOOD[:4] + ["0", "1.00"],
                GOOD[:4] + ["1", "-1.00"], GOOD[:4] + ["1", "abc"], GOOD[:2] + ["22 197"] + GOOD[3:], GOOD[:3]]
        r = self.run_rows(rows)
        self.assertEqual((r["rows"], r["rejected"], r["loaded"]), (7, 7, 0))
        problems = {f["problem"] for f in r["findings"]}
        for text in ("not a whole number of units", "not a number", "zero units", "negative price", "contains a space"):
            self.assertIn(text, problems)
        self.assertTrue(any("columns" in p for p in problems))

    def test_currency_symbols_and_thousands_separators_are_accepted(self):
        r = self.run_rows([GOOD[:4] + ["1,200", "£1,050.50"]])
        self.assertEqual((r["rejected"], r["clean"][0]["Quantity"], r["clean"][0]["Price"]), (0, 1200, 1050.5))

    def test_returns_become_cancellation_invoices(self):
        r = self.run_rows([GOOD[:4] + ["-3", "0.85"]])
        self.assertEqual(r["clean"][0]["Invoice"], "C5001")
        self.assertEqual(r["warnings"], 1)

    def test_empty_file_and_bad_mapping_are_clear_errors(self):
        with self.assertRaises(ValueError):
            onboard.onboard(b"")
        with self.assertRaises(ValueError):
            onboard.onboard(export([GOOD]), mapping={"quantity": "Units"})


class SettingsTests(unittest.TestCase):
    def test_the_committed_settings_are_valid_and_match_the_published_defaults(self):
        s = settings.parse(SETTINGS)
        self.assertEqual(s, settings.Settings(client=s.client, sign_off=s.sign_off))
        self.assertFalse(s.signed_off)

    def test_every_problem_is_reported_at_once(self):
        bad = {**SETTINGS, "unit_cost_share": 1.5, "default_service_level": 0.97, "trading_days_year": 30.5,
               "service_levels": [0.9, 0.9, 1.0], "lead_time_days": {"default_range": [20, 5], "overrides": {"X": 0}},
               "holding_rate": 0.2}
        with self.assertRaises(settings.SettingsError) as ctx:
            settings.parse(bad)
        text = "\n".join(ctx.exception.problems)
        for expected in ("unit_cost_share", "default_service_level", "trading_days_year", "listed twice",
                         "1.0 must be a fraction", "default_range", "overrides.X", "holding_rate: unknown"):
            self.assertIn(expected, text)

    def test_overrides_must_name_planned_products(self):
        data = {**SETTINGS, "lead_time_days": {"default_range": [5, 20], "overrides": {"NOPE": 10}}}
        with self.assertRaises(settings.SettingsError):
            settings.parse(data, known_products={"22197"})

    def test_a_client_lead_time_changes_that_products_policy_only(self):
        products = pd.read_csv(ROOT / "data/processed/products.csv", dtype={"product_code": str}).head(3)
        sales = pd.read_csv(ROOT / "data/processed/daily_sales.csv", dtype={"product_code": str})
        code = products["product_code"].iloc[0]
        data = {**SETTINGS, "service_levels": [0.95], "lead_time_days": {"default_range": [5, 20], "overrides": {code: 40}}}
        before = build_policies(products, sales, settings=settings.parse({**data, "lead_time_days": SETTINGS["lead_time_days"]}))
        after = build_policies(products, sales, settings=settings.parse(data))
        self.assertEqual(after.loc[after.product_code == code, "lead_time_days"].item(), 40)
        self.assertGreater(after.loc[after.product_code == code, "reorder_point"].item(),
                           before.loc[before.product_code == code, "reorder_point"].item())
        others = lambda d: d[d.product_code != code].reset_index(drop=True)
        pd.testing.assert_frame_equal(others(before), others(after))

    def test_bad_json_is_reported_with_its_position(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "s.json"
            p.write_text('{"unit_cost_share": 0.6,}')
            with self.assertRaises(settings.SettingsError) as ctx:
                settings.load(p)
            self.assertIn("line 1", str(ctx.exception))


class FinanceTests(unittest.TestCase):
    def setUp(self):
        self.t = pd.read_csv(ROOT / "data/processed/tradeoff.csv")
        self.wc = finance.working_capital(self.t, 0.95)

    def test_working_capital_is_average_stock_value(self):
        self.assertEqual(self.wc["working_capital"].tolist(), self.t["avg_stock_value"].round(2).tolist())
        base = self.wc[self.wc.is_baseline].iloc[0]
        self.assertEqual((base.extra_working_capital, base.net_saving), (0, 0))

    def test_recommendation_respects_finances_hurdle(self):
        self.assertEqual(finance.recommend(self.wc, 0.10), 0.98)    # 98% -> 99% returns 1.5%
        self.assertEqual(finance.recommend(self.wc, 0.01), 0.99)
        self.assertEqual(finance.recommend(self.wc, 0.50), 0.80)    # 80% -> 90% returns about 46%

    def test_step_returns_match_the_readme(self):
        last = finance.steps(self.wc)[-1]
        self.assertEqual((last["from"], last["to"]), (0.98, 0.99))
        self.assertAlmostEqual(last["extra_cash"], 3465.42, places=2)
        self.assertAlmostEqual(last["net_saving"], 50.66, places=2)

    def test_summary_names_the_recommendation_and_asks_for_sign_off(self):
        md = finance.summary_markdown(self.wc, settings.parse(SETTINGS))
        self.assertIn("Moving from 95% to **98%**", md)
        self.assertIn("below finance's 10% hurdle", md)
        self.assertIn("| Finance | ______________ |", md)

    def test_committed_summary_is_up_to_date(self):
        md = finance.summary_markdown(self.wc, settings.parse(SETTINGS))
        self.assertEqual((ROOT / "docs" / "finance-summary.md").read_text(encoding="utf-8"), md,
                         "Run `python -m inventory.finance` and commit docs/finance-summary.md")

    def test_unknown_baseline_is_an_error(self):
        with self.assertRaises(ValueError):
            finance.working_capital(self.t, 0.85)


if __name__ == "__main__":
    unittest.main()
