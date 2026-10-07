"""ETL pipeline orchestration.

    1 Extract + schema contract
    2 Clean, normalize, validate
    3 Source data-quality gate        (CRITICAL -> stop before loading)
    4 Write processed files
    5 Load staging + quarantine + post-load DQ checks, all in ONE transaction
                                      (CRITICAL -> rollback: dashboards keep the last good data)
    6 Build the star schema (ELT in SQL) + warehouse checks, in ONE transaction
                                      (CRITICAL -> rollback: the warehouse keeps the last good build)
    -> data-quality report is always written to audit.data_quality_report
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from common.config import PROJECT_ROOT
from common.logging_config import get_logger
from etl.extract.csv_extractor import SchemaValidationError, extract_all
from etl.load.audit import finish_run, start_run, write_rejected_rows
from etl.load.staging_loader import load_staging
from etl.load.warehouse_loader import build_warehouse
from etl.sources import SOURCE_COLUMNS
from etl.transform.cleaners import CleanResult, clean_all
from etl.validation.checks import CheckResult, raise_on_critical, run_checks
from etl.validation.report import summarize, write_report
from etl.validation.rules import (
    post_load_checks, schema_contract_result, source_stage_results, warehouse_checks,
)

log = get_logger("pipeline")
PIPELINE_NAME = "autosphere_etl"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


@dataclass
class PipelineResult:
    status: str = "running"
    run_id: int | None = None
    raw_rows: dict[str, int] = field(default_factory=dict)
    results: dict[str, CleanResult] = field(default_factory=dict)
    rows_loaded: dict[str, int] = field(default_factory=dict)
    rejected_rows: int = 0
    dq_results: list[CheckResult] = field(default_factory=list)
    duration_s: float = 0.0


class _Step:
    """Context manager that logs a pipeline step and its duration."""

    def __init__(self, number: int, name: str):
        self.number, self.name = number, name

    def __enter__(self):
        self.start = time.time()
        log.info("[%d] %s ...", self.number, self.name)
        return self

    def __exit__(self, exc_type, *_):
        if exc_type is None:
            log.info("[%d] %s done in %.1fs", self.number, self.name, time.time() - self.start)


def write_processed(results: dict[str, CleanResult], out_dir: Path = PROCESSED_DIR) -> None:
    """Persist cleaned data and rejected rows as CSV, for inspection without the database."""
    (out_dir / "clean").mkdir(parents=True, exist_ok=True)
    (out_dir / "rejected").mkdir(parents=True, exist_ok=True)
    for table, r in results.items():
        r.clean.to_csv(out_dir / "clean" / f"{table}.csv", index=False, encoding="utf-8")
        if not r.rejected.empty:
            expanded = pd.concat([r.rejected[["reason"]], pd.DataFrame(list(r.rejected.raw_record))], axis=1)
            expanded.to_csv(out_dir / "rejected" / f"{table}.csv", index=False, encoding="utf-8")
        else:
            (out_dir / "rejected" / f"{table}.csv").unlink(missing_ok=True)


def _extract(raw_dir: Path, result: PipelineResult):
    try:
        extracted = extract_all(raw_dir)
    except SchemaValidationError as exc:
        result.dq_results.append(schema_contract_result(exc.table, str(exc)))
        raise
    result.dq_results += [schema_contract_result(t, None) for t in SOURCE_COLUMNS]
    for warning in extracted.warnings:
        log.warning(warning)
    result.raw_rows = {t: len(df) for t, df in extracted.data.items()}
    log.info("Extracted %s rows from %d files", f"{sum(result.raw_rows.values()):,}", len(extracted.data))
    return extracted


def _load_and_verify(engine, result: PipelineResult, as_of: date) -> None:
    """Load staging and run post-load checks in one transaction; roll back on CRITICAL."""
    conn = engine.raw_connection()
    try:
        result.rows_loaded = load_staging(conn, {t: r.clean for t, r in result.results.items()})
        result.rejected_rows = write_rejected_rows(
            conn, result.run_id, {t: r.rejected for t, r in result.results.items()})
        with conn.cursor() as cur:
            post = run_checks(cur, post_load_checks(), as_of, stage="post_load")
        result.dq_results += post
        log.info("Post-load checks: %s", summarize(post))
        raise_on_critical(post)
        conn.commit()
    except Exception:
        conn.rollback()
        log.error("Load rolled back - staging still holds the previous successful load")
        raise
    finally:
        conn.close()
    log.info("Loaded %s rows into staging, quarantined %s rows",
             f"{sum(result.rows_loaded.values()):,}", f"{result.rejected_rows:,}")


def _build_and_verify_warehouse(engine, result: PipelineResult, as_of: date) -> None:
    """Build dimensions and facts, then reconcile against staging; roll back on CRITICAL."""
    conn = engine.raw_connection()
    try:
        counts = build_warehouse(conn, as_of)
        with conn.cursor() as cur:
            dw = run_checks(cur, warehouse_checks(), as_of, stage="post_load")
        result.dq_results += dw
        log.info("Warehouse checks: %s", summarize(dw))
        raise_on_critical(dw)
        conn.commit()
    except Exception:
        conn.rollback()
        log.error("Warehouse build rolled back - dw still holds the previous successful build")
        raise
    finally:
        conn.close()
    result.rows_loaded.update(counts)
    log.info("Warehouse: %s", ", ".join(f"{t.split('.')[1]}={n:,}" for t, n in counts.items()))


def run_pipeline(raw_dir: Path = RAW_DIR, as_of: date | None = None, load: bool = True,
                 triggered_by: str = "manual", engine=None) -> PipelineResult:
    as_of = as_of or date.today()
    result = PipelineResult()
    started = time.time()

    if load:
        from common.db import get_engine
        engine = engine or get_engine()
        result.run_id = start_run(engine, PIPELINE_NAME, triggered_by)
        log.info("Pipeline run %s started (as_of=%s, triggered_by=%s)", result.run_id, as_of, triggered_by)
    else:
        log.info("Dry run (no database writes), as_of=%s", as_of)

    error: Exception | None = None
    try:
        with _Step(1, "Extract raw files and validate schemas"):
            extracted = _extract(raw_dir, result)

        with _Step(2, "Clean, normalize and validate"):
            result.results = clean_all(extracted.data, as_of)
            for table, r in result.results.items():
                log.info("  %-18s raw=%6d clean=%6d rejected=%5d", table, result.raw_rows[table],
                         len(r.clean), len(r.rejected))

        with _Step(3, "Source data-quality gate"):
            source = source_stage_results(result.results, result.raw_rows)
            result.dq_results += source
            log.info("Source checks: %s", summarize(source))
            raise_on_critical(source)

        with _Step(4, "Write processed files"):
            write_processed(result.results)

        if load:
            with _Step(5, "Load staging + quarantine + post-load checks (single transaction)"):
                _load_and_verify(engine, result, as_of)
            with _Step(6, "Build star schema + warehouse checks (single transaction)"):
                _build_and_verify_warehouse(engine, result, as_of)

        result.status = "success"
    except Exception as exc:
        error = exc
        result.status = "failed"
        log.error("Pipeline failed: %s: %s", type(exc).__name__, exc)
    finally:
        result.duration_s = time.time() - started
        if load and result.run_id is not None:
            try:
                write_report(engine, result.run_id, result.dq_results)
            except Exception as report_exc:  # noqa: BLE001 - never mask the original error
                log.error("Could not write data-quality report: %s", report_exc)
            finish_run(engine, result.run_id, result.status, result.rows_loaded or None,
                       f"{type(error).__name__}: {error}" if error else None)

    if error is not None:
        raise error
    log.info("Pipeline finished: %s in %.1fs", result.status, result.duration_s)
    return result
