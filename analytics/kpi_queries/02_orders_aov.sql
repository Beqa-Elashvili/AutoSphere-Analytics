-- KPI: Orders and Average Order Value (all time).
-- Orders = number of DISTINCT completed invoices (an invoice can have several lines).
-- AOV    = Revenue / Orders.  (Dividing by line count would understate AOV.)
SELECT COUNT(DISTINCT invoice_number)                                      AS orders,
       COUNT(*)                                                            AS sales_lines,
       ROUND(SUM(net_amount) / NULLIF(COUNT(DISTINCT invoice_number), 0), 2) AS avg_order_value,
       ROUND(AVG(net_amount), 2)                                           AS avg_line_value_not_aov
FROM dw.fact_sales
WHERE is_revenue_recognized;
