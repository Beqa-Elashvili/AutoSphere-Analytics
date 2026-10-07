-- Business question: Which products are the most profitable?
-- KPI: Profit, Profit Margin, Revenue | Source: analytics.v_product_performance
-- Decision: protect availability and promotion of profit drivers; review pricing of low-margin volume items.
SELECT profit_rank,
       product_name,
       category_name,
       ROUND(profit)   AS profit_gel,
       ROUND(revenue)  AS revenue_gel,
       profit_margin_pct,
       units,
       portfolio_quadrant
FROM analytics.v_product_performance
ORDER BY profit_rank
LIMIT 10;
