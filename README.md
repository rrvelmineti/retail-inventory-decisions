# Retail Inventory Decision Dashboard

How much spare stock is worth holding? This project sets reorder points for an online gift
retailer's 50 best-selling regular products, tests them against a year of **real demand**, and
shows the trade-off between stockouts and the cost of holding stock. AI drafts SQL for business
questions and writes the manager's weekly update, and every AI output is checked before it is
trusted.

- **Data:** [UCI Online Retail II](https://doi.org/10.24432/C5CG6D), about 1.07 million real
  transactions from Dec 2009 to Dec 2011 (CC BY 4.0). Stock levels, costs and lead times are
  modelled assumptions, stated in [data/README.md](data/README.md).
- **Docs:** [implementation playbook](docs/implementation-playbook.md) ·
  [problem statement](docs/problem-statement.md) · [user stories](docs/user-stories.md) ·
  [UAT](docs/uat.md) · [Power BI dashboard](docs/powerbi-guide.md) · [SQL verification log](docs/sql-log.md)

## The implementation case

**Client problem.** A store manager sets stock levels by feel, and every sales question waits for an
analyst.
**What was delivered.** A reorder policy tested on a year of real demand, a Power BI dashboard, and
plain-English questions answered by AI-written SQL that the user approves before it runs.
**How it is rolled out safely.** AI SQL must pass a go-live gate on 10 verified business questions
(`python -m evaluation.go_live`). During the pilot, every question, approval and user rating is logged
(`python -m inventory.pilot`), and answers marked wrong become new verified questions. The full plan
is in the [implementation playbook](docs/implementation-playbook.md).

## The answer

Reorder points were set from **2010** demand, then each policy was run day by day on **2011**
demand it had never seen:

| Service level | Fill rate | Stockout days | Lost units | Holding cost | Lost margin | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 80% | 94.8% | 320 | 38,936 | £12,743 | £13,145 | £25,888 |
| 90% | 96.3% | 182 | 28,230 | £14,056 | £9,286 | £23,343 |
| 95% | 97.0% | 134 | 22,621 | £15,168 | £7,210 | £22,378 |
| **98%** | **98.0%** | **101** | **15,459** | **£16,370** | **£5,117** | **£21,488** |
| 99% | 98.4% | 78 | 12,491 | £17,188 | £4,249 | £21,437 |

**Recommendation: 98%.** For cheap, high-margin gift items, a lost sale costs more than holding
an extra unit, so total cost falls as the buffer grows. Going from 98% to 99% saves only about
£50 more a year, for £818 more in holding cost and £3,466 more stock on the shelf. That makes
98% the point where extra buffer stops paying for itself.

On the last day of the data, 9 December 2011, **22 of 50 products** were at or below their
reorder point at the 95% level, which is expected in the pre-Christmas peak.

## How it works

```
UCI workbook ──> clean ──> daily demand ──> reorder policies (2010) ──> 2011 backtest
                                                                           │
                          SQLite (read-only) <── CSV tables ──> Power BI dashboard
                               │
        plain-English question ─> Gemini drafts SQL ─> safety check ─> run ─> compare with verified answer
```

| Step | What happens | AI or code |
| --- | --- | --- |
| Clean | Remove cancellations and their original lines, postage and fee codes; flag one-off bulk orders | Code |
| Reorder points | Average demand × lead time + safety stock (z × std dev × √lead time) | Code |
| Backtest | Serve each day's real demand from stock, lose unmet demand, reorder at the reorder point | Code |
| Ask a question | Gemini drafts SQL from the schema description only; you see it and approve it before it runs | AI + human |
| Weekly update | Code writes the summary from verified figures; Gemini may rewrite it, but any figure not in the facts gets it rejected | Code, optional AI |
| Dashboard | Power BI project generated from code: reorder now, trade-off, stock over time, sales trend. Open `powerbi/RetailInventory.pbip` | Code |

## Run it

Python 3.10+:

```
python -m pip install -r requirements.txt
python -m inventory.db                     # build the SQLite database from data/processed
python -m inventory.summary                # this week's update for the manager
python -m evaluation.sql_eval              # run the 10 verified business queries
python -m unittest discover -s tests -v
```

With a Gemini API key (PowerShell: `$env:GEMINI_API_KEY="..."` and `$env:GEMINI_MODEL="..."`):

```
python -m inventory "Which products sold most in November 2011?"   # AI drafts SQL, you approve it
python -m evaluation.sql_eval --gemini     # score AI SQL on the 10 questions, write docs/sql-log.md
python -m inventory.summary --gemini       # AI-written weekly update, figure-checked
python -m evaluation.go_live               # GO / NO-GO / NOT READY for AI SQL, with a sign-off line
```

**Pilot.** Each question asked with `python -m inventory` is logged with whether the SQL was run and
the user's rating (right, wrong or unsure). Add `--user <name>` to record who asked.

```
python -m inventory.pilot                       # adoption, approval rate, accuracy as rated
python -m inventory.pilot --candidates new.json # answers marked wrong, as draft evaluation questions
```

**Dashboard:** open `powerbi/RetailInventory.pbip` in Power BI Desktop and choose Anonymous when asked how to connect to GitHub. See [docs/powerbi-guide.md](docs/powerbi-guide.md).

To rebuild from the original workbook, see [data/README.md](data/README.md).

## Example weekly update (code-written)

> Week of 2011-11-28 to 2011-12-04: 22,078 units sold for £33,524 (units up 24.8%, revenue up
> 29.2% on the week before). Top sellers: Small Popcorn Holder (3,275 units); Red Harmonica In
> Box (1,120 units); Jumbo Bag Red Retrospot (1,040 units). Stockouts: 2 products ran out on 4
> product-days, losing 1,202 units of sales. 22 products are at or below their reorder point...

## Where AI is and is not used, and why

- **SQL drafting: AI helps.** Turning "which products ran out most often?" into a correct join
  is where AI saves an analyst time. It sees the schema description only, never data rows. The
  query runs on a read-only database: one SELECT, with a time and row limit, and writes are
  refused by the database itself.
- **Trusting the answer: verified.** 10 business questions each have a hand-checked query. The
  AI's result is compared with it, and the outcome is logged in
  [docs/sql-log.md](docs/sql-log.md), with the verified query as the correction when the AI is wrong.
- **Reorder logic and costs: no AI.** These must be exact and explainable, so code computes them.
- **Weekly update: AI may rephrase, not invent.** Every number in an AI summary must already be in
  the verified facts, or the summary is discarded.

## How I used AI to build this

- **Requirements.** An AI assistant drafted the problem statement and user stories from a short
  brief. My edits are recorded in the review log in [user-stories.md](docs/user-stories.md).
- **Build.** I set the finish line first (what done means, what is out of scope), then built with
  an AI coding assistant in small steps, running each step before moving on.
- **What the AI got wrong, and how it was caught:**
  - The first version of the answer comparison was too complicated to trust. It was replaced
    with a simpler rule and tested on cases that must match and must not match.
  - The weekly summary first chose a week the data did not fully cover (data ends on a Friday),
    which exaggerated a 22% drop. It now uses only complete weeks.
  - The figure checker rejected the code's own summary, because "down 22.5%" is stored as −22.5.
    Fixed, and covered by a test that the code-written summary always passes its own check.
  - The Power BI dashboard is generated as code (TMDL and PBIR). Every JSON file is validated against Microsoft's published schemas, and the checker was proven by planting four mistakes and confirming each was caught.
  - A first check of the data found an 80,995-unit order that was cancelled the same day. Keeping
    it would have distorted demand, so cancelled originals are now removed.

## Limits

- Stock, costs and lead times are modelled. The trade-off depends on those assumptions,
  especially the 40% margin and the 25% holding rate.
- The products were chosen by 2010 volume, so 2011 demand is lower on average (regression to the
  mean). The backtest is still fair, because the policies never saw 2011.
- No forecasting: policies use a single yearly average, so seasonal peaks drive stockouts.
  At the 95% level, September to December account for 58% of stockout days and 53% of lost units.
  A seasonal reorder point is the obvious next step.
