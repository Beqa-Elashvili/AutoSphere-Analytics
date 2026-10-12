# Requirements Mapping

How the project covers the typical responsibilities of a **BI & AI Developer**, with evidence
a reviewer can open or run. All data is synthetic and the company is fictional.

## Core responsibilities

| Business / Technical Requirement | Project Implementation | Evidence |
|----------------------------------|------------------------|----------|
| Data collection | 11 synthetic source tables (CSV) from a deterministic generator with realistic volumes, business stories and 38 injected defect types | `datagen/`, `data/README.md`, `scripts/generate_data.py` |
| Data processing | Python ETL: text extraction, schema contract, normalisation (cities, dates, numbers), cleaning rules, quarantine with reasons | `etl/extract/`, `etl/transform/`, `docs/etl.md` |
| Data Warehouse | PostgreSQL star schema: 7 dimensions, 5 facts, surrogate keys, Unknown / N/A members, SCD Type 2 customers | `database/schemas/04_dw.sql`, `database/warehouse/`, `docs/data-model.md` |
| BI | Power BI semantic layer (`bi` views), model with relationships, 8 report pages | `database/views/10_bi.sql`, `powerbi/` |
| KPI dashboards | 79 documented DAX measures incl. time intelligence; dashboard specification per page with business questions and decisions | `powerbi/dax-measures.md`, `powerbi/dashboard-spec.md` |
| Data Quality | Declarative rule framework, severities, 4 quality gates, 340 checks per run, rollback on CRITICAL, audit trail | `etl/validation/`, `docs/data-quality.md`, `audit` schema |
| ETL | 9-step pipeline with transactions, logging and run audit; hybrid ETL (Python) + ELT (SQL) | `etl/pipeline.py`, `scripts/run_pipeline.py` |
| SQL | Analytical layer: KPI views, window functions, YTD logic, RFM, percentiles, anomaly detection; 10 business-question queries | `database/views/`, `analytics/sql/`, `analytics/README.md` |
| AI/NLP | Bilingual (ka/en) sentiment and topic classification with Gemini, structured output, validation, deterministic fallback, cache, cost budget; SQL-grounded AI insights | `ai/`, `docs/ai-analytics.md` |
| Business analysis | 12 business requirements traced from question to KPI, SQL, page, decision and test; KPI dictionary | `docs/business-requirements.md`, `docs/kpi-dictionary.md` |

## Extended responsibilities

| Requirement | Project Implementation | Evidence |
|-------------|------------------------|----------|
| Automated reporting | Scheduled job (Task Scheduler / cron / GitHub Actions): refresh, HTML/Markdown management report, rule-based alerts, failure handling | `reporting/`, `scripts/scheduled_run.py`, `docs/automated-reporting.md` |
| Testing | 238 pytest tests (167 offline, 71 database), three-way KPI reconciliation, 89% coverage, CI on every push | `tests/`, `.github/workflows/tests.yml`, `docs/testing.md` |
| End-to-end validation | One command follows data from raw CSV to report: 16 PASS/FAIL checks with evidence | `scripts/validate_end_to_end.py`, `reports/e2e_validation.md` |
| AI evaluation and monitoring | Ground-truth and hand-written held-out evaluation, rating agreement, fallback share, lineage per row | `scripts/evaluate_ai.py`, `ai/eval/`, `analytics.v_ai_classification_quality` |
| Data governance and security | Secrets only in `.env`, masked connection strings, no PII in the report layer, optional read-only BI login | `.gitignore`, `common/config.py`, `database/security/` |
| Performance tuning | Batched quality checks, materialized base views, byte-order collation keys, logical (verified) FKs instead of slow enforced triggers | `etl/validation/checks.py`, `database/views/01_base.sql`, `docs/architecture.md` |
| Documentation | Architecture, data model, ETL, DQ, KPI, AI, Power BI, reporting, testing, interview guide, demo script | `docs/`, `powerbi/`, `README.md` |
| Communication with stakeholders | Plain-language business findings, management report, explanation for non-technical managers | `docs/business-requirements.md`, `docs/interview-guide.md` (Q30), `docs/demo-script.md` |

## Skills demonstrated

| Skill | Where |
|-------|-------|
| SQL (DDL, ELT, analytics, window functions, CTEs, materialized views) | `database/`, `analytics/` |
| Python (pandas, SQLAlchemy, psycopg2, dataclasses, concurrency) | `etl/`, `ai/`, `reporting/` |
| Dimensional modelling (Kimball), SCD Type 1 and 2 | `database/warehouse/`, `docs/data-model.md` |
| Power BI (model, DAX, time intelligence, RLS concept) | `powerbi/` |
| Data quality engineering | `etl/validation/`, `docs/data-quality.md` |
| Applied LLMs (structured output, evaluation, cost control, fallback) | `ai/` |
| Testing and CI | `tests/`, `.github/workflows/` |
| Business analysis and KPI design | `docs/business-requirements.md`, `docs/kpi-dictionary.md` |
