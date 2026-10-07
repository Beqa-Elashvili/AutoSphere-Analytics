"""Persist and summarize data-quality results (audit.data_quality_report)."""
from __future__ import annotations

from collections import Counter

import pandas as pd
from sqlalchemy.engine import Engine

from etl.load.staging_loader import copy_frame
from etl.validation.checks import CheckResult

REPORT_COLUMNS = ["run_id", "stage", "check_name", "table_name", "column_name", "status", "severity",
                  "failed_rows", "total_rows", "message", "executed_at"]


def write_report(engine: Engine, run_id: int, results: list[CheckResult]) -> int:
    """Write results in their own transaction (so they survive a rolled-back load), via COPY."""
    if not results:
        return 0
    df = pd.DataFrame([{**r.as_row(), "run_id": run_id} for r in results])[REPORT_COLUMNS]
    df["total_rows"] = df["total_rows"].astype("Int64")
    df["executed_at"] = pd.to_datetime(df["executed_at"], utc=True).dt.strftime("%Y-%m-%d %H:%M:%S%z")
    conn = engine.raw_connection()
    try:
        with conn.cursor() as cur:
            copy_frame(cur, "audit.data_quality_report", df)
        conn.commit()
    finally:
        conn.close()
    return len(df)


def summarize(results: list[CheckResult]) -> str:
    counts = Counter((r.status, r.severity) for r in results)
    parts = [f"{n} {status}/{severity}" for (status, severity), n in sorted(counts.items())]
    return f"{len(results)} checks: " + ", ".join(parts)


def format_table(results: list[CheckResult], only_failures: bool = False) -> str:
    rows = [r for r in results if r.status == "FAIL"] if only_failures else results
    order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    rows = sorted(rows, key=lambda r: (order[r.severity], r.stage, r.table_name, r.check_name))
    lines = [f"{'severity':9s} {'status':6s} {'stage':9s} {'table':28s} {'check':38s} {'failed':>8s}"]
    lines += [f"{r.severity:9s} {r.status:6s} {r.stage:9s} {r.table_name:28s} {r.check_name:38s} {r.failed_rows:8,d}"
              for r in rows]
    return "\n".join(lines) if rows else "(none)"
