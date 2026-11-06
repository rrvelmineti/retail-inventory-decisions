"""Go-live gate for AI-written SQL: compare the latest evaluation with the agreed criteria.

    python -m evaluation.sql_eval --gemini      # first, needs a Gemini key
    python -m evaluation.go_live                # reads evaluation/results/sql_eval.json

Writes evaluation/results/go-live.md. Exit code 0 = GO, 1 = NO-GO, 2 = NOT READY (no AI evaluation yet).
If a pilot has been run, its figures are added to the report for context (they do not change the decision).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation" / "results"
DEFAULT_RUN = RESULTS / "sql_eval.json"
GO, NO_GO, NOT_READY = "GO", "NO-GO", "NOT READY"

# Agreed with the store manager before the pilot. Blocking checks must pass for GO.
CRITERIA = [
    {"id": "accuracy", "label": "AI SQL correct first time", "outcome": "correct", "min_share": 0.9, "blocking": True},
    {"id": "wrong", "label": "Queries that ran but gave a wrong answer", "outcome": "wrong answer", "max": 1, "blocking": True},
    {"id": "failed", "label": "Queries that failed to run", "outcome": "failed to run", "max": 1, "blocking": False},
    {"id": "blocked", "label": "Queries refused by the read-only check", "outcome": "blocked", "max": 0, "blocking": False},
]


def checks(run, criteria=CRITERIA):
    results = run.get("results") if run else None
    out = []
    for c in criteria:
        row = {"id": c["id"], "label": c["label"], "blocking": c["blocking"]}
        target = f"at least {c['min_share']:.0%}" if "min_share" in c else f"at most {c['max']}"
        if not results:
            out.append({**row, "result": "not measured", "target": target, "status": "missing"})
            continue
        n = sum(r["outcome"] == c["outcome"] for r in results)
        if "min_share" in c:
            ok, shown = n / len(results) >= c["min_share"], f"{n} of {len(results)} ({n / len(results):.0%})"
        else:
            ok, shown = n <= c["max"], str(n)
        out.append({**row, "result": shown, "target": target, "status": "pass" if ok else "fail"})
    return out


def decide(rows):
    blocking = [r for r in rows if r["blocking"]]
    if any(r["status"] == "missing" for r in blocking):
        return NOT_READY
    return GO if all(r["status"] == "pass" for r in blocking) else NO_GO


def report(run, rows, decision, pilot=None):
    status = {"pass": "Pass", "fail": "**Fail**", "missing": "Not measured"}
    lines = ["# Go-live readiness: AI-written SQL", "", f"**Decision: {decision}**", ""]
    if run:
        lines += [f"Evaluation: `{run.get('model') or 'unknown model'}`, run on {run.get('run_on', 'unknown date')}, "
                  f"{len(run.get('results', []))} verified business questions.", ""]
    lines += ["| Check | Result | Target | Blocking | Status |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {r['label']} | {r['result']} | {r['target']} | {'yes' if r['blocking'] else 'no'} | {status[r['status']]} |"
              for r in rows]
    if pilot and pilot.get("questions"):
        acc = pilot["accuracy_as_rated"]
        lines += ["", "## Pilot so far", "",
                  f"{pilot['questions']} questions from {pilot['users']} user(s). Users ran the AI's SQL for "
                  f"{pilot['approved_and_ran']} of {pilot['sql_drafted']} drafts, and rated "
                  f"{pilot['rated_correct']} of {pilot['rated']} answers correct"
                  + (f" ({acc:.0%})." if acc is not None else ".")]
    lines += ["", {
        GO: "Every blocking check passes. Open the pilot to the store team, and review "
            "`python -m inventory.pilot` weekly. Add every answer marked wrong to the evaluation.",
        NO_GO: "A blocking check fails. Read the corrections in docs/sql-log.md, improve the schema description "
               "or the prompt, and run the evaluation again.",
        NOT_READY: "AI SQL has not been evaluated yet. Run `python -m evaluation.sql_eval --gemini` with a Gemini "
                   "key, then run this gate again.",
    }[decision], "", "Sign-off: ______________________  (store manager)   Date: __________", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--out", type=Path, default=RESULTS / "go-live.md")
    parser.add_argument("--no-pilot", action="store_true", help="leave the pilot figures out")
    args = parser.parse_args(argv)
    run = json.loads(args.results.read_text()) if args.results.exists() else None
    rows = checks(run)
    decision = decide(rows)
    pilot = None
    if not args.no_pilot:
        from inventory import pilot as pilot_log
        if pilot_log.PILOT_DB.exists():
            pilot = pilot_log.report()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report(run, rows, decision, pilot), encoding="utf-8")
    for r in rows:
        print(f"  {r['status']:8} {r['label']}: {r['result']} (target {r['target']})")
    print(f"\nDecision: {decision}. Wrote {args.out}")
    return {GO: 0, NO_GO: 1, NOT_READY: 2}[decision]


if __name__ == "__main__":
    sys.exit(main())
