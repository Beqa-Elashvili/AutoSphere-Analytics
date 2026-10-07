-- Business question: How is revenue trending month over month and year over year?
-- KPI: Revenue, MoM Growth, YoY Growth, YTD revenue, 3-month rolling average
-- Source: analytics.v_revenue_monthly (LAG, self-join on month, SUM() OVER, rolling AVG)
-- Decision: detect seasonality (tires in spring/autumn) and real trend changes vs noise.
SELECT year_month,
       ROUND(revenue)                       AS revenue_gel,
       mom_growth_pct,
       yoy_growth_pct,
       ROUND(ytd_revenue)                   AS ytd_revenue_gel,
       ROUND(rolling_3m_avg_revenue)        AS rolling_3m_avg_gel,
       orders,
       avg_order_value
FROM analytics.v_revenue_monthly
ORDER BY year DESC, month_number DESC
LIMIT 15;
