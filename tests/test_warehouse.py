"""Star-schema tests: structure, grain, measures, unknown members, SCD Type 2, idempotency.

Database tests that modify data run inside a transaction that is always rolled back.
"""
import re
from datetime import date

import pytest

from common.config import PROJECT_ROOT
from etl.load.warehouse_loader import DW_TABLES, WAREHOUSE_SQL_DIR, build_warehouse, warehouse_sql_files
from etl.validation.checks import critical_failures, run_checks
from etl.validation.rules import LOGICAL_FOREIGN_KEYS, warehouse_checks

AS_OF = date(2026, 10, 7)
DDL = (PROJECT_ROOT / "database" / "schemas" / "04_dw.sql").read_text(encoding="utf-8")


# ---------------------------------------------------------------- static structure
def test_every_dw_table_is_defined_and_counted():
    defined = set(re.findall(r"CREATE TABLE IF NOT EXISTS dw\.(\w+)", DDL))
    assert defined == set(DW_TABLES)
    assert {t for t in defined if t.startswith("dim_")} >= {
        "dim_date", "dim_customer", "dim_vehicle", "dim_product", "dim_category", "dim_branch", "dim_employee"}
    assert {t for t in defined if t.startswith("fact_")} == {
        "fact_sales", "fact_service_orders", "fact_service_items", "fact_payments", "fact_customer_feedback"}


def test_warehouse_sql_runs_dimensions_before_facts():
    names = [p.name for p in warehouse_sql_files()]
    assert names == sorted(names)
    first_fact = next(i for i, n in enumerate(names) if "fact" in n)
    assert all("dim" in n or "unknown" in n for n in names[:first_fact])


def test_logical_foreign_keys_reference_real_tables_and_columns():
    for fact, column, dim in LOGICAL_FOREIGN_KEYS:
        assert fact in DW_TABLES and dim in DW_TABLES
        block = DDL[DDL.index(f"dw.{fact} ("):]
        assert re.search(rf"\n\s+{column}\s", block.split(");")[0]), (fact, column)


def test_warehouse_sql_has_no_stray_percent_signs():
    # SQL files are executed with psycopg2 parameters: a lone '%' would break interpolation.
    for path in warehouse_sql_files():
        text = re.sub(r"%\(as_of\)s", "", path.read_text(encoding="utf-8"))
        assert "%" not in text, path.name


# ---------------------------------------------------------------- loaded warehouse
@pytest.fixture
def cur(engine):
    """Cursor on a connection that is always rolled back."""
    conn = engine.raw_connection()
    with conn.cursor() as c:
        c.execute("SELECT count(*) FROM dw.fact_sales")
        if c.fetchone()[0] == 0:
            conn.close()
            pytest.skip("warehouse is empty - run scripts/run_pipeline.py first")
        yield c
    conn.rollback()
    conn.close()


def scalar(cur, sql, params=None):
    cur.execute(sql, params or {})
    return cur.fetchone()[0]


@pytest.mark.db
def test_current_warehouse_passes_all_critical_checks(cur):
    results = run_checks(cur, warehouse_checks(), AS_OF)
    assert not critical_failures(results), [r.message for r in critical_failures(results)]


@pytest.mark.db
def test_unknown_members_exist_in_every_dimension(cur):
    for dim, key in [("dim_branch", "branch_key"), ("dim_category", "category_key"), ("dim_product", "product_key"),
                     ("dim_customer", "customer_key"), ("dim_vehicle", "vehicle_key"), ("dim_employee", "employee_key")]:
        assert scalar(cur, f"SELECT count(*) FROM dw.{dim} WHERE {key} = -1") == 1, dim
    assert scalar(cur, "SELECT product_name FROM dw.dim_product WHERE product_key = -2") == "Labour (no product)"


@pytest.mark.db
def test_date_dimension_is_complete_and_flags_holidays(cur):
    assert scalar(cur, "SELECT count(*) FROM dw.dim_date") == (date(2027, 12, 31) - date(2016, 1, 1)).days + 1
    assert scalar(cur, "SELECT holiday_name FROM dw.dim_date WHERE date_key = 20250107") == "Orthodox Christmas"
    assert scalar(cur, "SELECT day_name FROM dw.dim_date WHERE date_key = 20251005") == "Sunday"
    assert scalar(cur, "SELECT is_weekend FROM dw.dim_date WHERE date_key = 20251005") is True


@pytest.mark.db
def test_sales_measures_are_derived_consistently(cur):
    bad = scalar(cur, """SELECT count(*) FROM dw.fact_sales
                         WHERE net_amount <> gross_amount - discount_amount
                            OR profit_amount <> net_amount - cost_amount
                            OR gross_amount <> ROUND(quantity * unit_price, 2)
                            OR is_revenue_recognized <> (order_status = 'completed')""")
    assert bad == 0


