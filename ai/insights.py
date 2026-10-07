"""Management insights from customer feedback: facts from SQL, narrative from AI.

The numbers are computed deterministically in SQL (negative rates, top complaint topics,
anomalies vs baseline, and the operational driver: service turnaround). The LLM only
turns those facts into a short narrative. It never computes or looks up numbers itself,
which keeps insights traceable: the exact facts are stored next to the text.
Without an AI provider a deterministic template writes the narrative.
"""
from __future__ import annotations

import json

import pandas as pd

from common.config import Settings
from common.logging_config import get_logger

log = get_logger("ai.insights")

INSIGHT_PROMPT = """\
You are a BI analyst writing for the management of an automotive dealer and service network.
Write at most 3 short bullet points (one line each) about the customer-feedback facts below,
then one line starting with "Action:" recommending what to investigate.
Rules: use ONLY the numbers given, do not invent figures, mention the period, plain English.

Facts (JSON):
"""


def _query(conn, sql: str, params: dict | None = None) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql, params or {})
        return pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])


def _num(v):
    return None if v is None or pd.isna(v) else round(float(v), 2)


def collect_facts(conn) -> list[dict]:
    """One fact set for the company and one per branch, for the latest quarter."""
    q = _query(conn, "SELECT year, quarter_number FROM analytics.v_feedback "
                     "ORDER BY year DESC, quarter_number DESC LIMIT 1").iloc[0]
    year, quarter = int(q.year), int(q.quarter_number)
    p = {"y": year, "q": quarter}
    period, prior = f"{year}-Q{quarter}", f"{year - 1}-Q{quarter}"

    stats = _query(conn, """
        SELECT COALESCE(branch_name, 'All branches') AS scope_value,
               count(*) FILTER (WHERE year = %(y)s AND quarter_number = %(q)s)            AS feedback,
               avg(is_negative) FILTER (WHERE year = %(y)s AND quarter_number = %(q)s)    AS neg_rate,
               avg(is_negative) FILTER (WHERE year = %(y)s - 1 AND quarter_number = %(q)s) AS neg_rate_prior,
               avg(rating) FILTER (WHERE year = %(y)s AND quarter_number = %(q)s)         AS avg_rating
        FROM analytics.v_feedback
        GROUP BY GROUPING SETS ((branch_name), ())""", p)
    topics = _query(conn, """
        SELECT COALESCE(branch_name, 'All branches') AS scope_value, topic,
               sum(is_negative) FILTER (WHERE year = %(y)s AND quarter_number = %(q)s)      AS negatives,
               sum(is_negative) FILTER (WHERE year = %(y)s - 1 AND quarter_number = %(q)s)  AS negatives_prior
        FROM analytics.v_feedback WHERE topic <> 'other'
        GROUP BY GROUPING SETS ((branch_name, topic), (topic))""", p)
    anomalies = _query(conn, """
        SELECT branch_name AS scope_value, topic, negative_count, baseline_negatives, ratio_to_baseline
        FROM analytics.v_feedback_anomalies
        WHERE year = %(y)s AND quarter_number = %(q)s AND is_anomaly""", p)
    turnaround = _query(conn, """
        SELECT cur.branch_name AS scope_value, cur.median_turnaround_hours AS median_hours,
               prev.median_turnaround_hours AS median_hours_prior
        FROM analytics.v_service_turnaround cur
        LEFT JOIN analytics.v_service_turnaround prev
               ON prev.branch_id = cur.branch_id AND prev.service_type = cur.service_type
              AND prev.year = cur.year - 1 AND prev.quarter_number = cur.quarter_number
        WHERE cur.service_type = 'maintenance' AND cur.year = %(y)s AND cur.quarter_number = %(q)s""", p)

    fact_sets = []
    for row in stats.itertuples():
        scope = row.scope_value
        t = topics[topics.scope_value == scope].fillna(0).sort_values("negatives", ascending=False).head(3)
        a = anomalies[anomalies.scope_value == scope] if scope != "All branches" else anomalies
        ta = turnaround[turnaround.scope_value == scope]
        facts = {
            "scope": "company" if scope == "All branches" else "branch",
            "scope_value": scope,
            "period": period,
            "comparison_period": prior,
            "feedback_count": int(row.feedback or 0),
            "negative_rate_pct": _num(100 * row.neg_rate) if row.neg_rate is not None else None,
            "negative_rate_same_quarter_last_year_pct": _num(100 * row.neg_rate_prior) if row.neg_rate_prior is not None else None,
            "avg_rating": _num(row.avg_rating),
            "top_complaint_topics": [
                {"topic": r.topic, "negatives": int(r.negatives), "negatives_same_quarter_last_year": int(r.negatives_prior)}
                for r in t.itertuples() if r.negatives > 0],
            "anomalies": [
                {"branch": r.scope_value, "topic": r.topic, "negatives": int(r.negative_count),
                 "baseline_avg_per_quarter": _num(r.baseline_negatives), "ratio_to_baseline": _num(r.ratio_to_baseline)}
                for r in a.itertuples()],
        }
        if not ta.empty and scope != "All branches":
            facts["maintenance_median_turnaround_hours"] = _num(ta.iloc[0].median_hours)
            facts["maintenance_median_turnaround_hours_last_year"] = _num(ta.iloc[0].median_hours_prior)
        fact_sets.append(facts)
    return fact_sets


