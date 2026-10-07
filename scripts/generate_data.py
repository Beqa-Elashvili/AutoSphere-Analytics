"""Generate the synthetic raw datasets for AutoSphere Analytics.

Usage:
    python scripts/generate_data.py                 # full size, seed from RANDOM_SEED (default 42)
    python scripts/generate_data.py --scale 0.1     # 10% size for quick experiments
    python scripts/generate_data.py --seed 7

Outputs:
    data/raw/*.csv                         11 raw source files WITH injected data-quality issues
    data/raw/_generation_manifest.json     what was injected, per table and issue type
    data/evaluation/feedback_labels.csv    ground-truth sentiment/topic (for AI evaluation only)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")  # Georgian text on Windows consoles

from common.config import PROJECT_ROOT, load_settings  # noqa: E402
from common.logging_config import get_logger  # noqa: E402
from datagen.corrupt import ISSUE_CATALOG, inject_quality_issues  # noqa: E402
from datagen.generate import generate_clean_datasets  # noqa: E402

log = get_logger("generate_data")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=None, help="random seed (default: RANDOM_SEED or 42)")
    parser.add_argument("--scale", type=float, default=1.0, help="volume multiplier (default 1.0)")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "raw")
    args = parser.parse_args()
    seed = args.seed if args.seed is not None else load_settings().random_seed

    started = time.time()
    log.info("Generating clean datasets (seed=%s, scale=%s)...", seed, args.scale)
    clean = generate_clean_datasets(seed=seed, scale=args.scale)
    log.info("Injecting data-quality issues...")
    raw, manifest = inject_quality_issues(clean, seed=seed)

    args.output.mkdir(parents=True, exist_ok=True)
    for table, df in raw.items():
        df.to_csv(args.output / f"{table}.csv", index=False, encoding="utf-8")

    eval_dir = PROJECT_ROOT / "data" / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    clean["_feedback_labels"].to_csv(eval_dir / "feedback_labels.csv", index=False, encoding="utf-8")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": seed,
        "scale": args.scale,
        "tables": {
            t: {"clean_rows": len(clean[t]), "raw_rows": len(raw[t]), "injected_issues": manifest.get(t, {})}
            for t in raw
        },
        "issue_catalog": {k: {"description": d, "expected_handling": h} for k, (d, h) in ISSUE_CATALOG.items()},
    }
    (args.output / "_generation_manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\n{'table':20s} {'clean':>8s} {'raw':>8s} {'issues':>8s}")
    for t, info in summary["tables"].items():
        print(f"{t:20s} {info['clean_rows']:8d} {info['raw_rows']:8d} {sum(info['injected_issues'].values()):8d}")
    log.info("Wrote %d files to %s in %.1fs", len(raw), args.output, time.time() - started)
    return 0


if __name__ == "__main__":
    sys.exit(main())
