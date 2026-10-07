"""The scheduled job: refresh the data, then publish the management report.

    1. take a lock (two overlapping runs would fight over the same tables)
    2. run the pipeline; retry once on a connection error (a transient network problem),
       never on a data-quality failure (retrying would fail the same way)
    3. generate the report - also when the pipeline failed: the database still holds the
       last good data (failed loads roll back), and the report says so in a red banner
    4. write reports/last_run.json and return an exit code the scheduler understands

Exit codes: 0 success · 1 pipeline failed (report still produced) · 2 report failed · 3 already running
"""
from __future__ import annotations

import json
import os
import shutil
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from common.config import PROJECT_ROOT, Settings, load_settings
from common.logging_config import get_logger
from reporting.alerts import build_alerts
from reporting.data import collect
from reporting.render import to_html, to_markdown

log = get_logger("reporting.job")

REPORTS_DIR = PROJECT_ROOT / "reports"
OUT_DIR = REPORTS_DIR / "management"
STATUS_FILE = REPORTS_DIR / "last_run.json"
LOCK_FILE = REPORTS_DIR / ".scheduled_run.lock"
STALE_LOCK_SECONDS = 2 * 3600
TITLE = "AutoSphere Analytics - Management Report"

EXIT_OK, EXIT_PIPELINE_FAILED, EXIT_REPORT_FAILED, EXIT_LOCKED = 0, 1, 2, 3


@dataclass
class JobStatus:
    started_at: str
    finished_at: str | None = None
    status: str = "running"            # success | pipeline_failed | report_failed | skipped_locked
    exit_code: int | None = None
    pipeline_run_id: int | None = None
    pipeline_error: str | None = None
    report_error: str | None = None
    report_html: str | None = None
    report_markdown: str | None = None
    alerts: dict[str, int] = field(default_factory=dict)


class RunLock:
    """Exclusive lock file; a lock older than STALE_LOCK_SECONDS is considered abandoned."""

    def __init__(self, path: Path = LOCK_FILE):
        self.path = path
        self.acquired = False

    def __enter__(self) -> "RunLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and time.time() - self.path.stat().st_mtime > STALE_LOCK_SECONDS:
            log.warning("Removing stale lock %s", self.path)
            self.path.unlink(missing_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            self.acquired = True
        except FileExistsError:
            self.acquired = False
        return self

    def __exit__(self, *exc) -> None:
        if self.acquired:
            self.path.unlink(missing_ok=True)


def is_connection_error(exc: BaseException) -> bool:
    import psycopg2
    from sqlalchemy.exc import OperationalError
    return isinstance(exc, (psycopg2.OperationalError, OperationalError))


def generate_report(engine, today: date, out_dir: Path = OUT_DIR, pipeline_error: str | None = None,
                    generated_at: datetime | None = None) -> tuple[Path, Path, list]:
    """Write the dated HTML + Markdown report and a stable latest.html copy."""
    generated_at = generated_at or datetime.now()
    conn = engine.raw_connection()
    try:
        data = collect(conn)
    finally:
        conn.close()
    alerts = build_alerts(data, today, pipeline_failed=pipeline_error is not None)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"management_report_{today:%Y-%m-%d}"
    html_path, md_path = out_dir / f"{stem}.html", out_dir / f"{stem}.md"
    html_path.write_text(to_html(data, alerts, generated_at, TITLE, failure=pipeline_error), encoding="utf-8")
    md_path.write_text(to_markdown(data, alerts, generated_at, TITLE), encoding="utf-8")
    shutil.copyfile(html_path, out_dir / "latest.html")
    return html_path, md_path, alerts


def run_job(settings: Settings | None = None, today: date | None = None, retries: int = 1,
            retry_delay_s: float = 30, run_pipeline_fn=None, engine=None,
            out_dir: Path = OUT_DIR, status_file: Path = STATUS_FILE, lock_file: Path = LOCK_FILE) -> int:
    settings = settings or load_settings()
    today = today or date.today()
    status = JobStatus(started_at=datetime.now().isoformat(timespec="seconds"))

    with RunLock(lock_file) as lock:
        if not lock.acquired:
            log.error("Another scheduled run holds %s - skipping", lock_file)
            status.status, status.exit_code = "skipped_locked", EXIT_LOCKED
            return _finish(status, status_file)

        if run_pipeline_fn is None:
            from etl.pipeline import run_pipeline as run_pipeline_fn
        if engine is None:
            from common.db import get_engine
            engine = get_engine(settings)

        # 1. refresh
        for attempt in range(retries + 1):
            try:
                result = run_pipeline_fn(triggered_by="scheduler", settings=settings, engine=engine)
                status.pipeline_run_id = result.run_id
                status.pipeline_error = None
                break
            except Exception as exc:  # noqa: BLE001 - every failure is reported, none is swallowed
                status.pipeline_error = f"{type(exc).__name__}: {exc}"
                if attempt < retries and is_connection_error(exc):
                    log.warning("Connection error (attempt %d/%d), retrying in %ss: %s",
                                attempt + 1, retries + 1, retry_delay_s, exc)
                    time.sleep(retry_delay_s)
                    continue
                log.error("Pipeline failed: %s", status.pipeline_error)
                break

        # 2. publish (also after a failed refresh: the last good data is still in place)
        try:
            html_path, md_path, alerts = generate_report(engine, today, out_dir, status.pipeline_error)
            status.report_html, status.report_markdown = str(html_path), str(md_path)
            status.alerts = dict(Counter(a.severity for a in alerts))
            log.info("Report written: %s (%s)", html_path, status.alerts)
        except Exception as exc:  # noqa: BLE001
            status.report_error = f"{type(exc).__name__}: {exc}"
            log.error("Report generation failed: %s", status.report_error)

    if status.report_error:
        status.status, status.exit_code = "report_failed", EXIT_REPORT_FAILED
    elif status.pipeline_error:
        status.status, status.exit_code = "pipeline_failed", EXIT_PIPELINE_FAILED
    else:
        status.status, status.exit_code = "success", EXIT_OK
    return _finish(status, status_file)


def _finish(status: JobStatus, status_file: Path) -> int:
    status.finished_at = datetime.now().isoformat(timespec="seconds")
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(json.dumps(asdict(status), indent=2), encoding="utf-8")
    log.info("Scheduled run finished: %s (exit %s)", status.status, status.exit_code)
    return status.exit_code
