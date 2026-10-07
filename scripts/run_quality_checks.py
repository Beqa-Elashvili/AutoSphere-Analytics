"""Run the staging and warehouse data-quality checks against the data in PostgreSQL.

Usage:
    python scripts/run_quality_checks.py            # run checks, store report, show findings
    python scripts/run_quality_checks.py --all      # show every check, including passes
    python scripts/run_quality_checks.py --no-save  # do not write to audit tables

The checks run in a READ ONLY transaction. Exit code 1 if any CRITICAL check fails.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")  # Georgian text on Windows consoles

from common.db import get_engine  # noqa: E402
from etl.load.audit import finish_run, start_run  # noqa: E402
from etl.validation.checks import critical_failures, run_checks  # noqa: E402
from etl.validation.report import format_table, summarize, write_report  # noqa: E402
from etl.validation.rules import post_load_checks, warehouse_checks  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true", help="show passing checks too")
    parser.add_argument("--no-save", action="store_true", help="do not write results to the audit schema")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()

    engine = get_engine()
    conn = engine.raw_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")   # scoped to this transaction only
            results = run_checks(cur, post_load_checks() + warehouse_checks(), args.as_of)
    finally:
        conn.rollback()
        conn.close()

    failures = critical_failures(results)
    if not args.no_save:
        run_id = start_run(engine, "autosphere_quality_checks", "manual")
        write_report(engine, run_id, results)
        finish_run(engine, run_id, "failed" if failures else "success",
                   error=f"{len(failures)} critical check(s) failed" if failures else None)
        print(f"Saved as run_id={run_id} in audit.data_quality_report")

    print(format_table(results, only_failures=not args.all))
    print(f"\n{summarize(results)}")
    print("RESULT:", "FAILED - critical issues found" if failures else "PASSED - no critical issues")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
