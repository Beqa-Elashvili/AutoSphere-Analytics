-- =============================================================================
-- 03_audit_views.sql — monitoring views over the data-quality report
-- Used for ad-hoc inspection and a data-quality page in Power BI.
-- =============================================================================

-- Latest result of every check (from the most recent run that produced a report).
CREATE OR REPLACE VIEW audit.v_latest_quality_report AS
SELECT r.run_id, p.pipeline_name, r.stage, r.severity, r.status, r.table_name, r.check_name,
       r.column_name, r.failed_rows, r.total_rows,
       ROUND(100.0 * r.failed_rows / NULLIF(r.total_rows, 0), 2) AS failed_pct,
       r.message, r.executed_at
FROM audit.data_quality_report r
JOIN audit.pipeline_runs p ON p.run_id = r.run_id
WHERE r.run_id = (SELECT max(run_id) FROM audit.data_quality_report);

-- One row per run: how many checks passed / failed at each severity (trend over time).
CREATE OR REPLACE VIEW audit.v_quality_summary_by_run AS
SELECT p.run_id, p.pipeline_name, p.status AS run_status, p.started_at,
       count(*)                                                          AS checks,
       count(*) FILTER (WHERE r.status = 'FAIL' AND r.severity = 'CRITICAL') AS critical_failures,
       count(*) FILTER (WHERE r.status = 'FAIL' AND r.severity = 'WARNING')  AS warnings,
       COALESCE(sum(r.failed_rows) FILTER (WHERE r.check_name LIKE 'rejected%%'), 0) AS rejected_rows
FROM audit.pipeline_runs p
JOIN audit.data_quality_report r ON r.run_id = p.run_id
GROUP BY p.run_id, p.pipeline_name, p.status, p.started_at;
