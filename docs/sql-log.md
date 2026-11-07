# AI-written SQL: verification log

Model: `gemini-3.5-flash-lite` · Run on 2026-11-07 · **9 of 10 correct first time**

Each question was given to Gemini with the schema description only (no data rows). The AI's query ran on a read-only copy of the database and its result was compared with a verified query. Where they differ, the verified query is the correction.

## Q1. Which 10 products sold the most units in 2011, counting both regular and bulk sales?

**Outcome:** correct. Returned 10 rows; matches the verified answer.

**AI's stated assumption:** Units in 2011 are calculated as the sum of regular units and bulk units across all trading days in the year 2011.

AI query:

```sql
SELECT p.product_code, p.description, SUM(d.units + d.bulk_units) AS total_units FROM products p JOIN daily_sales d ON p.product_code = d.product_code WHERE d.date LIKE '2011-%' GROUP BY p.product_code, p.description ORDER BY total_units DESC LIMIT 10
```

**What I checked:** 

## Q2. What was total revenue, regular plus bulk, in each month of 2011?

**Outcome:** correct. Returned 12 rows; matches the verified answer.

**AI's stated assumption:** Total revenue includes both regular and bulk revenue summed across all products for each trading month in 2011.

AI query:

```sql
SELECT t.month, ROUND(SUM(d.revenue + d.bulk_revenue), 2) AS total_revenue FROM trading_days t JOIN daily_sales d ON t.date = d.date WHERE t.month LIKE '2011-%' GROUP BY t.month ORDER BY t.month;
```

**What I checked:** 

## Q3. In the 2011 backtest at the 95% service level, which 5 products had the most stockout days?

**Outcome:** correct. Returned 5 rows; matches the verified answer.

**AI's stated assumption:** The 95% service level corresponds to service_level = 0.95 in the simulation_summary table.

AI query:

```sql
SELECT p.product_code, p.description, s.stockout_days FROM simulation_summary s JOIN products p ON s.product_code = p.product_code WHERE s.service_level = 0.95 ORDER BY s.stockout_days DESC, s.lost_units DESC LIMIT 5
```

**What I checked:** 

## Q4. Which products are at or below their reorder point on the last day of the data?

**Outcome:** correct. Returned 22 rows; matches the verified answer.

**AI's stated assumption:** Assumed the question refers to the pre-calculated 0.95 service level in the reorder_status table on the last trading day.

AI query:

```sql
SELECT p.product_code, p.description FROM reorder_status r JOIN products p ON r.product_code = p.product_code WHERE r.below_reorder_point = 1
```

**What I checked:** 

## Q5. Which day of the week has the highest average regular units sold per trading day, across all products?

**Outcome:** correct. Returned 1 rows; matches the verified answer.

**AI's stated assumption:** Average regular units sold per trading day is calculated by summing regular units across all products for each day, then averaging those daily totals by weekday.

AI query:

```sql
SELECT t.weekday, ROUND(AVG(d.total_units), 2) AS avg_units FROM trading_days t JOIN (SELECT date, SUM(units) AS total_units FROM daily_sales GROUP BY date) d ON t.date = d.date GROUP BY t.weekday ORDER BY avg_units DESC LIMIT 1;
```

**What I checked:** 

## Q6. Across all products, how much more holding cost did the 99% service level incur than the 95% level in the 2011 backtest?

**Outcome:** correct. Returned 1 rows; matches the verified answer.

**AI's stated assumption:** The holding cost difference is calculated by summing the total holding costs across all products for the 99% service level and subtracting the sum for the 95% service level from the simulation_summary table.

AI query:

```sql
SELECT ROUND(SUM(CASE WHEN service_level = 0.99 THEN holding_cost ELSE 0 END) - SUM(CASE WHEN service_level = 0.95 THEN holding_cost ELSE 0 END), 2) AS holding_cost_difference FROM simulation_summary WHERE service_level IN (0.95, 0.99);
```

**What I checked:** 

## Q7. For each service level, what fraction of 2011 regular demand was lost to stockouts in the backtest?

**Outcome:** correct. Returned 5 rows; matches the verified answer.

**AI's stated assumption:** Fraction of lost demand is calculated as total lost units divided by total demand units across all products for each service level.

AI query:

```sql
SELECT service_level, ROUND(CAST(SUM(lost_units) AS REAL) / SUM(demand_units), 4) AS fraction_lost FROM simulation_summary GROUP BY service_level ORDER BY service_level;
```

**What I checked:** 

## Q8. Which products have the longest supplier lead time, and what safety stock does each need at the 95% service level?

**Outcome:** wrong answer. Returned 5 rows; the verified answer has 1. Corrected with the verified query.

**AI's stated assumption:** Assumed the user wants the products with the absolute longest lead times at the 95% service level, returning the top products ordered by lead time descending.

AI query:

```sql
SELECT p.product_code, p.description, pol.lead_time_days, pol.safety_stock FROM products p JOIN policy pol ON p.product_code = pol.product_code WHERE pol.service_level = 0.95 ORDER BY pol.lead_time_days DESC, p.product_code ASC LIMIT 5
```

Verified query (correction):

```sql
SELECT product_code, lead_time_days, safety_stock FROM policy WHERE service_level = 0.95 AND lead_time_days = (SELECT MAX(lead_time_days) FROM policy)
```

**What I checked:** Returned the top 5 products by lead time (LIMIT 5) instead of only the products at the maximum lead time. Its first row matches the verified answer; the other 4 are extra. The AI's stated assumption shows the cause: "longest" was read as "top 5". Fix: reword the question to "the products with the maximum lead time", and check any "longest" or "highest" query for a LIMIT that drops or adds ties.

## Q9. Which products sold more than twice as many regular units in the fourth quarter of 2010 as in the first quarter of 2010?

**Outcome:** correct. Returned 15 rows; matches the verified answer.

**AI's stated assumption:** Quarter 1 is defined as January to March 2010 and Quarter 4 as October to December 2010 based on the month column.

AI query:

```sql
SELECT p.product_code, p.description FROM products p JOIN daily_sales d ON p.product_code = d.product_code JOIN trading_days t ON d.date = t.date WHERE t.month BETWEEN '2010-01' AND '2010-12' GROUP BY p.product_code, p.description HAVING SUM(CASE WHEN t.month BETWEEN '2010-10' AND '2010-12' THEN d.units ELSE 0 END) > 2 * SUM(CASE WHEN t.month BETWEEN '2010-01' AND '2010-03' THEN d.units ELSE 0 END)
```

**What I checked:** 

## Q10. Which service level had the lowest combined holding cost and lost margin across all products in the 2011 backtest?

**Outcome:** correct. Returned 1 rows; matches the verified answer.

**AI's stated assumption:** Combined holding cost and lost margin is calculated as the sum of holding_cost and lost_margin across all products for each service level.

AI query:

```sql
SELECT service_level, ROUND(SUM(holding_cost + lost_margin), 2) AS total_cost FROM simulation_summary GROUP BY service_level ORDER BY total_cost ASC LIMIT 1;
```

**What I checked:** 
