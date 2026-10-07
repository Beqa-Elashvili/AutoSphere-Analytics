# KPI Dictionary

> One definition per KPI, implemented once in SQL (`analytics` views) and once in DAX (Power BI).
> Automated tests prove that the views, the stand-alone KPI queries (`analytics/kpi_queries/`) and
> a pandas recomputation all produce the same numbers. Pipeline step 7 reconciles every view to the
> fact tables on every run.

**Conventions used by every KPI**

| Rule | Detail |
|------|--------|
| Revenue recognition | Only **completed** sales lines (`fact_sales.is_revenue_recognized`) and **completed** service orders (`fact_service_orders.is_completed`) count. Cancelled and returned sales, and open or cancelled service orders, are excluded. |
| Order | One **invoice** (`invoice_number`), not one line. |
| Customer | Counted by business key `customer_id`, so SCD2 versions of the same customer count once. |
| Currency | GEL, net of discounts, VAT not modelled. |
| Comparable periods | The latest year is partial (data ends 2026-09-30). Annual growth is only shown between complete years; year-to-date comparisons use the **same calendar window** last year (`v_kpi_ytd`). |

DAX table names match the PostgreSQL tables imported into Power BI (`fact_sales`, `dim_date`, ...).

---

## Current values (default dataset, all time unless stated)

| KPI | Value |
|-----|------:|
| Revenue | 28,441,790 GEL |
| Profit | 4,596,297 GEL |
| Profit Margin | 16.16% |
| Orders | 12,654 |
| Average Order Value | 2,247.65 GEL |
| Customer Count | 3,348 |
| Repeat Customer Rate | 66.28% |
| Service Revenue | 4,894,356 GEL |
| Service Orders | 10,440 |
| Average Service Order Value | 468.81 GEL |
| Revenue YoY, YTD 2026 vs YTD 2025 | **+15.58%** |
| Naive 2026 vs 2025 full year (wrong, shown for contrast) | −18.54% |

```powershell
python scripts/inspect_database.py --query "SELECT * FROM analytics.v_kpi_summary"
python scripts/inspect_database.py --query "SELECT * FROM analytics.v_kpi_ytd"
```

---

## 1. Revenue

| | |
|--|--|
| **Business definition** | Total recognized sales revenue: what customers paid for completed vehicle, part and accessory sales, after discounts. |
| **Calculation** | `SUM(quantity × unit_price − discount_amount)` over completed sales lines |
| **SQL** | `analytics.v_kpi_summary.revenue`, `analytics/kpi_queries/01_revenue_profit_margin.sql` |
| **Interpretation** | Size of the sales business. Compare across branches, categories and periods. |
| **Limitations** | Vehicle sales are about 70% of revenue but few in number, so short-period revenue (one branch, one month) is volatile. Service revenue is a separate KPI; `total_business_revenue` adds both. |

```sql
SELECT SUM(net_amount) FROM dw.fact_sales WHERE is_revenue_recognized;
```
```dax
Total Revenue =
CALCULATE ( SUM ( fact_sales[net_amount] ), fact_sales[is_revenue_recognized] = TRUE () )
```

## 2. Profit

| | |
|--|--|
| **Business definition** | Gross profit on sales: revenue minus the cost of the goods sold. |
| **Calculation** | `SUM(net_amount − quantity × unit_cost)`. The unit cost is stored **at the time of sale**, so historical profit is not distorted by later cost changes. |
| **SQL** | `v_kpi_summary.profit` |
| **Interpretation** | What the sales business actually earns. A high-revenue area can contribute little profit (vehicles). |
| **Limitations** | Gross profit only: staff, rent and marketing costs aren't allocated. Service profit is reported separately (`total_profit` in `v_branch_performance` combines both). |

```dax
Total Profit =
CALCULATE ( SUM ( fact_sales[profit_amount] ), fact_sales[is_revenue_recognized] = TRUE () )
```

## 3. Profit Margin

| | |
|--|--|
| **Business definition** | Share of each GEL of revenue that is kept as gross profit. |
| **Calculation** | `Profit / Revenue` |
| **SQL** | `v_kpi_summary.profit_margin_pct`; every performance view has a margin column |
| **Interpretation** | The current 16% overall is a mix of vehicles (~7–13%) and parts and accessories (30–60%). The sales mix explains most margin differences between branches; the parts-only store reaches about 38%. |
| **Limitations** | Ratio KPI: never average the margins of branches or months. Always recompute as total profit / total revenue (the DAX measure does this automatically). |

```dax
Profit Margin % = DIVIDE ( [Total Profit], [Total Revenue] )
```

## 4. Orders