def template_insight(f: dict) -> str:
    """Deterministic narrative used when no AI provider is configured (or as fallback)."""
    lines = []
    rate, prior = f["negative_rate_pct"], f["negative_rate_same_quarter_last_year_pct"]
    if rate is not None:
        change = f" ({rate - prior:+.1f} pp vs {f['comparison_period']})" if prior is not None else ""
        lines.append(f"- {f['scope_value']}: {f['feedback_count']} feedback in {f['period']}, "
                     f"negative rate {rate:.1f}%{change}.")
    if f["top_complaint_topics"]:
        t = f["top_complaint_topics"][0]
        lines.append(f"- Top complaint topic: {t['topic']} ({t['negatives']} negative, "
                     f"{t['negatives_same_quarter_last_year']} a year earlier).")
    for a in f["anomalies"][:2]:
        lines.append(f"- Anomaly: {a['topic']} complaints at {a['branch']} = {a['negatives']}, "
                     f"{a['ratio_to_baseline']}x the 4-quarter baseline.")
    if f.get("maintenance_median_turnaround_hours") is not None and f.get("maintenance_median_turnaround_hours_last_year"):
        lines.append(f"- Maintenance turnaround median {f['maintenance_median_turnaround_hours']}h "
                     f"vs {f['maintenance_median_turnaround_hours_last_year']}h a year earlier.")
    target = f["anomalies"][0]["topic"] if f["anomalies"] else (
        f["top_complaint_topics"][0]["topic"] if f["top_complaint_topics"] else None)
    lines.append(f"Action: review root causes of {target} complaints." if target else "Action: no action needed.")
    return "\n".join(lines)


def gemini_insight(client, model: str, facts: dict) -> str:
    from google.genai import types
    response = client.models.generate_content(
        model=model,
        contents=INSIGHT_PROMPT + json.dumps(facts, ensure_ascii=False, indent=1),
        config=types.GenerateContentConfig(
            temperature=0.2,
            thinking_config=types.ThinkingConfig(thinking_level="low"),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)),
    )
    text = (response.text or "").strip()
    if not text or len(text) > 1500:
        raise ValueError("empty or overly long insight")
    return text


def generate_insights(engine, settings: Settings, run_id: int | None = None) -> int:
    conn = engine.raw_connection()
    try:
        fact_sets = collect_facts(conn)
        client = None
        if settings.ai_mode == "external":
            from google import genai
            client = genai.Client(api_key=settings.ai_api_key)
        rows = []
        for f in fact_sets:
            method, model = "template", "template-v1"
            if client is not None:
                try:
                    text, method, model = gemini_insight(client, settings.ai_model, f), "gemini", settings.ai_model
                except Exception as exc:  # noqa: BLE001 - narrative falls back, numbers stay correct
                    log.warning("Gemini insight for %s failed (%s) - using template", f["scope_value"], exc)
                    text = template_insight(f)
            else:
                text = template_insight(f)
            rows.append((run_id, f["period"], f["scope"], f["scope_value"], text,
                         json.dumps(f, ensure_ascii=False), method, model))
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO dw.feedback_insights (run_id, period_label, scope, scope_value, insight_text, facts, "
                "method, model) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)", rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    log.info("Generated %d feedback insights (%s)", len(rows), rows[0][6] if rows else "-")
    return len(rows)
