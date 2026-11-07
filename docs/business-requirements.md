# Business requirements: inventory decisions for a retail client

| | |
| --- | --- |
| Client | UK online gift retailer (public data: UCI Online Retail II). The engagement is a worked example. |
| Sponsor | Store manager |
| Approvers | Store manager, finance |
| Prepared by | Implementation consultant |
| Version | 1.0, 7 November 2026 |
| Status | Draft for sign-off |

## 1. Background

The store manager sets reorder levels by feel. Popular lines run out in the run-up to Christmas, while
slow lines tie up cash all year. Every sales question waits for an analyst. The retailer wants reorder
decisions backed by evidence, a clear view of what stock costs, and faster answers to everyday questions,
without wrong figures reaching decisions.

## 2. Goals and success measures

| Goal | Measure | Target | Where it is measured |
| --- | --- | --- | --- |
| Fewer stockouts at a known cost | Fill rate in a backtest on demand the model never saw | At least 97% at the chosen level | `data/processed/tradeoff.csv` |
| Cash in stock spent well | Return on each extra step of stock, after holding cost | At least finance's hurdle (10% a year) | `docs/finance-summary.md` |
| Faster answers | Business questions answered without an analyst | 90% of verified questions correct first time | `evaluation/results/go-live.md` |
| Safe onboarding | Rows loaded that break the agreed rules | 0 | Onboarding report |

## 3. Scope

**In scope:** loading the client's sales history, reorder points and order quantities per product, a
service-level trade-off in units and money, a "reorder now" list, plain-English questions answered by
AI-written SQL that a person approves, a weekly summary, and a Power BI dashboard.

**Out of scope for this phase:** placing orders with suppliers, live stock feeds from the warehouse
system, supplier-specific minimum order quantities, and seasonal reorder points (planned next; see §8).

## 4. Business requirements

Priority: **M** = must have for go-live, **S** = should have.

| ID | Requirement | Priority | Acceptance criteria |
| --- | --- | --- | --- |
| BR-01 | Load the client's sales export in the client's own format | M | Columns are mapped by name. Any required field that can't be matched is set by the analyst, never guessed. The mapping is saved for reuse. |
| BR-02 | Load only rows that meet the agreed rules | M | Rows with a missing or invalid date, product, quantity or price are rejected, with their line number and reason. Returns load as cancellations. |
| BR-03 | Decide whether a file is fit to load | M | Ready to load only when every required field is mapped and rejected rows are at most 1% of the file. |
| BR-04 | Remove sales that did not happen | M | Cancellations and their original lines, postage, fees and zero-quantity lines are removed. Each step is counted in a cleaning log. |
| BR-05 | Keep one-off bulk orders from inflating everyday stock | M | Bulk lines are flagged, kept as sales, and left out when sizing stock. |
| BR-06 | Keep business assumptions in a client settings file, checked before any run | M | Unit cost share, holding rate, service levels, order cover and lead times live in `config/client_settings.json`. An invalid value stops the run and lists every problem. |
| BR-07 | Use the client's real supplier lead times where known | S | A lead time set for a product changes that product's policy only. |
| BR-08 | Set a reorder point and order quantity for every product | M | Set from one year of demand, tested on the next year. Results are reproducible. |
| BR-09 | Show the stockout versus holding-cost trade-off | M | For each service level: fill rate, stockout days, lost units, holding cost, lost margin and total cost. |
| BR-10 | Show the cash tied up in stock at each service level, for finance | M | Working capital per level, the change against the current level, and the return on each extra step, judged against finance's hurdle. |
| BR-11 | Recommend a service level that finance can sign off | M | Step up while each step clears the hurdle. The recommendation and the assumptions behind it carry sign-off lines. |
| BR-12 | List what to reorder now | M | Products at or below their reorder point on the latest day, with stock on hand and on order. |
| BR-13 | Answer plain-English questions safely | M | A person sees and approves the SQL before it runs. The database is read-only. Destructive, multi-statement and oversized queries are blocked. No data values are sent to the AI. |
| BR-14 | Know how far to trust AI-written SQL before go-live | M | Scored on verified business questions. Go-live needs at least 90% correct first time and at most 1 wrong answer. |
| BR-15 | Learn from real use during the pilot | S | Every question, approval and user rating is logged. Answers marked wrong become draft evaluation questions. |
| BR-16 | A weekly update the manager can trust | S | Every figure in the update must appear in the verified facts. An AI rewrite that adds a figure is rejected. |
| BR-17 | A dashboard for the decisions above | S | Power BI pages for reorder-now, the trade-off, stock over time and sales. The project validates against Microsoft's schemas. |

## 5. Assumptions and constraints

- The dataset has sales only. Unit cost, holding cost and lead times are modelled assumptions, set in
  `config/client_settings.json` and listed in [data/README.md](../data/README.md) until the client
  confirms them.
- Demand that cannot be met is lost, not back-ordered.
- AI is used only to draft SQL and, optionally, to reword the weekly update. It never sees data values
  and never decides anything on its own.

## 6. Risks

| Risk | Effect | Mitigation |
| --- | --- | --- |
| Assumed costs differ from the client's real costs | Recommendation shifts | Finance signs off the settings. The finance summary shows how each change affects the cost. |
| Client export changes format | Rows rejected or not mapped | The saved mapping is reused and checked every run. The report shows unmapped columns. |
| AI SQL is plausible but wrong | Wrong figure in a decision | Human approval, verified-question gate, pilot ratings, and a log of corrections. |
| Seasonal demand | Stockouts in September to December | Seasonal reorder points are next (§8). Until then, review the "reorder now" list weekly. |

## 7. Sign-off

Acceptance is tested against this document in the [UAT sign-off plan](uat-signoff.md).

| Role | Name | Signature | Date |
| --- | --- | --- | --- |
| Store manager (sponsor) | | | |
| Finance | | | |
| Implementation consultant | | | |

## 8. Next phase

Seasonal reorder points (most stockout days fall between September and December under one yearly
average), supplier minimum order quantities, and a live stock feed.
