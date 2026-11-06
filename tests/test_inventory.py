"""Offline tests. No test calls a live AI service; Gemini responses are simulated."""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from evaluation.sql_eval import evaluate
from inventory.ask import AIError, check_read_only, draft_sql, run_query, same_answer
from inventory.db import SCHEMA, build, connect_readonly
from inventory.policy import (LEAD_TIME_RANGE, build_policies, lead_time, reorder_status, run_backtest,
                              simulate, tradeoff)
from inventory.prepare import clean
from inventory.summary import check_summary, gemini_summary, week_facts, written_summary

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
GEMINI_ENV = {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "test-model"}


def fake_gemini(*texts):
    """An opener returning canned Gemini responses in turn, recording each request body."""
    sent, queue = [], list(texts)

    class Response:
        def __init__(self, text):
            self.text = text

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            return json.dumps({"candidates": [{"finishReason": "STOP",
                                               "content": {"parts": [{"text": self.text}]}}]}).encode()

    def opener(request, timeout):
        sent.append(json.loads(request.data))
        return Response(queue.pop(0))
    opener.sent = sent
    return opener


def load(name):
    return pd.read_csv(PROCESSED / name, dtype={"product_code": str})


class CleaningTests(unittest.TestCase):
    def test_removes_cancellations_their_originals_and_non_products_and_flags_bulk(self):
        t = pd.Timestamp
        rows = [
            ("100", "21212", "CAKE CASES", 24, t("2010-01-04 10:00"), 0.55, 1.0),
            ("101", "21212", "CAKE CASES", 12, t("2010-01-05 10:00"), 0.55, 2.0),   # later cancelled
            ("C102", "21212", "CAKE CASES", -12, t("2010-01-05 11:00"), 0.55, 2.0),
            ("103", "POST", "POSTAGE", 1, t("2010-01-05 12:00"), 18.0, 3.0),
            ("104", "21212", "CAKE CASES", 0, t("2010-01-06 10:00"), 0.55, 1.0),
        ] + [(str(200 + i), "22197", "POPCORN HOLDER", 10, day, 0.85, 5.0)
             for i, day in enumerate(pd.date_range("2010-02-01", periods=300))] + [("999", "22197", "POPCORN HOLDER", 5000, t("2010-03-01"), 0.72, 9.0)]
        raw = pd.DataFrame(rows, columns=["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID"])
        lines, log = clean(raw)
        self.assertEqual(log["cancellation_lines"], 1)
        self.assertEqual(log["cancelled_original_lines"], 1)
        self.assertEqual(log["non_product_lines"], 1)
        self.assertEqual(log["zero_or_negative_lines"], 1)
        self.assertEqual(set(lines.loc[lines["code"] == "21212", "Invoice"]), {"100"})
        self.assertEqual(lines.loc[lines["bulk_order"], "Invoice"].tolist(), ["999"])


class PolicyTests(unittest.TestCase):
    def test_lead_time_is_stable_and_in_range(self):
        self.assertEqual(lead_time("85123A"), lead_time("85123A"))
        self.assertTrue(all(LEAD_TIME_RANGE[0] <= lead_time(c) <= LEAD_TIME_RANGE[1]
                            for c in load("products.csv")["product_code"]))

    def test_simulation_serves_from_stock_loses_unmet_demand_and_receives_after_lead_time(self):
        pol = pd.Series({"reorder_point": 5, "order_qty": 10, "lead_time_days": 2})
        demand = pd.DataFrame({"date": [f"d{i}" for i in range(6)], "units": [8, 4, 4, 4, 0, 0]})
        sim = simulate(pol, demand)
        # start 15; day0 sells 8 -> 7; day1 -> 3, reorder 10 due day3; day2 sells 3 of 4 (lost 1);
        # day3 receives 10, sells 4 -> 6; position 6 > 5 so no reorder.
        self.assertEqual(sim["on_hand"].tolist(), [7, 3, 0, 6, 6, 6])
        self.assertEqual(sim["lost"].tolist(), [0, 0, 1, 0, 0, 0])
        self.assertEqual(sim["ordered"].tolist(), [0, 10, 0, 0, 0, 0])

    def test_higher_service_level_means_more_stock_and_fewer_lost_units(self):
        products, sales = load("products.csv"), load("daily_sales.csv")
        policies = build_policies(products, sales)
        _, summary = run_backtest(products, sales, policies)
        t = tradeoff(summary).sort_values("service_level")
        self.assertTrue(t["lost_units"].is_monotonic_decreasing)
        self.assertTrue(t["holding_cost"].is_monotonic_increasing)
        committed = load("tradeoff.csv")
        pd.testing.assert_frame_equal(t.reset_index(drop=True), committed, check_dtype=False)

    def test_policy_uses_only_2010_demand(self):
        products, sales = load("products.csv"), load("daily_sales.csv")
        changed = sales.copy()
        changed.loc[changed["date"] >= "2011-01-01", "units"] *= 10
        pd.testing.assert_frame_equal(build_policies(products, sales), build_policies(products, changed))


class SqlSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = build(Path(cls.tmp.name) / "retail.db")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.conn = connect_readonly(self.db)

    def tearDown(self):
        self.conn.close()

    def test_only_single_select_statements_pass_the_text_check(self):
        for sql in ("DELETE FROM products", "SELECT 1; DROP TABLE products", "PRAGMA table_info(products)",
                    "ATTACH 'x.db' AS y", "", "   "):
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                check_read_only(sql)
        self.assertEqual(check_read_only("SELECT 'a;b';"), "SELECT 'a;b'")

    def test_writes_hidden_in_a_with_clause_are_refused_by_the_database(self):
        with self.assertRaises(sqlite3.DatabaseError):
            run_query(self.conn, "WITH x AS (SELECT 1) DELETE FROM products")
        self.assertEqual(run_query(self.conn, "SELECT COUNT(*) FROM products")[1], [(50,)])

    def test_row_limit(self):
        with self.assertRaises(ValueError):
            run_query(self.conn, "SELECT * FROM daily_sales")

    def test_answer_comparison_ignores_names_extra_columns_and_order_when_allowed(self):
        expected = [("a", 1.004), ("b", 2.0)]
        self.assertTrue(same_answer(expected, [("Item A", "a", 1.0), ("Item B", "b", 2.0)], ordered=True))
        self.assertTrue(same_answer(expected, [("b", 2.0), ("a", 1.0)], ordered=False))
        self.assertFalse(same_answer(expected, [("b", 2.0), ("a", 1.0)], ordered=True))
        self.assertFalse(same_answer(expected, [("a", 1.0)], ordered=False))
        self.assertFalse(same_answer(expected, [("a", 1.5), ("b", 2.0)], ordered=False))

    def test_all_verified_queries_run(self):
        for q in json.loads((ROOT / "evaluation/questions.json").read_text()):
            with self.subTest(q["id"]):
                cols, rows = run_query(self.conn, q["reference_sql"])
                self.assertTrue(rows)

    def test_gemini_gets_schema_and_question_only(self):
        opener = fake_gemini(json.dumps({"sql": "SELECT 1", "assumptions": "none"}))
        with patch.dict(os.environ, GEMINI_ENV, clear=True):
            sql, _ = draft_sql("Which product sold most?", opener=opener)
        prompt = opener.sent[0]["contents"][0]["parts"][0]["text"]
        self.assertIn(SCHEMA, prompt)
        revenue = run_query(self.conn, "SELECT revenue FROM daily_sales WHERE revenue > 100 LIMIT 50")[1]
        self.assertFalse([r for (r,) in revenue if str(r) in prompt])
        self.assertEqual(sql, "SELECT 1")

    def test_evaluation_scores_and_corrects_ai_queries(self):
        questions = json.loads((ROOT / "evaluation/questions.json").read_text())[:3]
        answers = [
            {"sql": questions[0]["reference_sql"].replace("units_2011", "total"), "assumptions": ""},  # correct
            {"sql": "SELECT substr(date,1,7), SUM(revenue) FROM daily_sales WHERE date LIKE '2011%' GROUP BY 1",
             "assumptions": "Regular sales only."},                                                    # wrong: no bulk
            {"sql": "DROP TABLE simulation_summary", "assumptions": ""},                               # blocked
        ]
        with patch.dict(os.environ, GEMINI_ENV, clear=True):
            rows = evaluate(self.conn, questions, opener=fake_gemini(*map(json.dumps, answers)))
        self.assertEqual([r["outcome"] for r in rows], ["correct", "wrong answer", "blocked"])

    def test_missing_gemini_settings_give_a_clear_error(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(AIError):
            draft_sql("anything")


class SummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        conn = connect_readonly(build(Path(cls.tmp.name) / "retail.db"))
        cls.facts = week_facts(conn)
        conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_uses_last_week_fully_covered_by_data(self):
        self.assertEqual((self.facts["week_start"], self.facts["week_end"]), ("2011-11-28", "2011-12-04"))

    def test_code_written_summary_passes_its_own_figure_check(self):
        s = written_summary(self.facts)
        self.assertEqual(check_summary(s, self.facts), s)

    def test_ai_summary_with_invented_figures_is_rejected(self):
        good = (f"Sales were {self.facts['units']:,} units this week, up {self.facts['units_change_pct']}%. "
                "Check incoming orders for the products below their reorder point.")
        with patch.dict(os.environ, GEMINI_ENV, clear=True):
            self.assertEqual(gemini_summary(self.facts, opener=fake_gemini(good)), good)
            with self.assertRaises(AIError):
                gemini_summary(self.facts, opener=fake_gemini("Sales grew about 30% to roughly 25,000 units; reorder now."))


if __name__ == "__main__":
    unittest.main()
