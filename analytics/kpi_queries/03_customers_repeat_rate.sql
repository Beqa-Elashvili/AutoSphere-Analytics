-- KPI: Customer Count and Repeat Customer Rate (all time).
-- Customer Count = distinct customers (business key) with at least one completed order.
-- Repeat Rate    = customers with 2+ completed orders / Customer Count.
-- The business key comes from dim_customer, so SCD2 versions of one customer count once.
WITH orders_per_customer AS (
    SELECT c.customer_id, COUNT(DISTINCT f.invoice_number) AS orders
    FROM dw.fact_sales f
    JOIN dw.dim_customer c ON c.customer_key = f.customer_key
    WHERE f.is_revenue_recognized
    GROUP BY c.customer_id
)
SELECT COUNT(*)                                                   AS customer_count,
       COUNT(*) FILTER (WHERE orders >= 2)                        AS repeat_customers,
       ROUND(100.0 * COUNT(*) FILTER (WHERE orders >= 2) / NULLIF(COUNT(*), 0), 2) AS repeat_customer_rate_pct
FROM orders_per_customer;