| | |
|--|--|
| **Business definition** | Number of completed customer transactions (invoices). |
| **Calculation** | `COUNT(DISTINCT invoice_number)` over completed lines |
| **SQL** | `v_kpi_summary.orders`, `analytics/kpi_queries/02_orders_aov.sql` |
| **Interpretation** | Customer traffic. Falling orders with stable AOV means fewer customers; stable orders with falling AOV means smaller baskets. |
| **Limitations** | Counting lines instead of invoices would overstate orders about 2.5×. The test `test_aov_divides_by_orders_not_lines` guards this. |

```dax
Total Orders =
CALCULATE ( DISTINCTCOUNT ( fact_sales[invoice_number] ), fact_sales[is_revenue_recognized] = TRUE () )
```

## 5. Average Order Value (AOV)

| | |
|--|--|
| **Business definition** | Average revenue per completed order. |
| **Calculation** | `Revenue / Orders` |
| **SQL** | `v_kpi_summary.avg_order_value`, plus monthly, branch and customer views |
| **Interpretation** | Basket size. Upselling (accessories with a vehicle, parts with a service) raises AOV. |
| **Limitations** | A few vehicle invoices (30k–110k GEL) push the mean far above the typical invoice (median ≈ 460 GEL). Analyse AOV with and without the vehicle business line. |

```dax
Average Order Value = DIVIDE ( [Total Revenue], [Total Orders] )
```

## 6. Service Revenue

