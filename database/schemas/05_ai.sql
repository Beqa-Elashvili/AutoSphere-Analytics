-- =============================================================================
-- 05_ai.sql — persisted AI/NLP outputs
--
-- These tables are NOT rebuilt by the pipeline: model results are expensive to
-- produce, so they act as a cache keyed by feedback_id + text hash. Feedback is
-- (re)classified only when it is new, its text changed, or a better method is
-- available (external provider configured but row produced by the fallback).
-- =============================================================================

CREATE TABLE IF NOT EXISTS dw.feedback_classification (
    feedback_id    TEXT PRIMARY KEY,
    text_hash      TEXT        NOT NULL,          -- md5(feedback_text): detects edited feedback
    language       TEXT        NOT NULL CHECK (language IN ('ka', 'en', 'other')),
    sentiment      TEXT        NOT NULL CHECK (sentiment IN ('positive', 'neutral', 'negative')),
    topic          TEXT        NOT NULL CHECK (topic IN ('service_quality', 'waiting_time', 'price', 'staff',
                                                         'product_quality', 'availability', 'complaint', 'other')),
    confidence     NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    method         TEXT        NOT NULL CHECK (method IN ('gemini', 'rule_based', 'rule_based_fallback')),
    model          TEXT        NOT NULL,          -- e.g. gemini-3.5-flash | rules-v1
    classified_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_feedback_classification_method ON dw.feedback_classification (method);

-- Narrative insights for management, generated from computed facts (see ai/insights.py).
CREATE TABLE IF NOT EXISTS dw.feedback_insights (
    insight_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id         BIGINT,
    period_label   TEXT        NOT NULL,          -- e.g. '2026-Q3'
    scope          TEXT        NOT NULL CHECK (scope IN ('company', 'branch')),
    scope_value    TEXT        NOT NULL,          -- 'All branches' or branch name
    insight_text   TEXT        NOT NULL,
    facts          JSONB       NOT NULL,          -- the numbers the text was generated from (traceability)
    method         TEXT        NOT NULL,          -- gemini | template
    model          TEXT        NOT NULL,
    generated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_feedback_insights_latest ON dw.feedback_insights (scope, scope_value, generated_at DESC);
