# Dashboard Specification

Eight report pages. Each page answers a defined set of business questions for a defined
audience. Measures are defined in `dax-measures.md`; the table and column names come from
`data-model.md`.

**Global layout.** 16:9 canvas (1280 × 720). Title bar with the page name and the
`Data Through` card. Slicer panel on the left. KPI cards in the top row, main chart in the
middle, detail at the bottom. Theme: `theme/autosphere-theme.json`.

**Global slicers** (synced across pages 2–7 with *View → Sync slicers*): `Date[year]`,
`Branch[branch_name]`, `Branch[city]`.

| # | Page | Audience | Key question |
|---|------|----------|--------------|
| 1 | Executive Overview | Management | How is the business doing, and where do I need to look? |
| 2 | Sales Performance | Sales director | What drives revenue and margin? |
| 3 | Branch Performance | Regional managers | Which branches grow or decline, and why? |
| 4 | Product & Category | Category managers | What sells, and what earns money? |
| 5 | Customers | Marketing / CRM | Who are our customers, and who are we losing? |
| 6 | Service Operations | Service managers | Are we fast, busy and profitable in service? |
| 7 | Customer Feedback (AI) | Management / quality | Why are customers unhappy, and where? |
| 8 | Data Quality & Pipeline | BI team / data owners | Can I trust today's numbers? |

---

## 1. Executive Overview

**Business questions:** What is our revenue and profit this year vs last year (comparable
period)? Which branches are declining? What do customers complain about most? Is the data
fresh and clean?

| Area | Visual | Fields / measures |
|------|--------|-------------------|
| KPI row | 6 cards | `Revenue CY YTD` (subtitle `Revenue YTD YoY %`), `Profit Margin CY YTD %`, `Orders CY YTD` (`Orders YTD YoY %`), `Service Revenue CY YTD` (`Service Revenue YTD YoY %`), `Negative Rate %`, `Last Run Status` (colour `Status Color`) |
| Main | Line and clustered column chart | Axis `Date[year_month]`; columns `Revenue`; line `Revenue LY` |
| Right | Bar chart | `Branch[branch_name]` × `Revenue YoY %`, conditional colour red below 0 |
| Bottom left | Table | Branch, `Revenue`, `Revenue YoY %`, `Median Turnaround (h)`, `Negative Rate %` (red/amber/green icons) |
| Bottom right | Card (multi-row) | `Selected Insight` with an `AI Insights[scope_value]` slicer defaulting to "All branches" |

**Decision supported:** where to focus this month. Expected story in the data: revenue up
**+15.6% YTD**, Kutaisi down **−16.4%**, Batumi waiting-time complaints rising.

**Interaction:** clicking a branch in the bar chart filters the table. *Drill-through* from
any branch to page 3.

## 2. Sales Performance

**Business questions:** How does revenue develop month by month? Which channel and business
line drive it? Are discounts eating margin?

| Area | Visual | Fields / measures |
|------|--------|-------------------|
| KPI row | 5 cards | `Revenue`, `Profit`, `Profit Margin %`, `Avg Order Value`, `Discount Rate %` |
| Main | Line chart | `Date[year_month]` × `Revenue`, `Revenue Rolling 3M Avg`; tooltip `Revenue MoM %`, `Revenue YoY %` |
| Middle left | Stacked column | `Date[year]` × `Revenue`, legend `Category[business_line]` |
| Middle right | Donut | `Sales[sales_channel]` × `Revenue` |
| Bottom | Matrix | Rows `Date[year]` → `Date[quarter_label]` → `Date[month_name]`; values `Revenue`, `Revenue YoY %`, `Profit Margin %`, `Orders` |

**Decision supported:** channel investment, discount policy, seasonality planning (stock and staff).

## 3. Branch Performance

**Business questions:** Which branches grow or decline on a comparable basis? How do sales and
service combine per branch? Is a decline driven by fewer orders or by smaller orders?

| Area | Visual | Fields / measures |
|------|--------|-------------------|
| KPI row | 4 cards | `Total Business Revenue`, `Branch Revenue Share %`, `Revenue YTD YoY %`, `Customers` |
| Main | Clustered bar | `Branch[branch_name]` × `Revenue`, `Service Revenue` (sorted descending) |
| Middle | Line chart (small multiples by branch) | `Date[year_month]` × `Revenue` |
| Bottom | Table | Branch, `Branch Revenue Rank`, `Revenue`, `Revenue YoY %`, `Orders`, `Avg Order Value`, `Profit Margin %`, `Service Order Count`, `Median Turnaround (h)` |
| Map | Map / filled map | `Branch[city]` sized by `Total Business Revenue` |

**Drill-through target:** `Branch[branch_name]`. The page shows one branch when opened from
pages 1, 6 or 7.

**Decision supported:** where to intervene. Kutaisi: are orders falling (traffic) or is the
order value falling (mix/price)? Compare `Orders YTD YoY %` with `Avg Order Value`.

## 4. Product & Category

**Business questions:** Which products and categories bring revenue vs profit? Which products
sell a lot at low margin, and which sell little at high margin?

| Area | Visual | Fields / measures |
|------|--------|-------------------|
| KPI row | 4 cards | `Revenue`, `Profit Margin %`, `Units Sold`, `Category Revenue Share %` |
| Main | Scatter chart | Each `Product[product_name]`: X `Revenue`, Y `Profit Margin %`, size `Units Sold`, legend `Category[business_line]`. Average lines on both axes create the 4 portfolio quadrants (same logic as `v_product_performance.portfolio_quadrant`) |
| Right | Treemap | `Category[category_name]` × `Revenue` |
| Bottom | Table | Product, brand, `Product Revenue Rank`, `Revenue`, `Profit`, `Profit Margin %`, `Units Sold` |

