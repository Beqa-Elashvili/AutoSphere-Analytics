-- =============================================================================
-- 01_base.sql — semantic base layer over the star schema
-- Every analytical view builds on these, so business rules live in one place:
--   * revenue = net amount of COMPLETED sales lines (is_revenue_recognized)
--   * service revenue = revenue of COMPLETED service orders
--
-- The two base datasets are MATERIALIZED views (the 6-table join is computed once
-- per pipeline run and indexed); v_sales / v_service are thin views on top so the
-- rest of the analytics layer does not care how the base is stored. This file is
-- re-run by the pipeline after every warehouse build, which rebuilds the data.
-- DROP ... CASCADE also drops dependent views; later files (02_ .. 08_) recreate them.
-- =============================================================================
DROP MATERIALIZED VIEW IF EXISTS analytics.mv_sales CASCADE;
DROP MATERIALIZED VIEW IF EXISTS analytics.mv_service CASCADE;
DROP VIEW IF EXISTS analytics.v_sales CASCADE;
DROP VIEW IF EXISTS analytics.v_service CASCADE;

-- Data coverage: drives "comparable period" (YTD vs prior YTD) calculations.
CREATE OR REPLACE VIEW analytics.v_data_period AS
SELECT min(sale_datetime)::date                                AS first_date,
       max(sale_datetime)::date                                AS last_date,
       extract(year FROM max(sale_datetime))::int              AS current_year,
       extract(month FROM max(sale_datetime))::int             AS last_month,
       extract(day FROM max(sale_datetime))::int               AS last_day
FROM dw.fact_sales
WHERE is_revenue_recognized;

-- Recognized sales lines with descriptive attributes (customer attributes as of the sale).
-- Business keys use the "C" collation (byte order): COUNT(DISTINCT invoice_number) and
-- similar sorts are ~10x faster than with linguistic collation, and IDs need no locale rules.
CREATE MATERIALIZED VIEW analytics.mv_sales AS
SELECT f.sale_line_id COLLATE "C" AS sale_line_id, f.invoice_number COLLATE "C" AS invoice_number,
       d.full_date AS sale_date, d.year, d.quarter_number, d.month_number, d.year_month,
       b.branch_id COLLATE "C" AS branch_id, b.branch_name, b.city AS branch_city, b.region,
       c.category_name, c.business_line,
       p.product_id COLLATE "C" AS product_id, p.product_name, p.brand,
       cu.customer_id COLLATE "C" AS customer_id, cu.customer_name, cu.customer_type,
       cu.city AS customer_city, cu.loyalty_tier,
       e.employee_id COLLATE "C" AS employee_id, e.full_name AS employee_name,
       f.sales_channel, f.quantity, f.gross_amount, f.discount_amount,
       f.net_amount    AS revenue,
       f.cost_amount   AS cost,
       f.profit_amount AS profit
FROM dw.fact_sales f
JOIN dw.dim_date d      ON d.date_key = f.date_key
JOIN dw.dim_branch b    ON b.branch_key = f.branch_key
JOIN dw.dim_category c  ON c.category_key = f.category_key
JOIN dw.dim_product p   ON p.product_key = f.product_key
JOIN dw.dim_customer cu ON cu.customer_key = f.customer_key
JOIN dw.dim_employee e  ON e.employee_key = f.employee_key
WHERE f.is_revenue_recognized;
CREATE INDEX ix_mv_sales_period   ON analytics.mv_sales (year, month_number);
CREATE INDEX ix_mv_sales_customer ON analytics.mv_sales (customer_id);
CREATE INDEX ix_mv_sales_branch   ON analytics.mv_sales (branch_id, year);
CREATE VIEW analytics.v_sales AS SELECT * FROM analytics.mv_sales;

-- Completed service orders with descriptive attributes (dated by the opening date).
CREATE MATERIALIZED VIEW analytics.mv_service AS
SELECT o.service_order_id COLLATE "C" AS service_order_id,
       d.full_date AS service_date, d.year, d.quarter_number, d.month_number, d.year_month,
       b.branch_id COLLATE "C" AS branch_id, b.branch_name, b.city AS branch_city,
       cu.customer_id COLLATE "C" AS customer_id, cu.customer_type,
       v.make, v.age_band,
       o.service_type, o.is_warranty, o.turnaround_hours, o.item_count, o.labor_hours,
       o.labor_revenue, o.parts_revenue, o.total_revenue, o.total_cost, o.profit_amount
FROM dw.fact_service_orders o
JOIN dw.dim_date d      ON d.date_key = o.opened_date_key
JOIN dw.dim_branch b    ON b.branch_key = o.branch_key
JOIN dw.dim_customer cu ON cu.customer_key = o.customer_key
JOIN dw.dim_vehicle v   ON v.vehicle_key = o.vehicle_key
WHERE o.is_completed;
CREATE INDEX ix_mv_service_period ON analytics.mv_service (year, month_number);
CREATE INDEX ix_mv_service_branch ON analytics.mv_service (branch_id, year);
CREATE VIEW analytics.v_service AS SELECT * FROM analytics.mv_service;
