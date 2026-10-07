-- =============================================================================
-- 01_audit.sql — pipeline observability and data quality tables
-- =============================================================================

-- One row per pipeline execution. Every DQ result and rejected row links here,
-- so any number on a dashboard can be traced back to the run that produced it.
CREATE TABLE IF NOT EXISTS audit.pipeline_runs (
    run_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_name  TEXT        NOT NULL,
    triggered_by   TEXT        NOT NULL DEFAULT 'manual',   -- manual | scheduler | ci
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ,
    status         TEXT        NOT NULL DEFAULT 'running'
                   CHECK (status IN ('running', 'success', 'failed')),
    rows_loaded    JSONB,                                   -- {"staging.sales": 31250, ...}
    error_message  TEXT,
    CHECK (finished_at IS NULL OR finished_at >= started_at)
);

-- The data quality report: one row per check per run.
--   stage = 'source'    -> checks on raw files before cleaning (expected to find issues)
--   stage = 'post_load' -> checks on loaded staging/warehouse tables (must pass)
CREATE TABLE IF NOT EXISTS audit.data_quality_report (
    check_result_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id          BIGINT REFERENCES audit.pipeline_runs (run_id) ON DELETE CASCADE,
    stage           TEXT        NOT NULL CHECK (stage IN ('source', 'post_load')),
    check_name      TEXT        NOT NULL,
    table_name      TEXT        NOT NULL,
    column_name     TEXT,
    status          TEXT        NOT NULL CHECK (status IN ('PASS', 'FAIL')),
    severity        TEXT        NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL')),
    failed_rows     INTEGER     NOT NULL DEFAULT 0 CHECK (failed_rows >= 0),
    total_rows      INTEGER              CHECK (total_rows IS NULL OR total_rows >= 0),
    message         TEXT,
    executed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_dq_report_run   ON audit.data_quality_report (run_id);
CREATE INDEX IF NOT EXISTS ix_dq_report_check ON audit.data_quality_report (table_name, check_name);

-- Quarantine: rows removed during cleaning, with the reason and the original record.
-- Nothing is silently dropped — every rejected row can be inspected and explained.
CREATE TABLE IF NOT EXISTS audit.rejected_rows (
    rejected_row_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id          BIGINT REFERENCES audit.pipeline_runs (run_id) ON DELETE CASCADE,
    source_table    TEXT        NOT NULL,
    record_key      TEXT,                     -- business key of the rejected row, if any
    reason          TEXT        NOT NULL,     -- e.g. 'orphan_customer_id', 'negative_quantity'
    raw_record      JSONB       NOT NULL,     -- original values exactly as received
    rejected_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_rejected_rows_run    ON audit.rejected_rows (run_id);
CREATE INDEX IF NOT EXISTS ix_rejected_rows_reason ON audit.rejected_rows (source_table, reason);
