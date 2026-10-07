-- Business question: Which service categories generate the most revenue?
-- KPI: Service Revenue, margin, share | Source: analytics.v_service_type_performance,
--      analytics.v_service_revenue_by_category
-- Decision: capacity planning (bays, technicians) and parts stocking for service.

-- By service type (work-order level)
SELECT 'service_type' AS dimension, service_type AS name,
       service_orders, ROUND(service_revenue) AS revenue_gel, avg_service_order_value,
       profit_margin_pct, order_share_pct AS share_pct
FROM analytics.v_service_type_performance
UNION ALL
-- By category of what was sold in service (labour vs part categories), all years
SELECT 'line_category', category_name,
       NULL, ROUND(sum(service_revenue)), NULL,
       ROUND(100 * sum(service_profit) / NULLIF(sum(service_revenue), 0), 2),
       ROUND(100 * sum(service_revenue) / sum(sum(service_revenue)) OVER (), 2)
FROM analytics.v_service_revenue_by_category
GROUP BY category_name
ORDER BY dimension DESC, revenue_gel DESC;
