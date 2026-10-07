-- fact_customer_feedback: grain = one feedback submission.
-- AI columns (language, sentiment, topic, confidence, classification_method) stay NULL
-- here; the NLP pipeline (Phase 8) enriches them.
INSERT INTO dw.fact_customer_feedback (
    feedback_id, date_key, customer_key, branch_key, service_order_id, invoice_number,
    feedback_source, channel, rating, feedback_text)
SELECT f.feedback_id,
       to_char(f.feedback_date, 'YYYYMMDD')::int,
       COALESCE(c.customer_key, -1),
       COALESCE(b.branch_key, -1),
       f.service_order_id,
       f.invoice_number,
       CASE WHEN f.service_order_id IS NOT NULL THEN 'service'
            WHEN f.invoice_number IS NOT NULL   THEN 'sale'
            ELSE 'general' END,
       f.channel,
       f.rating,
       f.feedback_text
FROM staging.customer_feedback f
LEFT JOIN dw.dim_customer c ON c.customer_id = f.customer_id
                           AND f.feedback_date BETWEEN c.valid_from AND c.valid_to
LEFT JOIN dw.dim_branch b   ON b.branch_id = f.branch_id;
