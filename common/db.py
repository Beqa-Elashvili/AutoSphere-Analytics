"""PostgreSQL connectivity (SQLAlchemy engine factory)."""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from common.config import ConfigError, Settings, load_settings


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
