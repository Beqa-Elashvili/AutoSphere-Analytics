"""Data Journey: one visual page that follows the data from raw CSV to business answer.

Built for demos (Georgian + English). It shows real "before" values read from the raw
files next to the "after" values in PostgreSQL, the quarantine with reasons, the quality
gates, the star schema and the findings. Every number is queried, nothing is typed in.
"""
from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

import pandas as pd

from common.config import PROJECT_ROOT
from etl.sources import SOURCE_COLUMNS

RAW_DIR = PROJECT_ROOT / "data" / "raw"
TEMPLATE = Path(__file__).with_name("journey_template.html")
LAST_RUN = ("(SELECT max(run_id) FROM audit.pipeline_runs "
            "WHERE pipeline_name = 'autosphere_etl' AND status = 'success')")


def _num(v):
    if isinstance(v, Decimal):
        return float(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _rows(cur, sql, params=None) -> list[dict]:
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [{c: _num(v) for c, v in zip(cols, r)} for r in cur.fetchall()]


def _one(cur, sql, params=None):
    cur.execute(sql, params)
    return _num(cur.fetchone()[0])


def _raw(table: str, raw_dir: Path) -> pd.DataFrame:
    return pd.read_csv(raw_dir / f"{table}.csv", dtype=str, keep_default_na=False, encoding="utf-8")


def _raw_count(table: str, raw_dir: Path) -> int:
    with open(raw_dir / f"{table}.csv", encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.reader(f)) - 1


def collect(conn, raw_dir: Path = RAW_DIR) -> dict:
    with conn.cursor() as cur:
        run_id = _one(cur, f"SELECT {LAST_RUN}")
        rejected = dict((r["source_table"], r["n"]) for r in _rows(
            cur, "SELECT source_table, count(*) AS n FROM audit.rejected_rows WHERE run_id = %s GROUP BY 1", (run_id,)))
        lineage = []
        for table in SOURCE_COLUMNS:
            clean = _one(cur, f"SELECT count(*) FROM staging.{table}")
            lineage.append({"table": table, "raw": _raw_count(table, raw_dir), "clean": clean,
                            "quarantined": rejected.get(table, 0)})

        reasons = _rows(cur, """
            SELECT reason, source_table, count(*) AS n FROM audit.rejected_rows WHERE run_id = %s
            GROUP BY 1, 2 ORDER BY n DESC LIMIT 12""", (run_id,))

        # --- before -> after examples, taken from the real files
        customers = _raw("customers", raw_dir)
        mask = customers.city.str.contains(r"bil|თბ|tiflis", case=False, regex=True)
        city_variants = (customers[mask].city.value_counts().rename_axis("value").reset_index(name="n")
                         .assign(value=lambda d: d.value.map(lambda v: v.replace(" ", "␣") if v != v.strip() else v)))
        city_after = _one(cur, "SELECT count(*) FROM staging.customers WHERE city = 'Tbilisi'")

        sales = _raw("sales", raw_dir)
        odd_dates = sales[~sales.sale_datetime.str.match(r"^\d{4}-\d{2}-\d{2}")].head(4)
        clean_dates = dict((r["sale_line_id"], r["sale_datetime"]) for r in _rows(
            cur, "SELECT sale_line_id, sale_datetime::text AS sale_datetime FROM staging.sales WHERE sale_line_id = ANY(%s)",
            (list(odd_dates.sale_line_id),)))
        dates = [{"id": r.sale_line_id, "before": r.sale_datetime, "after": clean_dates.get(r.sale_line_id)}
                 for r in odd_dates.itertuples()]

        neg = sales[sales.quantity.str.startswith("-")].iloc[0]
        quarantine = _rows(cur, """
            SELECT reason, raw_record::text AS raw_record FROM audit.rejected_rows
            WHERE run_id = %s AND source_table = 'sales' AND record_key = %s LIMIT 1""", (run_id, neg.sale_line_id))
        in_staging = _one(cur, "SELECT count(*) FROM staging.sales WHERE sale_line_id = %s", (neg.sale_line_id,))

        # --- quality gates of the last run
        gates = _rows(cur, """
            SELECT stage, count(*) AS checks,
                   count(*) FILTER (WHERE status = 'FAIL' AND severity = 'CRITICAL') AS critical,
                   count(*) FILTER (WHERE status = 'FAIL' AND severity = 'WARNING') AS warnings
            FROM audit.data_quality_report WHERE run_id = %s GROUP BY stage
            ORDER BY array_position(ARRAY['source','post_load','analytics'], stage)""", (run_id,))

        # --- warehouse, reconciliation, findings
        star = {t: _one(cur, f"SELECT count(*) FROM dw.{t}") for t in (
            "fact_sales", "fact_service_orders", "fact_service_items", "fact_payments", "fact_customer_feedback",
            "dim_date", "dim_branch", "dim_product", "dim_category", "dim_customer", "dim_employee", "dim_vehicle")}
        revenue = {
            "warehouse": _one(cur, "SELECT sum(net_amount) FROM dw.fact_sales WHERE is_revenue_recognized"),
            "kpi_views": _one(cur, "SELECT revenue FROM analytics.v_kpi_summary"),
            "power_bi": _one(cur, "SELECT sum(net_amount) FROM bi.fact_sales"),
        }
        ytd = _rows(cur, "SELECT current_year, ytd_to, ytd_revenue, prior_ytd_revenue, revenue_yoy_pct FROM analytics.v_kpi_ytd")[0]
        years = _rows(cur, "SELECT year, revenue, months_covered FROM analytics.v_kpi_by_year ORDER BY year")
        kutaisi = _rows(cur, """SELECT ytd_yoy_pct, ytd_orders, prior_ytd_orders FROM analytics.v_branch_growth
                                WHERE branch_name = 'AutoSphere Kutaisi'""")
        turnaround = _rows(cur, """
            SELECT year_quarter, median_turnaround_hours AS hours FROM analytics.v_service_turnaround
            WHERE branch_name = 'AutoSphere Batumi' AND service_type = 'maintenance' ORDER BY year_quarter""")
        ai = {
            "labelled": _one(cur, "SELECT count(*) FROM dw.fact_customer_feedback WHERE sentiment IS NOT NULL"),
            "total": _one(cur, "SELECT count(*) FROM dw.fact_customer_feedback"),
            "methods": _rows(cur, "SELECT method, labels FROM analytics.v_ai_classification_quality ORDER BY labels DESC"),
            "anomalies": _rows(cur, """
                SELECT branch_name, topic, year_quarter, negative_count, ratio_to_baseline
                FROM analytics.v_feedback_anomalies WHERE is_anomaly
                  AND year * 10 + quarter_number = (SELECT max(year * 10 + quarter_number)
                                                    FROM analytics.v_feedback_anomalies WHERE feedback_count > 0)
                ORDER BY ratio_to_baseline DESC"""),
        }

    full_years = [y for y in years if y["months_covered"] == 12]
    naive = None
    if full_years and years[-1]["months_covered"] < 12:
        naive = (years[-1]["revenue"] / full_years[-1]["revenue"] - 1) * 100
    return {
        "run_id": run_id,
        "lineage": lineage,
        "reasons": reasons,
        "examples": {
            "city_variants": city_variants.to_dict("records"), "city_after": city_after,
            "dates": dates,
            "negative": {"id": neg.sale_line_id, "quantity": neg.quantity,
                         "reason": quarantine[0]["reason"] if quarantine else None,
                         "raw_record": quarantine[0]["raw_record"] if quarantine else None,
                         "in_staging": in_staging},
        },
        "gates": gates,
        "star": star,
        "revenue": revenue,
        "ytd": ytd,
        "naive_full_year_pct": naive,
        "kutaisi": kutaisi[0] if kutaisi else None,
        "turnaround": turnaround,
        "ai": ai,
    }


def render(data: dict) -> str:
    """Fill the template. Data travels as JSON and is written to the page with textContent only."""
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", payload)
