"""Inspect the database without needing psql.

Usage:
    python scripts/inspect_database.py                         # tables + row counts per schema
    python scripts/inspect_database.py --table staging.sales   # columns and constraints
    python scripts/inspect_database.py --query "SELECT ..."    # ad-hoc READ-ONLY query

Queries run inside a READ ONLY transaction, so they cannot modify data.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.db import PROJECT_SCHEMAS, get_engine  # noqa: E402

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)
pd.set_option("display.max_colwidth", 60)


def read_only(engine, sql: str, params: dict | None = None) -> pd.DataFrame:
    with engine.connect() as conn:
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        result = conn.execute(text(sql), params or {})
        return pd.DataFrame(result.fetchall(), columns=list(result.keys()))


def overview(engine) -> None:
    tables = read_only(engine, """
        SELECT table_schema, table_name, table_type
        FROM information_schema.tables
        WHERE table_schema = ANY(:schemas)
        ORDER BY table_schema, table_type, table_name
    """, {"schemas": list(PROJECT_SCHEMAS)})
    if tables.empty:
        print("No project tables found. Run: python scripts/setup_database.py")
        return
    counts = []
    for row in tables.itertuples():
        n = read_only(engine, f'SELECT count(*) AS n FROM "{row.table_schema}"."{row.table_name}"')["n"][0]
        counts.append(n)
    tables["rows"] = counts
    tables["table_type"] = tables["table_type"].map({"BASE TABLE": "table", "VIEW": "view"})
    for schema in PROJECT_SCHEMAS:
        part = tables[tables.table_schema == schema]
        print(f"\n[{schema}]" + ("  (empty)" if part.empty else ""))
        if not part.empty:
            print(part[["table_name", "table_type", "rows"]].to_string(index=False))


def describe(engine, qualified: str) -> None:
    schema, _, table = qualified.partition(".")
    if not table:
        sys.exit("Use schema.table, e.g. staging.sales")
    cols = read_only(engine, """
        SELECT column_name, data_type, is_nullable AS nullable, column_default AS default_value
        FROM information_schema.columns
        WHERE table_schema = :s AND table_name = :t ORDER BY ordinal_position
    """, {"s": schema, "t": table})
    if cols.empty:
        sys.exit(f"Table {qualified} not found.")
    print(f"\nColumns of {qualified}:\n" + cols.to_string(index=False))
    cons = read_only(engine, """
        SELECT con.conname AS constraint_name,
               CASE con.contype WHEN 'p' THEN 'PRIMARY KEY' WHEN 'f' THEN 'FOREIGN KEY'
                                WHEN 'u' THEN 'UNIQUE' WHEN 'c' THEN 'CHECK' END AS type,
               pg_get_constraintdef(con.oid) AS definition
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        WHERE nsp.nspname = :s AND rel.relname = :t AND con.contype IN ('p', 'f', 'u', 'c')
        ORDER BY type, constraint_name
    """, {"s": schema, "t": table})
    print(f"\nConstraints of {qualified}:\n" + (cons.to_string(index=False) if not cons.empty else "(none)"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--table", help="schema.table to describe")
    group.add_argument("--query", help="read-only SQL query to run")
    args = parser.parse_args()

    engine = get_engine()
    if args.table:
        describe(engine, args.table)
    elif args.query:
        df = read_only(engine, args.query)
        print(df.to_string(index=False) if not df.empty else "(no rows)")
        print(f"\n({len(df)} rows)")
    else:
        overview(engine)
    return 0


if __name__ == "__main__":
    sys.exit(main())
