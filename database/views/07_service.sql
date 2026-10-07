-- =============================================================================
-- 07_service.sql — service-centre KPIs
-- =============================================================================

-- Monthly service volume, revenue and turnaround (completed orders).
CREATE OR REPLACE VIEW analytics.v_service_monthly AS
SELECT year_month, year, month_number,
       count(*)                                                          AS service_orders,
       sum(total_revenue)                                                AS service_revenue,
       ROUND(avg(total_revenue), 2)                                      AS avg_service_order_value,
       sum(profit_amount)                                                AS service_profit,
       ROUND(100 * sum(labor_revenue) / NULLIF(sum(total_revenue), 0), 2) AS labor_share_pct,
       ROUND(avg(turnaround_hours), 1)                                   AS avg_turnaround_hours,
       ROUND(percentile_cont(0.5) WITHIN GROUP (ORDER BY turnaround_hours)::numeric, 1) AS median_turnaround_hours
FROM analytics.v_service
GROUP BY year_month, year, month_number;

-- Performance per service type.
CREATE OR REPLACE VIEW analytics.v_service_type_performance AS
SELECT service_type,
       count(*)                                                          AS service_orders,
       sum(total_revenue)                                                AS service_revenue,
       ROUND(avg(total_revenue), 2)                                      AS avg_service_order_value,
       ROUND(100 * sum(profit_amount) / NULLIF(sum(total_revenue), 0), 2) AS profit_margin_pct,
       ROUND(avg(labor_hours), 2)                                        AS avg_labor_hours,
       ROUND(percentile_cont(0.5) WITHIN GROUP (ORDER BY turnaround_hours)::numeric, 1) AS median_turnaround_hours,
       ROUND(100.0 * count(*) / sum(count(*)) OVER (), 2)                AS order_share_pct
FROM analytics.v_service
GROUP BY service_type;

-- Service revenue by category: parts by product category, labour as its own line.
CREATE OR REPLACE VIEW analytics.v_service_revenue_by_category AS
SELECT c.category_name, c.business_line, d.year,
       sum(i.revenue_amount)                                                   AS service_revenue,
       sum(i.profit_amount)                                                    AS service_profit,
       ROUND(100 * sum(i.profit_amount) / NULLIF(sum(i.revenue_amount), 0), 2) AS profit_margin_pct,
       sum(i.quantity)                                                         AS quantity,
       ROUND(100 * sum(i.revenue_amount) / sum(sum(i.revenue_amount)) OVER (PARTITION BY d.year), 2) AS revenue_share_pct
FROM dw.fact_service_items i
JOIN dw.dim_category c ON c.category_key = i.category_key
JOIN dw.dim_date d     ON d.date_key = i.date_key
WHERE i.is_revenue_recognized
GROUP BY c.category_name, c.business_line, d.year;

-- Branch x quarter turnaround: the operational signal behind waiting-time complaints.
CREATE OR REPLACE VIEW analytics.v_service_turnaround AS
SELECT branch_id, branch_name, year, quarter_number,
       year || '-Q' || quarter_number                                    AS year_quarter,
       service_type,
       count(*)                                                          AS service_orders,
       ROUND(percentile_cont(0.5) WITHIN GROUP (ORDER BY turnaround_hours)::numeric, 1) AS median_turnaround_hours,
       ROUND(percentile_cont(0.9) WITHIN GROUP (ORDER BY turnaround_hours)::numeric, 1) AS p90_turnaround_hours
FROM analytics.v_service
GROUP BY branch_id, branch_name, year, quarter_number, service_type;
