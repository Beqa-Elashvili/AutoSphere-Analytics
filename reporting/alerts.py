"""Rule-based alerts: what management should look at first.

Each rule is a plain threshold on numbers that already exist in the analytics layer.
Thresholds are deliberately simple and documented (docs/automated-reporting.md), so a
manager can understand why something was flagged.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from reporting.data import ReportData

CRITICAL, HIGH, MEDIUM, INFO = "CRITICAL", "HIGH", "MEDIUM", "INFO"
SEVERITY_ORDER = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, INFO: 3}

FALLBACK_SHARE_MAX_PCT = 2.0  # same threshold as the warehouse check fallback_label_share


@dataclass(frozen=True)
class Alert:
    severity: str
    area: str
    message: str


def build_alerts(data: ReportData, today: date, pipeline_failed: bool = False,
                 stale_data_days: int = 0) -> list[Alert]:
    """stale_data_days: alert when the latest sale is older (0 = off). Off by default because the
    synthetic dataset has a fixed end date; for a live feed set STALE_DATA_DAYS (e.g. 31 for monthly extracts)."""
    alerts: list[Alert] = []

    # --- data trust first: if the numbers can't be trusted, nothing else matters
    if pipeline_failed:
        good = data.row("last_success")
        since = f"run {good['run_id']} ({good['finished_at']:%Y-%m-%d %H:%M})" if good else "no successful run"
        alerts.append(Alert(CRITICAL, "Data refresh",
                            f"Today's refresh failed; figures below are from the last good {since}."))
    dq = data.row("dq_summary")
    if dq and dq["critical_failures"]:
        alerts.append(Alert(CRITICAL, "Data quality", f"{dq['critical_failures']} critical check(s) failed in run {dq['run_id']}."))
    period = data.row("period")
    if period and stale_data_days:
        age = (today - period["last_date"]).days
        if age > stale_data_days:
            alerts.append(Alert(HIGH, "Data freshness", f"Latest sale is {age} days old ({period['last_date']})."))

    # --- business
    for b in data["branches"].itertuples():
        if b.trend_status == "Declining":
            alerts.append(Alert(HIGH, "Revenue", f"{b.branch_name}: revenue {b.ytd_yoy_pct:+.1f}% YTD vs last year."))
    for t in data["turnaround"].itertuples():
        if t.flag == "INVESTIGATE":
            alerts.append(Alert(HIGH, "Service operations",
                                f"{t.branch_name}: median maintenance turnaround {t.median_turnaround_hours:.1f} h in "
                                f"{t.year_quarter} vs {t.median_same_quarter_last_year:.1f} h a year earlier."))
    for a in data["anomalies"].itertuples():
        severity = HIGH if a.ratio_to_baseline >= 2 else MEDIUM
        alerts.append(Alert(severity, "Customer feedback",
                            f"{a.branch_name}: {int(a.negative_count)} negative '{a.topic}' comments in {a.year_quarter} "
                            f"({a.ratio_to_baseline:.1f}x the 4-quarter baseline)."))

    # --- AI monitoring
    ai = data["ai_quality"]
    fallback = ai.loc[ai.method == "rule_based_fallback", "share_pct"].sum() if len(ai) else 0
    if fallback > FALLBACK_SHARE_MAX_PCT:
        alerts.append(Alert(MEDIUM, "AI", f"{fallback:.1f}% of feedback labels came from the fallback classifier."))

    if dq and dq["warnings"]:
        alerts.append(Alert(INFO, "Data quality", f"{dq['warnings']} warning(s), {dq['rejected_rows']:,} source rows "
                                                  f"quarantined in run {dq['run_id']} (see audit.rejected_rows)."))
    return sorted(alerts, key=lambda a: SEVERITY_ORDER[a.severity])
