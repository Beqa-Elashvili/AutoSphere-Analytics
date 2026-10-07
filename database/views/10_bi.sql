-- =============================================================================
-- 10_bi.sql — Power BI semantic layer (schema `bi`)
--
-- Power BI imports ONLY these views (docs: powerbi/data-model.md). Why a separate layer:
--   * stable contract: warehouse tables can change; these view names/columns do not
--   * business rules stay in SQL, not DAX: revenue = recognized sales lines only,
--     service = completed orders only (same rules as analytics.mv_sales / mv_service)
--   * privacy: no e-mail, phone or VIN reaches the report
--   * security: a read-only reporting role needs SELECT on `bi` only
--     (database/security/powerbi_reader.sql)
--
-- Views are dropped and recreated (not the schema) so grants on the schema survive.
-- =============================================================================
DROP VIEW IF EXISTS bi.dim_date, bi.dim_branch, bi.dim_category, bi.dim_product, bi.dim_customer,
                    bi.dim_employee, bi.dim_vehicle, bi.fact_sales, bi.fact_service_orders,
                    bi.fact_service_items, bi.fact_payments, bi.fact_customer_feedback,
                    bi.feedback_anomalies, bi.ai_insights, bi.dq_results, bi.dq_run_history,
                    bi.pipeline_runs CASCADE;

-- ---------------------------------------------------------------- dimensions
-- Date table: whole calendar years covering the data (a valid Power BI date table must be
-- contiguous). The YTD flags reproduce analytics.v_kpi_ytd: current year-to-date vs the
-- SAME calendar window last year, so DAX does not have to know where the data ends.
CREATE VIEW bi.dim_date AS
SELECT d.date_key, d.full_date, d.year, d.quarter_number, d.quarter_label, d.year_quarter,
       d.month_number, d.month_name, d.month_short, d.year_month,
       d.year * 100 + d.month_number                                         AS year_month_sort,
       d.iso_week, d.day_of_month, d.day_name, d.day_of_week, d.is_weekend,
       d.is_public_holiday, d.holiday_name,
       d.full_date <= p.last_date                                            AS is_in_data_period,
       (d.year = p.current_year     AND (d.month_number, d.day_of_month) <= (p.last_month, p.last_day)) AS is_current_ytd,
       (d.year = p.current_year - 1 AND (d.month_number, d.day_of_month) <= (p.last_month, p.last_day)) AS is_prior_ytd
FROM dw.dim_date d
CROSS JOIN analytics.v_data_period p
WHERE d.year BETWEEN extract(year FROM p.first_date) AND p.current_year;

CREATE VIEW bi.dim_branch AS
SELECT branch_key, branch_id, branch_name, city, region, branch_type,
       offers_sales, offers_service, opened_date, is_active
FROM dw.dim_branch;

CREATE VIEW bi.dim_category AS
SELECT category_key, category_id, category_name, business_line
FROM dw.dim_category;

CREATE VIEW bi.dim_product AS
SELECT product_key, product_id, product_name, brand, list_price, unit_cost, list_margin_pct,
       price_band, launch_date, is_active
FROM dw.dim_product;

-- SCD Type 2: one row per customer VERSION. Facts point to the version valid at the time
-- of the transaction, so "sales by loyalty tier" uses the tier the customer had back then.
-- rfm_segment is the customer's CURRENT segment (analytics.v_customer_metrics), repeated on
-- every version so it can be used as a slicer. E-mail and phone are deliberately excluded.
CREATE VIEW bi.dim_customer AS
SELECT c.customer_key, c.customer_id, c.customer_name, c.customer_type, c.city, c.region,
       c.loyalty_tier, c.registration_date, c.valid_from, c.valid_to, c.is_current,
       COALESCE(m.rfm_segment, CASE WHEN c.customer_key < 0 THEN 'Unknown' ELSE 'No purchases' END) AS rfm_segment
FROM dw.dim_customer c
LEFT JOIN analytics.v_customer_metrics m ON m.customer_id = c.customer_id;

CREATE VIEW bi.dim_employee AS
SELECT employee_key, employee_id, full_name, role, department, home_branch_name, hire_date, is_active
FROM dw.dim_employee;

