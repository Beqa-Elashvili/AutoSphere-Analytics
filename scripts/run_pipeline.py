"""Run the AutoSphere ETL pipeline.

Usage:
    python scripts/run_pipeline.py                     # full run, loads PostgreSQL
    python scripts/run_pipeline.py --dry-run           # extract + clean only, no database writes
    python scripts/run_pipeline.py --as-of 2026-09-30  # override the "today" used for future-date checks

Exit code 0 = success, 1 = failure (details in logs/autosphere.log and audit.pipeline_runs).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")  # Georgian text on Windows consoles

from etl.pipeline import RAW_DIR, run_pipeline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="do not write to the database")
    parser.add_argument("--as-of", type=date.fromisoformat, default=None, help="reference date (YYYY-MM-DD)")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--triggered-by", default="manual", choices=["manual", "scheduler", "ci"])
    args = parser.parse_args()

    try:
        result = run_pipeline(raw_dir=args.raw_dir, as_of=args.as_of, load=not args.dry_run,
                              triggered_by=args.triggered_by)
    except Exception:
        return 1

    print(f"\n{'table':20s} {'raw':>7s} {'clean':>7s} {'rejected':>8s}  top rejection reasons")
    for table, r in result.results.items():
        top = ", ".join(f"{k}={v}" for k, v in list(r.rejected_by_reason.items())[:3])
        print(f"{table:20s} {result.raw_rows[table]:7d} {len(r.clean):7d} {len(r.rejected):8d}  {top}")
    if result.run_id:
        print(f"\nrun_id={result.run_id}  status={result.status}  duration={result.duration_s:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
