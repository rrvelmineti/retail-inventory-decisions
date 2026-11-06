"""Pilot log, the ask command's feedback step, and the go-live gate. Offline; no AI calls."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from evaluation import go_live
from inventory import __main__ as ask_cli
from inventory import pilot
from tests.test_inventory import GEMINI_ENV, fake_gemini

GOOD_SQL = "SELECT product_code, description FROM products ORDER BY product_code LIMIT 3"


def answers(*replies):
    """Stand-in for input(): returns the given replies in turn."""
    queue = list(replies)
    return lambda prompt="": queue.pop(0)


class PilotTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "pilot.db"

    def tearDown(self):
        self.tmp.cleanup()

    def ask(self, question, *replies, sql=GOOD_SQL, user=None):
        argv = (["--user", user] if user else []) + [question]
        opener = fake_gemini(json.dumps({"sql": sql, "assumptions": "Top 3 by code."}))
        with patch.dict(os.environ, GEMINI_ENV, clear=True), redirect_stdout(io.StringIO()):
            return ask_cli.main(argv, ask=answers(*replies), pilot_db=self.db, opener=opener)


class AskCommandTests(PilotTestCase):
    def test_every_path_is_logged_with_its_outcome(self):
        self.ask("Which products?", "y", "y")                          # ran, rated correct
        self.ask("Which products again?", "n")                         # declined
        self.ask("Drop it", "y", sql="DROP TABLE products")             # blocked
        self.ask("Which products, by Priya?", "y", "n", "Wrong year", user="priya")   # ran, rated wrong
        r = pilot.report(self.db)
        self.assertEqual((r["questions"], r["users"], r["sql_drafted"]), (4, 2, 4))
        self.assertEqual((r["approved_and_ran"], r["declined"], r["blocked"]), (2, 1, 1))
        self.assertEqual(r["approval_rate"], 0.75)                       # 3 of 4 drafts approved
        self.assertEqual((r["rated"], r["rated_correct"], r["accuracy_as_rated"]), (2, 1, 0.5))
        self.assertEqual(r["wrong_answers"][0]["note"], "Wrong year")

    def test_skipping_the_rating_leaves_feedback_empty(self):
        self.ask("Which products?", "y", "")
        r = pilot.report(self.db)
        self.assertEqual((r["approved_and_ran"], r["rated"], r["accuracy_as_rated"]), (1, 0, None))

    def test_no_gemini_key_is_logged(self):
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(io.StringIO()):
            code = ask_cli.main(["Which products?"], ask=answers(), pilot_db=self.db)
        self.assertEqual(code, 1)
        self.assertEqual(pilot.report(self.db)["questions"], 1)


class PilotReportTests(PilotTestCase):
    def test_wrong_answers_become_draft_evaluation_questions(self):
        self.ask("Which products sold most in 2011?", "y", "n", "Missed bulk sales")
        found = pilot.candidates(self.db)
        self.assertEqual(len(found), 1)
        self.assertEqual(set(found[0]) >= {"id", "question", "ordered", "reference_sql"}, True)
        self.assertEqual(found[0]["reference_sql"], "")                 # an analyst writes and verifies it
        self.assertEqual(found[0]["ai_sql_in_pilot"], GOOD_SQL)

    def test_bad_feedback_is_rejected(self):
        ask_id = pilot.record("q", outcome="ran", rows=1, path=self.db)
        with self.assertRaises(ValueError):
            pilot.give_feedback(ask_id, "great", path=self.db)
        with self.assertRaises(ValueError):
            pilot.give_feedback(999, "correct", path=self.db)

    def test_empty_report_reads_clearly(self):
        self.assertIn("No pilot questions", pilot.report_text(pilot.report(self.db)))


def run(*outcomes):
    return {"model": "m", "run_on": "2026-11-06", "results": [{"outcome": o} for o in outcomes]}


class GoLiveTests(unittest.TestCase):
    def test_nine_of_ten_correct_is_go(self):
        self.assertEqual(go_live.decide(go_live.checks(run(*["correct"] * 9, "failed to run"))), go_live.GO)

    def test_two_wrong_answers_block_go_live(self):
        rows = go_live.checks(run(*["correct"] * 8, "wrong answer", "wrong answer"))
        self.assertEqual(go_live.decide(rows), go_live.NO_GO)

    def test_a_blocked_query_is_reported_but_does_not_block(self):
        rows = go_live.checks(run(*["correct"] * 9, "blocked"))
        self.assertEqual(go_live.decide(rows), go_live.GO)
        self.assertEqual({r["id"]: r["status"] for r in rows}["blocked"], "fail")

    def test_without_an_ai_evaluation_it_is_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "go-live.md"
            with redirect_stdout(io.StringIO()):
                code = go_live.main(["--results", str(Path(tmp) / "missing.json"), "--out", str(out), "--no-pilot"])
            self.assertEqual(code, 2)
            self.assertIn("**Decision: NOT READY**", out.read_text())

    def test_pilot_figures_appear_in_the_report(self):
        p = {"questions": 5, "users": 2, "approved_and_ran": 4, "sql_drafted": 5, "rated": 4, "rated_correct": 3,
             "accuracy_as_rated": 0.75}
        text = go_live.report(run(*["correct"] * 10), go_live.checks(run(*["correct"] * 10)), go_live.GO, p)
        self.assertIn("rated 3 of 4 answers correct (75%)", text)


if __name__ == "__main__":
    unittest.main()
