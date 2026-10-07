"""Data-quality framework tests: rule logic, severity gating, defect detection, rollback."""
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from common.config import PROJECT_ROOT
from datagen.corrupt import inject_quality_issues
from datagen.generate import generate_clean_datasets
from etl.pipeline import run_pipeline
from etl.sources import BUSINESS_KEYS
from etl.transform.cleaners import CleanResult, clean_all
from etl.validation.checks import (
    BATCH_SEPARATOR, CRITICAL, INFO, SEVERITIES, WARNING, Check, DataQualityError, critical_failures, foreign_key,
    not_null, raise_on_critical, run_checks, unique,
)
from etl.validation.rules import (
    REJECTION_RATE_CRITICAL, post_load_checks, source_stage_results,
)

AS_OF = date(2026, 10, 7)


# ---------------------------------------------------------------- runner logic (no database)
class FakeCursor:
    """Answers a batched check query: preset violation counts per check, fixed table sizes."""

    def __init__(self, violations: dict[str, int], total: int = 1000):
        self.violations, self.total, self.row = violations, total, None

    def execute(self, sql, params=None):
        assert sql.startswith("SELECT ")
        values = []
        for expr in sql[len("SELECT "):].split(BATCH_SEPARATOR):
            if expr.startswith("(SELECT count(*) FROM ") and " WHERE " not in expr and "GROUP BY" not in expr:
                values.append(self.total)
            else:
                values.append(next(v for k, v in self.violations.items() if k in expr))
        self.row = tuple(values)

    def fetchone(self):
        return self.row


def test_any_violation_fails_a_strict_check():
    chk = Check("c", "t", CRITICAL, "SELECT count(*) FROM t WHERE x < 0")
    [r] = run_checks(FakeCursor({"x < 0": 1}), [chk], AS_OF)
    assert (r.status, r.failed_rows, r.total_rows) == ("FAIL", 1, 1000)
    assert r.is_critical_failure


def test_completeness_check_tolerates_failures_below_threshold():
    chk = not_null("t", "email", WARNING, max_failed_ratio=0.10)
    ok, = run_checks(FakeCursor({"email IS NULL": 99}), [chk], AS_OF)
    bad, = run_checks(FakeCursor({"email IS NULL": 101}), [chk], AS_OF)
    assert ok.status == "PASS" and bad.status == "FAIL"


def test_warning_failures_do_not_stop_the_pipeline():
    chk = Check("c", "t", WARNING, "SELECT count(*) FROM t WHERE y")
    results = run_checks(FakeCursor({"WHERE y": 5}), [chk], AS_OF)
    assert not critical_failures(results)
    raise_on_critical(results)          # must not raise


def test_critical_failure_raises_with_details():
    chk = Check("fk_x", "t", CRITICAL, "SELECT count(*) FROM t WHERE z")
    results = run_checks(FakeCursor({"WHERE z": 3}), [chk], AS_OF)
    with pytest.raises(DataQualityError, match="t.fk_x") as exc:
        raise_on_critical(results)
    assert exc.value.failures[0].failed_rows == 3


def test_builders_generate_expected_sql():
    assert "GROUP BY sale_line_id HAVING count(*) > 1" in unique("s.sales", "sale_line_id").violation_sql
    fk = foreign_key("s.sales", "customer_id", "s.customers").violation_sql
    assert "NOT EXISTS" in fk and "p.customer_id = c.customer_id" in fk and "IS NOT NULL" in fk


# ---------------------------------------------------------------- rule catalog
def test_every_staging_table_has_existence_and_key_checks():
    checks = post_load_checks()
    for table, key in BUSINESS_KEYS.items():
        names = {c.name for c in checks if c.table == f"staging.{table}"}
        assert {"row_count_minimum", f"unique_{key}", f"not_null_{key}"} <= names, table


def test_rule_catalog_is_well_formed():
    checks = post_load_checks()
    assert len(checks) >= 80
    assert all(c.severity in SEVERITIES for c in checks)
    assert len({(c.table, c.name) for c in checks}) == len(checks), "duplicate check names"


