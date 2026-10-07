"""ETL pipeline orchestration.

    Extract -> Transform (clean + validate) -> Write processed files -> Load staging
    (+ quarantine rejected rows, + run log)

Later phases extend this with data-quality gating, warehouse loading and
analytical views. Each step is logged with its duration and row counts.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from common.config import PROJECT_ROOT
from common.logging_config import get_logger
from etl.extract.csv_extractor import extract_all
from etl.load.audit import finish_run, start_run, write_rejected_rows
from etl.load.staging_loader import load_staging
from etl.transform.cleaners import CleanResult, clean_all

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

    try:
        with _Step(1, "Extract raw files and validate schemas"):
            extracted = extract_all(raw_dir)
            for warning in extracted.warnings:
                log.warning(warning)
            result.raw_rows = {t: len(df) for t, df in extracted.data.items()}
            log.info("Extracted %s rows from %d files", f"{sum(result.raw_rows.values()):,}", len(extracted.data))

        with _Step(2, "Clean, normalize and validate"):
            result.results = clean_all(extracted.data, as_of)
            for table, r in result.results.items():
                log.info("  %-18s raw=%6d clean=%6d rejected=%5d", table, result.raw_rows[table],
                         len(r.clean), len(r.rejected))

        with _Step(3, "Write processed files"):
            write_processed(result.results)

        if load:
            with _Step(4, "Load staging + quarantine rejected rows (single transaction)"):
                conn = engine.raw_connection()
                try:
                    result.rows_loaded = load_staging(conn, {t: r.clean for t, r in result.results.items()})
                    result.rejected_rows = write_rejected_rows(
                        conn, result.run_id, {t: r.rejected for t, r in result.results.items()})
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    conn.close()
                log.info("Loaded %s rows into staging, quarantined %s rows",
                         f"{sum(result.rows_loaded.values()):,}", f"{result.rejected_rows:,}")

        result.status = "success"
    except Exception as exc:
        result.status = "failed"
        log.exception("Pipeline failed: %s", exc)
        if load and result.run_id is not None:
            finish_run(engine, result.run_id, "failed", result.rows_loaded or None, f"{type(exc).__name__}: {exc}")
        raise
    finally:
        result.duration_s = time.time() - started

    if load:
        finish_run(engine, result.run_id, "success", result.rows_loaded)
    log.info("Pipeline finished: %s in %.1fs", result.status, result.duration_s)
    return result
