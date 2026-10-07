-- =============================================================================
-- 03_trends.sql — time series with MoM / YoY growth (window functions)
-- =============================================================================

-- Monthly sales trend: MoM via LAG, YoY via join to the same month last year,
-- running YTD via SUM() OVER (PARTITION BY year), 3-month rolling average.
CREATE OR REPLACE VIEW analytics.v_revenue_monthly AS
WITH m AS (
    SELECT year, month_number, year_month,
           sum(revenue) AS revenue, sum(profit) AS profit, count(DISTINCT invoice_number) AS orders
    FROM analytics.v_sales
    GROUP BY year, month_number, year_month
)
SELECT m.year_month, m.year, m.month_number,
       m.revenue, m.profit,
       ROUND(100 * m.profit / NULLIF(m.revenue, 0), 2)                              AS profit_margin_pct,
       m.orders,
       ROUND(m.revenue / NULLIF(m.orders, 0), 2)                                    AS avg_order_value,
       LAG(m.revenue) OVER w                                                        AS prev_month_revenue,
       ROUND(100 * (m.revenue / NULLIF(LAG(m.revenue) OVER w, 0) - 1), 2)           AS mom_growth_pct,
       ly.revenue                                                                   AS same_month_last_year_revenue,
       ROUND(100 * (m.revenue / NULLIF(ly.revenue, 0) - 1), 2)                      AS yoy_growth_pct,
       sum(m.revenue) OVER (PARTITION BY m.year ORDER BY m.month_number)            AS ytd_revenue,
       ROUND(avg(m.revenue) OVER (w ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2)   AS rolling_3m_avg_revenue
FROM m
LEFT JOIN m ly ON ly.year = m.year - 1 AND ly.month_number = m.month_number
WINDOW w AS (ORDER BY m.year, m.month_number)
ORDER BY m.year, m.month_number;

-- Branch x month: the input for spotting declining branches.
CREATE OR REPLACE VIEW analytics.v_branch_monthly AS
WITH m AS (
    SELECT branch_id, branch_name, year, month_number, year_month,
           sum(revenue) AS revenue, count(DISTINCT invoice_number) AS orders
    FROM analytics.v_sales
    GROUP BY branch_id, branch_name, year, month_number, year_month
)
SELECT m.branch_id, m.branch_name, m.year_month, m.year, m.month_number, m.revenue, m.orders,
       ly.revenue                                                   AS same_month_last_year_revenue,
       ROUND(100 * (m.revenue / NULLIF(ly.revenue, 0) - 1), 2)      AS yoy_growth_pct,
       ROUND(100 * (m.revenue / NULLIF(LAG(m.revenue) OVER (PARTITION BY m.branch_id
                                         ORDER BY m.year, m.month_number), 0) - 1), 2) AS mom_growth_pct
FROM m
LEFT JOIN m ly ON ly.branch_id = m.branch_id AND ly.year = m.year - 1 AND ly.month_number = m.month_number;
