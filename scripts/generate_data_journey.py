"""Generate the visual Data Journey page (Georgian + English) for demos.

Follows the data from the raw CSV files to business answers on one self-contained HTML page:
lineage per table, real before/after examples, quarantine reasons, quality gates, star schema,
revenue reconciliation and the key findings. Works offline; no paid API calls.

Usage:
    python scripts/generate_data_journey.py
    start reports\\data_journey.html          # Windows: open in the browser

Requires a completed pipeline run (python scripts/run_pipeline.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from common.config import PROJECT_ROOT  # noqa: E402
from common.db import get_engine  # noqa: E402
from reporting.journey import collect, render  # noqa: E402

OUT = PROJECT_ROOT / "reports" / "data_journey.html"


def main() -> int:
    conn = get_engine().raw_connection()
    try:
        data = collect(conn)
    finally:
        conn.rollback()
        conn.close()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(render(data), encoding="utf-8")
    raw = sum(r["raw"] for r in data["lineage"])
    clean = sum(r["clean"] for r in data["lineage"])
    quarantined = sum(r["quarantined"] for r in data["lineage"])
    print(f"Pipeline run {data['run_id']}: {raw:,} raw = {clean:,} clean + {quarantined:,} quarantined")
    print(f"Written to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
