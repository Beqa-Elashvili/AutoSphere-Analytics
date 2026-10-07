-- =============================================================================
-- 02_kpis.sql — headline KPIs (definitions: docs/kpi-dictionary.md)
-- =============================================================================

-- All-time headline KPIs (one row).
CREATE OR REPLACE VIEW analytics.v_kpi_summary AS
WITH sales AS (
    SELECT sum(revenue) AS revenue, sum(profit) AS profit,
           count(DISTINCT invoice_number) AS orders, count(DISTINCT customer_id) AS customers
    FROM analytics.v_sales
), per_customer AS (
    SELECT customer_id, count(DISTINCT invoice_number) AS orders FROM analytics.v_sales GROUP BY customer_id
), service AS (
    SELECT sum(total_revenue) AS service_revenue, count(*) AS service_orders FROM analytics.v_service
)
SELECT s.revenue,
       s.profit,
       ROUND(100 * s.profit / NULLIF(s.revenue, 0), 2)                      AS profit_margin_pct,
       s.orders,
       ROUND(s.revenue / NULLIF(s.orders, 0), 2)                            AS avg_order_value,
       s.customers                                                          AS customer_count,
       (SELECT count(*) FROM per_customer WHERE orders >= 2)                AS repeat_customers,
       ROUND(100.0 * (SELECT count(*) FROM per_customer WHERE orders >= 2)
             / NULLIF(s.customers, 0), 2)                                    AS repeat_customer_rate_pct,
       sv.service_revenue,
       sv.service_orders,
       ROUND(sv.service_revenue / NULLIF(sv.service_orders, 0), 2)          AS avg_service_order_value,
       s.revenue + sv.service_revenue                                       AS total_business_revenue
FROM sales s CROSS JOIN service sv;

-- KPIs per calendar year. The latest year may be partial: see months_covered and v_kpi_ytd.
CREATE OR REPLACE VIEW analytics.v_kpi_by_year AS
WITH sales AS (
    SELECT year, sum(revenue) AS revenue, sum(profit) AS profit,
           count(DISTINCT invoice_number) AS orders, count(DISTINCT customer_id) AS customers,
           count(DISTINCT month_number) AS months_covered
    FROM analytics.v_sales GROUP BY year
), repeaters AS (
    SELECT year, count(*) FILTER (WHERE orders >= 2) AS repeat_customers
    FROM (SELECT year, customer_id, count(DISTINCT invoice_number) AS orders
          FROM analytics.v_sales GROUP BY year, customer_id) x
    GROUP BY year
), service AS (
    SELECT year, sum(total_revenue) AS service_revenue, count(*) AS service_orders
    FROM analytics.v_service GROUP BY year
)
SELECT s.year,
       s.months_covered,
       s.months_covered < 12                                                AS is_partial_year,
       s.revenue,
       s.profit,
       ROUND(100 * s.profit / NULLIF(s.revenue, 0), 2)                      AS profit_margin_pct,
       s.orders,
       ROUND(s.revenue / NULLIF(s.orders, 0), 2)                            AS avg_order_value,
       s.customers                                                          AS customer_count,
       r.repeat_customers,
       ROUND(100.0 * r.repeat_customers / NULLIF(s.customers, 0), 2)        AS repeat_customer_rate_pct,
       sv.service_revenue,
       sv.service_orders,
       ROUND(sv.service_revenue / NULLIF(sv.service_orders, 0), 2)          AS avg_service_order_value,
       -- Growth only between two COMPLETE years; a partial year would show a fake decline
       -- (use v_kpi_ytd for comparable year-to-date growth).
       CASE WHEN s.months_covered = 12 AND LAG(s.months_covered) OVER (ORDER BY s.year) = 12
            THEN ROUND(100 * (s.revenue / NULLIF(LAG(s.revenue) OVER (ORDER BY s.year), 0) - 1), 2)
       END                                                                  AS revenue_growth_pct
FROM sales s
LEFT JOIN repeaters r USING (year)
LEFT JOIN service sv  USING (year)
ORDER BY s.year;

-- Comparable-period growth: current year-to-date vs the same calendar window last year.
CREATE OR REPLACE VIEW analytics.v_kpi_ytd AS
WITH p AS (SELECT * FROM analytics.v_data_period),
ytd AS (
    SELECT v.year,
           sum(v.revenue) AS revenue, sum(v.profit) AS profit,
           count(DISTINCT v.invoice_number) AS orders, count(DISTINCT v.customer_id) AS customers
    FROM analytics.v_sales v CROSS JOIN p
    WHERE v.year IN (p.current_year, p.current_year - 1)
      AND (v.month_number, extract(day FROM v.sale_date)) <= (p.last_month, p.last_day)
    GROUP BY v.year
), svc AS (
    SELECT v.year, sum(v.total_revenue) AS service_revenue, count(*) AS service_orders
    FROM analytics.v_service v CROSS JOIN p
    WHERE v.year IN (p.current_year, p.current_year - 1)
      AND (v.month_number, extract(day FROM v.service_date)) <= (p.last_month, p.last_day)
    GROUP BY v.year
)
SELECT p.current_year,
       make_date(p.current_year, 1, 1) AS ytd_from,
       p.last_date                     AS ytd_to,
       cur.revenue                     AS ytd_revenue,
       prev.revenue                    AS prior_ytd_revenue,
       ROUND(100 * (cur.revenue / NULLIF(prev.revenue, 0) - 1), 2)          AS revenue_yoy_pct,
       cur.profit                      AS ytd_profit,
       ROUND(100 * cur.profit / NULLIF(cur.revenue, 0), 2)                  AS ytd_margin_pct,
       ROUND(100 * prev.profit / NULLIF(prev.revenue, 0), 2)                AS prior_ytd_margin_pct,
       cur.orders                      AS ytd_orders,
       prev.orders                     AS prior_ytd_orders,
       ROUND(100.0 * (cur.orders::numeric / NULLIF(prev.orders, 0) - 1), 2) AS orders_yoy_pct,
       ROUND(cur.revenue / NULLIF(cur.orders, 0), 2)                        AS ytd_avg_order_value,
       ROUND(prev.revenue / NULLIF(prev.orders, 0), 2)                      AS prior_ytd_avg_order_value,
       scur.service_revenue            AS ytd_service_revenue,
       sprev.service_revenue           AS prior_ytd_service_revenue,
       ROUND(100 * (scur.service_revenue / NULLIF(sprev.service_revenue, 0) - 1), 2) AS service_revenue_yoy_pct
FROM p
LEFT JOIN ytd cur   ON cur.year = p.current_year
LEFT JOIN ytd prev  ON prev.year = p.current_year - 1
LEFT JOIN svc scur  ON scur.year = p.current_year
LEFT JOIN svc sprev ON sprev.year = p.current_year - 1;
