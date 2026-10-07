"""Automated reporting: alert rules, rendering, and the scheduled job's failure handling."""
import json
import os
import time
from datetime import date, datetime, timezone

import pandas as pd
import psycopg2
import pytest

from etl.validation.checks import DataQualityError
from reporting import job
from reporting.alerts import CRITICAL, HIGH, INFO, MEDIUM, build_alerts
from reporting.data import ReportData
from reporting.render import to_html, to_markdown

TODAY = date(2026, 10, 7)


def fake_data(**overrides) -> ReportData:
    """A healthy business by default; override frames to create problems."""
    frames = {
        "period": pd.DataFrame([{"first_date": date(2024, 1, 1), "last_date": date(2026, 9, 30), "current_year": 2026}]),
        "ytd": pd.DataFrame([{"ytd_revenue": 1000.0, "revenue_yoy_pct": 5.0, "ytd_orders": 10, "orders_yoy_pct": 1.0,
                              "ytd_avg_order_value": 100.0, "prior_ytd_avg_order_value": 95.0, "ytd_margin_pct": 16.0,
                              "prior_ytd_margin_pct": 15.0, "ytd_service_revenue": 300.0,
                              "service_revenue_yoy_pct": 2.0}]),
        "branches": pd.DataFrame([{"branch_name": "Branch A", "ytd_revenue": 600.0, "prior_ytd_revenue": 550.0,
                                   "ytd_yoy_pct": 9.1, "last_3m_yoy_pct": 3.0, "trend_status": "Growing",
                                   "negative_rate_current_year_pct": 30.0, "avg_rating": 3.5}]),
        "turnaround": pd.DataFrame([{"branch_name": "Branch A", "year_quarter": "2026-Q3", "median_turnaround_hours": 3.0,
                                     "median_same_quarter_last_year": 2.9, "flag": "ok"}]),
        "anomalies": pd.DataFrame(columns=["branch_name", "topic", "year_quarter", "negative_count",
                                           "baseline_negatives", "ratio_to_baseline"]),
        "complaints": pd.DataFrame([{"topic": "price", "negative_count": 5, "negatives_latest_quarter": 2,
                                     "negatives_same_quarter_last_year": 1}]),
        "insight": pd.DataFrame([{"insight_text": "* Point one.\n* Point two.\n\nAction: do it.", "method": "template",
                                  "model": "rules-v1", "period_label": "2026-Q3"}]),
        "ai_quality": pd.DataFrame([{"method": "gemini", "model": "m", "labels": 100, "share_pct": 100.0,
                                     "avg_confidence": 0.9}]),
        "last_run": pd.DataFrame([{"run_id": 7, "status": "success", "started_at": None, "finished_at": None,
                                   "error_message": None}]),
        "last_success": pd.DataFrame([{"run_id": 7, "finished_at": datetime(2026, 10, 6, 6, 5, tzinfo=timezone.utc)}]),
        "dq_summary": pd.DataFrame([{"run_id": 7, "checks": 300, "critical_failures": 0, "warnings": 0,
                                     "rejected_rows": 0}]),
        "dq_critical": pd.DataFrame(columns=["table_name", "check_name", "failed_rows", "message"]),
    }
    frames.update(overrides)
    return ReportData(frames)


# ---------------------------------------------------------------- alert rules
def test_healthy_business_has_no_alerts():
    assert build_alerts(fake_data(), TODAY) == []


def test_declining_branch_is_high():
    branches = fake_data()["branches"].assign(trend_status="Declining", ytd_yoy_pct=-16.4)
    alerts = build_alerts(fake_data(branches=branches), TODAY)
    assert [(a.severity, a.area) for a in alerts] == [(HIGH, "Revenue")]
    assert "-16.4%" in alerts[0].message


