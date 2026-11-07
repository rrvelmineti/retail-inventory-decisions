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

Discovery produces two documents:

- **The business requirements** ([business-requirements.md](business-requirements.md)): goals,
  17 requirements with acceptance criteria, assumptions, risks and a sign-off table.
- **The client settings** ([config/client_settings.json](../config/client_settings.json)): unit cost
  share, holding rate, service levels, order size, the client's real lead times and finance's hurdle
  return. `python -m inventory.settings` checks them and lists every problem at once, so a typo cannot
  quietly change every reorder point.

## 2. Load the client's data (week 2)

The client sends a sales export in its own format.

1. `python -m inventory.onboard export.csv` maps the columns by name. Anything it can't match is set
   by the analyst in `mapping.json`, never guessed.
2. Every row is checked: date in the agreed format, product code, whole-number quantity, price.
   Returns load as cancellations, and double exports are flagged.
3. The decision is **Ready to load** only when every required field is mapped and at most 1% of rows
   are rejected. Otherwise `rejected.csv`, with line numbers and reasons, goes back to the client.
4. The saved mapping is reused on next month's file.

On the sample export, all 17 planted bad rows were rejected and no good ones
([report](onboarding-sample-report.md)).

## 3. Decision support (weeks 2–3)

- Backtest the reorder policies on demand they never saw, and show the trade-off, not just one number.
  The manager chooses the service level; the recommendation (98%) explains why.
- Give finance the cash view: `python -m inventory.finance` writes the
  [finance summary](finance-summary.md). It shows the working capital tied up at each service level,
  and judges each step up against finance's hurdle return. Finance signs off the assumptions there.
- Build the Power BI dashboard around the decisions people make: what to reorder now, what each
  service level costs, and how stock moved.

## 4. Go-live gate for AI questions (end of week 3)

Before anyone outside the project uses AI-written SQL, it is scored on 10 verified business
questions (`python -m evaluation.sql_eval --gemini`). The criteria are agreed in advance:

| Check | Target | Blocks go-live |
| --- | --- | --- |
| AI SQL correct first time | at least 90% | Yes |
| Queries that ran but gave a wrong answer | at most 1 | Yes |
| Queries that failed to run | at most 1 | No |
| Queries refused by the read-only check | 0 | No |

`python -m evaluation.go_live` writes a GO, NO-GO or NOT READY decision with a sign-off line.
**Result on 7 Nov 2026: 9 of 10 correct, GO.** The miss (Q8) returned the top 5 products when the
question meant the single longest lead time. The fix was partly a clearer question, a useful lesson
for training users.

## 5. Pilot (weeks 4–5)

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

## 6. Training and change management

- 30 minutes on reading the AI's SQL: which table, which dates, regular or bulk sales.
- One rule: **check the stated assumption before running the query.**
- The weekly update is code-written from verified figures. The team learns why an AI rewrite that
  adds a number is rejected.

## 7. After go-live

- Weekly: pilot report, the reorder-now list, and the weekly update.
- Monthly: rerun the evaluation, including the questions added from the pilot, and the go-live gate.
- Next improvement, already identified: seasonal reorder points. Most stockout days fall in
  September to December under a single yearly average.

## 8. User acceptance and handover

Acceptance is run from the [UAT plan](uat-signoff.md): 27 cases, each traced to a requirement and,
where possible, to an automated test that reruns on every push. A test fails if any requirement is
left untested. The store manager and finance sign the plan's sign-off table.

The store team receives: the dashboard, the run commands in the README, the verified question set,
the client settings, the onboarding mapping, the requirements and signed UAT plan, and this playbook.
