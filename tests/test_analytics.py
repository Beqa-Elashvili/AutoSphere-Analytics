"""Analytics/KPI tests: independent implementations must agree on every number.

Three ways of computing each KPI are compared:
  1. the analytics views (what Power BI and reports use)
  2. the stand-alone KPI queries in analytics/kpi_queries (written directly on the star schema)
  3. a pandas recomputation from raw fact rows
"""
import re
from decimal import Decimal

import pandas as pd
import pytest

from common.config import PROJECT_ROOT
from etl.validation.rules import ANALYTICS_VIEWS

SQL_DIR = PROJECT_ROOT / "analytics" / "sql"
KPI_DIR = PROJECT_ROOT / "analytics" / "kpi_queries"
VIEWS_DIR = PROJECT_ROOT / "database" / "views"


# ---------------------------------------------------------------- static
def test_every_registered_view_is_defined_in_sql():
    defined = set()
    for path in VIEWS_DIR.glob("*.sql"):
        defined |= set(re.findall(r"CREATE (?:OR REPLACE )?VIEW analytics\.(\w+)", path.read_text(encoding="utf-8")))
    assert set(ANALYTICS_VIEWS) <= defined


@pytest.mark.parametrize("path", sorted(SQL_DIR.glob("*.sql")), ids=lambda p: p.stem)
def test_business_queries_document_question_kpi_and_decision(path):
    head = path.read_text(encoding="utf-8").split("\nSELECT")[0].split("\nWITH")[0]
    for label in ("Business question:", "KPI:", "Decision:"):
        assert label in head, f"{path.name} lacks '{label}'"


def test_at_least_ten_business_questions_are_answered():
    assert len(list(SQL_DIR.glob("*.sql"))) >= 10


# ---------------------------------------------------------------- database helpers
@pytest.fixture(scope="module")
def conn(engine):
    c = engine.raw_connection()
    with c.cursor() as cur:
        cur.execute("SELECT count(*) FROM analytics.v_sales")
        if cur.fetchone()[0] == 0:
            c.close()
            pytest.skip("analytics layer is empty - run scripts/run_pipeline.py first")
    yield c
    c.rollback()
    c.close()


def query(conn, sql) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql)
        df = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
    return df.apply(lambda col: col.map(lambda v: float(v) if isinstance(v, Decimal) else v))


def one(conn, sql) -> dict:
    return query(conn, sql).iloc[0].to_dict()


