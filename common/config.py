"""Central configuration, resolved from environment variables.

Every component (ETL, AI, scripts, tests) reads settings through
``load_settings()`` so there is exactly one place that knows about env var
names, aliases and defaults. Secrets are never hardcoded or logged.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Provider -> default model. Empty AI_PROVIDER (or "local") means offline mode.
SUPPORTED_AI_PROVIDERS: dict[str, str] = {"gemini": "gemini-3.5-flash"}
LOCAL_PROVIDER_ALIASES = {"", "local", "none", "rule_based"}
VALID_SSLMODES = {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}


class ConfigError(ValueError):
    """Raised when the environment is configured inconsistently."""


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    db_sslmode: str
    ai_provider: str          # "local" or an external provider name
    ai_model: str | None
    ai_api_key: str | None
    log_level: str
    random_seed: int
    ai_batch_size: int = 25            # feedback items per external API request
    ai_concurrency: int = 4            # parallel external API requests
    ai_max_external_per_run: int = 20000  # cost guard: max items sent to the provider per run

    @property
    def ai_mode(self) -> str:
        """'external' when a real AI provider is configured, otherwise 'local'."""
        return "local" if self.ai_provider == "local" else "external"

    @property
    def has_database(self) -> bool:
        return bool(self.database_url)

    def with_provider(self, provider: str) -> "Settings":
        """Explicit override (e.g. a CLI flag): use this provider regardless of AI_PROVIDER."""
        provider = provider.lower()
        if provider in LOCAL_PROVIDER_ALIASES:
            return replace(self, ai_provider="local")
        if provider not in SUPPORTED_AI_PROVIDERS:
            raise ConfigError(f"Unsupported provider '{provider}'.")
        if not self.ai_api_key:
            raise ConfigError(f"Provider '{provider}' requires AI_API_KEY (or GEMINI_API_KEY).")
        return replace(self, ai_provider=provider, ai_model=self.ai_model or SUPPORTED_AI_PROVIDERS[provider])


def _first(env: Mapping[str, str], *names: str) -> str | None:
    """Return the first non-empty value among several env var names (aliases)."""
    for name in names:
        value = (env.get(name) or "").strip()
        if value:
            return value
    return None


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build Settings from a mapping (tests) or from .env + os.environ (runtime)."""
    if env is None:
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        env = os.environ

    provider = (_first(env, "AI_PROVIDER") or "").lower()
    if provider in LOCAL_PROVIDER_ALIASES:
        provider = "local"
    elif provider not in SUPPORTED_AI_PROVIDERS:
        raise ConfigError(
            f"Unsupported AI_PROVIDER '{provider}'. "
            f"Use one of {sorted(SUPPORTED_AI_PROVIDERS)} or leave empty for local mode."
        )

    api_key = _first(env, "AI_API_KEY", "GEMINI_API_KEY")
    model = _first(env, "AI_MODEL", "GEMINI_MODEL")
    if provider != "local":
        # An explicitly requested provider without a key is a misconfiguration;
        # silently falling back would hide the problem.
        if not api_key:
            raise ConfigError(f"AI_PROVIDER='{provider}' requires AI_API_KEY (or GEMINI_API_KEY).")
        model = model or SUPPORTED_AI_PROVIDERS[provider]

    sslmode = (_first(env, "DB_SSLMODE") or "prefer").lower()
    if sslmode not in VALID_SSLMODES:
        raise ConfigError(f"Invalid DB_SSLMODE '{sslmode}'. Use one of {sorted(VALID_SSLMODES)}.")

    seed_raw = _first(env, "RANDOM_SEED") or "42"
    try:
        seed = int(seed_raw)
    except ValueError as exc:
        raise ConfigError(f"RANDOM_SEED must be an integer, got '{seed_raw}'.") from exc

    return Settings(
        database_url=_first(env, "DATABASE_URL", "POSTGRESQL_URL"),
        db_sslmode=sslmode,
        ai_provider=provider,
        ai_model=model,
        ai_api_key=api_key,
        log_level=(_first(env, "LOG_LEVEL") or "INFO").upper(),
        random_seed=seed,
        ai_batch_size=_positive_int(env, "AI_BATCH_SIZE", 25),
        ai_concurrency=_positive_int(env, "AI_CONCURRENCY", 4),
        ai_max_external_per_run=_positive_int(env, "AI_MAX_EXTERNAL_PER_RUN", 20000),
    )


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = _first(env, name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got '{raw}'.") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be positive, got {value}.")
    return value


def mask_url(url: str | None) -> str:
    """Hide the password in a connection URL so it can be printed or logged safely."""
    if not url:
        return "<not set>"
    parts = urlsplit(url)
    if parts.password is None:
        return url
    netloc = parts.netloc.replace(f":{parts.password}@", ":***@", 1)
    return urlunsplit(parts._replace(netloc=netloc))
