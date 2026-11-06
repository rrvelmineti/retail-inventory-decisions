# Power BI dashboard: build guide

Build time: about 45 to 60 minutes in Power BI Desktop (Windows, free). Everything comes from
the CSV files in `data/processed/`, so no database connection is needed. When finished, save as
`dashboard/retail-inventory.pbix` and add screenshots to `docs/screenshots/`.

## 1. Load the data

**Home > Get data > Text/CSV**, then load each file from `data/processed/`:

`products.csv`, `daily_sales.csv`, `policy.csv`, `simulation_daily.csv`,
`simulation_summary.csv`, `tradeoff.csv`, `reorder_status.csv`

In **Transform data** (Power Query), check these types before closing:

| Column | Type |
| --- | --- |
| `product_code` in every table | **Text** (some codes end in a letter, like 85123A) |
| `date` columns | Date |
| `service_level` | Decimal number |
| `below_reorder_point` | True/False |

## 2. Add two small tables

**Modeling > New table**, one at a time:

```DAX
Calendar =
ADDCOLUMNS (
    CALENDAR ( DATE ( 2009, 12, 1 ), DATE ( 2011, 12, 31 ) ),
    "Month", FORMAT ( [Date], "YYYY-MM" ),
    "Weekday", FORMAT ( [Date], "dddd" ),
    "Year", YEAR ( [Date] )
)
```

```DAX
Service Levels = DISTINCT ( policy[service_level] )
```

Mark `Calendar` as the date table: select it, then **Table tools > Mark as date table > Date**.

## 3. Relationships

In **Model view**, create these one-to-many relationships (single direction):

| From (one) | To (many) |
| --- | --- |
| products[product_code] | daily_sales, policy, simulation_daily, simulation_summary, reorder_status [product_code] |
| Calendar[Date] | daily_sales[date], simulation_daily[date] |
| Service Levels[service_level] | policy, simulation_daily, simulation_summary, tradeoff [service_level] |

## 4. Measures

Create a blank table called `_Measures` to hold them (**Home > Enter data**, name it, load),
then **New measure** for each:

```DAX
Units Sold = SUM ( daily_sales[units] ) + SUM ( daily_sales[bulk_units] )
Revenue = SUM ( daily_sales[revenue] ) + SUM ( daily_sales[bulk_revenue] )
Stockout Days = SUM ( simulation_summary[stockout_days] )
Lost Units = SUM ( simulation_summary[lost_units] )
Fill Rate = DIVIDE ( SUM ( simulation_summary[sold_units] ), SUM ( simulation_summary[demand_units] ) )
Holding Cost = SUM ( simulation_summary[holding_cost] )
Lost Margin = SUM ( simulation_summary[lost_margin] )
Total Cost = [Holding Cost] + [Lost Margin]
Avg Stock Value = SUM ( simulation_summary[avg_stock_value] )
Products Below Reorder Point =
    CALCULATE ( COUNTROWS ( reorder_status ), reorder_status[below_reorder_point] = TRUE () )
Shortfall = SUM ( reorder_status[reorder_point] ) - SUM ( reorder_status[on_hand] )
```

Format `Fill Rate` as a percentage, and the money measures as currency in £ with no decimals.

## 5. Pages

### Page 1: Reorder now

The manager's first question: what needs attention?

- **Card:** Products Below Reorder Point.
- **Card:** text box "Position on 9 December 2011, 95% service level (simulated stock)".
- **Table:** products[description], reorder_status on_hand, on_order, reorder_point,
  safety_stock, order_qty, and [Shortfall].
  Filter `below_reorder_point = True` and sort by Shortfall, descending.
  Add conditional formatting (background colour) on Shortfall.

### Page 2: Stockouts vs holding cost

The core trade-off.

- **Line and clustered column chart:** X axis Service Levels[service_level];
  columns [Holding Cost] and [Lost Margin]; line [Stockout Days] on the secondary axis.
- **Line chart:** X axis service_level, value [Total Cost]. This shows total cost falling
  until 98%, then flattening.
- **Table:** tradeoff with service_level, fill_rate, stockout_days, lost_units,
  avg_stock_value, holding_cost, lost_margin, total_cost.
- **Text box:** "Moving from 95% to 98% cuts stockout days from 134 to 101 and adds about
  £1,200 a year in holding cost. Beyond 98% the saving is about £50."

### Page 3: Stock over time

Shows what the reorder policy actually does, day by day.

- **Slicers:** products[description] (single select), Service Levels[service_level] (single select).
- **Line chart:** X axis Calendar[Date] (2011), values simulation_daily on_hand (sum) and
  policy reorder_point (sum). Use a constant line or a measure for the reorder point.
- **Clustered column chart:** X axis Calendar[Date], value simulation_daily lost (sum),
  to show when stockouts happened.

### Page 4: Sales trend

Real sales, for context.

- **Line chart:** X axis Calendar[Month], values [Revenue] and [Units Sold].
- **Bar chart:** top 10 products by [Units Sold] (use a Top N visual filter).
- **Slicer:** Calendar[Year].

## 6. Check the numbers

Before taking screenshots, confirm these figures against `data/processed/tradeoff.csv`:

| Service level | Stockout days | Holding cost | Lost margin |
| --- | ---: | ---: | ---: |
| 80% | 320 | £12,743 | £13,145 |
| 95% | 134 | £15,168 | £7,210 |
| 99% | 78 | £17,188 | £4,249 |

And Products Below Reorder Point should show **22**. If a figure differs, check the
relationships and the `product_code` type first.
