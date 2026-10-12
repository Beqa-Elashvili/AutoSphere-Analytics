# Testing and Validation

Three levels of evidence that the platform works:

| Level | Command | What it proves | Time |
|-------|---------|----------------|------|
| **Unit and component tests** (offline) | `pytest -m "not db"` | Rules, transformations, generator, AI client behaviour, alert logic, documentation consistency. No database or API needed. Runs in CI on every push. | ~20 s |
| **Integration tests** (database) | `pytest` | The same plus SQL against PostgreSQL: schema, loads, rollback, warehouse, KPI reconciliation, Power BI layer, reports | ~3 min |
| **End-to-end acceptance** | `python scripts/validate_end_to_end.py` | One run of the whole platform, followed through every layer, with a PASS/FAIL checklist and evidence | ~3 min (`--skip-pipeline`: ~30 s) |

```powershell
pytest -m "not db"                       # offline: 167 passed, DB tests deselected
pytest                                   # full: 238 passed (needs DATABASE_URL)
pytest --cov=common --cov=datagen --cov=etl --cov=ai --cov=reporting   # with coverage (89%)
python scripts/validate_end_to_end.py    # 16/16 checks, writes reports/e2e_validation.md
```

**Nothing in the test suite spends money or changes business data.** Gemini is replaced by a
fake client. Database tests that write run inside a transaction that is rolled back, or they
check that a failed load rolled back. The one test that records an audit row uses the
pipeline name `autosphere_tests`, so reports and dashboards ignore it.

## Test pyramid

```
                 ┌─────────────────────────┐
                 │ end-to-end (16 checks)  │  validate_end_to_end.py · test_end_to_end.py
              ┌──┴─────────────────────────┴──┐
              │ integration (71 DB tests)     │  SQL against PostgreSQL, always rolled back
         ┌────┴───────────────────────────────┴────┐
         │ unit / component (167 offline tests)    │  pure Python, fake Gemini, no network
         └─────────────────────────────────────────┘
```

## What each test file covers

| File | Tests (collected) | Covers |
|------|------:|--------|
| `test_config.py` | 19 | Settings resolution, aliases, AI mode selection, secret masking, invalid values |
| `test_data_generation.py` | 23 | Volumes, reproducibility (same seed = same data), referential integrity, business-time rules, injected defects, **no real company names** |
| `test_etl.py` | 36 | Normalizers (cities, dates, numbers), schema contract, every cleaning rule, row reconciliation, staging load, **rollback of a failed load** |
| `test_data_quality.py` | 15 | Severity gating, thresholds, rule catalog, **every one of the 38 injected defect types is detected**, pipeline stops on a broken source, rollback |
| `test_database.py` | 17 | Schema objects exist, setup is idempotent, CHECK constraints reject bad data |
| `test_warehouse.py` | 13 | Grain, measures, unknown members, SCD Type 2 point-in-time lookups, idempotent rebuild with stable keys |
| `test_analytics.py` | 37 | Every KPI computed **three independent ways** (view, stand-alone SQL, pandas) and compared; YTD windows; partial-year guard; shares sum to 100% |
| `test_ai.py` | 37 | Bilingual classifier, label contract, Gemini behaviour with a fake client (invalid answers, batch failure, 429 retry, batching, cost budget), evaluation metrics, warehouse lineage, anomaly detection, insight cache |
| `test_powerbi.py` | 16 | Every DAX measure reference is defined, every `Table[column]` exists in the `bi` views, relationships valid, reference values = SQL KPIs |
| `test_reporting.py` | 20 | Alert rules, HTML escaping, failure banner, lock, retry only on connection errors, exit codes, report from live data |
| `test_end_to_end.py` | 2 | The full acceptance checklist passes on the current database |
| `test_journey.py` | 2 | Data Journey page: bilingual, offline, injection-safe; its numbers reconcile with the data |

## Coverage of the required test areas