def kpi_file(conn, name) -> pd.DataFrame:
    return query(conn, (KPI_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- execution
@pytest.mark.db
@pytest.mark.parametrize("path", sorted(SQL_DIR.glob("*.sql")) + sorted(KPI_DIR.glob("*.sql")), ids=lambda p: p.stem)
def test_every_analytical_query_runs_and_returns_rows(conn, path):
    df = query(conn, path.read_text(encoding="utf-8"))
    assert not df.empty


# ---------------------------------------------------------------- independent implementations agree
@pytest.mark.db
def test_headline_kpis_match_independent_queries(conn):
    view = one(conn, "SELECT * FROM analytics.v_kpi_summary")
    money = kpi_file(conn, "01_revenue_profit_margin.sql").iloc[0]
    orders = kpi_file(conn, "02_orders_aov.sql").iloc[0]
    customers = kpi_file(conn, "03_customers_repeat_rate.sql").iloc[0]
    service = kpi_file(conn, "05_service_kpis.sql").iloc[0]
    assert view["revenue"] == pytest.approx(money.revenue)
    assert view["profit"] == pytest.approx(money.profit)
    assert view["profit_margin_pct"] == pytest.approx(money.profit_margin_pct)
    assert view["orders"] == orders.orders
    assert view["avg_order_value"] == pytest.approx(orders.avg_order_value)
    assert view["customer_count"] == customers.customer_count
    assert view["repeat_customer_rate_pct"] == pytest.approx(customers.repeat_customer_rate_pct)
    assert view["service_revenue"] == pytest.approx(service.service_revenue)
    assert view["avg_service_order_value"] == pytest.approx(service.avg_service_order_value)


@pytest.mark.db
def test_aov_divides_by_orders_not_lines(conn):
    o = kpi_file(conn, "02_orders_aov.sql").iloc[0]
    assert o.sales_lines > o.orders
    assert o.avg_order_value > o.avg_line_value_not_aov


@pytest.mark.db
def test_monthly_growth_matches_independent_window_query(conn):
    view = query(conn, "SELECT year, month_number, revenue, mom_growth_pct, yoy_growth_pct FROM analytics.v_revenue_monthly")
    kpi = kpi_file(conn, "04_growth_mom_yoy.sql")
    merged = view.merge(kpi, on=["year", "month_number"], suffixes=("_view", "_kpi"))
    assert len(merged) == len(view)
    assert (merged.revenue_view - merged.revenue_kpi).abs().max() < 0.01
    both = merged.dropna(subset=["yoy_growth_pct_view", "yoy_growth_pct_kpi"])
    assert len(both) >= 12 and (both.yoy_growth_pct_view - both.yoy_growth_pct_kpi).abs().max() < 0.01


# ---------------------------------------------------------------- pandas recomputation from facts
@pytest.fixture(scope="module")
def facts(conn):
    return query(conn, """SELECT f.invoice_number, f.net_amount, d.full_date, d.year, d.month_number, c.customer_id
                          FROM dw.fact_sales f JOIN dw.dim_date d USING (date_key)
                          JOIN dw.dim_customer c USING (customer_key) WHERE f.is_revenue_recognized""")


@pytest.mark.db
def test_yoy_for_a_month_recomputed_in_pandas(conn, facts):
    monthly = facts.groupby(["year", "month_number"]).net_amount.sum()
    y, m = 2025, 10
    expected = round(100 * (monthly[(y, m)] / monthly[(y - 1, m)] - 1), 2)
    got = one(conn, f"SELECT yoy_growth_pct FROM analytics.v_revenue_monthly WHERE year={y} AND month_number={m}")
    assert got["yoy_growth_pct"] == pytest.approx(expected, abs=0.01)


@pytest.mark.db
def test_ytd_compares_identical_calendar_windows(conn, facts):
    ytd = one(conn, "SELECT * FROM analytics.v_kpi_ytd")
    cutoff = pd.Timestamp(ytd["ytd_to"])
    cur_year = cutoff.year
    dates = pd.to_datetime(facts.full_date)
    same_window = (dates.dt.month * 100 + dates.dt.day) <= cutoff.month * 100 + cutoff.day
    assert ytd["ytd_revenue"] == pytest.approx(facts[(facts.year == cur_year) & same_window].net_amount.sum())
    assert ytd["prior_ytd_revenue"] == pytest.approx(facts[(facts.year == cur_year - 1) & same_window].net_amount.sum())


@pytest.mark.db
def test_repeat_rate_recomputed_in_pandas(conn, facts):
    orders = facts.groupby("customer_id").invoice_number.nunique()
    view = one(conn, "SELECT customer_count, repeat_customer_rate_pct FROM analytics.v_kpi_summary")
    assert view["customer_count"] == len(orders)
    assert view["repeat_customer_rate_pct"] == pytest.approx(round(100 * (orders >= 2).mean(), 2), abs=0.01)


# ---------------------------------------------------------------- business-rule correctness
@pytest.mark.db
def test_partial_year_has_no_misleading_annual_growth(conn):
    years = query(conn, "SELECT year, months_covered, revenue_growth_pct FROM analytics.v_kpi_by_year")
    assert years[years.months_covered < 12].revenue_growth_pct.isna().all()


@pytest.mark.db
def test_rfm_segmentation_is_complete_and_consistent(conn):
    m = query(conn, "SELECT rfm_segment, r_score, f_score, m_score, orders FROM analytics.v_customer_metrics")
    assert m.rfm_segment.notna().all()
    assert m[["r_score", "f_score", "m_score"]].isin([1, 2, 3, 4, 5]).all().all()
    champions = m[m.rfm_segment == "Champions"]
    assert ((champions.r_score >= 4) & (champions.f_score >= 4)).all()
    assert (m[m.rfm_segment == "New"].orders == 1).all()
    seg = query(conn, "SELECT sum(customers) AS n, sum(revenue_share_pct) AS share FROM analytics.v_customer_segments")
    assert seg.n[0] == len(m) and seg.share[0] == pytest.approx(100, abs=0.05)


@pytest.mark.db
def test_branch_trend_status_follows_the_documented_rule(conn):
    g = query(conn, "SELECT ytd_revenue, prior_ytd_revenue, trend_status FROM analytics.v_branch_growth")
    expected = g.apply(lambda r: "Declining" if r.ytd_revenue < 0.95 * r.prior_ytd_revenue
                       else "Growing" if r.ytd_revenue > 1.05 * r.prior_ytd_revenue else "Stable", axis=1)
    assert (expected == g.trend_status).all()


@pytest.mark.db
def test_shares_sum_to_100_percent(conn):
    for view, col, part in [("v_branch_performance", "revenue_share_pct", "year"),
                            ("v_category_performance", "revenue_share_pct", "year"),
                            ("v_city_revenue", "revenue_share_pct", "year")]:
        sums = query(conn, f"SELECT {part}, sum({col}) AS s FROM analytics.{view} GROUP BY {part}")
        assert (sums.s - 100).abs().max() < 0.1, view
