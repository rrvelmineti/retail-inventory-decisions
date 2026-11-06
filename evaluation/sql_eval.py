"""Check AI-written SQL against verified answers and write the verification log.

Offline (checks the 10 verified queries run):   python -m evaluation.sql_eval
With Gemini (writes docs/sql-log.md):           set GEMINI_API_KEY and GEMINI_MODEL, then add --gemini
"""
import argparse
import json
import os
import sqlite3
from datetime import date
from pathlib import Path

from inventory.ask import AIError, draft_sql, run_query, same_answer
from inventory.db import connect_readonly

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "evaluation" / "questions.json"
LOG = ROOT / "docs" / "sql-log.md"
RESULTS = ROOT / "evaluation" / "results" / "sql_eval.json"


def evaluate(conn, questions, opener=None):
    rows = []
    for q in questions:
        cols, expected = run_query(conn, q["reference_sql"])
        entry = {"id": q["id"], "question": q["question"], "verified_sql": q["reference_sql"],
                 "ai_sql": None, "assumptions": "", "outcome": None, "note": ""}
        try:
            entry["ai_sql"], entry["assumptions"] = draft_sql(q["question"], opener=opener)
        except AIError as exc:
            entry.update(outcome="no answer", note=str(exc))
            rows.append(entry)
            continue
        try:
            _, actual = run_query(conn, entry["ai_sql"])
        except ValueError as exc:
            entry.update(outcome="blocked", note=f"Rejected by the read-only check: {exc}")
        except sqlite3.Error as exc:
            entry.update(outcome="failed to run", note=f"SQLite error: {exc}")
        else:
            ok = same_answer(expected, actual, q["ordered"])
            entry["outcome"] = "correct" if ok else "wrong answer"
            entry["note"] = (f"Returned {len(actual)} rows; matches the verified answer." if ok else
                             f"Returned {len(actual)} rows; the verified answer has {len(expected)}. "
                             "Corrected with the verified query.")
        rows.append(entry)
    return rows


def write_log(rows, model):
    correct = sum(r["outcome"] == "correct" for r in rows)
    out = [f"# AI-written SQL: verification log", "",
           f"Model: `{model}` · Run on {date.today().isoformat()} · **{correct} of {len(rows)} correct first time**", "",
           "Each question was given to Gemini with the schema description only (no data rows). "
           "The AI's query ran on a read-only copy of the database and its result was compared with a "
           "verified query. Where they differ, the verified query is the correction.", ""]
    for r in rows:
        out += [f"## {r['id']}. {r['question']}", "", f"**Outcome:** {r['outcome']}. {r['note']}", ""]
        if r["assumptions"]:
            out += [f"**AI's stated assumption:** {r['assumptions']}", ""]
        if r["ai_sql"]:
            out += ["AI query:", "", "```sql", r["ai_sql"], "```", ""]
        if r["outcome"] != "correct":
            out += ["Verified query (correction):", "", "```sql", r["verified_sql"], "```", ""]
        out += ["**What I checked:** ", ""]
    LOG.write_text("\n".join(out), encoding="utf-8")
    RESULTS.parent.mkdir(exist_ok=True)
    RESULTS.write_text(json.dumps({"model": model, "run_on": date.today().isoformat(),
                                   "correct": correct, "total": len(rows), "results": rows}, indent=2) + "\n")
    return correct


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gemini", action="store_true", help="ask Gemini for each query and write the log")
    args = parser.parse_args(argv)
    questions = json.loads(QUESTIONS.read_text())
    conn = connect_readonly()
    if not args.gemini:
        for q in questions:
            cols, rows = run_query(conn, q["reference_sql"])
            print(f"{q['id']:4} {len(rows):>3} rows  {q['question']}")
        print(f"\nAll {len(questions)} verified queries ran. Add --gemini to test AI-written SQL.")
        return
    rows = evaluate(conn, questions)
    correct = write_log(rows, os.environ.get("GEMINI_MODEL", ""))
    for r in rows:
        print(f"{r['id']:4} {r['outcome']:14} {r['question']}")
    print(f"\n{correct} of {len(rows)} correct first time. Log written to {LOG.relative_to(ROOT)}. "
          "Fill in 'What I checked' for each question.")


if __name__ == "__main__":
    main()
