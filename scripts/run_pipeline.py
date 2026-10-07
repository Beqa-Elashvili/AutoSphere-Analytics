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

from common.config import load_settings  # noqa: E402
from etl.pipeline import RAW_DIR, run_pipeline  # noqa: E402
from etl.validation.checks import DataQualityError  # noqa: E402
from etl.validation.report import format_table, summarize  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="do not write to the database")
    parser.add_argument("--as-of", type=date.fromisoformat, default=None, help="reference date (YYYY-MM-DD)")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--triggered-by", default="manual", choices=["manual", "scheduler", "ci"])
    parser.add_argument("--ai-provider", choices=["local", "gemini"],
                        help="override AI_PROVIDER for this run (gemini uses the key/model from .env)")
    args = parser.parse_args()
    settings = load_settings()
    if args.ai_provider:
        settings = settings.with_provider(args.ai_provider)

    try:
        result = run_pipeline(raw_dir=args.raw_dir, as_of=args.as_of, load=not args.dry_run,
                              triggered_by=args.triggered_by, settings=settings)
    except DataQualityError as exc:
        print(f"\nPIPELINE STOPPED BY DATA QUALITY GATE\n{format_table(exc.failures)}")
        return 1
    except Exception:
        return 1

    print(f"\n{'table':20s} {'raw':>7s} {'clean':>7s} {'rejected':>8s}  top rejection reasons")
    for table, r in result.results.items():
        top = ", ".join(f"{k}={v}" for k, v in list(r.rejected_by_reason.items())[:3])
        print(f"{table:20s} {result.raw_rows[table]:7d} {len(r.clean):7d} {len(r.rejected):8d}  {top}")
    print(f"\nData quality: {summarize(result.dq_results)}")
    print("Findings (WARNING / CRITICAL):")
    print(format_table([r for r in result.dq_results if r.severity != "INFO"], only_failures=True))
    if result.ai is not None:
        print(f"\nNLP: mode={result.ai.mode} pending={result.ai.pending} classified={result.ai.classified} "
              f"by_method={result.ai.by_method} {result.ai.provider_stats or ''}")
        print(f"AI insights generated: {result.insights}")
    if result.run_id:
        print(f"\nrun_id={result.run_id}  status={result.status}  duration={result.duration_s:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