def test_transaction_references_are_critical_and_master_references_warn():
    sev = {(c.table, c.name): c.severity for c in post_load_checks()}
    assert sev[("staging.sales", "fk_customer_id")] == CRITICAL
    assert sev[("staging.payments", "fk_source_reference")] == CRITICAL
    assert sev[("staging.products", "fk_category_id")] == WARNING
    assert sev[("staging.vehicles", "fk_customer_id")] == WARNING


# ---------------------------------------------------------------- source-stage gate
def _result(table, raw, reasons):
    rejected = pd.DataFrame({"record_key": [None] * sum(reasons.values()),
                             "reason": [r for r, n in reasons.items() for _ in range(n)],
                             "raw_record": [{}] * sum(reasons.values())})
    return CleanResult(table, pd.DataFrame(), rejected, {})


def _rate_check(results, table):
    return next(r for r in results if r.table_name == table and r.check_name == "invalid_row_rate")


def test_invalid_row_rate_thresholds():
    results = source_stage_results(
        {"a": _result("a", 1000, {"negative_quantity": 5}),
         "b": _result("b", 1000, {"negative_quantity": 50}),
         "c": _result("c", 1000, {"negative_quantity": 150})},
        {"a": 1000, "b": 1000, "c": 1000})
    assert (_rate_check(results, "a").status, _rate_check(results, "a").severity) == ("PASS", INFO)
    assert (_rate_check(results, "b").status, _rate_check(results, "b").severity) == ("FAIL", WARNING)
    assert (_rate_check(results, "c").status, _rate_check(results, "c").severity) == ("FAIL", CRITICAL)


def test_duplicates_do_not_count_towards_the_invalid_rate():
    results = source_stage_results({"a": _result("a", 100, {"exact_duplicate": 50})}, {"a": 100})
    assert _rate_check(results, "a").severity == INFO


# ---------------------------------------------------------------- detection completeness
# Which source-stage check proves each injected defect type was caught.
DETECTED_BY = {
    "exact_duplicate": r"rejected_exact_duplicate",
    "duplicate_id_variant": r"rejected_duplicate_business_key",
    "duplicate_vin": r"rejected_duplicate_vin",
    "city_variant": r"fixed_city_normalized",
    "missing_city": r"fixed_city_missing_defaulted",
    "category_case_variant": r"fixed_\w+_normalized",
    "text_case_variant": r"fixed_\w+_cleaned",
    "date_format_variant": r"fixed_\w+_reformatted",
    "id_format_variant": r"fixed_\w+_id_reformatted",
    "decimal_comma": r"fixed_\w+_reformatted",
    "currency_case_variant": r"fixed_currency_normalized",
    "invalid_email": r"fixed_email_invalid_nullified",
    "missing_model_year": r"fixed_model_year_invalid_nullified",
    "rating_out_of_range": r"fixed_rating_out_of_range_nullified",
    "invalid_date": r"rejected_invalid_date|fixed_\w+_invalid_nullified",
    "future_date": r"rejected_future_date|fixed_\w+_invalid_nullified",
    "negative_amount": r"rejected_negative_amount|fixed_\w+_invalid_nullified",
}
# Kept on purpose (master-data policy) and therefore detected by post-load checks instead.
DETECTED_POST_LOAD = {
    ("products", "orphan_category_id"): "fk_category_id",
    ("employees", "orphan_branch_id"): "fk_branch_id",
    ("vehicles", "orphan_customer_id"): "fk_customer_id",
    ("customers", "missing_email"): "completeness_email",
}


@pytest.fixture(scope="module")
def generated():
    clean = generate_clean_datasets(seed=42, scale=0.05)
    raw, manifest = inject_quality_issues(clean, seed=42)
    results = clean_all(raw, AS_OF)
    return raw, manifest, source_stage_results(results, {t: len(df) for t, df in raw.items()})


