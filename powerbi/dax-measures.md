# DAX Measures

All measures live in the **_Measures** table and are organised into display folders that
match the headings below. Table and column names refer to the model in `data-model.md`.
`tests/test_powerbi.py` checks that every `Table[column]` used here exists in the `bi` views
and every `[Measure]` reference is defined in this file.

**Conventions**
- `DIVIDE()` instead of `/`: it returns BLANK on a zero denominator instead of an error.
- Business filters (completed sales, completed service orders) are already applied in SQL. Measures never repeat them.
- Rates return a fraction (0.153); format them as percentage in Power BI.
- Each measure's SQL equivalent is listed in `docs/kpi-dictionary.md`. `scripts/powerbi_reference.py` prints the values the report must show.

## Sales

```dax
Revenue = SUM ( Sales[net_amount] )

Cost = SUM ( Sales[cost_amount] )

Profit = SUM ( Sales[profit_amount] )

Profit Margin % = DIVIDE ( [Profit], [Revenue] )

Orders = DISTINCTCOUNT ( Sales[invoice_number] )

Avg Order Value = DIVIDE ( [Revenue], [Orders] )

Units Sold = SUM ( Sales[quantity] )

Discount Rate % = DIVIDE ( SUM ( Sales[discount_amount] ), SUM ( Sales[gross_amount] ) )

Customers = DISTINCTCOUNT ( Sales[customer_id] )

Repeat Customers =
    COUNTROWS (
        FILTER ( VALUES ( Sales[customer_id] ), CALCULATE ( [Orders] ) >= 2 )
    )

Repeat Customer Rate % = DIVIDE ( [Repeat Customers], [Customers] )

Branch Revenue Share % = DIVIDE ( [Revenue], CALCULATE ( [Revenue], REMOVEFILTERS ( Branch ) ) )

Category Revenue Share % = DIVIDE ( [Revenue], CALCULATE ( [Revenue], REMOVEFILTERS ( Category ) ) )

Branch Revenue Rank =
    IF (
        HASONEVALUE ( Branch[branch_name] ),
        RANKX ( ALLSELECTED ( Branch[branch_name] ), [Revenue] )
    )

Product Revenue Rank =
    IF (
        HASONEVALUE ( Product[product_name] ),
        RANKX ( ALLSELECTED ( Product[product_name] ), [Revenue] )
    )
```

*Why `Customers` counts `Sales[customer_id]`:* the Customer table is SCD Type 2, so one person
can have several `customer_key` values. Counting keys would count the same customer twice.

## Time intelligence

Standard time intelligence works on the visual's date context (e.g. a month on the axis):

```dax
Revenue LY = CALCULATE ( [Revenue], SAMEPERIODLASTYEAR ( 'Date'[full_date] ) )

Revenue YoY % = DIVIDE ( [Revenue] - [Revenue LY], [Revenue LY] )

Revenue PM = CALCULATE ( [Revenue], DATEADD ( 'Date'[full_date], -1, MONTH ) )

Revenue MoM % = DIVIDE ( [Revenue] - [Revenue PM], [Revenue PM] )

Revenue YTD = TOTALYTD ( [Revenue], 'Date'[full_date] )

Revenue Rolling 3M Avg =
    DIVIDE (
        CALCULATE (
            [Revenue],
            DATESINPERIOD ( 'Date'[full_date], MAX ( 'Date'[full_date] ), -3, MONTH )
        ),
        3
    )
```

### Comparable YTD (headline cards)

The data ends in the middle of the current year. Comparing a partial year with a full previous
year would show a fake decline: **−18.5%** instead of the real **+15.6%**. The Date table
carries two flags computed in SQL (`is_current_ytd`, `is_prior_ytd`) for "1 January to the last
data day" this year and the same window last year. The cards ignore date slicers on purpose.

