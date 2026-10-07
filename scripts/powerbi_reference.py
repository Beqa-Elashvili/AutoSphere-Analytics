"""Print the values the Power BI report must show (validation of the .pbix).

Every number is computed from the same `bi` views Power BI imports, with the same logic as
the DAX measures in powerbi/dax-measures.md. After building or refreshing the report, compare
its cards with this output (no filters applied, unless a section says otherwise).

Usage:
    python scripts/powerbi_reference.py            # prints and writes reports/powerbi_reference.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from common.config import PROJECT_ROOT  # noqa: E402
from common.db import get_engine  # noqa: E402

# measure name -> SQL over the bi views (one scalar each)
CARDS = {
    "Revenue": "SELECT sum(net_amount) FROM bi.fact_sales",
    "Profit": "SELECT sum(profit_amount) FROM bi.fact_sales",
    "Profit Margin %": "SELECT sum(profit_amount) / sum(net_amount) FROM bi.fact_sales",
    "Orders": "SELECT count(DISTINCT invoice_number) FROM bi.fact_sales",
    "Avg Order Value": "SELECT sum(net_amount) / count(DISTINCT invoice_number) FROM bi.fact_sales",
    "Customers": "SELECT count(DISTINCT customer_id) FROM bi.fact_sales",
    "Repeat Customer Rate %": """SELECT avg((n >= 2)::int) FROM
        (SELECT customer_id, count(DISTINCT invoice_number) AS n FROM bi.fact_sales GROUP BY 1) x""",
    "Revenue CY YTD": "SELECT sum(f.net_amount) FROM bi.fact_sales f JOIN bi.dim_date d USING (date_key) WHERE d.is_current_ytd",
    "Revenue PY YTD": "SELECT sum(f.net_amount) FROM bi.fact_sales f JOIN bi.dim_date d USING (date_key) WHERE d.is_prior_ytd",
    "Service Revenue": "SELECT sum(total_revenue) FROM bi.fact_service_orders",
    "Service Order Count": "SELECT count(*) FROM bi.fact_service_orders",
    "Median Turnaround (h)": "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY turnaround_hours) FROM bi.fact_service_orders",
    "Net Cash": "SELECT sum(net_cash_amount) FROM bi.fact_payments",
    "Failed Payment Rate %": "SELECT avg((payment_status = 'failed')::int) FROM bi.fact_payments",
    "Feedback Count": "SELECT count(*) FROM bi.fact_customer_feedback",
    "Negative Rate %": "SELECT avg((sentiment = 'negative')::int) FROM bi.fact_customer_feedback",
    "Avg Rating": "SELECT avg(rating) FROM bi.fact_customer_feedback",
    "Active Anomalies": "SELECT count(*) FROM bi.feedback_anomalies WHERE is_anomaly",
    "Checks Run": "SELECT count(*) FROM bi.dq_results",
    "Critical Failures": "SELECT count(*) FROM bi.dq_results WHERE status = 'FAIL' AND severity = 'CRITICAL'",
    "Data Through": "SELECT max(full_date) FROM bi.dim_date WHERE is_current_ytd",
}

BY_BRANCH = """
SELECT b.branch_name,
       sum(f.net_amount)                                                     AS revenue,
       sum(f.net_amount) FILTER (WHERE d.is_current_ytd)                     AS revenue_cy_ytd,
       sum(f.net_amount) FILTER (WHERE d.is_prior_ytd)                       AS revenue_py_ytd,
       sum(f.net_amount) FILTER (WHERE d.is_current_ytd)
         / NULLIF(sum(f.net_amount) FILTER (WHERE d.is_prior_ytd), 0) - 1    AS revenue_ytd_yoy
FROM bi.fact_sales f
JOIN bi.dim_branch b USING (branch_key)
JOIN bi.dim_date d USING (date_key)
GROUP BY b.branch_name
ORDER BY revenue DESC
"""

BY_YEAR = """
SELECT d.year, sum(f.net_amount) AS revenue, count(DISTINCT d.year_month) AS months_with_sales
FROM bi.fact_sales f JOIN bi.dim_date d USING (date_key)
GROUP BY d.year ORDER BY d.year
"""


def fmt(name: str, value) -> str:
    if value is None:
        return "(blank)"
    if name.endswith("%"):
        return f"{float(value):.1%}"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, int):
        return f"{value:,}"
    return f"{float(value):,.2f}"


def collect(cur) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    names = list(CARDS)
    cur.execute("SELECT " + ", ".join(f"({CARDS[n]})" for n in names))
    cards = dict(zip(names, cur.fetchone()))
    cy, py = cards["Revenue CY YTD"], cards["Revenue PY YTD"]
    cards["Revenue YTD YoY %"] = (cy / py - 1) if cy is not None and py else None
    frames = []
    for sql in (BY_BRANCH, BY_YEAR):
        cur.execute(sql)
        frames.append(pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description]))
    return cards, frames[0], frames[1]


def main() -> int:
    conn = get_engine().raw_connection()
    try:
        with conn.cursor() as cur:
            cards, branches, years = collect(cur)
    finally:
        conn.close()

    lines = ["# Power BI reference values", "",
             "Values the report must show with no filters applied (`scripts/powerbi_reference.py`).", "",
             "| Measure | Expected |", "|---|---:|"]
    lines += [f"| {name} | {fmt(name, value)} |" for name, value in cards.items()]
    branches["revenue_ytd_yoy"] = branches["revenue_ytd_yoy"].map(lambda v: fmt("%", v))
    lines += ["", "## Revenue by branch", "", branches.to_markdown(index=False, floatfmt=",.2f"),
              "", "## Revenue by year (growth is shown only between complete years)", "",
              years.to_markdown(index=False, floatfmt=",.2f"), ""]
    text = "\n".join(lines)

    out = PROJECT_ROOT / "reports" / "powerbi_reference.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nWritten to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
