-- =============================================================================
-- 00_schemas.sql — database namespaces (layers of the platform)
-- Idempotent: safe to run repeatedly.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS dw;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS bi;

COMMENT ON SCHEMA staging   IS 'Cleaned, typed, de-duplicated source data keyed by business (natural) keys. Rebuilt on every pipeline run.';
COMMENT ON SCHEMA dw        IS 'Analytical data warehouse: star schema with surrogate-keyed dimensions and fact tables.';
COMMENT ON SCHEMA analytics IS 'Reusable KPI and reporting views consumed by Power BI and automated reports.';
COMMENT ON SCHEMA audit     IS 'Operational metadata: pipeline runs, data quality results, quarantined (rejected) rows.';
COMMENT ON SCHEMA bi        IS 'Power BI semantic layer: the only objects the report imports (stable, privacy-filtered views).';
