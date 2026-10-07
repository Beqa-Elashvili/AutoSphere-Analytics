-- Business question: How is the customer base segmented, and where is the revenue?
-- KPI: RFM segments (Recency, Frequency, Monetary quintiles via NTILE(5))
-- Source: analytics.v_customer_segments, analytics.v_purchase_frequency
-- Decision: win-back campaigns for 'At Risk', onboarding for 'New', VIP care for 'Champions'.
SELECT rfm_segment,
       customers,
       customer_share_pct,
       ROUND(revenue)             AS revenue_gel,
       revenue_share_pct,
       avg_orders,
       ROUND(avg_revenue_per_customer) AS avg_revenue_per_customer_gel,
       avg_recency_days
FROM analytics.v_customer_segments
ORDER BY revenue_share_pct DESC;
