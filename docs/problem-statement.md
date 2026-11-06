# Problem statement

## Context

A UK online gift retailer sells thousands of low-priced items (cake cases, T-light holders,
paper party goods) to individuals and small shops. Demand is uneven: steady most of the year,
then a sharp rise from September to December.

The store manager decides when to reorder each product and how much spare stock to hold.

## Problem

- **Too little stock** means stockouts: customers can't buy, and the sale is lost.
- **Too much stock** ties up cash in inventory and costs money to store.

Today the trade-off is judged by feel. The manager can't see, product by product, how much
extra buffer stock would cost against how many lost sales it would prevent.

## Stakeholders

| Stakeholder | Need |
| --- | --- |
| Store manager | Know which products to reorder now, and how big a safety buffer is worth it |
| Finance | Understand the cash tied up in stock and the cost of holding it |
| Buyer | Reorder points and order quantities per product |
| Analyst | Answer ad-hoc questions about sales and stock quickly and correctly |

## Goal

1. Set a reorder point for each of the 50 most regularly sold products, at several target
   service levels.
2. Test each level against a year of real demand, and show stockouts against holding cost.
3. Show the manager, each week, which products are at or below their reorder point.
4. Let an analyst ask business questions in plain English, using AI to write the SQL,
   with every query checked before its answer is trusted.

## Data

- **Sales are real:** UCI Online Retail II, about 1.07 million transaction lines from
  December 2009 to December 2011, licensed CC BY 4.0.
- **Stock is modelled:** the dataset has no stock levels, costs or lead times. Unit cost,
  supplier lead time, holding rate and order size are stated assumptions (see
  [data/README.md](../data/README.md)), so stock results are a scenario, not history.

## Out of scope

- Forecasting models or machine learning. The reorder logic is deliberately transparent.
- Supplier minimum order quantities, price breaks and warehouse space limits.
