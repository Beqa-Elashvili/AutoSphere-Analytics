-- Business question: Who are our top customers and how valuable are they?
-- KPI: Customer revenue, orders, AOV, recency, RFM segment | Source: analytics.v_customer_metrics
-- Decision: key-account management; protect top customers who show signs of churn.
SELECT revenue_rank,
       customer_id,
       customer_name,
       customer_type,
       city,
       loyalty_tier,
       orders,
       ROUND(revenue)          AS revenue_gel,
       avg_order_value,
       recency_days,
       avg_days_between_orders,
       rfm_segment
FROM analytics.v_customer_metrics
ORDER BY revenue_rank
LIMIT 15;
