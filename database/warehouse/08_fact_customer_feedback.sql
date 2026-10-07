-- fact_customer_feedback: grain = one feedback submission.
-- AI columns come from the persisted classification cache (dw.feedback_classification),
-- filled by the NLP step that runs before the warehouse build. The text hash join
-- guarantees a label is only used for the exact text it was produced from.
INSERT INTO dw.fact_customer_feedback (
    feedback_id, date_key, customer_key, branch_key, service_order_id, invoice_number,
    feedback_source, channel, rating, feedback_text,
    language, sentiment, topic, confidence, classification_method)
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
       f.feedback_text,
       ai.language,
       ai.sentiment,
       ai.topic,
       ai.confidence,
       ai.method || ':' || ai.model
FROM staging.customer_feedback f
LEFT JOIN dw.dim_customer c ON c.customer_id = f.customer_id
                           AND f.feedback_date BETWEEN c.valid_from AND c.valid_to
LEFT JOIN dw.dim_branch b   ON b.branch_id = f.branch_id
LEFT JOIN dw.feedback_classification ai
       ON ai.feedback_id = f.feedback_id AND ai.text_hash = md5(f.feedback_text);
