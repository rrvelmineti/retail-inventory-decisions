"""Pilot log: every question a business user asks, whether they ran the SQL, and whether the answer was right.

During a pilot the implementation team needs to know three things: are people using it, do they trust
the AI's SQL enough to run it, and where is it wrong. Every `python -m inventory "..."` question is
recorded here, in a separate writable database (the data itself stays read-only).

    python -m inventory.pilot                       # pilot report
    python -m inventory.pilot --candidates out.json # wrong answers, ready to become verified questions

Wrong answers become new verified questions in evaluation/questions.json, so the evaluation grows
from real use instead of guesses.
"""
import argparse
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .db import ROOT

PILOT_DB = ROOT / "data" / "pilot.db"
FEEDBACK = ("correct", "wrong", "unsure")

TABLE = """CREATE TABLE IF NOT EXISTS asks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asked_at TEXT NOT NULL,
    user TEXT NOT NULL,
    question TEXT NOT NULL,
    sql TEXT,
    assumptions TEXT,
    outcome TEXT NOT NULL,      -- no_sql | declined | blocked | ran
    rows INTEGER,
    error TEXT,
    feedback TEXT,              -- correct | wrong | unsure, or NULL when not given
    note TEXT
)"""


def connect(path=PILOT_DB):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(TABLE)
    return conn


def record(question, *, user="analyst", sql=None, assumptions="", outcome, rows=None, error=None, path=PILOT_DB):
    """Log one question. Returns its id so feedback can be added after the user sees the result."""
    if outcome not in ("no_sql", "declined", "blocked", "ran"):
        raise ValueError(f"Unknown outcome: {outcome}")
    with closing(connect(path)) as conn, conn:
        return conn.execute(
            "INSERT INTO asks (asked_at, user, question, sql, assumptions, outcome, rows, error) VALUES (?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), user, question, sql, assumptions or "",
             outcome, rows, error)).lastrowid


def give_feedback(ask_id, feedback, note="", path=PILOT_DB):
    if feedback not in FEEDBACK:
        raise ValueError(f"Feedback must be one of: {', '.join(FEEDBACK)}")
    with closing(connect(path)) as conn, conn:
        if conn.execute("UPDATE asks SET feedback = ?, note = ? WHERE id = ?", (feedback, note, ask_id)).rowcount == 0:
            raise ValueError(f"No question with id {ask_id}")


def report(path=PILOT_DB):
    """Adoption, trust and accuracy figures for the pilot."""
    with closing(connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        asks = [dict(r) for r in conn.execute("SELECT * FROM asks ORDER BY id")]
    total = len(asks)
    drafted = [a for a in asks if a["outcome"] != "no_sql"]
    ran = [a for a in asks if a["outcome"] == "ran"]
    rated = [a for a in ran if a["feedback"]]

    def share(part, whole):
        return round(len(part) / len(whole), 3) if whole else None
    return {
        "questions": total,
        "users": len({a["user"] for a in asks}),
        "first_asked": asks[0]["asked_at"] if asks else None,
        "last_asked": asks[-1]["asked_at"] if asks else None,
        "sql_drafted": len(drafted),
        "approved_and_ran": len(ran),
        "declined": sum(a["outcome"] == "declined" for a in asks),
        "blocked": sum(a["outcome"] == "blocked" for a in asks),
        "approval_rate": share([a for a in drafted if a["outcome"] in ("ran", "blocked")], drafted),
        "rated": len(rated),
        "rated_correct": sum(a["feedback"] == "correct" for a in rated),
        "rated_wrong": sum(a["feedback"] == "wrong" for a in rated),
        "accuracy_as_rated": share([a for a in rated if a["feedback"] == "correct"], rated),
        "wrong_answers": [{k: a[k] for k in ("id", "user", "question", "sql", "note")}
                          for a in asks if a["feedback"] == "wrong"],
    }


def candidates(path=PILOT_DB):
    """Wrong answers in the shape of evaluation/questions.json, for an analyst to complete and verify."""
    return [{"id": f"P{w['id']}", "question": w["question"], "ordered": False,
             "reference_sql": "", "ai_sql_in_pilot": w["sql"], "user_note": w["note"] or ""}
            for w in report(path)["wrong_answers"]]


def report_text(r):
    if not r["questions"]:
        return "No pilot questions logged yet. Ask one with: python -m inventory \"your question\""
    pct = lambda v: "n/a" if v is None else f"{v:.0%}"
    lines = [f"Pilot: {r['questions']} questions from {r['users']} user(s), {r['first_asked']} to {r['last_asked']}.",
             f"  SQL drafted: {r['sql_drafted']}  approved and ran: {r['approved_and_ran']}  "
             f"declined: {r['declined']}  blocked by the safety check: {r['blocked']}",
             f"  Approval rate (users chose to run the AI's SQL): {pct(r['approval_rate'])}",
             f"  Rated by users: {r['rated']}  correct: {r['rated_correct']}  wrong: {r['rated_wrong']}  "
             f"accuracy as rated: {pct(r['accuracy_as_rated'])}"]
    if r["wrong_answers"]:
        lines += ["", "Answers users marked wrong (add them to the evaluation with --candidates):"]
        lines += [f"  #{w['id']} {w['question']}" + (f"  ({w['note']})" if w["note"] else "") for w in r["wrong_answers"]]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidates", type=Path, help="write wrong answers as draft evaluation questions")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    r = report()
    print(json.dumps(r, indent=2) if args.json else report_text(r))
    if args.candidates:
        found = candidates()
        args.candidates.write_text(json.dumps(found, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {len(found)} draft question(s) to {args.candidates}. Write and verify reference_sql for each.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
