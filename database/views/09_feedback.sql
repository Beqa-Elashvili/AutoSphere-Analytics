-- =============================================================================
-- 09_feedback.sql — AI customer-feedback analytics (sentiment, topics, anomalies)
-- Labels come from the NLP step (dw.feedback_classification -> fact_customer_feedback).
-- =============================================================================

CREATE OR REPLACE VIEW analytics.v_feedback AS
SELECT f.feedback_id,
       d.full_date AS feedback_date, d.year, d.quarter_number,
       d.year || '-Q' || d.quarter_number                AS year_quarter,
       d.year_month,
       b.branch_id, b.branch_name, b.city,
       f.feedback_source, f.channel, f.rating, f.feedback_text,
       f.language, f.sentiment, f.topic, f.confidence, f.classification_method,
       (f.sentiment = 'negative')::int                   AS is_negative
FROM dw.fact_customer_feedback f
JOIN dw.dim_date d   ON d.date_key = f.date_key
JOIN dw.dim_branch b ON b.branch_key = f.branch_key;

-- Sentiment distribution per branch (all time and current year).
CREATE OR REPLACE VIEW analytics.v_sentiment_by_branch AS
SELECT branch_id, branch_name, city,
       count(*)                                                                     AS feedback_count,
       ROUND(100.0 * avg((sentiment = 'positive')::int), 2)                         AS positive_pct,
       ROUND(100.0 * avg((sentiment = 'neutral')::int), 2)                          AS neutral_pct,
       ROUND(100.0 * avg(is_negative), 2)                                           AS negative_rate_pct,
       ROUND(100.0 * avg(is_negative) FILTER (WHERE year = (SELECT max(year) FROM analytics.v_feedback)), 2)
                                                                                    AS negative_rate_current_year_pct,
       ROUND(avg(rating), 2)                                                        AS avg_rating,
       RANK() OVER (ORDER BY avg(is_negative) DESC)                                 AS negative_rate_rank
FROM analytics.v_feedback
GROUP BY branch_id, branch_name, city;

-- Sentiment per topic.
CREATE OR REPLACE VIEW analytics.v_sentiment_by_topic AS
SELECT topic,
       count(*)                                                        AS feedback_count,
       sum(is_negative)                                                AS negative_count,
       ROUND(100.0 * avg(is_negative), 2)                              AS negative_rate_pct,
       ROUND(100.0 * sum(is_negative) / sum(sum(is_negative)) OVER (), 2) AS share_of_all_negatives_pct,
       ROUND(avg(rating), 2)                                           AS avg_rating
FROM analytics.v_feedback
GROUP BY topic;

-- Monthly trend of feedback volume and negativity (company level).
CREATE OR REPLACE VIEW analytics.v_feedback_monthly AS
SELECT year_month, year,
       count(*)                                                              AS feedback_count,
       sum(is_negative)                                                      AS negative_count,
       ROUND(100.0 * avg(is_negative), 2)                                    AS negative_rate_pct,
       count(*) FILTER (WHERE is_negative = 1 AND topic = 'waiting_time')    AS waiting_time_complaints,
       count(*) FILTER (WHERE is_negative = 1 AND topic = 'price')           AS price_complaints,
       count(*) FILTER (WHERE is_negative = 1 AND topic = 'availability')    AS availability_complaints,
       ROUND(avg(rating), 2)                                                 AS avg_rating
FROM analytics.v_feedback
GROUP BY year_month, year;

