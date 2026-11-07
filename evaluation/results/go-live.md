# Go-live readiness: AI-written SQL

**Decision: GO**

Evaluation: `gemini-3.5-flash-lite`, run on 2026-11-07, 10 verified business questions.

| Check | Result | Target | Blocking | Status |
| --- | --- | --- | --- | --- |
| AI SQL correct first time | 9 of 10 (90%) | at least 90% | yes | Pass |
| Queries that ran but gave a wrong answer | 1 | at most 1 | yes | Pass |
| Queries that failed to run | 0 | at most 1 | no | Pass |
| Queries refused by the read-only check | 0 | at most 0 | no | Pass |

Every blocking check passes. Open the pilot to the store team, and review `python -m inventory.pilot` weekly. Add every answer marked wrong to the evaluation.

Sign-off: ______________________  (store manager)   Date: __________
