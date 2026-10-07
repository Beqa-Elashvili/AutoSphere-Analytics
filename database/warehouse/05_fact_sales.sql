-- Facts are fully rebuilt from staging on every run (simple, always consistent with
-- staging; incremental loading is a documented scale-up option).
TRUNCATE dw.fact_service_items, dw.fact_service_orders, dw.fact_sales, dw.fact_payments,
         dw.fact_customer_feedback;

-- fact_sales: grain = one invoice line.
-- Customer lookup is point-in-time: the dim_customer version valid on the sale date.
-- category_key is carried on the fact so Power BI can filter by category in a pure star.
INSERT INTO dw.fact_sales (
    sale_line_id, invoice_number, date_key, customer_key, product_key, category_key, branch_key,
    employee_key, sale_datetime, sales_channel, order_status, is_revenue_recognized, quantity,
    unit_price, unit_cost, gross_amount, discount_amount, net_amount, cost_amount, profit_amount)
SELECT s.sale_line_id,
       s.invoice_number,
       to_char(s.sale_datetime, 'YYYYMMDD')::int,
       COALESCE(c.customer_key, -1),
       COALESCE(p.product_key, -1),
       COALESCE(cat.category_key, -1),
       COALESCE(b.branch_key, -1),
       COALESCE(e.employee_key, -1),
       s.sale_datetime,
       s.sales_channel,
       s.order_status,
       s.order_status = 'completed',
       s.quantity,
       s.unit_price,
       s.unit_cost,
       ROUND(s.quantity * s.unit_price, 2),
       s.discount_amount,
       ROUND(s.quantity * s.unit_price - s.discount_amount, 2),
       ROUND(s.quantity * s.unit_cost, 2),
       ROUND(s.quantity * s.unit_price - s.discount_amount - s.quantity * s.unit_cost, 2)
FROM staging.sales s
LEFT JOIN dw.dim_customer c
       ON c.customer_id = s.customer_id
      AND s.sale_datetime::date BETWEEN c.valid_from AND c.valid_to
LEFT JOIN dw.dim_product p           ON p.product_id = s.product_id
LEFT JOIN staging.products sp        ON sp.product_id = s.product_id
LEFT JOIN dw.dim_category cat        ON cat.category_id = sp.category_id
LEFT JOIN dw.dim_branch b            ON b.branch_id = s.branch_id
LEFT JOIN dw.dim_employee e          ON e.employee_id = s.employee_id;
