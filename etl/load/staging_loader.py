"""Load: full refresh of the staging schema using PostgreSQL COPY.

The caller owns the transaction. TRUNCATE + COPY of all tables happen in one
transaction, so a failed load leaves the previous staging data untouched.
"""
from __future__ import annotations

import io

import pandas as pd

from etl.sources import LOAD_ORDER


def copy_frame(cursor, qualified_table: str, df: pd.DataFrame) -> int:
    """Bulk-insert a DataFrame with COPY (much faster than row-by-row INSERTs)."""
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="", date_format="%Y-%m-%d %H:%M:%S")
    buf.seek(0)
    columns = ", ".join(df.columns)
    cursor.copy_expert(f"COPY {qualified_table} ({columns}) FROM STDIN WITH (FORMAT csv, NULL '')", buf)
    return len(df)


def load_staging(conn, clean_frames: dict[str, pd.DataFrame]) -> dict[str, int]:
    """Replace the contents of every staging table. Returns rows loaded per table."""
    with conn.cursor() as cur:
        cur.execute("TRUNCATE " + ", ".join(f"staging.{t}" for t in LOAD_ORDER))
        counts = {f"staging.{t}": copy_frame(cur, f"staging.{t}", clean_frames[t]) for t in LOAD_ORDER}
        # Fresh statistics so the planner picks good join plans for checks and the warehouse build.
        cur.execute("ANALYZE " + ", ".join(f"staging.{t}" for t in LOAD_ORDER))
        return counts