def test_turnaround_flag_becomes_alert():
    t = fake_data()["turnaround"].assign(flag="INVESTIGATE", median_turnaround_hours=7.1, median_same_quarter_last_year=2.8)
    [alert] = build_alerts(fake_data(turnaround=t), TODAY)
    assert alert.area == "Service operations" and "7.1 h" in alert.message and "2.8 h" in alert.message


def test_anomaly_severity_depends_on_ratio():
    anomalies = pd.DataFrame([
        {"branch_name": "A", "topic": "waiting_time", "year_quarter": "2026-Q3", "negative_count": 52,
         "baseline_negatives": 24.5, "ratio_to_baseline": 2.12},
        {"branch_name": "B", "topic": "price", "year_quarter": "2026-Q3", "negative_count": 9,
         "baseline_negatives": 5.0, "ratio_to_baseline": 1.8},
    ])
    alerts = build_alerts(fake_data(anomalies=anomalies), TODAY)
    assert [a.severity for a in alerts] == [HIGH, MEDIUM]


def test_failed_refresh_is_first_and_names_last_good_run():
    branches = fake_data()["branches"].assign(trend_status="Declining")
    alerts = build_alerts(fake_data(branches=branches), TODAY, pipeline_failed=True)
    assert alerts[0].severity == CRITICAL and alerts[0].area == "Data refresh"
    assert "run 7" in alerts[0].message


def test_critical_quality_failures_and_warnings():
    dq = pd.DataFrame([{"run_id": 8, "checks": 300, "critical_failures": 2, "warnings": 5, "rejected_rows": 40}])
    alerts = build_alerts(fake_data(dq_summary=dq), TODAY)
    assert (alerts[0].severity, alerts[-1].severity) == (CRITICAL, INFO)


def test_stale_data_alert():
    alerts = build_alerts(fake_data(), date(2026, 12, 1))
    assert [a.area for a in alerts] == ["Data freshness"]


def test_fallback_share_alert():
    ai = pd.DataFrame([{"method": "gemini", "model": "m", "labels": 90, "share_pct": 90.0, "avg_confidence": 0.9},
                       {"method": "rule_based_fallback", "model": "r", "labels": 10, "share_pct": 10.0,
                        "avg_confidence": 0.6}])
    [alert] = build_alerts(fake_data(ai_quality=ai), TODAY)
    assert alert.area == "AI" and "10.0%" in alert.message


# ---------------------------------------------------------------- rendering
def test_html_escapes_text_and_shows_failure_banner():
    branches = fake_data()["branches"].assign(branch_name="<script>alert(1)</script>")
    html = to_html(fake_data(branches=branches), [], datetime(2026, 10, 7, 8, 0), "Report", failure="DQ failed")
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert "Refresh failed: DQ failed" in html and "No alerts." in html


def test_markdown_has_all_sections_and_insight_bullets():
    md = to_markdown(fake_data(), [], datetime(2026, 10, 7, 8, 0), "Report")
    for section in ("## Alerts", "## Headline KPIs", "## Branches", "## AI summary", "## Top complaint topics"):
        assert section in md
    assert "- Point one." in md and "- Action: do it." in md
    assert "+5.0% vs prior YTD" in md


# ---------------------------------------------------------------- lock and job
def test_lock_is_exclusive_and_released(tmp_path):
    path = tmp_path / "x.lock"
    with job.RunLock(path) as first:
        with job.RunLock(path) as second:
            assert first.acquired and not second.acquired
    assert not path.exists()


def test_stale_lock_is_taken_over(tmp_path):
    path = tmp_path / "x.lock"
    path.write_text("12345")
    old = time.time() - job.STALE_LOCK_SECONDS - 60
    os.utime(path, (old, old))
    with job.RunLock(path) as lock:
        assert lock.acquired


class FakeResult:
    run_id = 42


