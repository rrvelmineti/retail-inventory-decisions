# User stories

First drafted with an AI assistant from a short brief, then reviewed. Record your changes in
the review log at the end, so the gap between the AI draft and the final version stays visible.

**Brief given to the AI:** "A store manager at an online gift retailer wants fewer stockouts
without tying up cash in stock. Write user stories with acceptance criteria for reorder points,
a stockout-versus-holding-cost comparison, a weekly reorder view, and AI-assisted SQL for
analysts. Real sales data, simulated stock."

---

### US-1 Clean, trustworthy sales history

As an analyst, I want cancelled orders, postage and fee lines, and one-off wholesale orders
handled consistently so that demand reflects real everyday sales.

Acceptance criteria:
- Cancellation lines are removed, along with one matching original line per cancellation.
- Non-product codes (postage, bank charges, manual adjustments, gift vouchers) are excluded.
- Bulk orders are flagged and kept as sales, but are not used to size everyday stock.
- A cleaning log shows how many lines each step removed.

### US-2 Reorder point per product

As a buyer, I want a reorder point and order quantity for each product so that I know when to
reorder and how much.

Acceptance criteria:
- Reorder point = average daily demand × lead time + safety stock.
- Safety stock uses the demand variability and a chosen service level.
- Policies are set from 2010 demand only, so the 2011 test is fair.

### US-3 Stockouts versus holding cost

As a store manager, I want to compare service levels side by side so that I can choose how much
buffer stock is worth holding.

Acceptance criteria:
- For each service level (80%, 90%, 95%, 98%, 99%): stockout days, lost units, fill rate,
  average stock value, holding cost and lost margin over 2011.
- Results come from a day-by-day simulation on real 2011 demand.

### US-4 What to reorder now

As a store manager, I want to see which products are at or below their reorder point so that I
can check replenishment orders are on the way.

Acceptance criteria:
- A list of products at or below the reorder point at the chosen service level, with on-hand
  stock, stock on order and the reorder point.

### US-5 Ask questions in plain English

As an analyst, I want to ask a business question in plain English and get the SQL drafted by AI
so that I can answer ad-hoc questions faster.

Acceptance criteria:
- The AI receives the schema description and the question only, never data rows.
- I see the SQL before it runs and choose whether to run it.
- Only a single read-only SELECT can run; writes are blocked.

### US-6 Know how far to trust AI-written SQL

As the analyst responsible, I want AI-written SQL checked against verified answers so that I
know how often it is right and where it goes wrong.

Acceptance criteria:
- 10 business questions, each with a verified query.
- The AI's result is compared with the verified result, and the outcome is logged as correct,
  wrong answer, blocked or failed to run.
- Wrong answers show the verified query as the correction.

### US-7 Weekly update for the manager

As a store manager, I want a short weekly written update so that I don't have to read the whole
dashboard.

Acceptance criteria:
- A code-written summary is always available.
- An optional AI-written summary is rejected if it contains any figure not in the verified facts.

---

## Review log

| Story | What changed after review | Why |
| --- | --- | --- |
| | | |
