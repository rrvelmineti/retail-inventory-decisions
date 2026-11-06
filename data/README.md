# Data

## Source

**Online Retail II**, Chen, D. (2019). UCI Machine Learning Repository.
https://doi.org/10.24432/C5CG6D. Licensed under
[Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/).

All transactions of a UK-based, registered non-store online retailer from 1 December 2009 to
9 December 2011: 1,067,371 lines, 8 columns. The raw workbook (45 MB) is not committed. The files
in `processed/` are derived from it.

To rebuild everything from the original:

```
python -m inventory.prepare path/to/online_retail_II.xlsx   # ~1 minute
python -m inventory.policy
python -m inventory.db
```

## Cleaning

From `processed/cleaning_log.csv`:

| Step | Lines |
| --- | ---: |
| Raw lines | 1,067,371 |
| Cancellation lines removed (invoice starts with C) | 19,494 |
| Zero or negative price or quantity removed | 6,207 |
| Non-product codes removed (POST, DOT, M, BANK CHARGES, gift vouchers...) | 4,793 |
| Original lines matching a cancellation removed | 6,950 |
| Bulk order lines flagged (kept as sales, not used to size stock) | 632 |
| **Clean sale lines** | **1,029,927** |

A cancellation leaves the original order line in the data, so one original line is removed per
cancellation, matched on customer, product and quantity. Without this step, an 80,995-unit order
cancelled the same day would count as real demand.

A **bulk order** is a single line of at least 500 units that is also above the product's 99.5th
percentile line size. These are one-off wholesale orders that a retailer fills separately.

## Products

The 50 products with the most regular 2010 units, among those sold on at least 150 trading days
in 2010 and also sold in 2011. Demand is recorded on every one of the 604 trading days, with zero
on days a product did not sell.

## Modelled assumptions

The dataset has sales only. These assumptions turn it into an inventory scenario:

| Assumption | Value |
| --- | --- |
| Unit cost | 60% of the product's median selling price |
| Holding cost | 25% of stock value per year (302 trading days) |
| Supplier lead time | 5 to 20 trading days, fixed per product (derived from the product code so it is reproducible) |
| Order quantity | About 24 trading days (4 weeks) of average demand |
| Lost sale | Unmet demand is lost, not back-ordered |
| Lost margin | Selling price minus unit cost, per lost unit |

## Files in `processed/`

| File | Contents |
| --- | --- |
| products.csv | 50 products: code, description, median price |
| trading_days.csv | 604 trading days with weekday and month |
| daily_sales.csv | Regular and bulk units and revenue per product per trading day |
| policy.csv | Reorder point, safety stock and order quantity per product and service level |
| simulation_daily.csv | 2011 day-by-day stock, sales and lost sales per product and service level |
| simulation_summary.csv | 2011 totals per product and service level |
| tradeoff.csv | 2011 totals per service level, all products |
| reorder_status.csv | Position of each product on 9 December 2011 at the 95% level |
| cleaning_log.csv | Lines removed at each cleaning step |
