"""Run the analytical SQL queries (business questions and KPI implementations).

Usage:
    python scripts/run_analytics.py --list           # list available queries
    python scripts/run_analytics.py 03               # run by number or name prefix
    python scripts/run_analytics.py declining        # ... or by part of the name
    python scripts/run_analytics.py --all            # run every business question

Queries live in analytics/sql (business questions) and analytics/kpi_queries (KPI
definitions implemented directly on the star schema). They run in a READ ONLY transaction.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from common.config import PROJECT_ROOT  # noqa: E402
from common.db import get_engine  # noqa: E402

QUERY_DIRS = {"business": PROJECT_ROOT / "analytics" / "sql", "kpi": PROJECT_ROOT / "analytics" / "kpi_queries"}
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 30)
pd.set_option("display.max_colwidth", 45)


def all_queries() -> list[tuple[str, Path]]:
    return [(kind, p) for kind, d in QUERY_DIRS.items() for p in sorted(d.glob("*.sql"))]


def header(path: Path) -> str:
    """The leading comment block: business question, KPI, source, decision."""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("--"):
            break
        lines.append(line[2:].strip())
    return "\n".join(lines)


def run(conn, path: Path) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(path.read_text(encoding="utf-8"))
        df = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
    conn.rollback()
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", nargs="?", help="number or part of the query file name")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--all", action="store_true", help="run every business-question query")
    args = parser.parse_args()

    queries = all_queries()
    if args.list or not (args.query or args.all):
        for kind, p in queries:
            first = header(p).splitlines()[0] if header(p) else ""
            print(f"[{kind:8s}] {p.stem:32s} {first}")
        return 0

    if args.all:
        selected = [p for kind, p in queries if kind == "business"]
    else:
        selected = [p for _, p in queries if p.stem.startswith(args.query) or args.query in p.stem]
        if not selected:
            print(f"No query matches '{args.query}'. Use --list.")
            return 1

    conn = get_engine().raw_connection()
    try:
        for path in selected:
            print("=" * 100 + f"\n{path.parent.name}/{path.name}\n{header(path)}\n" + "-" * 100)
            df = run(conn, path)
            print(df.to_string(index=False) if not df.empty else "(no rows)")
            print()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
