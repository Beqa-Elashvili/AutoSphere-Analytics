"""Shared pytest fixtures."""
import pytest

from common.config import load_settings


@pytest.fixture(scope="session")
def engine():
    """A live database engine, or skip DB tests when no database is reachable."""
    settings = load_settings()
    if not settings.has_database:
        pytest.skip("No DATABASE_URL configured")
    from common.db import get_engine

    eng = get_engine(settings)
    try:
        with eng.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Database not reachable: {exc}")
    yield eng
    eng.dispose()
