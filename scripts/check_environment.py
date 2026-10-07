"""Verify the local environment is ready to run AutoSphere Analytics.

Usage:  python scripts/check_environment.py

Checks Python version, required packages, configuration, database
connectivity and which AI mode is active. Never prints secret values.
Exit code 0 = ready, 1 = at least one required check failed.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config import ConfigError, load_settings, mask_url  # noqa: E402

REQUIRED_PACKAGES = ["pandas", "numpy", "sqlalchemy", "psycopg2", "dotenv", "pytest"]
OPTIONAL_PACKAGES = {"google.genai": "needed only when AI_PROVIDER=gemini"}

failures = 0


def report(ok: bool, label: str, detail: str = "", required: bool = True) -> None:
    global failures
    status = "OK  " if ok else ("FAIL" if required else "WARN")
    if not ok and required:
        failures += 1
    print(f"  [{status}] {label}" + (f" - {detail}" if detail else ""))


def main() -> int:
    print("AutoSphere Analytics - environment check\n")

    print("Python")
    report(sys.version_info >= (3, 10), "Python >= 3.10", sys.version.split()[0])

    print("\nPackages")
    for pkg in REQUIRED_PACKAGES:
        try:
            mod = importlib.import_module(pkg)
            report(True, pkg, getattr(mod, "__version__", ""))
        except ImportError:
            report(False, pkg, "missing - run: pip install -r requirements.txt")
    for pkg, why in OPTIONAL_PACKAGES.items():
        try:
            importlib.import_module(pkg)
            report(True, pkg)
        except ImportError:
            report(False, pkg, why, required=False)

    print("\nConfiguration")
    try:
        settings = load_settings()
    except ConfigError as exc:
        report(False, "settings", str(exc))
        return 1
    report(settings.has_database, "database URL", mask_url(settings.database_url))
    report(True, "DB_SSLMODE", settings.db_sslmode)
    ai_detail = (
        f"external provider={settings.ai_provider}, model={settings.ai_model}"
        if settings.ai_mode == "external"
        else "local rule-based classifier (no API calls)"
    )
    report(True, "AI mode", ai_detail)
    if settings.ai_mode == "local" and settings.ai_api_key:
        print("         note: an API key is present but AI_PROVIDER is empty, so local mode is used.")

    print("\nDatabase connectivity")
    if settings.has_database:
        try:
            from common.db import get_engine, server_info

            info = server_info(get_engine(settings))
            report(True, "PostgreSQL reachable",
                   f"version {info['version']}, database '{info['database']}'")
        except Exception as exc:  # noqa: BLE001 - surface any driver/network error
            report(False, "PostgreSQL reachable", f"{type(exc).__name__}: {str(exc)[:150]}")
    else:
        report(False, "PostgreSQL reachable", "skipped (no database URL)")

    print("\nResult:", "READY" if failures == 0 else f"{failures} required check(s) failed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
