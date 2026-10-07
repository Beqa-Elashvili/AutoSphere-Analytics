-- KPI: Service Revenue, Service Orders, Average Service Order Value (all time).
-- Only COMPLETED service orders count (open and cancelled orders are not revenue).
SELECT SUM(total_revenue)                                         AS service_revenue,
       COUNT(*)                                                   AS service_orders,
       ROUND(SUM(total_revenue) / NULLIF(COUNT(*), 0), 2)         AS avg_service_order_value,
       ROUND(100 * SUM(labor_revenue) / NULLIF(SUM(total_revenue), 0), 2) AS labor_share_pct,
       ROUND(AVG(turnaround_hours), 1)                            AS avg_turnaround_hours
FROM dw.fact_service_orders
WHERE is_completed;
