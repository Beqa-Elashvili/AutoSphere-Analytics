"""Project-wide logging: console + rotating file in logs/autosphere.log."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from common.config import PROJECT_ROOT, load_settings

_CONFIGURED = False
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def get_logger(name: str) -> logging.Logger:
    global _CONFIGURED
    if not _CONFIGURED:
        try:
            level = load_settings().log_level
        except Exception:  # noqa: BLE001 - logging must never break on bad config
            level = "INFO"
        log_dir = PROJECT_ROOT / "logs"
        log_dir.mkdir(exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "autosphere.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
        console = logging.StreamHandler()
        for handler in (file_handler, console):
            handler.setFormatter(logging.Formatter(LOG_FORMAT, "%Y-%m-%d %H:%M:%S"))
        root = logging.getLogger("autosphere")
        root.setLevel(level)
        root.addHandler(file_handler)
        root.addHandler(console)
        _CONFIGURED = True
    return logging.getLogger(f"autosphere.{name}")