```dax
Revenue CY YTD =
    CALCULATE ( [Revenue], REMOVEFILTERS ( 'Date' ), 'Date'[is_current_ytd] = TRUE () )

Revenue PY YTD =
    CALCULATE ( [Revenue], REMOVEFILTERS ( 'Date' ), 'Date'[is_prior_ytd] = TRUE () )

Revenue YTD YoY % = DIVIDE ( [Revenue CY YTD] - [Revenue PY YTD], [Revenue PY YTD] )

Orders CY YTD =
    CALCULATE ( [Orders], REMOVEFILTERS ( 'Date' ), 'Date'[is_current_ytd] = TRUE () )

Orders PY YTD =
    CALCULATE ( [Orders], REMOVEFILTERS ( 'Date' ), 'Date'[is_prior_ytd] = TRUE () )

Orders YTD YoY % = DIVIDE ( [Orders CY YTD] - [Orders PY YTD], [Orders PY YTD] )

Profit Margin CY YTD % =
    CALCULATE ( [Profit Margin %], REMOVEFILTERS ( 'Date' ), 'Date'[is_current_ytd] = TRUE () )

Service Revenue CY YTD =
    CALCULATE ( [Service Revenue], REMOVEFILTERS ( 'Date' ), 'Date'[is_current_ytd] = TRUE () )

Service Revenue PY YTD =
    CALCULATE ( [Service Revenue], REMOVEFILTERS ( 'Date' ), 'Date'[is_prior_ytd] = TRUE () )

Service Revenue YTD YoY % =
    DIVIDE ( [Service Revenue CY YTD] - [Service Revenue PY YTD], [Service Revenue PY YTD] )

Data Through = CALCULATE ( MAX ( 'Date'[full_date] ), 'Date'[is_current_ytd] = TRUE () )
```

### Growth between complete years only

```dax
Months With Sales = COUNTROWS ( SUMMARIZE ( Sales, 'Date'[year_month] ) )

Revenue YoY % (Complete Years) =
    VAR CurrentMonths = [Months With Sales]
    VAR PreviousMonths =
        CALCULATE ( [Months With Sales], SAMEPERIODLASTYEAR ( 'Date'[full_date] ) )
    RETURN
        IF ( CurrentMonths = 12 && PreviousMonths = 12, [Revenue YoY %] )
```

Same rule as `revenue_growth_pct` in `analytics.v_kpi_by_year`: a year-level growth number is
shown only when both years are complete.

## Service

```dax
Service Revenue = SUM ( 'Service Orders'[total_revenue] )

Service Order Count = COUNTROWS ( 'Service Orders' )

Avg Service Order Value = DIVIDE ( [Service Revenue], [Service Order Count] )

Service Profit = SUM ( 'Service Orders'[profit_amount] )

Service Margin % = DIVIDE ( [Service Profit], [Service Revenue] )

Labor Share % = DIVIDE ( SUM ( 'Service Orders'[labor_revenue] ), [Service Revenue] )

Warranty Share % =
    DIVIDE (
        CALCULATE ( [Service Order Count], 'Service Orders'[is_warranty] = TRUE () ),
        [Service Order Count]
    )

Median Turnaround (h) = MEDIAN ( 'Service Orders'[turnaround_hours] )

P90 Turnaround (h) = PERCENTILE.INC ( 'Service Orders'[turnaround_hours], 0.9 )

Median Turnaround LY (h) =
    CALCULATE ( [Median Turnaround (h)], SAMEPERIODLASTYEAR ( 'Date'[full_date] ) )

Orders Closed =
    CALCULATE (
        [Service Order Count],
        USERELATIONSHIP ( 'Service Orders'[closed_date_key], 'Date'[date_key] )
    )

Parts Revenue (Items) =
    CALCULATE ( SUM ( 'Service Items'[revenue_amount] ), 'Service Items'[item_type] = "part" )

Total Business Revenue = [Revenue] + [Service Revenue]
```

*Median, not average:* turnaround has a long tail (a few orders wait days for parts), so the
average would be dominated by outliers. `PERCENTILE.INC` matches PostgreSQL's
`percentile_cont` used in `analytics.v_service_turnaround`.

## Payments

```dax
Payment Attempts = COUNTROWS ( Payments )

Failed Payment Rate % =
    DIVIDE ( CALCULATE ( [Payment Attempts], Payments[payment_status] = "failed" ), [Payment Attempts] )

Collected Amount = CALCULATE ( SUM ( Payments[amount] ), Payments[payment_status] = "completed" )

Refunded Amount = CALCULATE ( SUM ( Payments[amount] ), Payments[payment_status] = "refunded" )

Net Cash = SUM ( Payments[net_cash_amount] )
```

