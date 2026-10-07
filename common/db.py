"""PostgreSQL connectivity and schema management."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from common.config import PROJECT_ROOT, ConfigError, Settings, load_settings

SCHEMA_DIR = PROJECT_ROOT / "database" / "schemas"
# Schemas owned by this project. Only these are ever dropped by a reset.
PROJECT_SCHEMAS = ("staging", "dw", "analytics", "audit")


def normalize_url(url: str) -> str:
    """Force the psycopg2 driver; accept Heroku/Render-style 'postgres://' URLs."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


def get_engine(settings: Settings | None = None) -> Engine:
    settings = settings or load_settings()
    if not settings.database_url:
        raise ConfigError("DATABASE_URL (or POSTGRESQL_URL) is not set. See .env.example.")
    return create_engine(
        normalize_url(settings.database_url),
        connect_args={"sslmode": settings.db_sslmode, "connect_timeout": 15},
        pool_pre_ping=True,
    )


def server_info(engine: Engine) -> dict[str, str]:
    """Small connectivity probe used by the environment check."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT current_setting('server_version'), current_database(), current_user")
        ).one()
    return {"version": row[0], "database": row[1], "user": row[2]}


def schema_files(directory: Path = SCHEMA_DIR) -> list[Path]:
    """DDL files in execution order (numeric filename prefix: 00_, 01_, ...)."""
    return sorted(directory.glob("*.sql"))


def run_sql_file(engine: Engine, path: Path) -> None:
    """Execute a (multi-statement) SQL file in a single transaction."""
    sql = path.read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.exec_driver_sql(sql)


def apply_schema(engine: Engine, directory: Path = SCHEMA_DIR) -> list[str]:
    """Create all project schemas/tables. Idempotent (DDL uses IF NOT EXISTS)."""
    applied = []
    for path in schema_files(directory):
        run_sql_file(engine, path)
        applied.append(path.name)
    return applied


def drop_project_schemas(engine: Engine) -> None:
    """Drop ONLY this project's schemas (never `public` or anything else)."""
    with engine.begin() as conn:
        for schema in PROJECT_SCHEMAS:
            conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