-- Branch x topic x quarter on a complete spine (quarters without feedback count as 0),
-- with each cell compared to the branch-topic's own baseline (average of the previous
-- 4 quarters). A cell is an anomaly when negatives are at least double the baseline
-- and at least 8 cases (to ignore noise in small numbers).
CREATE OR REPLACE VIEW analytics.v_feedback_anomalies AS
WITH quarters AS (
    SELECT DISTINCT year, quarter_number FROM analytics.v_feedback
), spine AS (
    SELECT b.branch_name, t.topic, q.year, q.quarter_number
    FROM (SELECT DISTINCT branch_name FROM analytics.v_feedback) b
    CROSS JOIN (SELECT DISTINCT topic FROM analytics.v_feedback) t
    CROSS JOIN quarters q
), counts AS (
    SELECT branch_name, topic, year, quarter_number, count(*) AS feedback_count, sum(is_negative) AS negative_count
    FROM analytics.v_feedback
    GROUP BY branch_name, topic, year, quarter_number
), series AS (
    SELECT s.branch_name, s.topic, s.year, s.quarter_number,
           s.year || '-Q' || s.quarter_number                                   AS year_quarter,
           COALESCE(c.feedback_count, 0)                                        AS feedback_count,
           COALESCE(c.negative_count, 0)                                        AS negative_count
    FROM spine s
    LEFT JOIN counts c USING (branch_name, topic, year, quarter_number)
), scored AS (
    SELECT series.*,
           avg(negative_count) OVER w                                           AS baseline_negatives,
           count(*) OVER w                                                      AS baseline_quarters
    FROM series
    WINDOW w AS (PARTITION BY branch_name, topic ORDER BY year, quarter_number
                 ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING)
)
SELECT branch_name, topic, year, quarter_number, year_quarter, feedback_count, negative_count,
       ROUND(baseline_negatives, 2)                                             AS baseline_negatives,
       ROUND(negative_count / NULLIF(baseline_negatives, 0), 2)                 AS ratio_to_baseline,
       baseline_quarters >= 2
         AND negative_count >= 8
         AND negative_count >= 2 * GREATEST(baseline_negatives, 1)              AS is_anomaly
FROM scored;

-- Most common complaint topics: all time and latest quarter vs the same quarter last year.
CREATE OR REPLACE VIEW analytics.v_top_complaint_topics AS
WITH latest AS (
    SELECT year, quarter_number FROM analytics.v_feedback ORDER BY year DESC, quarter_number DESC LIMIT 1
)
SELECT f.topic,
       sum(f.is_negative)                                                         AS negative_count,
       ROUND(100.0 * sum(f.is_negative) / sum(sum(f.is_negative)) OVER (), 2)     AS share_of_negatives_pct,
       sum(f.is_negative) FILTER (WHERE f.year = l.year AND f.quarter_number = l.quarter_number)
                                                                                  AS negatives_latest_quarter,
       sum(f.is_negative) FILTER (WHERE f.year = l.year - 1 AND f.quarter_number = l.quarter_number)
                                                                                  AS negatives_same_quarter_last_year,
       RANK() OVER (ORDER BY sum(f.is_negative) DESC)                             AS complaint_rank
FROM analytics.v_feedback f CROSS JOIN latest l
WHERE f.topic <> 'other'
GROUP BY f.topic;

-- Validation signal: does the AI sentiment agree with the customer's own star rating?
CREATE OR REPLACE VIEW analytics.v_rating_vs_sentiment AS
SELECT rating, sentiment, count(*) AS feedback_count,
       CASE WHEN (rating >= 4 AND sentiment = 'positive') OR (rating <= 2 AND sentiment = 'negative')
              OR (rating = 3 AND sentiment = 'neutral') THEN 'agree'
            WHEN (rating >= 4 AND sentiment = 'negative') OR (rating <= 2 AND sentiment = 'positive')
            THEN 'contradict' ELSE 'partial' END                                  AS agreement
FROM analytics.v_feedback
WHERE rating IS NOT NULL
GROUP BY rating, sentiment;

-- Monitoring of the AI step: which method produced the labels and how confident it was.
CREATE OR REPLACE VIEW analytics.v_ai_classification_quality AS
SELECT method, model,
       count(*)                                                        AS labels,
       ROUND(100.0 * count(*) / sum(count(*)) OVER (), 2)              AS share_pct,
       ROUND(avg(confidence), 3)                                       AS avg_confidence,
       count(*) FILTER (WHERE confidence < 0.6)                        AS low_confidence_labels,
       max(classified_at)                                              AS last_classified_at
FROM dw.feedback_classification
GROUP BY method, model;

-- Latest generated insight per scope (company + each branch).
CREATE OR REPLACE VIEW analytics.v_ai_insights_latest AS
SELECT DISTINCT ON (scope, scope_value)
       scope, scope_value, period_label, insight_text, method, model, generated_at
FROM dw.feedback_insights
ORDER BY scope, scope_value, generated_at DESC;
