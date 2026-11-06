"""Ask your own question: Gemini drafts SQL, you approve it, then it runs read-only.

    python -m inventory "Which products sold most in November 2011?"
    python -m inventory --user priya "Which products ran out most often in 2011?"

Every question is logged for the pilot report (python -m inventory.pilot), with your rating of the answer.
"""
import sqlite3
import sys

from . import pilot
from .ask import AIError, draft_sql, run_query
from .db import connect_readonly


def main(argv=None, ask=input, pilot_db=pilot.PILOT_DB, opener=None):
    args = sys.argv[1:] if argv is None else list(argv)
    user = "analyst"
    if args[:1] == ["--user"] and len(args) >= 2:
        user, args = args[1], args[2:]
    if not args:
        print(__doc__)
        return 1
    question = " ".join(args)
    log = dict(user=user, path=pilot_db)
    try:
        sql, assumptions = draft_sql(question, opener=opener)
    except AIError as exc:
        print(exc)
        pilot.record(question, outcome="no_sql", error=str(exc), **log)
        return 1
    log.update(sql=sql, assumptions=assumptions)
    print("\nAI-drafted SQL:\n\n" + sql + "\n")
    if assumptions:
        print("Assumption: " + assumptions + "\n")
    if ask("Run this query? Check it first. [y/N] ").strip().lower() != "y":
        pilot.record(question, outcome="declined", **log)
        print("Not run.")
        return 0
    conn = connect_readonly()
    try:
        columns, rows = run_query(conn, sql)
    except (ValueError, sqlite3.Error) as exc:  # the safety check or SQLite refused it
        pilot.record(question, outcome="blocked", error=str(exc), **log)
        print(f"Not run: {exc}")
        return 1
    finally:
        conn.close()
    ask_id = pilot.record(question, outcome="ran", rows=len(rows), **log)
    print(" | ".join(columns))
    for row in rows[:50]:
        print(" | ".join(str(v) for v in row))
    if len(rows) > 50:
        print(f"... {len(rows) - 50} more rows")
    rating = ask("\nWas this answer right? [y]es / [n]o / [u]nsure / Enter to skip: ").strip().lower()[:1]
    feedback = {"y": "correct", "n": "wrong", "u": "unsure"}.get(rating)
    if feedback:
        note = ask("What was wrong? (optional) ").strip() if feedback == "wrong" else ""
        pilot.give_feedback(ask_id, feedback, note, path=pilot_db)
        print("Thanks, recorded for the pilot report.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
