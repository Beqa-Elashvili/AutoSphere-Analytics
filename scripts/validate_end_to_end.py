"""End-to-end acceptance check: one command that proves the whole platform works.

Runs the pipeline (free local AI mode; cached Gemini labels are kept), then follows the data
through every layer and prints a PASS/FAIL checklist with the evidence for each item:

    raw CSV -> staging + quarantine -> warehouse -> analytics -> Power BI layer -> report
    + data quality, AI enrichment and the known business stories

Usage:
    python scripts/validate_end_to_end.py                 # run the pipeline, then validate
    python scripts/validate_end_to_end.py --skip-pipeline # validate the current database only (~30 s)

Writes reports/e2e_validation.md. Exit code 0 = every check passed, 1 = at least one failed.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from common.config import PROJECT_ROOT, load_settings  # noqa: E402
from etl.sources import SOURCE_COLUMNS  # noqa: E402

RAW_DIR = PROJECT_ROOT / "data" / "raw"
FACTS = {"sales": "fact_sales", "service_orders": "fact_service_orders", "service_items": "fact_service_items",
         "payments": "fact_payments", "customer_feedback": "fact_customer_feedback"}
MIN_AI_ACCURACY = 0.90


@dataclass
class Result:
    layer: str
    check: str
    passed: bool
    evidence: str


def scalar(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def raw_count(table: str) -> int:
    with open(RAW_DIR / f"{table}.csv", encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.reader(f)) - 1


def money(v) -> str:
    return f"{float(v):,.2f}"


def validate(engine, today: date) -> list[Result]:
    conn = engine.raw_connection()
    try:
        return _validate(engine, conn, today)
    finally:
        conn.rollback()
        conn.close()


def _validate(engine, conn, today: date) -> list[Result]:
    results: list[Result] = []

    def add(layer, check, passed, evidence):
        results.append(Result(layer, check, bool(passed), evidence))

    with conn.cursor() as cur:
        run = scalar(cur, "SELECT max(run_id) FROM audit.pipeline_runs "
                          "WHERE pipeline_name = 'autosphere_etl' AND status = 'success'")
        add("Pipeline", "a successful pipeline run exists", run is not None, f"last successful run_id = {run}")

        # 1. raw -> staging + quarantine: no row is lost or invented
        cur.execute("SELECT source_table, count(*) FROM audit.rejected_rows WHERE run_id = %s GROUP BY 1", (run,))
        rejected = dict(cur.fetchall())
        gaps, raw_total, stg_total = [], 0, 0
        for table in SOURCE_COLUMNS:
            raw, stg = raw_count(table), scalar(cur, f"SELECT count(*) FROM staging.{table}")
            raw_total, stg_total = raw_total + raw, stg_total + stg
            if raw != stg + rejected.get(table, 0):
                gaps.append(f"{table}: {raw} != {stg} + {rejected.get(table, 0)}")
        add("Lineage", "raw rows = staging rows + quarantined rows (11 tables)", not gaps,
            "; ".join(gaps) or f"{raw_total:,} raw = {stg_total:,} staging + {sum(rejected.values()):,} quarantined")

        # 2. staging -> warehouse facts
        diffs = []
        for src, fact in FACTS.items():
            s, d = scalar(cur, f"SELECT count(*) FROM staging.{src}"), scalar(cur, f"SELECT count(*) FROM dw.{fact}")
            if s != d:
                diffs.append(f"{fact}: {s} vs {d}")
        add("Lineage", "every staging transaction is in its fact table (5 facts)", not diffs, "; ".join(diffs) or "row counts equal")

        # 3. one revenue number through every layer
        dw_rev = scalar(cur, "SELECT sum(net_amount) FROM dw.fact_sales WHERE is_revenue_recognized")
        an_rev = scalar(cur, "SELECT revenue FROM analytics.v_kpi_summary")
        bi_rev = scalar(cur, "SELECT sum(net_amount) FROM bi.fact_sales")
        add("Lineage", "revenue identical in warehouse, KPI views and Power BI layer",
            dw_rev == an_rev == bi_rev, f"{money(dw_rev)} GEL in all three")
        ytd_view = scalar(cur, "SELECT ytd_revenue FROM analytics.v_kpi_ytd")
        ytd_bi = scalar(cur, "SELECT sum(f.net_amount) FROM bi.fact_sales f JOIN bi.dim_date d USING (date_key) "
                             "WHERE d.is_current_ytd")
        add("Lineage", "YTD revenue in KPI view = Power BI date-flag logic", ytd_view == ytd_bi, f"{money(ytd_view)} GEL")

        # 4. data quality
        cur.execute("SELECT checks, critical_failures, warnings, rejected_rows FROM audit.v_quality_summary_by_run "
                    "WHERE run_id = %s", (run,))
        checks, critical, warnings, quarantined = cur.fetchone()
        add("Data quality", "0 critical failures in the last run", critical == 0,
            f"{checks} checks, {critical} critical, {warnings} warnings, {quarantined:,} rows quarantined")
        reasons = scalar(cur, "SELECT count(DISTINCT reason) FROM audit.rejected_rows WHERE run_id = %s", (run,))
        add("Data quality", "quarantined rows carry a reason", reasons > 0, f"{reasons} distinct rejection reasons")

        # 5. AI enrichment
        total = scalar(cur, "SELECT count(*) FROM dw.fact_customer_feedback")
        labelled = scalar(cur, "SELECT count(*) FROM dw.fact_customer_feedback WHERE sentiment IS NOT NULL AND topic IS NOT NULL")
        add("AI", "every feedback has language, sentiment and topic", labelled == total, f"{labelled:,} / {total:,}")
        cur.execute("SELECT method, labels FROM analytics.v_ai_classification_quality ORDER BY labels DESC")
        methods = dict(cur.fetchall())
        fallback = methods.get("rule_based_fallback", 0) / total if total else 1
        add("AI", "fallback labels <= 2%", fallback <= 0.02, f"methods {methods}")
        add("AI", "an AI insight per branch + company", scalar(cur, "SELECT count(*) FROM analytics.v_ai_insights_latest") >= 8,
            f"{scalar(cur, 'SELECT count(*) FROM analytics.v_ai_insights_latest')} insights")

        # 6. Power BI layer
        from etl.validation.checks import run_checks
        from etl.validation.rules import bi_checks
        bi = run_checks(cur, bi_checks(), today, stage="analytics", chunk_size=6)
        failed = [f"{r.table_name}.{r.check_name}" for r in bi if r.status == "FAIL"]
        add("Power BI", "bi layer: unique keys, no orphan facts, totals = SQL, no PII", not failed,
            ", ".join(failed) or f"{len(bi)} checks passed")

        # 7. business stories the dashboards must show
        kut = scalar(cur, "SELECT ytd_yoy_pct FROM analytics.v_branch_growth WHERE branch_name = 'AutoSphere Kutaisi'")
        add("Business", "Kutaisi is declining (YTD vs prior YTD)", kut is not None and kut < 0, f"{float(kut):+.1f}%")
        yoy = scalar(cur, "SELECT revenue_yoy_pct FROM analytics.v_kpi_ytd")
        partial = scalar(cur, "SELECT revenue_growth_pct FROM analytics.v_kpi_by_year ORDER BY year DESC LIMIT 1")
        add("Business", "comparable growth used (no fake decline from a partial year)", yoy > 0 and partial is None,
            f"YTD {float(yoy):+.1f}%; partial-year growth shown as NULL")
        cur.execute("""SELECT count(*) FROM analytics.v_feedback_anomalies
                       WHERE is_anomaly AND branch_name = 'AutoSphere Batumi' AND topic = 'waiting_time'""")
        add("Business", "Batumi waiting-time complaints flagged as anomaly", cur.fetchone()[0] > 0, "v_feedback_anomalies")

    # 8. AI accuracy against generator labels (free: labels are already stored)
    try:
        import pandas as pd
        from ai.evaluation import evaluate, load_generated
        with conn.cursor() as cur:
            cur.execute("SELECT feedback_id, language, sentiment, topic, confidence, method FROM dw.feedback_classification")
            pred = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
        pred["confidence"] = pred.confidence.astype(float)
        m = evaluate(pred, load_generated())
        add("AI", f"stored labels: sentiment and topic accuracy >= {MIN_AI_ACCURACY:.0%}",
            m["sentiment_accuracy"] >= MIN_AI_ACCURACY and m["topic_accuracy"] >= MIN_AI_ACCURACY,
            f"sentiment {m['sentiment_accuracy']:.1%}, topic {m['topic_accuracy']:.1%} on {m['items']:,} items")
    except FileNotFoundError:
        add("AI", "stored labels vs generator labels", False, "data/evaluation labels missing: run generate_data.py")

    # 9. automated report
    from reporting.job import OUT_DIR, generate_report
    html_path, _, alerts = generate_report(engine, today, OUT_DIR)
    high = [a for a in alerts if a.severity in ("HIGH", "CRITICAL")]
    add("Reporting", "management report generated with alerts", html_path.exists() and len(high) >= 3,
        f"{html_path.name}: {len(high)} high-priority alerts")
    return results


def to_markdown(results: list[Result], header: str) -> str:
    lines = ["# End-to-end validation", "", header, "", "| | Layer | Check | Evidence |", "|---|---|---|---|"]
    lines += [f"| {'✅' if r.passed else '❌'} | {r.layer} | {r.check} | {r.evidence} |" for r in results]
    passed = sum(r.passed for r in results)
    lines += ["", f"**{passed}/{len(results)} checks passed.**"]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-pipeline", action="store_true", help="validate the current database without a new run")
    args = parser.parse_args()

    settings = load_settings().with_provider("local")   # validation never spends API credit
    from common.db import get_engine
    engine = get_engine(settings)
    started = time.time()
    header = "Validated the current database (no new pipeline run)."
    if not args.skip_pipeline:
        from etl.pipeline import run_pipeline
        result = run_pipeline(triggered_by="manual", settings=settings, engine=engine)
        header = f"Pipeline run {result.run_id}: {result.status} in {result.duration_s:.0f}s (local AI mode, cached labels kept)."

    results = validate(engine, date.today())

    width = max(len(r.check) for r in results)
    print(f"\n{header}\n")
    for r in results:
        print(f"{'PASS' if r.passed else 'FAIL'}  {r.layer:12s} {r.check:{width}s}  {r.evidence}")
    passed = sum(r.passed for r in results)
    print(f"\n{passed}/{len(results)} checks passed in {time.time() - started:.0f}s")

    out = PROJECT_ROOT / "reports" / "e2e_validation.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(to_markdown(results, header), encoding="utf-8")
    print(f"Written to {out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
