"""Collect the numbers for the management report from the analytics layer.

The report computes nothing itself: every figure comes from the same SQL views that
Power BI uses, so the e-mail/HTML report and the dashboard can never disagree.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

import pandas as pd

from common.config import PROJECT_ROOT

# Reuse business question 10 as-is, restricted to the latest quarter.
_OPERATIONAL = (PROJECT_ROOT / "analytics" / "sql" / "10_operational_issues.sql").read_text(encoding="utf-8")
_OPERATIONAL = _OPERATIONAL.strip().rstrip(";")
TURNAROUND_SQL = (f"SELECT * FROM (\n{_OPERATIONAL}\n) t\n"
                  f"WHERE t.year_quarter = (SELECT max(year_quarter) FROM (\n{_OPERATIONAL}\n) t2)")

# Pipeline status refers to the ETL pipeline (not ad-hoc quality-check runs).
QUERIES = {
    "period": "SELECT first_date, last_date, current_year FROM analytics.v_data_period",
    "ytd": "SELECT * FROM analytics.v_kpi_ytd",
    "branches": """
        SELECT g.branch_name, g.ytd_revenue, g.prior_ytd_revenue, g.ytd_yoy_pct, g.last_3m_yoy_pct, g.trend_status,
               s.negative_rate_current_year_pct, s.avg_rating
        FROM analytics.v_branch_growth g
        LEFT JOIN analytics.v_sentiment_by_branch s USING (branch_id)
        ORDER BY g.ytd_revenue DESC""",
    "turnaround": TURNAROUND_SQL,
    "anomalies": """
        WITH latest AS (SELECT max(year * 10 + quarter_number) AS yq FROM analytics.v_feedback_anomalies
                        WHERE feedback_count > 0)
        SELECT branch_name, topic, year_quarter, negative_count, baseline_negatives, ratio_to_baseline
        FROM analytics.v_feedback_anomalies, latest
        WHERE is_anomaly AND year * 10 + quarter_number = latest.yq
        ORDER BY ratio_to_baseline DESC""",
    "complaints": """
        SELECT topic, negative_count, negatives_latest_quarter, negatives_same_quarter_last_year
        FROM analytics.v_top_complaint_topics ORDER BY complaint_rank LIMIT 5""",
    "insight": """
        SELECT insight_text, method, model, period_label FROM analytics.v_ai_insights_latest
        WHERE scope = 'company' LIMIT 1""",
    "ai_quality": "SELECT method, model, labels, share_pct, avg_confidence FROM analytics.v_ai_classification_quality",
    "last_run": """
        SELECT run_id, status, started_at, finished_at, error_message FROM audit.pipeline_runs
        WHERE pipeline_name = 'autosphere_etl' ORDER BY run_id DESC LIMIT 1""",
    "last_success": """
        SELECT run_id, finished_at FROM audit.pipeline_runs
        WHERE pipeline_name = 'autosphere_etl' AND status = 'success' ORDER BY run_id DESC LIMIT 1""",
    "dq_summary": """
        SELECT run_id, checks, critical_failures, warnings, rejected_rows FROM audit.v_quality_summary_by_run
        WHERE pipeline_name = 'autosphere_etl' ORDER BY run_id DESC LIMIT 1""",
    "dq_critical": """
        SELECT table_name, check_name, failed_rows, message FROM audit.data_quality_report
        WHERE status = 'FAIL' AND severity = 'CRITICAL'
          AND run_id = (SELECT max(run_id) FROM audit.pipeline_runs WHERE pipeline_name = 'autosphere_etl')
        ORDER BY failed_rows DESC LIMIT 20""",
}


@dataclass
class ReportData:
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)

    def __getitem__(self, name: str) -> pd.DataFrame:
        return self.frames[name]

    def row(self, name: str) -> dict:
        """First row of a one-row query as a dict ({} when empty)."""
        df = self.frames[name]
        return df.iloc[0].to_dict() if len(df) else {}


def _plain(value):
    return float(value) if isinstance(value, Decimal) else value


def collect(conn) -> ReportData:
    data = ReportData()
    with conn.cursor() as cur:
        for name, sql in QUERIES.items():
            cur.execute(sql)
            df = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
            data.frames[name] = df.apply(lambda col: col.map(_plain)) if len(df) else df
    return data
