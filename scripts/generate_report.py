"""Generate the management report from the current database (no pipeline run).

Usage:
    python scripts/generate_report.py
    python scripts/generate_report.py --as-of 2026-10-07

Writes reports/management/management_report_<date>.html + .md and reports/management/latest.html.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from common.config import load_settings  # noqa: E402
from common.db import get_engine  # noqa: E402
from reporting.job import generate_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today(), help="report date (YYYY-MM-DD)")
    args = parser.parse_args()

    settings = load_settings()
    html_path, md_path, alerts = generate_report(get_engine(settings), args.as_of,
                                                 stale_data_days=settings.stale_data_days)
    print(f"Alerts ({len(alerts)}):")
    for a in alerts:
        print(f"  {a.severity:8s} {a.area:18s} {a.message}")
    print(f"\nHTML:     {html_path}\nMarkdown: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
