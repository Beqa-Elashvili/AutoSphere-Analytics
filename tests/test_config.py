"""Tests for configuration resolution: aliases, AI mode selection, secret masking."""
import pytest

from common.config import ConfigError, load_settings, mask_url
from common.db import normalize_url


def test_empty_environment_defaults_to_local_ai_and_no_database():
    s = load_settings({})
    assert s.ai_mode == "local"
    assert s.ai_model is None
    assert s.database_url is None
    assert s.db_sslmode == "prefer"
    assert s.random_seed == 42


def test_database_url_takes_precedence_over_alias():
    s = load_settings({"DATABASE_URL": "postgresql://a@h/db1", "POSTGRESQL_URL": "postgresql://b@h/db2"})
    assert s.database_url.endswith("/db1")


def test_postgresql_url_alias_is_accepted():
    s = load_settings({"POSTGRESQL_URL": "postgresql://b@h/db2"})
    assert s.database_url.endswith("/db2")


def test_api_key_without_provider_stays_local():
    # A key alone must not trigger paid API calls; the provider must be explicit.
    s = load_settings({"GEMINI_API_KEY": "secret"})
    assert s.ai_mode == "local"


def test_gemini_provider_uses_alias_key_and_default_model():
    s = load_settings({"AI_PROVIDER": "Gemini", "GEMINI_API_KEY": "secret"})
    assert s.ai_mode == "external"
    assert s.ai_provider == "gemini"
    assert s.ai_api_key == "secret"
    assert s.ai_model  # default model filled in


def test_explicit_model_overrides_default():
    s = load_settings({"AI_PROVIDER": "gemini", "AI_API_KEY": "k", "AI_MODEL": "custom-model"})
    assert s.ai_model == "custom-model"


def test_provider_without_key_is_a_config_error():
    with pytest.raises(ConfigError, match="requires AI_API_KEY"):
        load_settings({"AI_PROVIDER": "gemini"})


def test_unknown_provider_is_rejected():
    with pytest.raises(ConfigError, match="Unsupported AI_PROVIDER"):
        load_settings({"AI_PROVIDER": "unknown-llm", "AI_API_KEY": "k"})


@pytest.mark.parametrize("bad", [{"DB_SSLMODE": "maybe"}, {"RANDOM_SEED": "abc"}])
def test_invalid_values_are_rejected(bad):
    with pytest.raises(ConfigError):
        load_settings(bad)


def test_mask_url_hides_password():
    masked = mask_url("postgresql://user:s3cr3t@db.example.com:5432/app")
    assert "s3cr3t" not in masked
    assert masked == "postgresql://user:***@db.example.com:5432/app"


def test_mask_url_handles_missing_values():
    assert mask_url(None) == "<not set>"
    assert mask_url("postgresql://localhost/app") == "postgresql://localhost/app"


@pytest.mark.parametrize("raw", ["postgres://u:p@h/d", "postgresql://u:p@h/d"])
def test_normalize_url_forces_psycopg2_driver(raw):
    assert normalize_url(raw) == "postgresql+psycopg2://u:p@h/d"


def test_gemini_model_alias_is_accepted():
    s = load_settings({"AI_PROVIDER": "gemini", "GEMINI_API_KEY": "k", "GEMINI_MODEL": "gemini-x"})
    assert s.ai_model == "gemini-x"
