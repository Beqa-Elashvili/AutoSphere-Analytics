-- Business question: Which branch generates the most revenue (and profit) this year?
-- KPI: Revenue, Profit, Profit Margin, Revenue share | Source: analytics.v_branch_performance
-- Decision: where to invest (stock, staff) and which branches to benchmark against.
SELECT sales_revenue_rank AS rank,
       branch_name,
       city,
       ROUND(sales_revenue)   AS sales_revenue_gel,
       ROUND(sales_profit)    AS sales_profit_gel,
       sales_margin_pct,
       revenue_share_pct,
       orders,
       avg_order_value,
       ROUND(total_revenue)   AS sales_plus_service_gel
FROM analytics.v_branch_performance
WHERE year = (SELECT current_year FROM analytics.v_data_period)
  AND branch_type <> 'service_only'
ORDER BY sales_revenue_rank;
