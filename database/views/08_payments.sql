-- =============================================================================
-- 08_payments.sql — payment mix and collection quality
-- =============================================================================

CREATE OR REPLACE VIEW analytics.v_payment_mix AS
SELECT d.year, p.source_type, p.payment_method,
       count(*)                                                                   AS attempts,
       count(*) FILTER (WHERE p.payment_status = 'completed')                     AS successful_payments,
       ROUND(100.0 * count(*) FILTER (WHERE p.payment_status = 'failed') / count(*), 2) AS failure_rate_pct,
       sum(p.amount) FILTER (WHERE p.payment_status = 'completed')                AS collected_amount,
       sum(p.amount) FILTER (WHERE p.payment_status = 'refunded')                 AS refunded_amount,
       sum(p.net_cash_amount)                                                     AS net_cash,
       ROUND(100 * sum(p.net_cash_amount) / NULLIF(sum(sum(p.net_cash_amount)) OVER (PARTITION BY d.year), 0), 2)
                                                                                  AS net_cash_share_pct
FROM dw.fact_payments p
JOIN dw.dim_date d ON d.date_key = p.date_key
GROUP BY d.year, p.source_type, p.payment_method;
