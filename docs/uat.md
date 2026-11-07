# UAT test cases

This is the working test log. The client-facing plan, with every case traced to a business
requirement and a sign-off section, is [uat-signoff.md](uat-signoff.md).

Run on 5 November 2026. Cases 1 to 13 and 16 have automated equivalents in `tests/` and
run on every push. Cases 14, 15 and 17 need a Gemini key or Power BI Desktop and are run by hand.

| # | Story | Steps | Expected | Actual | Result |
| --- | --- | --- | --- | --- | --- |
| 1 | US-1 | Clean a sample with a cancelled order, postage, a zero quantity and a 5,000-unit line | Cancellation and its original removed; postage and zero line removed; large line flagged as bulk | As expected | Pass |
| 2 | US-1 | Run cleaning on the full dataset | Cleaning log shows each step | 1,067,371 raw lines to 1,029,927 clean lines | Pass |
| 3 | US-2 | Change all 2011 demand tenfold, rebuild policies | Policies unchanged (set from 2010 only) | Unchanged | Pass |
| 4 | US-2 | Simulate a 6-day toy case by hand and in code | Same stock, lost sales and order timing | Identical | Pass |
| 5 | US-3 | Compare service levels 80% to 99% | Lost units fall and holding cost rises as the level rises | 38,936 to 12,491 lost units; £12,743 to £17,188 holding cost | Pass |
| 6 | US-4 | List products at or below reorder point on 9 Dec 2011 at 95% | A list with on-hand, on-order and reorder point | 22 of 50 products | Pass |
| 7 | US-5 | Run DELETE, UPDATE, PRAGMA, ATTACH, two statements | All blocked before running | Blocked | Pass |
| 8 | US-5 | Hide a DELETE inside a WITH clause | Refused by the read-only database | Refused; data unchanged | Pass |
| 9 | US-5 | Query returning more than 1,000 rows | Stopped with a clear message | Stopped | Pass |
| 10 | US-5 | Inspect what is sent to Gemini | Schema description and question only, no data values | No data values found | Pass |
| 11 | US-6 | Evaluate one correct, one wrong and one destructive AI query | Logged as correct, wrong answer, blocked | As expected | Pass |
| 12 | US-7 | Check the code-written weekly summary against its facts | Passes the figure check | Passes | Pass |
| 13 | US-7 | AI summary claims "about 30%" and "roughly 25,000 units" | Rejected | Rejected | Pass |
| 14 | US-6 | `python -m evaluation.sql_eval --gemini` | 10 questions logged with outcome and corrections in `docs/sql-log.md` | 9 of 10 correct; Q8 returned the top 5 instead of the single longest lead time (7 Nov 2026) | Pass |
| 15 | US-5 | `python -m inventory "Which products sold most in November 2011?"`, answer N | SQL shown; query not run | | Not yet run |
| 16 | US-3, US-4 | Validate the Power BI project against Microsoft's schemas | 0 problems; planted mistakes are caught | 29 files, 0 problems; 4 of 4 planted mistakes caught | Pass |
| 17 | US-3, US-4 | Open `powerbi/RetailInventory.pbip` in Power BI Desktop and compare with the check table in the dashboard guide | Figures match; 22 products below reorder point | | Not yet run |
| 18 | Rollout | Ask four questions (run and rated right, declined, blocked, run and rated wrong) | Each logged with its outcome; approval rate 75%, accuracy as rated 50% | As expected (simulated AI) | Pass |
| 19 | Rollout | Skip the rating after a query runs | Logged as run, not rated | As expected | Pass |
| 20 | Rollout | `python -m inventory.pilot --candidates new.json` after an answer is marked wrong | Draft evaluation question with empty verified SQL and the user's note | As expected | Pass |
| 21 | Rollout | Go-live gate on 9 of 10 correct; on 2 wrong answers; with no AI evaluation | GO; NO-GO; NOT READY | As expected | Pass |