@pytest.mark.db
def test_service_order_grain_aggregates_its_lines(cur):
    bad = scalar(cur, """SELECT count(*) FROM dw.fact_service_orders o
                         LEFT JOIN (SELECT service_order_id, count(*) n, sum(revenue_amount) r
                                    FROM dw.fact_service_items GROUP BY 1) i USING (service_order_id)
                         WHERE o.item_count <> COALESCE(i.n, 0)
                            OR abs(o.total_revenue - COALESCE(i.r, 0)) > 0.01""")
    assert bad == 0


@pytest.mark.db
def test_labour_lines_use_not_applicable_members(cur):
    assert scalar(cur, "SELECT count(*) FROM dw.fact_service_items WHERE item_type = 'labor' "
                       "AND (product_key <> -2 OR category_key <> -2)") == 0


@pytest.mark.db
def test_master_data_gaps_map_to_unknown_instead_of_losing_sales(cur):
    # The product with an invalid category was kept by policy: its sales are present with category -1.
    orphan_products = scalar(cur, """SELECT count(*) FROM staging.products p WHERE NOT EXISTS
                                     (SELECT 1 FROM staging.product_categories c WHERE c.category_id = p.category_id)""")
    if orphan_products == 0:
        pytest.skip("dataset has no product with an unknown category")
    assert scalar(cur, "SELECT count(*) FROM dw.fact_sales WHERE category_key = -1") > 0
    assert scalar(cur, "SELECT count(*) FROM dw.fact_sales") == scalar(cur, "SELECT count(*) FROM staging.sales")


@pytest.mark.db
def test_scd2_creates_versions_and_facts_use_point_in_time_lookup(cur):
    sql = {n: (WAREHOUSE_SQL_DIR / n).read_text(encoding="utf-8")
           for n in ("04_dim_customer_scd2.sql", "05_fact_sales.sql")}
    cur.execute("SELECT customer_id FROM staging.sales GROUP BY 1 ORDER BY count(*) DESC LIMIT 1")
    customer = cur.fetchone()[0]
    p = {"c": customer, "as_of": date(2025, 6, 1)}

    cur.execute("UPDATE staging.customers SET city = 'Zugdidi', loyalty_tier = 'silver' WHERE customer_id = %(c)s", p)
    cur.execute(sql["04_dim_customer_scd2.sql"], p)
    cur.execute("SELECT city, loyalty_tier, valid_from, valid_to, is_current FROM dw.dim_customer "
                "WHERE customer_id = %(c)s ORDER BY valid_from", p)
    old, new = cur.fetchall()
    assert old[2:] == (date(1900, 1, 1), date(2025, 5, 31), False)
    assert new == ("Zugdidi", "silver", date(2025, 6, 1), date(9999, 12, 31), True)

    # Re-running the same load is a no-op; a second change on the same day updates in place.
    cur.execute(sql["04_dim_customer_scd2.sql"], p)
    assert scalar(cur, "SELECT count(*) FROM dw.dim_customer WHERE customer_id = %(c)s", p) == 2
    cur.execute("UPDATE staging.customers SET loyalty_tier = 'gold' WHERE customer_id = %(c)s", p)
    cur.execute(sql["04_dim_customer_scd2.sql"], p)
    assert scalar(cur, "SELECT count(*) FROM dw.dim_customer WHERE customer_id = %(c)s", p) == 2
    assert scalar(cur, "SELECT loyalty_tier FROM dw.dim_customer WHERE customer_id = %(c)s AND is_current", p) == "gold"

    cur.execute(sql["05_fact_sales.sql"], p)
    wrong_version = scalar(cur, """
        SELECT count(*) FROM dw.fact_sales f JOIN dw.dim_customer d ON d.customer_key = f.customer_key
        WHERE d.customer_id = %(c)s AND NOT (f.sale_datetime::date BETWEEN d.valid_from AND d.valid_to)""", p)
    assert wrong_version == 0
    assert scalar(cur, """SELECT count(DISTINCT f.customer_key) FROM dw.fact_sales f
                          JOIN dw.dim_customer d ON d.customer_key = f.customer_key
                          WHERE d.customer_id = %(c)s""", p) == 2


@pytest.mark.db
def test_rebuild_is_idempotent_with_stable_surrogate_keys(cur):
    key_sql = "SELECT md5(string_agg(product_id || ':' || product_key, ',' ORDER BY product_id)) FROM dw.dim_product"
    keys_before = scalar(cur, key_sql)
    first = build_warehouse(cur.connection, AS_OF)
    second = build_warehouse(cur.connection, AS_OF)
    assert first == second
    assert scalar(cur, key_sql) == keys_before