| Required area | Where it is tested |
|---------------|--------------------|
| Data generation | `test_data_generation.py` (realism, integrity, reproducibility, defects) |
| Transformations | `test_etl.py` (normalizers, cleaners), `test_warehouse.py` (SQL transforms) |
| Data-quality rules | `test_data_quality.py`, warehouse/analytics/bi checks in `test_warehouse.py`, `test_powerbi.py` |
| ETL logic | `test_etl.py` (extract → clean → load, reconciliation, transactions) |
| Analytical calculations | `test_analytics.py` (three-way reconciliation of every KPI) |
| AI fallback | `test_ai.py` (`test_valid_model_answers_are_used_and_invalid_or_missing_ones_fall_back`, `test_failed_request_falls_back_for_the_whole_batch`, `test_rate_limit_is_retried_with_backoff`) |
| Critical business rules | see below |

### Critical business rules and the test that guards each

| Business rule | Test |
|---------------|------|
| Revenue counts only completed sales | `test_headline_kpis_match_independent_queries`, `bi_checks.reconcile_revenue` |
| Average order value divides by orders, not lines | `test_aov_divides_by_orders_not_lines` |
| Growth compares identical calendar windows (YTD) | `test_ytd_compares_identical_calendar_windows` |
| A partial year never shows annual growth | `test_partial_year_has_no_misleading_annual_growth` |
| No row is lost: raw = staging + quarantine | `test_no_rows_are_lost_unaccounted`, end-to-end lineage check |
| Sales with unknown master data are kept (Unknown member), not dropped | `test_master_data_gaps_map_to_unknown_instead_of_losing_sales` |
| Historical customer attributes are used for historical sales (SCD2) | `test_scd2_creates_versions_and_facts_use_point_in_time_lookup` |
| A failed load never replaces good data | `test_failed_load_keeps_previous_staging_data` |
| Warranty work is free of charge | `test_warranty_work_is_free_of_charge` |
| Customers never buy before registering | `test_customers_never_buy_before_registering` |
| Customer contact data never reaches the report layer | `test_customer_dimension_has_no_contact_data`, `bi_checks.no_pii_columns` |
| The scheduled job never spends API credit by default | `test_scheduled_job_defaults_to_free_local_ai` |

## Code coverage

`pytest --cov=...` on the full suite: **89%** of 2,400 statements.

| Area | Coverage | Note |
|------|---------:|------|
| `etl/transform/cleaners.py`, `datagen/*`, `reporting/*` | 95–100% | |
| `etl/validation/checks.py`, `rules.py` | 90–99% | |
| `ai/classification/*` | 95–98% | |
| `etl/pipeline.py`, `ai/pipeline.py`, `ai/insights.py` | 35–50% | Orchestration that runs against the live database and Gemini. It is exercised by the end-to-end validation and by every pipeline run (logged in `audit.pipeline_runs`) rather than by unit tests. |

Coverage is a guide, not a goal: the tests above check **business outcomes** (numbers
reconcile, failures roll back), not just that lines execute.

## End-to-end acceptance checklist

`python scripts/validate_end_to_end.py` runs the pipeline in free local AI mode (cached Gemini
labels are kept), then checks:

| Layer | Check |
|-------|-------|
| Pipeline | a successful run exists |
| Lineage | raw rows = staging + quarantined (11 tables); staging = fact rows (5 facts); revenue identical in warehouse, KPI views and Power BI layer; YTD identical in SQL and Power BI date logic |
| Data quality | 0 critical failures; quarantined rows carry a reason |
| AI | 100% of feedback labelled; fallback ≤ 2%; insight per branch + company; stored labels ≥ 90% accurate vs generator labels |
| Power BI | `bi` layer checks (unique keys, no orphan facts, totals = SQL, no PII) |
| Business | Kutaisi declining; comparable growth used (no fake partial-year decline); Batumi waiting-time anomaly |
| Reporting | management report generated with high-priority alerts |

Current result: **16/16 passed** (`reports/e2e_validation.md`).

## Continuous integration

`.github/workflows/tests.yml` runs `pytest -m "not db"` with coverage on every push and pull
request. It needs no secrets and touches no database. A red build blocks a broken change
before anyone runs it against real data.
