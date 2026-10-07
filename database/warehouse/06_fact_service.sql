-- fact_service_orders: grain = one service order; measures aggregated from its lines.
WITH items AS (
    SELECT service_order_id,
           count(*)                                                              AS item_count,
           COALESCE(sum(quantity) FILTER (WHERE item_type = 'labor'), 0)              AS labor_hours,
           COALESCE(sum(quantity * unit_price) FILTER (WHERE item_type = 'labor'), 0) AS labor_revenue,
           COALESCE(sum(quantity * unit_price) FILTER (WHERE item_type = 'part'), 0)  AS parts_revenue,
           sum(quantity * unit_cost)                                             AS total_cost
    FROM staging.service_items
    GROUP BY service_order_id
)
INSERT INTO dw.fact_service_orders (
    service_order_id, opened_date_key, closed_date_key, customer_key, vehicle_key, branch_key,
    employee_key, service_type, order_status, is_completed, is_warranty, opened_at, closed_at,
    turnaround_hours, odometer_km, item_count, labor_hours, labor_revenue, parts_revenue,
    total_revenue, total_cost, profit_amount)
SELECT o.service_order_id,
       to_char(o.opened_at, 'YYYYMMDD')::int,
       CASE WHEN o.closed_at IS NOT NULL THEN to_char(o.closed_at, 'YYYYMMDD')::int END,
       COALESCE(c.customer_key, -1),
       COALESCE(v.vehicle_key, -1),
       COALESCE(b.branch_key, -1),
       COALESCE(e.employee_key, -1),
       o.service_type,
       o.order_status,
       o.order_status = 'completed',
       o.service_type = 'warranty',
       o.opened_at,
       o.closed_at,
       ROUND(extract(epoch FROM o.closed_at - o.opened_at) / 3600.0, 2),
       o.odometer_km,
       COALESCE(i.item_count, 0),
       COALESCE(i.labor_hours, 0),
       ROUND(COALESCE(i.labor_revenue, 0), 2),
       ROUND(COALESCE(i.parts_revenue, 0), 2),
       ROUND(COALESCE(i.labor_revenue, 0) + COALESCE(i.parts_revenue, 0), 2),
       ROUND(COALESCE(i.total_cost, 0), 2),
       ROUND(COALESCE(i.labor_revenue, 0) + COALESCE(i.parts_revenue, 0) - COALESCE(i.total_cost, 0), 2)
FROM staging.service_orders o
LEFT JOIN items i           ON i.service_order_id = o.service_order_id
LEFT JOIN dw.dim_customer c ON c.customer_id = o.customer_id
                           AND o.opened_at::date BETWEEN c.valid_from AND c.valid_to
LEFT JOIN dw.dim_vehicle v  ON v.vehicle_id = o.vehicle_id
LEFT JOIN dw.dim_branch b   ON b.branch_id = o.branch_id
LEFT JOIN dw.dim_employee e ON e.employee_id = o.employee_id;

-- fact_service_items: grain = one labour or part line. Labour lines use the
-- 'not applicable' product/category members (-2).
INSERT INTO dw.fact_service_items (
    service_item_id, service_order_id, date_key, customer_key, vehicle_key, product_key, category_key,
    branch_key, service_type, item_type, order_status, is_revenue_recognized, quantity, unit_price,
    unit_cost, revenue_amount, cost_amount, profit_amount)
SELECT i.service_item_id,
       i.service_order_id,
       f.opened_date_key,
       f.customer_key,
       f.vehicle_key,
       CASE WHEN i.item_type = 'labor' THEN -2 ELSE COALESCE(p.product_key, -1) END,
       CASE WHEN i.item_type = 'labor' THEN -2 ELSE COALESCE(cat.category_key, -1) END,
       f.branch_key,
       f.service_type,
       i.item_type,
       f.order_status,
       f.is_completed,
       i.quantity,
       i.unit_price,
       i.unit_cost,
       ROUND(i.quantity * i.unit_price, 2),
       ROUND(i.quantity * i.unit_cost, 2),
       ROUND(i.quantity * (i.unit_price - i.unit_cost), 2)
FROM staging.service_items i
JOIN dw.fact_service_orders f   ON f.service_order_id = i.service_order_id
LEFT JOIN dw.dim_product p      ON p.product_id = i.product_id
LEFT JOIN staging.products sp   ON sp.product_id = i.product_id
LEFT JOIN dw.dim_category cat   ON cat.category_id = sp.category_id;
