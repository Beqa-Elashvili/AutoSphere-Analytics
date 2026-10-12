"""Power BI layer tests.

The .pbix itself cannot be unit-tested, so the tests guard everything it depends on:
  * the documents are consistent: every DAX measure reference is defined, every
    Table[column] in the DAX and the dashboard spec exists in the `bi` views
  * the `bi` views satisfy what Power BI relationships need (bi_checks)
  * the reference values (what the report must show) equal the SQL KPI layer
"""
import re

import pytest

from common.config import PROJECT_ROOT
from etl.validation.checks import run_checks
from etl.validation.rules import BI_DIMENSION_KEYS, BI_RELATIONSHIPS, bi_checks

PBI_DIR = PROJECT_ROOT / "powerbi"
BI_SQL = PROJECT_ROOT / "database" / "views" / "10_bi.sql"

COLUMN_REF = re.compile(r"(?:'([^']+)'|\b([A-Za-z_][A-Za-z_ ]*?))\[([^\]]+)\]")
MEASURE_REF = re.compile(r"(?<![\w'\]])\[([^\]]+)\]")
MEASURE_DEF = re.compile(r"^([A-Z_][^=\n]*?) =(?:\s|$)", re.MULTILINE)


def read(name: str) -> str:
    return (PBI_DIR / name).read_text(encoding="utf-8")


def model_tables() -> dict[str, str]:
    """Power BI table name -> bi view, parsed from the table in data-model.md."""
    return dict(re.findall(r"^\|\s*\*\*(.+?)\*\*\s*\|\s*`bi\.(\w+)`", read("data-model.md"), re.MULTILINE))


def dax_blocks() -> list[str]:
    return re.findall(r"```dax\n(.*?)```", read("dax-measures.md"), re.DOTALL)


def measures() -> list[str]:
    return [name.strip() for block in dax_blocks() for name in MEASURE_DEF.findall(block)]


def strip_strings(code: str) -> str:
    return re.sub(r'"[^"]*"', '""', code)


def column_refs(text: str) -> set[tuple[str, str]]:
    """{(table, column)}; the docs' shorthand Table[a / b] expands to both columns."""
    return {((q or u).strip(), col.strip())
            for q, u, cols in COLUMN_REF.findall(strip_strings(text)) for col in cols.split(" / ")}


# ---------------------------------------------------------------- static (no database)
def test_data_model_lists_every_bi_view():
    views = set(re.findall(r"CREATE VIEW bi\.(\w+)", BI_SQL.read_text(encoding="utf-8")))
    assert set(model_tables().values()) == views


def test_measures_are_unique_and_plentiful():
    names = measures()
    assert len(names) == len(set(names)), "duplicate measure names"
    assert len(names) >= 60


def test_measure_names_do_not_clash_with_tables():
    assert not set(measures()) & set(model_tables())


def test_every_measure_reference_is_defined():
    defined = set(measures())
    for block in dax_blocks():
        code = strip_strings(COLUMN_REF.sub("", block))
        missing = set(MEASURE_REF.findall(code)) - defined
        assert not missing, f"undefined measures: {missing}"


def test_dax_uses_only_model_tables():
    tables = set(model_tables())
    for block in dax_blocks():
        unknown = {t for t, _ in column_refs(block)} - tables
        assert not unknown, f"unknown tables: {unknown}"


def test_dashboard_spec_uses_defined_measures():
    defined, tables = set(measures()), set(model_tables())
    spec = read("dashboard-spec.md")
    for token in re.findall(r"`([^`]+)`", spec):
        if "[" in token or not token[0].isupper() or re.search(r"[./_=]", token):
            continue
        assert token in defined or token in tables, f"dashboard-spec references unknown measure `{token}`"


def test_relationships_in_docs_match_validated_relationships():
    doc = read("data-model.md")
    documented = {(fact, col) for fact, col, _ in BI_RELATIONSHIPS}
    tables = {v: k for k, v in model_tables().items()}
    for fact, col in documented:
        assert tables[fact] in doc and col in doc


def test_theme_is_valid_json():
    import json
    theme = json.loads(read("theme/autosphere-theme.json"))
    assert theme["name"] and len(theme["dataColors"]) >= 6


# ---------------------------------------------------------------- database
@pytest.fixture(scope="module")
def conn(engine):
    c = engine.raw_connection()
    with c.cursor() as cur:
        cur.execute("SELECT to_regclass('bi.fact_sales') IS NOT NULL")
        if not cur.fetchone()[0]:
            c.close()
            pytest.skip("bi layer missing - run scripts/setup_database.py")
    yield c
    c.rollback()
    c.close()


