# Analytics layer

```powershell
python scripts/run_analytics.py --list      # all queries with the question they answer
python scripts/run_analytics.py 03          # run one (number or part of the name)
python scripts/run_analytics.py --all       # run all business questions
```

| Folder | Contents |
|--------|----------|
| `sql/` | 10 business questions. Each file starts with *Business question / KPI / Source / Decision*. |
| `kpi_queries/` | Each KPI implemented **directly on the star schema**, independently of the views. Tests require both implementations to agree. |
| `../database/views/` | The `analytics` schema: reusable KPI views used by Power BI, reports and the queries above. |

## Views (`analytics` schema)

| View | Grain | Purpose | SQL techniques |
|------|-------|---------|----------------|
| `mv_sales` / `v_sales` | sales line | completed sales with all descriptive attributes (materialized, indexed) | 6-table star join, `COLLATE "C"` keys |
| `mv_service` / `v_service` | service order | completed service orders with attributes (materialized) | star join |
| `v_data_period` | 1 row | data coverage for comparable periods | aggregates |
| `v_kpi_summary` | 1 row | headline KPIs, all time | CTEs |
| `v_kpi_by_year` | year | KPIs per year; growth only between complete years | CTEs, `LAG`, `FILTER` |
| `v_kpi_ytd` | 1 row | YTD vs the same window last year | row-value comparison `(month, day) <= (…)` |
| `v_revenue_monthly` | month | revenue, MoM, YoY, YTD, 3-month rolling average | `LAG`, self-join, `SUM() OVER (PARTITION BY)`, window frame |
| `v_branch_monthly` | branch × month | branch trend with MoM and YoY | `LAG … PARTITION BY` |
| `v_branch_performance` | branch × year | sales and service KPIs, share, rank | `RANK()`, `SUM() OVER` |
| `v_branch_growth` | branch | YTD and last-3-months YoY, `trend_status` | `FILTER`, interval arithmetic, `CASE` |
| `v_city_revenue` | city × year | revenue by branch city | window share |
| `v_category_performance` | category × year | revenue, margin, units, share, rank | window functions |
| `v_product_performance` | product | ranks and sales-vs-margin quadrant vs peer medians | `percentile_cont`, `RANK()` |
| `v_customer_metrics` | customer | orders, revenue, AOV, recency, purchase interval, RFM | `LAG`, `NTILE(5)` |
| `v_customer_segments` | RFM segment | size and value per segment | window share |
| `v_purchase_frequency` | orders bucket | how many customers bought 1, 2, 3 … times | `CASE` buckets |
| `v_service_monthly` | month | service volume, revenue, turnaround | `percentile_cont` |
| `v_service_type_performance` | service type | value, margin, labour hours, turnaround | aggregates |
| `v_service_revenue_by_category` | category × year | labour vs part categories in service | joins to `dim_category` |
| `v_service_turnaround` | branch × quarter × type | median and P90 turnaround | `percentile_cont(0.5/0.9)` |
| `v_payment_mix` | year × source × method | collected, refunded, failure rate | `FILTER` |

## Performance notes

The base datasets are **materialized views**, rebuilt by pipeline step 7 after every
warehouse build, so they're always consistent with the facts. Business keys use the `"C"`
collation: on the hosted database, sorting 30k IDs with the linguistic collation took
~740 ms, compared with a fraction of that in byte order. Together these cut the analytics
layer's response time about 2–3×.

## Key insights (default dataset)

| Question | Answer |
|----------|--------|
| Top branch (2026 YTD) | Tbilisi Vake: 2.36M GEL, 26% of sales revenue |
| Declining branch | **Kutaisi: −16.4% YTD**, orders −28%. The only branch flagged *Declining* |
| Growth (comparable) | Company revenue +15.6% YTD vs prior YTD (a naive full-year comparison would show −18.5%) |
| Most profitable product | All-season tires (444k GEL profit at 30% margin), ahead of the top-selling SUV (7.5% margin) |
| Low sales, high margin | Accessories and car care: trunk organizer (62%), CarPlay adapter (61%), dash camera (57%) |
| Repeat customers | 48% of customers buy again within a year; 66% over the full history |
| Customer concentration | *Champions* are 25% of customers and 57% of revenue |
| Service mix | Maintenance is the most frequent job (36%), repair the largest revenue; labour is 44% of service revenue at 54% margin |
| Operational issue | Batumi maintenance turnaround deteriorates in 2026, flagged INVESTIGATE (query 10) |
