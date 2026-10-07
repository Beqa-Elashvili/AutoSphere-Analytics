"""Create (or reset) the AutoSphere database schemas and tables.

Usage:
    python scripts/setup_database.py               # create missing objects (idempotent)
    python scripts/setup_database.py --reset --yes # DROP project schemas, then recreate

Only the project's own schemas (staging, dw, analytics, audit) are ever dropped.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config import load_settings, mask_url  # noqa: E402
from common.db import PROJECT_SCHEMAS, apply_schema, apply_views, drop_project_schemas, get_engine  # noqa: E402
from common.logging_config import get_logger  # noqa: E402

log = get_logger("setup_database")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="drop and recreate project schemas (deletes their data)")
    parser.add_argument("--yes", action="store_true", help="confirm --reset without prompting")
    args = parser.parse_args()

    settings = load_settings()
    engine = get_engine(settings)
    log.info("Target database: %s", mask_url(settings.database_url))

    if args.reset:
        if not args.yes:
            log.error("--reset deletes all data in schemas %s. Re-run with --reset --yes to confirm.",
                      ", ".join(PROJECT_SCHEMAS))
            return 2
        log.warning("Dropping schemas: %s", ", ".join(PROJECT_SCHEMAS))
        drop_project_schemas(engine)

    for name in apply_schema(engine):
        log.info("Applied %s", name)
    for name in apply_views(engine):
        log.info("Applied views/%s", name)
    log.info("Database schema is up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
