-- Business question: Which branches have declining revenue?
-- KPI: YTD revenue vs prior-year YTD (comparable period) | Source: analytics.v_branch_growth
-- Decision: trigger a root-cause review (traffic, staffing, stock, competition) for declining branches.
-- Note: the last-3-months comparison is volatile because vehicle sales are few and large;
--       the YTD comparison is the primary signal.
SELECT branch_name,
       trend_status,
       ROUND(ytd_revenue)        AS ytd_revenue_gel,
       ROUND(prior_ytd_revenue)  AS prior_ytd_revenue_gel,
       ytd_yoy_pct,
       ytd_orders,
       prior_ytd_orders,
       ROUND(100.0 * (ytd_orders::numeric / NULLIF(prior_ytd_orders, 0) - 1), 2) AS orders_yoy_pct,
       last_3m_yoy_pct
FROM analytics.v_branch_growth
ORDER BY ytd_yoy_pct;
