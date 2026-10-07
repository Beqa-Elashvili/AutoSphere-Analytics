"""Pipeline run log and quarantine of rejected rows (audit schema)."""
from __future__ import annotations

import json

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.load.staging_loader import copy_frame


def start_run(engine: Engine, pipeline_name: str, triggered_by: str) -> int:
    """Record the run start in its own committed transaction, so failures stay visible."""
    with engine.begin() as conn:
        return conn.execute(
            text("INSERT INTO audit.pipeline_runs (pipeline_name, triggered_by) "
                 "VALUES (:p, :t) RETURNING run_id"),
            {"p": pipeline_name, "t": triggered_by},
        ).scalar_one()


def finish_run(engine: Engine, run_id: int, status: str, rows_loaded: dict | None = None,
               error: str | None = None) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE audit.pipeline_runs SET finished_at = now(), status = :s, "
                 "rows_loaded = CAST(:r AS JSONB), error_message = :e WHERE run_id = :id"),
            {"s": status, "r": json.dumps(rows_loaded) if rows_loaded else None,
             "e": error[:2000] if error else None, "id": run_id},
        )


def write_rejected_rows(conn, run_id: int, rejected: dict[str, pd.DataFrame]) -> int:
    """Quarantine rejected rows with their reason and the original raw record (JSONB)."""
    frames = [
        pd.DataFrame({
            "run_id": run_id,
            "source_table": table,
            "record_key": df.record_key.values,
            "reason": df.reason.values,
            "raw_record": [json.dumps(r, ensure_ascii=False) for r in df.raw_record],
        })
        for table, df in rejected.items() if not df.empty
    ]
    if not frames:
        return 0
    with conn.cursor() as cur:
        return copy_frame(cur, "audit.rejected_rows", pd.concat(frames, ignore_index=True))
