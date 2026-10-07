"""Database schema tests: objects exist, setup is idempotent, constraints reject bad data."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from common.db import PROJECT_SCHEMAS, apply_schema, schema_files

STAGING_TABLES = {
    "branches", "product_categories", "products", "employees", "customers", "vehicles",
    "sales", "service_orders", "service_items", "payments", "customer_feedback",
}
AUDIT_TABLES = {"pipeline_runs", "data_quality_report", "rejected_rows"}


def test_schema_files_run_in_numeric_order():
    names = [p.name for p in schema_files()]
    assert names == sorted(names)
    assert names[0].startswith("00_"), "schemas must be created before tables"


@pytest.mark.db
def test_setup_is_idempotent(engine):
    # Running the DDL twice must not fail or duplicate anything.
    apply_schema(engine)
    apply_schema(engine)


def _tables(engine, schema):
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"), {"s": schema}
        )
        return {r[0] for r in rows}


@pytest.mark.db
def test_project_schemas_exist(engine):
    with engine.connect() as conn:
        existing = {r[0] for r in conn.execute(text("SELECT schema_name FROM information_schema.schemata"))}
    assert set(PROJECT_SCHEMAS) <= existing


@pytest.mark.db
def test_all_staging_tables_exist(engine):
    assert STAGING_TABLES <= _tables(engine, "staging")


@pytest.mark.db
def test_audit_tables_exist(engine):
    assert AUDIT_TABLES <= _tables(engine, "audit")


VALID_SALE = dict(
    sale_line_id="TEST-1", invoice_number="INV-T", sale_datetime="2025-01-15 10:00",
    customer_id="C", product_id="P", branch_id="B", employee_id="E",
    quantity=2, unit_price=100, unit_cost=60, discount_amount=0,
    sales_channel="in_store", order_status="completed",
)


def _insert_sale(conn, **overrides):
    row = {**VALID_SALE, **overrides}
    cols = ", ".join(row)
    vals = ", ".join(f":{k}" for k in row)
    conn.execute(text(f"INSERT INTO staging.sales ({cols}) VALUES ({vals})"), row)


@pytest.fixture
def rollback_conn(engine):
    """Connection whose work is always rolled back — tests leave no data behind."""
    conn = engine.connect()
    trans = conn.begin()
    yield conn
    trans.rollback()
    conn.close()


@pytest.mark.db
def test_valid_sale_is_accepted(rollback_conn):
    _insert_sale(rollback_conn)


@pytest.mark.db
@pytest.mark.parametrize("overrides, reason", [
    ({"quantity": -1}, "negative quantity"),
    ({"quantity": 0}, "zero quantity"),
    ({"unit_price": -5}, "negative price"),
    ({"discount_amount": 500}, "discount larger than line value"),
    ({"sales_channel": "In Store"}, "non-canonical category value"),
    ({"order_status": "done"}, "unknown status"),
    ({"customer_id": None}, "missing customer"),
])
def test_staging_rejects_invalid_sales(rollback_conn, overrides, reason):
    savepoint = rollback_conn.begin_nested()
    with pytest.raises(IntegrityError):
        _insert_sale(rollback_conn, **overrides)
    savepoint.rollback()


@pytest.mark.db
def test_duplicate_business_key_is_rejected(rollback_conn):
    _insert_sale(rollback_conn)
    savepoint = rollback_conn.begin_nested()
    with pytest.raises(IntegrityError):
        _insert_sale(rollback_conn)  # same sale_line_id
    savepoint.rollback()


@pytest.mark.db
def test_part_line_requires_product(rollback_conn):
    savepoint = rollback_conn.begin_nested()
    with pytest.raises(IntegrityError):
        rollback_conn.execute(text("""
            INSERT INTO staging.service_items
                (service_item_id, service_order_id, item_type, product_id, description, quantity, unit_price, unit_cost)
            VALUES ('SI-T', 'SO-T', 'part', NULL, 'Brake pads', 1, 100, 50)
        """))
    savepoint.rollback()


@pytest.mark.db
def test_completed_service_order_requires_close_time(rollback_conn):
    savepoint = rollback_conn.begin_nested()
    with pytest.raises(IntegrityError):
        rollback_conn.execute(text("""
            INSERT INTO staging.service_orders
                (service_order_id, vehicle_id, customer_id, branch_id, employee_id,
                 service_type, opened_at, closed_at, order_status)
            VALUES ('SO-T', 'V', 'C', 'B', 'E', 'repair', '2025-01-10 09:00', NULL, 'completed')
        """))
    savepoint.rollback()


@pytest.mark.db
def test_payments_only_accept_gel(rollback_conn):
    savepoint = rollback_conn.begin_nested()
    with pytest.raises(IntegrityError):
        rollback_conn.execute(text("""
            INSERT INTO staging.payments
                (payment_id, source_type, source_reference, customer_id, payment_datetime,
                 amount, payment_method, payment_status, currency)
            VALUES ('PAY-T', 'sale', 'INV-T', 'C', '2025-01-15 10:05', 100, 'card', 'completed', 'USD')
        """))
    savepoint.rollback()
