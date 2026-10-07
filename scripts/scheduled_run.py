"""Scheduled job: refresh the data, then publish the management report.

This is the command Windows Task Scheduler, cron or GitHub Actions runs (docs/automated-reporting.md).

Usage:
    python scripts/scheduled_run.py                       # pipeline (local AI rules) + report
    python scripts/scheduled_run.py --ai-provider gemini  # opt in to Gemini (PAID; only new feedback is sent)

Exit codes: 0 success · 1 pipeline failed (report still produced) · 2 report failed · 3 already running
Status of the last run: reports/last_run.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from common.config import load_settings  # noqa: E402
from reporting.job import run_job  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ai-provider", choices=["local", "gemini"], default="local",
                        help="default local: an unattended job never spends API credit unless asked to")
    parser.add_argument("--retries", type=int, default=1, help="retries after a connection error (default 1)")
    parser.add_argument("--retry-delay", type=float, default=30, help="seconds between retries (default 30)")
    args = parser.parse_args()

    settings = load_settings().with_provider(args.ai_provider)
    return run_job(settings, retries=args.retries, retry_delay_s=args.retry_delay)


if __name__ == "__main__":
    sys.exit(main())
