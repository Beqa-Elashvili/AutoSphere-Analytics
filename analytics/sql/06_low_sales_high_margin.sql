-- Business question: Which products have low sales but high margin?
-- KPI: Revenue vs Profit Margin compared with peer-group medians | Source: analytics.v_product_performance
-- Decision: candidates for cross-selling, better shelf placement or bundling with service visits.
SELECT product_name,
       category_name,
       ROUND(revenue)  AS revenue_gel,
       revenue_rank,
       profit_margin_pct,
       margin_rank,
       units
FROM analytics.v_product_performance
WHERE portfolio_quadrant LIKE 'Niche%'
ORDER BY profit_margin_pct DESC;