def scalar(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()[0]


@pytest.fixture(scope="module")
def bi_columns(conn) -> dict[str, set[str]]:
    with conn.cursor() as cur:
        cur.execute("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'bi'")
        cols: dict[str, set[str]] = {}
        for table, column in cur.fetchall():
            cols.setdefault(table, set()).add(column)
    return cols


@pytest.mark.db
@pytest.mark.parametrize("doc", ["dax-measures.md", "dashboard-spec.md", "data-model.md"])
def test_documented_columns_exist(bi_columns, doc):
    tables = model_tables()
    text = "\n".join(dax_blocks()) if doc == "dax-measures.md" else read(doc)
    refs = {(t, c) for t, c in column_refs(text) if t in tables}
    assert refs, "no column references found"
    missing = {f"{t}[{c}]" for t, c in refs if c not in bi_columns[tables[t]]}
    assert not missing, f"{doc}: columns not in bi views: {missing}"


@pytest.mark.db
def test_relationship_keys_exist(bi_columns):
    for fact, col, dim in BI_RELATIONSHIPS:
        assert col in bi_columns[fact]
        assert BI_DIMENSION_KEYS[dim] in bi_columns[dim]


@pytest.mark.db
def test_bi_layer_passes_its_quality_checks(conn):
    import datetime as dt
    with conn.cursor() as cur:
        results = run_checks(cur, bi_checks(), dt.date.today(), stage="analytics", chunk_size=6)
    failed = [f"{r.table_name}.{r.check_name}" for r in results if r.status == "FAIL"]
    assert not failed, failed


@pytest.mark.db
def test_reference_values_match_sql_kpi_layer(conn):
    from scripts.powerbi_reference import collect
    with conn.cursor() as cur:
        cards, branches, years = collect(cur)
        cur.execute("SELECT revenue, orders, customer_count, service_revenue, service_orders, repeat_customer_rate_pct "
                    "FROM analytics.v_kpi_summary")
        revenue, orders, customers, service_revenue, service_orders, repeat_pct = cur.fetchone()
        cur.execute("SELECT ytd_revenue, prior_ytd_revenue, revenue_yoy_pct FROM analytics.v_kpi_ytd")
        ytd, prior_ytd, yoy_pct = cur.fetchone()
    assert cards["Revenue"] == revenue and cards["Orders"] == orders and cards["Customers"] == customers
    assert cards["Service Revenue"] == service_revenue and cards["Service Order Count"] == service_orders
    assert round(float(cards["Repeat Customer Rate %"]) * 100, 2) == pytest.approx(float(repeat_pct))
    assert cards["Revenue CY YTD"] == ytd and cards["Revenue PY YTD"] == prior_ytd
    assert round(float(cards["Revenue YTD YoY %"]) * 100, 2) == pytest.approx(float(yoy_pct), abs=0.01)
    assert float(branches.revenue.sum()) == pytest.approx(float(revenue))
    assert cards["Critical Failures"] == 0


@pytest.mark.db
def test_date_table_is_contiguous_whole_years(conn):
    days, first, last, years = (
        scalar(conn, "SELECT count(*) FROM bi.dim_date"),
        scalar(conn, "SELECT min(full_date) FROM bi.dim_date"),
        scalar(conn, "SELECT max(full_date) FROM bi.dim_date"),
        scalar(conn, "SELECT count(DISTINCT year) FROM bi.dim_date"),
    )
    assert (first.month, first.day, last.month, last.day) == (1, 1, 12, 31)
    assert days == (last - first).days + 1 and years >= 2


@pytest.mark.db
def test_customer_dimension_has_no_contact_data(bi_columns):
    assert not {"email", "phone"} & bi_columns["dim_customer"]
    assert "vin" not in bi_columns["dim_vehicle"]


def test_kpi_dictionary_dax_matches_the_measure_catalog():
    """The KPI dictionary shows the same measures as powerbi/dax-measures.md, never stale variants."""
    catalog = {}
    for block in dax_blocks():
        for m in re.finditer(r"^([A-Z_][^=\n]*?) =(.*?)(?=^\S|\Z)", block, re.MULTILINE | re.DOTALL):
            catalog[m.group(1).strip()] = " ".join(m.group(2).split())
    dictionary = (PROJECT_ROOT / "docs" / "kpi-dictionary.md").read_text(encoding="utf-8")
    shown = re.findall(r"```dax\n(.*?)```", dictionary, re.DOTALL)
    assert shown
    for block in shown:
        for m in re.finditer(r"^([A-Z_][^=\n]*?) =(.*?)(?=^\S|\Z)", block, re.MULTILINE | re.DOTALL):
            name, body = m.group(1).strip(), " ".join(m.group(2).split())
            assert catalog.get(name) == body, f"kpi-dictionary measure '{name}' differs from dax-measures.md"
