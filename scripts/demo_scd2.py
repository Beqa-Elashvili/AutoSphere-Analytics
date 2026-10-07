"""Demonstrate SCD Type 2 on dim_customer without changing any data.

Scenario: a customer moves to Batumi and is upgraded to 'platinum'. The change is
detected by a warehouse load "as of" 2025-06-01. Everything runs in one transaction
that is ROLLED BACK at the end, so the database is left untouched.

Usage:
    python scripts/demo_scd2.py                 # busiest non-platinum customer outside Batumi
    python scripts/demo_scd2.py --customer CUS00042
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from common.db import get_engine  # noqa: E402
from etl.load.warehouse_loader import WAREHOUSE_SQL_DIR  # noqa: E402

CHANGE_DATE = date(2025, 6, 1)


def show(cur, title: str, sql: str, params: dict) -> None:
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    print(f"\n{title}")
    print("  " + " | ".join(f"{c:>14s}" for c in cols))
    for r in rows:
        print("  " + " | ".join(f"{str(v):>14s}" for v in r))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--customer")
    args = parser.parse_args()

    conn = get_engine().raw_connection()
    try:
        with conn.cursor() as cur:
            customer = args.customer
            if not customer:
                cur.execute("SELECT s.customer_id FROM staging.sales s JOIN staging.customers c USING (customer_id) "
                            "WHERE c.loyalty_tier <> 'platinum' AND c.city <> 'Batumi' "
                            "GROUP BY s.customer_id ORDER BY count(*) DESC LIMIT 1")
                customer = cur.fetchone()[0]
            p = {"c": customer, "as_of": CHANGE_DATE}

            versions = ("SELECT customer_key, city, loyalty_tier, valid_from, valid_to, is_current "
                        "FROM dw.dim_customer WHERE customer_id = %(c)s ORDER BY valid_from")
            show(cur, f"BEFORE: versions of {customer}", versions, p)

            print(f"\n>>> Source change: {customer} moves to Batumi and becomes platinum "
                  f"(detected by the load of {CHANGE_DATE})")
            cur.execute("UPDATE staging.customers SET city = 'Batumi', loyalty_tier = 'platinum' "
                        "WHERE customer_id = %(c)s", p)
            for name in ("04_dim_customer_scd2.sql", "05_fact_sales.sql"):
                cur.execute((WAREHOUSE_SQL_DIR / name).read_text(encoding="utf-8"), p)

            show(cur, "AFTER: old version closed, new version opened", versions, p)
            show(cur, "Point-in-time lookup: each sale keeps the version valid on its date",
                 "SELECT d.customer_key, d.city, d.loyalty_tier, min(f.sale_datetime)::date AS first_sale, "
                 "max(f.sale_datetime)::date AS last_sale, count(*) AS sales_lines, sum(f.net_amount) AS revenue "
                 "FROM dw.fact_sales f JOIN dw.dim_customer d ON d.customer_key = f.customer_key "
                 "WHERE d.customer_id = %(c)s GROUP BY 1, 2, 3 ORDER BY 4", p)
    finally:
        conn.rollback()
        conn.close()
    print("\nTransaction rolled back - the warehouse is unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
