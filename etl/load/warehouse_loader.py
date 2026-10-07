"""ELT step: build the star schema from staging with set-based SQL.

The SQL files in database/warehouse/ run in filename order inside the caller's
transaction: date dimension -> unknown members -> SCD1 dimensions -> SCD2 customer
dimension -> facts.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from common.config import PROJECT_ROOT

WAREHOUSE_SQL_DIR = PROJECT_ROOT / "database" / "warehouse"
DW_TABLES = [
    "dim_date", "dim_branch", "dim_category", "dim_product", "dim_customer", "dim_vehicle", "dim_employee",
    "fact_sales", "fact_service_orders", "fact_service_items", "fact_payments", "fact_customer_feedback",
]


def warehouse_sql_files(directory: Path = WAREHOUSE_SQL_DIR) -> list[Path]:
    return sorted(directory.glob("*.sql"))


def build_warehouse(conn, as_of: date) -> dict[str, int]:
    """Run every warehouse SQL file; return row counts per dw table."""
    with conn.cursor() as cur:
        for path in warehouse_sql_files():
            cur.execute(path.read_text(encoding="utf-8"), {"as_of": as_of})
        counts = {}
        for table in DW_TABLES:
            cur.execute(f"SELECT count(*) FROM dw.{table}")
            counts[f"dw.{table}"] = cur.fetchone()[0]
    return counts
