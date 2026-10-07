-- =============================================================================
-- 06_customer.sql — customer value, purchase frequency, RFM segmentation
-- Customers are analysed by business key (all SCD2 versions together); descriptive
-- attributes come from the CURRENT version.
-- =============================================================================

CREATE OR REPLACE VIEW analytics.v_customer_metrics AS
WITH inv AS (                              -- one row per customer order
    SELECT customer_id, invoice_number, min(sale_date) AS order_date,
           sum(revenue) AS revenue, sum(profit) AS profit
    FROM analytics.v_sales
    GROUP BY customer_id, invoice_number
), gaps AS (
    SELECT customer_id,
           order_date - LAG(order_date) OVER (PARTITION BY customer_id ORDER BY order_date, invoice_number) AS gap_days
    FROM inv
), gap_avg AS (
    SELECT customer_id, ROUND(avg(gap_days), 1) AS avg_days_between_orders FROM gaps GROUP BY customer_id
), agg AS (
    SELECT i.customer_id, count(*) AS orders, sum(i.revenue) AS revenue, sum(i.profit) AS profit,
           min(i.order_date) AS first_purchase, max(i.order_date) AS last_purchase
    FROM inv i GROUP BY i.customer_id
), scored AS (
    SELECT a.*,
           ga.avg_days_between_orders,
           p.last_date - a.last_purchase                                                     AS recency_days,
           NTILE(5) OVER (ORDER BY p.last_date - a.last_purchase DESC, a.customer_id)        AS r_score,
           NTILE(5) OVER (ORDER BY a.orders, a.customer_id)                                  AS f_score,
           NTILE(5) OVER (ORDER BY a.revenue, a.customer_id)                                 AS m_score
    FROM agg a
    JOIN gap_avg ga USING (customer_id)
    CROSS JOIN analytics.v_data_period p
)
SELECT s.customer_id, c.customer_name, c.customer_type, c.city, c.loyalty_tier,
       s.orders, s.revenue, s.profit,
       ROUND(s.revenue / s.orders, 2)                    AS avg_order_value,
       s.first_purchase, s.last_purchase, s.recency_days, s.avg_days_between_orders,
       s.orders >= 2                                     AS is_repeat_customer,
       s.r_score, s.f_score, s.m_score,
       s.r_score::text || s.f_score::text || s.m_score::text AS rfm_code,
       CASE WHEN s.r_score >= 4 AND s.f_score >= 4 THEN 'Champions'
            WHEN s.f_score >= 4                    THEN 'Loyal'
            WHEN s.r_score >= 4 AND s.orders = 1   THEN 'New'
            WHEN s.r_score <= 2 AND s.f_score >= 3 THEN 'At Risk'
            WHEN s.r_score = 1                     THEN 'Lost'
            WHEN s.r_score >= 3                    THEN 'Potential'
            ELSE 'Needs Attention' END              AS rfm_segment,
       RANK() OVER (ORDER BY s.revenue DESC)        AS revenue_rank
FROM scored s
JOIN dw.dim_customer c ON c.customer_id = s.customer_id AND c.is_current;

-- Segment summary: size, value and behaviour per RFM segment.
CREATE OR REPLACE VIEW analytics.v_customer_segments AS
SELECT rfm_segment,
       count(*)                                                        AS customers,
       ROUND(100.0 * count(*) / sum(count(*)) OVER (), 2)              AS customer_share_pct,
       sum(revenue)                                                    AS revenue,
       ROUND(100 * sum(revenue) / sum(sum(revenue)) OVER (), 2)        AS revenue_share_pct,
       ROUND(avg(orders), 2)                                           AS avg_orders,
       ROUND(avg(revenue), 2)                                          AS avg_revenue_per_customer,
       ROUND(avg(recency_days), 0)                                     AS avg_recency_days
FROM analytics.v_customer_metrics
GROUP BY rfm_segment;

-- Purchase-frequency distribution (how many customers bought 1, 2, 3, ... times).
CREATE OR REPLACE VIEW analytics.v_purchase_frequency AS
SELECT CASE WHEN orders >= 10 THEN '10+' ELSE orders::text END             AS orders_bucket,
       min(orders)                                                          AS sort_order,
       count(*)                                                             AS customers,
       ROUND(100.0 * count(*) / sum(count(*)) OVER (), 2)                   AS customer_share_pct,
       sum(revenue)                                                         AS revenue
FROM analytics.v_customer_metrics
GROUP BY 1;
