"""Ask your own question: Gemini drafts SQL, you approve it, then it runs read-only.

    python -m inventory "Which products sold most in November 2011?"
"""
import sys

from .ask import AIError, draft_sql, run_query
from .db import connect_readonly


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(__doc__)
        return 1
    question = " ".join(args)
    try:
        sql, assumptions = draft_sql(question)
    except AIError as exc:
        print(exc)
        return 1
    print("\nAI-drafted SQL:\n\n" + sql + "\n")
    if assumptions:
        print("Assumption: " + assumptions + "\n")
    if input("Run this query? Check it first. [y/N] ").strip().lower() != "y":
        print("Not run.")
        return 0
    try:
        columns, rows = run_query(connect_readonly(), sql)
    except Exception as exc:  # show any SQLite or safety error plainly
        print(f"Not run: {exc}")
        return 1
    print(" | ".join(columns))
    for row in rows[:50]:
        print(" | ".join(str(v) for v in row))
    if len(rows) > 50:
        print(f"... {len(rows) - 50} more rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
