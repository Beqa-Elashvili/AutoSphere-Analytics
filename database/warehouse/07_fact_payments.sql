-- fact_payments: grain = one payment attempt. The branch is inherited from the paid
-- invoice or service order. net_cash_amount: completed +, refunded -, failed 0.
WITH invoice_branch AS (
    SELECT DISTINCT ON (invoice_number) invoice_number, branch_id
    FROM staging.sales
    ORDER BY invoice_number, sale_line_id
)
INSERT INTO dw.fact_payments (
    payment_id, date_key, customer_key, branch_key, source_type, source_reference, payment_datetime,
    payment_method, payment_status, is_successful, amount, net_cash_amount)
SELECT p.payment_id,
       to_char(p.payment_datetime, 'YYYYMMDD')::int,
       COALESCE(c.customer_key, -1),
       COALESCE(b.branch_key, -1),
       p.source_type,
       p.source_reference,
       p.payment_datetime,
       p.payment_method,
       p.payment_status,
       p.payment_status = 'completed',
       p.amount,
       CASE p.payment_status WHEN 'completed' THEN p.amount
                             WHEN 'refunded'  THEN -p.amount
                             ELSE 0 END
FROM staging.payments p
LEFT JOIN invoice_branch ib        ON p.source_type = 'sale' AND ib.invoice_number = p.source_reference
LEFT JOIN staging.service_orders o ON p.source_type = 'service' AND o.service_order_id = p.source_reference
LEFT JOIN dw.dim_branch b          ON b.branch_id = COALESCE(ib.branch_id, o.branch_id)
LEFT JOIN dw.dim_customer c        ON c.customer_id = p.customer_id
                                  AND p.payment_datetime::date BETWEEN c.valid_from AND c.valid_to;