**Decision supported:** assortment and pricing. Promote high-margin, low-volume products;
re-price high-volume, low-margin ones.

## 5. Customers

**Business questions:** How many customers buy again? Which RFM segments carry revenue? Who is
at risk of churning? Do corporate and individual customers behave differently?

| Area | Visual | Fields / measures |
|------|--------|-------------------|
| KPI row | 4 cards | `Customers`, `Repeat Customer Rate %`, `Avg Order Value`, `Revenue` |
| Main | Bar chart | `Customer[rfm_segment]` × `Customers` and `Revenue` |
| Middle | Column chart | `Customer[loyalty_tier]` × `Revenue` (tier at the time of purchase, SCD2) |
| Right | Donut | `Customer[customer_type]` × `Revenue` |
| Bottom | Table (Top N = 20 by `Revenue`) | `Customer[customer_name]`, `Customer[rfm_segment]`, `Orders`, `Revenue`, `Avg Order Value` |

**Decision supported:** retention campaigns aimed at "At Risk" and "Needs Attention" customers,
and loyalty-tier rules.

**Note:** a slicer on `Customer[rfm_segment]` filters every fact, because the segment is an
attribute of the Customer dimension.

## 6. Service Operations

**Business questions:** How busy is the service, and how fast is it? Which branch has
growing turnaround times? Which service types are profitable?

| Area | Visual | Fields / measures |
|------|--------|-------------------|
| KPI row | 5 cards | `Service Revenue`, `Service Order Count`, `Avg Service Order Value`, `Median Turnaround (h)` (subtitle `Median Turnaround LY (h)`), `Labor Share %` |
| Main | Line chart | `Date[year_quarter]` × `Median Turnaround (h)`, legend `Branch[branch_name]` |
| Middle left | Bar chart | `Service Orders[service_type]` × `Service Revenue`, tooltip `Service Margin %` |
| Middle right | Column chart | `Date[year_month]` × `Service Order Count` and `Orders Closed` (opened vs closed: backlog) |
| Bottom | Matrix | Branch × `Service Orders[service_type]`: `Median Turnaround (h)`, `P90 Turnaround (h)` with conditional formatting |

**Decision supported:** staffing and capacity. Expected story: Batumi's median maintenance
turnaround grew from **~2.8 h to ~7.1 h**. Page 7 shows the same problem in customer comments.

## 7. Customer Feedback (AI)

**Business questions:** What do customers complain about, in which branch, and is it getting
worse? Which complaints are unusual (anomalies)? Can we trust the AI labels?

| Area | Visual | Fields / measures |
|------|--------|-------------------|
| KPI row | 5 cards | `Feedback Count`, `Negative Rate %` (subtitle `Negative Rate Change (pp)`), `Avg Rating`, `Net Sentiment Score`, `Active Anomalies` |
| Main left | 100% stacked bar | `Branch[branch_name]` × `Feedback Count`, legend `Feedback[sentiment]` (green / grey / red) |
| Main right | Bar chart | `Feedback[topic]` × `Negative Feedback` (sorted) |
| Middle | Line chart | `Date[year_quarter]` × `Waiting Time Complaints`, `Price Complaints`, `Availability Complaints` |
| Anomalies | Table | `Feedback Anomalies`: branch, topic, `year_quarter`, `negative_count`, `baseline_negatives`, `ratio_to_baseline`; visual filter `is_anomaly = True`; data bars on the ratio |
| AI narrative | Multi-row card | `Selected Insight` + `AI Insights[scope_value]` slicer |
| Evidence | Table | `Feedback[feedback_text]`, `language`, `sentiment`, `topic`, `confidence`, `rating`. Shows the actual comments behind any selection |
| AI quality (small) | Cards | `Model Label Share %`, `Fallback Label Share %`, `Low Confidence Labels`, `Rating Contradiction Rate %` |

**Decision supported:** fix root causes, not symptoms. In Batumi, waiting-time complaints
(2.12× baseline) coincide with turnaround growth on page 6, so the action is service capacity.
In Kutaisi the price anomaly (2.5×) points at pricing.

**Responsible AI on this page:** the evidence table shows the real text behind every number,
and the AI quality cards show how labels were produced. Users can always check the model.

## 8. Data Quality & Pipeline

**Business questions:** Did the last refresh succeed? How many checks failed, and how severe
are they? How many source rows were rejected, and why? Is quality getting better or worse?

| Area | Visual | Fields / measures |
|------|--------|-------------------|
| KPI row | 5 cards | `Last Run Status` (colour `Status Color`), `Last Refresh`, `Checks Run`, `Check Pass Rate %`, `Critical Failures` |
| Main | Stacked bar | `DQ Results[stage]` × `Checks Run`, legend `DQ Results[status]` |
| Middle | Table | `DQ Results` filtered to `status = FAIL`: severity, table, check, failed rows, failed %, message (severity icons) |
| Trend | Line chart | `DQ Run History[run_id]` × `warnings`, `rejected_rows`, `critical_failures` |
| Runs | Table | `Pipeline Runs`: run_id, triggered_by, started_at, `duration_seconds`, status, error_message |

**Decision supported:** whether to trust and publish today's numbers. If the critical count is
above 0, the pipeline has already rolled back the load and the report still shows the last
good data. This page explains why.

---

## Accessibility and usability checklist

- Colour is never the only signal: icons or labels are added next to red, amber and green.
- Every visual has a title phrased as a question or a takeaway ("Kutaisi is the only branch declining").
- Tooltips show the comparison value (LY, baseline) next to the current value.
- Alt text on KPI cards; tab order set (*View → Selection pane*).
- Bookmarks: "Reset filters" button on every page.
