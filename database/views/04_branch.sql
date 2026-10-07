-- =============================================================================
-- 04_branch.sql — branch performance and decline alerts
-- =============================================================================

-- Branch x year: sales + service performance, share of company revenue and rank.
CREATE OR REPLACE VIEW analytics.v_branch_performance AS
WITH b AS (
    SELECT branch_id, branch_name, city, region, branch_type FROM dw.dim_branch WHERE branch_key <> -1
), years AS (
    SELECT DISTINCT year FROM analytics.v_sales
), sales AS (
    SELECT branch_id, year, sum(revenue) AS revenue, sum(profit) AS profit,
           count(DISTINCT invoice_number) AS orders, count(DISTINCT customer_id) AS customers
    FROM analytics.v_sales GROUP BY branch_id, year
), service AS (
    SELECT branch_id, year, sum(total_revenue) AS service_revenue, count(*) AS service_orders,
           sum(profit_amount) AS service_profit, avg(turnaround_hours) AS avg_turnaround_hours
    FROM analytics.v_service GROUP BY branch_id, year
)
SELECT b.branch_id, b.branch_name, b.city, b.region, b.branch_type, y.year,
       COALESCE(s.revenue, 0)                                                    AS sales_revenue,
       COALESCE(s.profit, 0)                                                     AS sales_profit,
       ROUND(100 * s.profit / NULLIF(s.revenue, 0), 2)                           AS sales_margin_pct,
       COALESCE(s.orders, 0)                                                     AS orders,
       ROUND(s.revenue / NULLIF(s.orders, 0), 2)                                 AS avg_order_value,
       COALESCE(s.customers, 0)                                                  AS customers,
       ROUND(100 * s.revenue / NULLIF(sum(s.revenue) OVER (PARTITION BY y.year), 0), 2) AS revenue_share_pct,
       RANK() OVER (PARTITION BY y.year ORDER BY COALESCE(s.revenue, 0) DESC)    AS sales_revenue_rank,
       COALESCE(sv.service_revenue, 0)                                           AS service_revenue,
       COALESCE(sv.service_orders, 0)                                            AS service_orders,
       ROUND(sv.service_revenue / NULLIF(sv.service_orders, 0), 2)               AS avg_service_order_value,
       ROUND(sv.avg_turnaround_hours, 1)                                         AS avg_turnaround_hours,
       COALESCE(s.revenue, 0) + COALESCE(sv.service_revenue, 0)                  AS total_revenue,
       COALESCE(s.profit, 0) + COALESCE(sv.service_profit, 0)                    AS total_profit
FROM b CROSS JOIN years y
LEFT JOIN sales s    ON s.branch_id = b.branch_id AND s.year = y.year
LEFT JOIN service sv ON sv.branch_id = b.branch_id AND sv.year = y.year;

-- Comparable-period branch growth (YTD vs prior YTD) with a simple alert status.
CREATE OR REPLACE VIEW analytics.v_branch_growth AS
WITH p AS (SELECT * FROM analytics.v_data_period),
ytd AS (
    SELECT v.branch_id, v.branch_name, v.year, sum(v.revenue) AS revenue, count(DISTINCT v.invoice_number) AS orders
    FROM analytics.v_sales v CROSS JOIN p
    WHERE v.year IN (p.current_year, p.current_year - 1)
      AND (v.month_number, extract(day FROM v.sale_date)) <= (p.last_month, p.last_day)
    GROUP BY v.branch_id, v.branch_name, v.year
), last3 AS (   -- last three months vs the same three months a year earlier
    SELECT v.branch_id,
           sum(v.revenue) FILTER (WHERE v.sale_date >  p.last_date - INTERVAL '3 months')                AS rev_last_3m,
           sum(v.revenue) FILTER (WHERE v.sale_date >  p.last_date - INTERVAL '15 months'
                                    AND v.sale_date <= p.last_date - INTERVAL '12 months')              AS rev_last_3m_prior_year
    FROM analytics.v_sales v CROSS JOIN p
    GROUP BY v.branch_id
)
SELECT cur.branch_id, cur.branch_name,
       cur.revenue                                                       AS ytd_revenue,
       prev.revenue                                                      AS prior_ytd_revenue,
       ROUND(100 * (cur.revenue / NULLIF(prev.revenue, 0) - 1), 2)       AS ytd_yoy_pct,
       cur.orders                                                        AS ytd_orders,
       prev.orders                                                       AS prior_ytd_orders,
       l.rev_last_3m,
       l.rev_last_3m_prior_year,
       ROUND(100 * (l.rev_last_3m / NULLIF(l.rev_last_3m_prior_year, 0) - 1), 2) AS last_3m_yoy_pct,
       CASE WHEN cur.revenue < prev.revenue * 0.95 THEN 'Declining'
            WHEN cur.revenue > prev.revenue * 1.05 THEN 'Growing'
            ELSE 'Stable' END                                            AS trend_status
FROM ytd cur
JOIN ytd prev  ON prev.branch_id = cur.branch_id AND prev.year = cur.year - 1
JOIN last3 l   ON l.branch_id = cur.branch_id
WHERE cur.year = (SELECT current_year FROM p);

-- Revenue by the branch's city.
CREATE OR REPLACE VIEW analytics.v_city_revenue AS
SELECT branch_city AS city, year,
       sum(revenue)                                                       AS revenue,
       sum(profit)                                                        AS profit,
       ROUND(100 * sum(profit) / NULLIF(sum(revenue), 0), 2)              AS profit_margin_pct,
       count(DISTINCT invoice_number)                                     AS orders,
       count(DISTINCT branch_id)                                          AS branches,
       ROUND(100 * sum(revenue) / sum(sum(revenue)) OVER (PARTITION BY year), 2) AS revenue_share_pct
FROM analytics.v_sales
GROUP BY branch_city, year;