CREATE VIEW bi.dim_vehicle AS
SELECT vehicle_key, vehicle_id, make, model, make_model, model_year, age_band, fuel_type, transmission
FROM dw.dim_vehicle;

-- ---------------------------------------------------------------- facts
-- Recognized sales lines only. customer_id is kept as a degenerate attribute: with SCD2 one
-- customer has several keys, so "distinct customers" must count customer_id, not the key.
CREATE VIEW bi.fact_sales AS
SELECT f.sale_line_id, f.invoice_number, f.date_key, f.customer_key, c.customer_id,
       f.product_key, f.category_key, f.branch_key, f.employee_key, f.sales_channel,
       f.quantity, f.unit_price, f.gross_amount, f.discount_amount, f.net_amount,
       f.cost_amount, f.profit_amount
FROM dw.fact_sales f
JOIN dw.dim_customer c ON c.customer_key = f.customer_key
WHERE f.is_revenue_recognized;

-- Completed service orders. opened_date_key -> active relationship to Date,
-- closed_date_key -> inactive relationship (USERELATIONSHIP in DAX).
CREATE VIEW bi.fact_service_orders AS
SELECT service_order_id, opened_date_key, closed_date_key, customer_key, vehicle_key, branch_key,
       employee_key, service_type, is_warranty, turnaround_hours, odometer_km, item_count,
       labor_hours, labor_revenue, parts_revenue, total_revenue, total_cost, profit_amount
FROM dw.fact_service_orders
WHERE is_completed;

CREATE VIEW bi.fact_service_items AS
SELECT service_item_id, service_order_id, date_key, customer_key, vehicle_key, product_key,
       category_key, branch_key, service_type, item_type, quantity, unit_price,
       revenue_amount, cost_amount, profit_amount
FROM dw.fact_service_items
WHERE is_revenue_recognized;

-- All payment attempts (failed/refunded included): needed for failure rate and refunds.
CREATE VIEW bi.fact_payments AS
SELECT payment_id, date_key, customer_key, branch_key, source_type, payment_method,
       payment_status, is_successful, amount, net_cash_amount
FROM dw.fact_payments;

CREATE VIEW bi.fact_customer_feedback AS
SELECT feedback_id, date_key, customer_key, branch_key, feedback_source, channel, rating,
       feedback_text, language, sentiment, topic, confidence, classification_method,
       CASE WHEN rating IS NULL THEN 'no rating'
            WHEN (rating >= 4 AND sentiment = 'positive') OR (rating <= 2 AND sentiment = 'negative')
              OR (rating = 3 AND sentiment = 'neutral') THEN 'agree'
            WHEN (rating >= 4 AND sentiment = 'negative') OR (rating <= 2 AND sentiment = 'positive')
            THEN 'contradict' ELSE 'partial' END                              AS rating_agreement
FROM dw.fact_customer_feedback;

-- ---------------------------------------------------------------- precomputed / operational
-- Baseline comparison needs a 4-quarter window per cell: cheaper and testable in SQL.
CREATE VIEW bi.feedback_anomalies AS
SELECT a.branch_name, b.branch_key, a.topic, a.year, a.quarter_number, a.year_quarter,
       a.feedback_count, a.negative_count, a.baseline_negatives, a.ratio_to_baseline, a.is_anomaly
FROM analytics.v_feedback_anomalies a
LEFT JOIN dw.dim_branch b ON b.branch_name = a.branch_name;

CREATE VIEW bi.ai_insights AS
SELECT scope, scope_value, period_label, insight_text, method, model, generated_at
FROM analytics.v_ai_insights_latest;

CREATE VIEW bi.dq_results AS
SELECT run_id, stage, severity, status, table_name, check_name, column_name,
       failed_rows, total_rows, failed_pct, message, executed_at
FROM audit.v_latest_quality_report;

CREATE VIEW bi.dq_run_history AS
SELECT run_id, run_status, started_at, checks, critical_failures, warnings, rejected_rows
FROM audit.v_quality_summary_by_run;

CREATE VIEW bi.pipeline_runs AS
SELECT run_id, pipeline_name, triggered_by, started_at, finished_at,
       ROUND(extract(epoch FROM finished_at - started_at)::numeric, 1)      AS duration_seconds,
       status, error_message
FROM audit.pipeline_runs;