| | |
|--|--|
| **Business definition** | Revenue from completed service-centre work orders (labour and parts used in service). |
| **Calculation** | `SUM(total_revenue)` of completed service orders. Order revenue equals the sum of its lines, which the warehouse gate verifies. |
| **SQL** | `v_kpi_summary.service_revenue`, `v_service_monthly`, `analytics/kpi_queries/05_service_kpis.sql` |
| **Interpretation** | The after-sales business: steadier than vehicle sales and high-margin (labour ≈ 54%). |
| **Limitations** | Warranty work is billed at 0 GEL to the customer (manufacturer reimbursement isn't modelled), so warranty orders lower the average service value. Service is dated by the **opening** date. |

```dax
Service Revenue =
CALCULATE ( SUM ( fact_service_orders[total_revenue] ), fact_service_orders[is_completed] = TRUE () )
```

## 7. Service Orders

| | |
|--|--|
| **Business definition** | Number of completed service visits. |
| **Calculation** | `COUNT(*)` of completed service orders |
| **SQL** | `v_kpi_summary.service_orders` |
| **Interpretation** | Workshop throughput. Combine with turnaround hours to judge capacity. |
| **Limitations** | Excludes open (in-progress) and cancelled orders. Recent periods are slightly understated until open orders close. |

```dax
Service Orders =
CALCULATE ( COUNTROWS ( fact_service_orders ), fact_service_orders[is_completed] = TRUE () )
```

## 8. Average Service Order Value

| | |
|--|--|
| **Business definition** | Average revenue per completed service visit. |
| **Calculation** | `Service Revenue / Service Orders` |
| **SQL** | `v_kpi_summary.avg_service_order_value`, `v_service_type_performance` |
| **Interpretation** | Body work (~1,070 GEL) and tire service (~720 GEL) are the high-value jobs; diagnostics (~94 GEL) is a low-value entry service. |
| **Limitations** | Includes 0-GEL warranty orders. Filter `is_warranty = false` for paid work only. |

```dax
Avg Service Order Value = DIVIDE ( [Service Revenue], [Service Orders] )
```

## 9. Customer Count

| | |
|--|--|
| **Business definition** | Number of distinct customers with at least one completed purchase in the period. |
| **Calculation** | `COUNT(DISTINCT customer_id)` over completed sales |
| **SQL** | `v_kpi_summary.customer_count`, `analytics/kpi_queries/03_customers_repeat_rate.sql` |
| **Interpretation** | Active buying customer base, not registered customers (5,000 are registered, 3,348 have bought). |
| **Limitations** | Service-only customers aren't counted (this is a sales KPI). Counted on the business key, so SCD2 versions don't inflate it. |

```dax
Customer Count =
CALCULATE (
    DISTINCTCOUNT ( dim_customer[customer_id] ),
    FILTER ( fact_sales, fact_sales[is_revenue_recognized] = TRUE () )
)
```
*The fact table used as a filter propagates to `dim_customer` through the expanded table,
so only customers with completed sales in the current filter context are counted.*

## 10. Repeat Customer Rate

| | |
|--|--|
| **Business definition** | Share of buying customers who bought more than once in the period. |
| **Calculation** | `customers with 2+ completed orders / Customer Count` |
| **SQL** | `v_kpi_summary.repeat_customer_rate_pct`, `v_kpi_by_year`, `analytics/sql/04_repeat_customer_rate.sql` |
| **Interpretation** | Loyalty. About 48% within a year and 66% over the whole history. A falling yearly rate signals retention problems. |
| **Limitations** | Depends on period length: a 9-month period naturally shows a lower rate than 12 months (2026: 40.8%). Compare equal-length periods only. |

```dax
Repeat Customers =
COUNTROWS (
    FILTER ( VALUES ( dim_customer[customer_id] ), CALCULATE ( [Total Orders] ) >= 2 )
)

Repeat Customer Rate % = DIVIDE ( [Repeat Customers], [Customer Count] )
```

## 11. Revenue Growth

| | |
|--|--|
| **Business definition** | Relative change in revenue versus a comparable earlier period. |
| **Calculation** | `Revenue(period) / Revenue(comparable period) − 1` |
| **SQL** | `v_kpi_by_year.revenue_growth_pct` (complete years only), `v_kpi_ytd.revenue_yoy_pct`, `v_branch_growth.ytd_yoy_pct` |
| **Interpretation** | Momentum. Branch-level growth drives the "declining branches" alert (`trend_status`: below −5% = Declining). |
| **Limitations** | **Comparability is everything.** Comparing 9 months of 2026 with 12 months of 2025 shows a fake −18.5%; the correct YTD comparison is +15.6%. The views therefore return NULL annual growth for partial years. |

```dax
Revenue Growth % (YTD vs PY YTD) =
VAR LastDataDate = CALCULATE ( MAX ( fact_sales[sale_datetime] ), REMOVEFILTERS () )
VAR CurYTD  = CALCULATE ( [Total Revenue], DATESYTD ( dim_date[full_date] ),
                          dim_date[full_date] <= LastDataDate )
VAR PrevYTD = CALCULATE ( [Total Revenue], SAMEPERIODLASTYEAR ( DATESYTD ( dim_date[full_date] ) ),
                          dim_date[full_date] <= EDATE ( LastDataDate, -12 ) )
RETURN DIVIDE ( CurYTD - PrevYTD, PrevYTD )
```

## 12. YoY Growth (Year-over-Year)

| | |
|--|--|
| **Business definition** | Revenue in a period compared with the same period one year earlier. |
| **Calculation** | `Revenue(month) / Revenue(same month last year) − 1` |
| **SQL** | `v_revenue_monthly.yoy_growth_pct` (self-join on month); independently in `kpi_queries/04_growth_mom_yoy.sql` (`LAG(revenue, 12)` over a gap-free month spine) |
| **Interpretation** | Removes seasonality (October always beats August because of winter tires). This is the right lens for "are we really growing?". |
| **Limitations** | Monthly YoY per branch is noisy because of vehicles. Prefer quarterly or YTD views for decisions. |

```dax
Previous Year Revenue =
CALCULATE ( [Total Revenue], SAMEPERIODLASTYEAR ( dim_date[full_date] ) )

YoY Revenue % = DIVIDE ( [Total Revenue] - [Previous Year Revenue], [Previous Year Revenue] )
```

## 13. MoM Growth (Month-over-Month)

| | |
|--|--|
| **Business definition** | Revenue in a month compared with the previous month. |
| **Calculation** | `Revenue(month) / Revenue(previous month) − 1` |
| **SQL** | `v_revenue_monthly.mom_growth_pct` (`LAG` over ordered months) |
| **Interpretation** | Short-term momentum and early warning. |
| **Limitations** | Strongly seasonal (tire seasons, winter batteries) and volatile. Use together with YoY and the 3-month rolling average (`rolling_3m_avg_revenue`). |

```dax
Previous Month Revenue =
CALCULATE ( [Total Revenue], DATEADD ( dim_date[full_date], -1, MONTH ) )

MoM Revenue % = DIVIDE ( [Total Revenue] - [Previous Month Revenue], [Previous Month Revenue] )
```

---

## Supporting operational KPIs

| KPI | Definition | Source | Why it matters |
|-----|-----------|--------|----------------|
| Median turnaround hours | Median hours from opening to closing a completed service order | `v_service_turnaround`, `v_service_monthly` | The operational driver of waiting-time complaints (Batumi 2026) |
| Revenue share % | Share of company revenue per branch, category or city | performance views | Concentration risk |
| Payment failure rate | Failed payment attempts / attempts | `v_payment_mix` | Checkout friction |
| RFM segment | Recency, Frequency and Monetary quintiles → Champions, Loyal, At Risk, ... | `v_customer_metrics`, `v_customer_segments` | Targeted retention actions |
| Portfolio quadrant | Product revenue and margin vs peer-group medians | `v_product_performance` | Pricing, promotion and range decisions |

## KPI vs metric

A **metric** is any measurement (number of sales lines, average turnaround of diagnostics).
A **KPI** is a metric tied to a business objective, with an owner and a target, used to make
decisions (Revenue Growth vs plan, Repeat Customer Rate vs loyalty target). Every KPI above
lists the decision it supports in `docs/business-requirements.md` (Phase 12).
