# Implementation playbook: rolling out AI reporting and reorder decisions to a store team

How I would take this project from analysis to a team that uses it every week. The retailer's sales
are real (UCI Online Retail II); the engagement around it is a **hypothetical** plan.

## The engagement in one paragraph

A store manager judges reorder levels by feel, and every sales question waits for an analyst. The
engagement delivers two things: a reorder policy backed by a backtest on a year of real demand, and
plain-English questions answered by AI-written SQL that users approve before it runs. Success means
fewer stockouts at a known holding cost, and questions answered in minutes without wrong figures
reaching decisions.

## Stakeholders

| Who | Role | Responsible for |
| --- | --- | --- |
| Store manager | Sponsor and main user | Chooses the service level, signs off go-live |
| Buyer | User | Places orders from the "reorder now" list |
| Finance | Approver | Accepts the holding-cost and margin assumptions |
| 2 pilot users (manager, buyer) | Pilot | Ask real questions, rate each answer |
| Implementation consultant (me) | Delivery lead | Discovery, policy, evaluation, pilot, training |

## 1. Discovery (week 1)

1. Which products cause the most pain: stockouts, or overstock?
2. What does a lost sale cost compared with holding one more unit? (This drives the recommendation.)
3. What are the supplier lead times, and how reliable are they?
4. Which questions does the team ask every week? (These become the verified question set.)
5. Who checks a figure before it drives an order or a report?

The assumptions that come out of this (margin, holding rate, lead times) are written down in
[data/README.md](../data/README.md), so finance can challenge them before anyone relies on the results.

## 2. Decision support (weeks 2–3)

- Backtest the reorder policies on demand they never saw, and show the trade-off, not just one number.
  The manager chooses the service level; the recommendation (98%) explains why.
- Build the Power BI dashboard around the decisions people make: what to reorder now, what each
  service level costs, and how stock moved.

## 3. Go-live gate for AI questions (end of week 3)

Before anyone outside the project uses AI-written SQL, it is scored on 10 verified business
questions (`python -m evaluation.sql_eval --gemini`). The criteria are agreed in advance:

| Check | Target | Blocks go-live |
| --- | --- | --- |
| AI SQL correct first time | at least 90% | Yes |
| Queries that ran but gave a wrong answer | at most 1 | Yes |
| Queries that failed to run | at most 1 | No |
| Queries refused by the read-only check | 0 | No |

`python -m evaluation.go_live` writes a GO, NO-GO or NOT READY decision with a sign-off line.

## 4. Pilot (weeks 4–5)

- Pilot users ask real questions: `python -m inventory --user <name> "..."`. They see the SQL and
  approve it before it runs, then rate the answer: right, wrong or unsure.
- Every question is logged in a separate pilot database; the data itself stays read-only.
- `python -m inventory.pilot` reports adoption and trust:

| Signal | What it tells me |
| --- | --- |
| Questions and users | Is the team using it? |
| Approval rate | Do users trust the SQL enough to run it? A low rate means the SQL is hard to read; add a plain-English explanation. |
| Accuracy as rated | Do users think the answers are right? |
| Answers marked wrong | `--candidates` exports each one as a draft evaluation question for an analyst to verify, so the test set grows from real use. |

## 5. Training and change management

- 30 minutes on reading the AI's SQL: which table, which dates, regular or bulk sales.
- One rule: **check the stated assumption before running the query.**
- The weekly update is code-written from verified figures. The team learns why an AI rewrite that
  adds a number is rejected.

## 6. After go-live

- Weekly: pilot report, the reorder-now list, and the weekly update.
- Monthly: rerun the evaluation, including the questions added from the pilot, and the go-live gate.
- Next improvement, already identified: seasonal reorder points. Most stockout days fall in
  September to December under a single yearly average.

## 7. Handover

The store team receives: the dashboard, the run commands in the README, the verified question set,
the assumptions in `data/README.md`, and this playbook.