@pytest.fixture
def job_env(tmp_path, monkeypatch):
    """Run the job without a database: the report step is replaced by a recorder."""
    calls = {"report": []}

    def fake_report(engine, today, out_dir, pipeline_error=None, generated_at=None):
        calls["report"].append(pipeline_error)
        return out_dir / "r.html", out_dir / "r.md", build_alerts(fake_data(), today, pipeline_error is not None)

    monkeypatch.setattr(job, "generate_report", fake_report)
    kwargs = dict(today=TODAY, engine=object(), out_dir=tmp_path / "out", status_file=tmp_path / "status.json",
                  lock_file=tmp_path / "job.lock", retry_delay_s=0)
    return calls, kwargs, tmp_path / "status.json"


def test_job_success(job_env):
    calls, kwargs, status_file = job_env
    code = job.run_job(run_pipeline_fn=lambda **kw: FakeResult(), **kwargs)
    status = json.loads(status_file.read_text())
    assert code == job.EXIT_OK and status["status"] == "success" and status["pipeline_run_id"] == 42
    assert calls["report"] == [None]


def test_job_reports_even_when_quality_gate_fails_and_does_not_retry(job_env):
    calls, kwargs, status_file = job_env
    attempts = []

    def failing(**kw):
        attempts.append(1)
        raise DataQualityError([])

    code = job.run_job(run_pipeline_fn=failing, retries=3, **kwargs)
    status = json.loads(status_file.read_text())
    assert code == job.EXIT_PIPELINE_FAILED and len(attempts) == 1
    assert status["status"] == "pipeline_failed" and "DataQualityError" in status["pipeline_error"]
    assert calls["report"] and calls["report"][0] is not None       # report produced, with failure banner
    assert status["alerts"].get(CRITICAL) == 1


def test_job_retries_connection_errors(job_env):
    calls, kwargs, status_file = job_env
    attempts = []

    def flaky(**kw):
        attempts.append(1)
        if len(attempts) == 1:
            raise psycopg2.OperationalError("SSL connection has been closed unexpectedly")
        return FakeResult()

    assert job.run_job(run_pipeline_fn=flaky, retries=1, **kwargs) == job.EXIT_OK
    assert len(attempts) == 2 and calls["report"] == [None]


def test_job_report_failure_exit_code(job_env, monkeypatch):
    _, kwargs, status_file = job_env
    monkeypatch.setattr(job, "generate_report", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full")))
    assert job.run_job(run_pipeline_fn=lambda **kw: FakeResult(), **kwargs) == job.EXIT_REPORT_FAILED
    assert "disk full" in json.loads(status_file.read_text())["report_error"]


def test_job_skips_when_another_run_is_active(job_env):
    calls, kwargs, status_file = job_env
    with job.RunLock(kwargs["lock_file"]):
        code = job.run_job(run_pipeline_fn=lambda **kw: FakeResult(), **kwargs)
    assert code == job.EXIT_LOCKED and calls["report"] == []
    assert json.loads(status_file.read_text())["status"] == "skipped_locked"


def test_scheduled_job_defaults_to_free_local_ai():
    import scripts.scheduled_run as sr
    import inspect
    assert 'default="local"' in inspect.getsource(sr.main)


# ---------------------------------------------------------------- database
@pytest.mark.db
def test_report_from_live_data(engine, tmp_path):
    html_path, md_path, alerts = job.generate_report(engine, TODAY, tmp_path)
    assert html_path.exists() and md_path.exists() and (tmp_path / "latest.html").exists()
    messages = " ".join(a.message for a in alerts)
    assert "AutoSphere Kutaisi: revenue" in messages                 # declining branch (YTD)
    assert "AutoSphere Batumi: median maintenance turnaround" in messages
    assert "waiting_time" in messages
    assert all(a.severity != CRITICAL for a in alerts)


@pytest.mark.db
def test_failed_refresh_report_from_live_data(engine, tmp_path):
    html_path, _, alerts = job.generate_report(engine, TODAY, tmp_path, pipeline_error="DataQualityError: test")
    assert alerts[0].severity == CRITICAL and "last good run" in alerts[0].message
    assert "Refresh failed: DataQualityError: test" in html_path.read_text(encoding="utf-8")