## Customer feedback (AI)

```dax
Feedback Count = COUNTROWS ( Feedback )

Negative Feedback = CALCULATE ( [Feedback Count], Feedback[sentiment] = "negative" )

Positive Feedback = CALCULATE ( [Feedback Count], Feedback[sentiment] = "positive" )

Negative Rate % = DIVIDE ( [Negative Feedback], [Feedback Count] )

Positive Rate % = DIVIDE ( [Positive Feedback], [Feedback Count] )

Net Sentiment Score = DIVIDE ( [Positive Feedback] - [Negative Feedback], [Feedback Count] )

Avg Rating = AVERAGE ( Feedback[rating] )

Negative Rate LY % = CALCULATE ( [Negative Rate %], SAMEPERIODLASTYEAR ( 'Date'[full_date] ) )

Negative Rate Change (pp) =
    IF ( NOT ISBLANK ( [Negative Rate LY %] ), ( [Negative Rate %] - [Negative Rate LY %] ) * 100 )

Waiting Time Complaints = CALCULATE ( [Negative Feedback], Feedback[topic] = "waiting_time" )

Price Complaints = CALCULATE ( [Negative Feedback], Feedback[topic] = "price" )

Availability Complaints = CALCULATE ( [Negative Feedback], Feedback[topic] = "availability" )

Rating Contradiction Rate % =
    DIVIDE (
        CALCULATE ( [Feedback Count], Feedback[rating_agreement] = "contradict" ),
        CALCULATE ( [Feedback Count], Feedback[rating_agreement] <> "no rating" )
    )

Low Confidence Labels = CALCULATE ( [Feedback Count], Feedback[confidence] < 0.6 )

Model Label Share % =
    DIVIDE (
        CALCULATE ( [Feedback Count], LEFT ( Feedback[classification_method], 7 ) = "gemini:" ),
        [Feedback Count]
    )

Fallback Label Share % =
    DIVIDE (
        CALCULATE ( [Feedback Count], CONTAINSSTRING ( Feedback[classification_method], "fallback" ) ),
        [Feedback Count]
    )

Active Anomalies =
    CALCULATE ( COUNTROWS ( 'Feedback Anomalies' ), 'Feedback Anomalies'[is_anomaly] = TRUE () )

Selected Insight = SELECTEDVALUE ( 'AI Insights'[insight_text], "Select one branch or All branches" )
```

*Rating Contradiction Rate* doubles as an AI quality monitor: a customer who gives 5 stars
and writes a comment the model labels negative is either sarcasm, a mixed review or a model
error. A sudden rise means "review the model".

## Data quality & pipeline

```dax
Checks Run = COUNTROWS ( 'DQ Results' )

Failed Checks = CALCULATE ( [Checks Run], 'DQ Results'[status] = "FAIL" )

Critical Failures = CALCULATE ( [Failed Checks], 'DQ Results'[severity] = "CRITICAL" )

Check Pass Rate % = DIVIDE ( [Checks Run] - [Failed Checks], [Checks Run] )

Last Run Status =
    VAR LastRun = MAX ( 'Pipeline Runs'[run_id] )
    RETURN
        CALCULATE ( SELECTEDVALUE ( 'Pipeline Runs'[status] ), 'Pipeline Runs'[run_id] = LastRun )

Last Run Duration (s) =
    VAR LastRun = MAX ( 'Pipeline Runs'[run_id] )
    RETURN
        CALCULATE ( SUM ( 'Pipeline Runs'[duration_seconds] ), 'Pipeline Runs'[run_id] = LastRun )

Last Refresh = MAX ( 'Pipeline Runs'[finished_at] )

Last Run Rejected Rows =
    VAR LastRun = MAX ( 'DQ Run History'[run_id] )
    RETURN
        CALCULATE ( SUM ( 'DQ Run History'[rejected_rows] ), 'DQ Run History'[run_id] = LastRun )

Status Color =
    SWITCH (
        TRUE (),
        [Critical Failures] > 0, "#C0392B",
        [Failed Checks] > 0, "#E67E22",
        "#27AE60"
    )
```

`Status Color` drives conditional formatting (Format → Conditional formatting → Field value)
on the DQ status card: red for critical, orange for warnings, green for clean.