def test_every_injected_defect_type_is_detected(generated):
    _, manifest, source = generated
    for table, issues in manifest.items():
        found = {r.check_name for r in source if r.table_name == table and r.failed_rows > 0}
        for issue in issues:
            if (table, issue) in DETECTED_POST_LOAD:
                continue
            pattern = DETECTED_BY.get(issue, f"rejected_{issue}")
            assert any(re.fullmatch(pattern, name) for name in found), f"{table}.{issue} not detected"


def test_pipeline_stops_before_loading_when_a_source_is_badly_broken(generated, tmp_path):
    raw, _, _ = generated
    for table, df in raw.items():
        df = df.copy()
        if table == "sales":   # simulate a broken export: 30% of quantities corrupted
            idx = df.sample(frac=0.30, random_state=1).index
            df.loc[idx, "quantity"] = "-1"
        df.to_csv(tmp_path / f"{table}.csv", index=False, encoding="utf-8")
    with pytest.raises(DataQualityError) as exc:
        run_pipeline(raw_dir=tmp_path, as_of=AS_OF, load=False)
    [failure] = exc.value.failures
    assert (failure.table_name, failure.check_name, failure.severity) == ("sales", "invalid_row_rate", CRITICAL)
    assert failure.failed_rows / failure.total_rows > REJECTION_RATE_CRITICAL


# ---------------------------------------------------------------- database
def _staging_loaded(engine) -> bool:
    with engine.connect() as c:
        return c.exec_driver_sql("SELECT count(*) FROM staging.sales").scalar() > 0


@pytest.mark.db
def test_loaded_staging_passes_all_critical_checks(engine):
    if not _staging_loaded(engine):
        pytest.skip("staging is empty - run scripts/run_pipeline.py first")
    conn = engine.raw_connection()
    try:
        with conn.cursor() as cur:
            results = run_checks(cur, post_load_checks(), AS_OF)
    finally:
        conn.rollback()
        conn.close()
    assert not critical_failures(results), [r.message for r in critical_failures(results)]


@pytest.mark.db
def test_post_load_checks_catch_injected_orphans_and_trigger_rollback(engine):
    if not _staging_loaded(engine):
        pytest.skip("staging is empty - run scripts/run_pipeline.py first")
    conn = engine.raw_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO staging.sales (sale_line_id, invoice_number, sale_datetime, customer_id, product_id,
                    branch_id, employee_id, quantity, unit_price, unit_cost, discount_amount, sales_channel, order_status)
                VALUES ('SL-TEST', 'INV-TEST', '2025-01-15 10:00', 'CUS99999', 'PRD001', 'BR01', 'EMP001',
                        1, 100, 60, 0, 'in_store', 'completed')""")
            results = run_checks(cur, post_load_checks(), AS_OF)
        failed = {(r.table_name, r.check_name): r.failed_rows for r in critical_failures(results)}
        assert failed.get(("staging.sales", "fk_customer_id")) == 1
        with pytest.raises(DataQualityError):
            raise_on_critical(results)
    finally:
        conn.rollback()
        conn.close()
    with engine.connect() as c:
        assert c.exec_driver_sql("SELECT count(*) FROM staging.sales WHERE sale_line_id='SL-TEST'").scalar() == 0


@pytest.mark.db
def test_master_data_defects_kept_by_policy_are_reported_as_warnings(engine):
    manifest_path = PROJECT_ROOT / "data" / "raw" / "_generation_manifest.json"
    if not manifest_path.exists() or not _staging_loaded(engine):
        pytest.skip("full dataset not generated/loaded")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))["tables"]
    conn = engine.raw_connection()
    try:
        with conn.cursor() as cur:
            results = run_checks(cur, post_load_checks(), AS_OF)
    finally:
        conn.rollback()
        conn.close()
    by_name = {(r.table_name, r.check_name): r for r in results}
    for (table, issue), check in DETECTED_POST_LOAD.items():
        r = by_name[(f"staging.{table}", check)]
        assert r.severity in (WARNING, INFO)
        assert r.failed_rows >= manifest[table]["injected_issues"][issue], (table, issue)
