"""Environment configuration with fail-fast validation.

Implements Requirements 7.2, 7.5, 12.4, 12.5: all environment-specific settings are
read from the environment, and missing/invalid required values cause startup to fail
with a message naming each problem rather than serving in a broken state.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing or invalid.

    Carries the list of individual problems so the caller (startup) can report
    every missing/invalid value at once (Requirements 7.5, 12.5).
    """

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("Configuration error:\n  - " + "\n  - ".join(problems))


_VALID_PROVIDERS = {"ollama", "groq", "openrouter", "hf", "openai", "gemini"}


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    base_url: str
    chat_model: str
    embed_model: str
    api_credential: str


@dataclass(frozen=True)
class Settings:
    database_url: str
    provider: ProviderConfig
    short_term_n: int
    long_term_memory_enabled: bool
    llm_timeout_seconds: int
    auth_enabled: bool
    api_keys: tuple[str, ...]
    rate_limit_max_requests: int
    rate_limit_window_seconds: int
    persona_dir: Path
    telegram_bot_token: str
    telegram_webhook_secret: str
    # Records non-fatal config issues that fell back to defaults (Requirement 4.6).
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _normalize_database_url(raw: str) -> str:
    """Make a connection string usable by SQLAlchemy's async drivers.

    Neon hands out `postgresql://...?sslmode=require`. asyncpg does not understand
    the libpq `sslmode` query parameter, so we translate it.
    """
    url = raw.strip()
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)

    # asyncpg uses `ssl` not `sslmode`. Strip sslmode and let db.py pass ssl via
    # connect_args when the host looks like a managed (non-local) Postgres.
    if "asyncpg" in url and "sslmode=" in url:
        # remove the sslmode parameter; SSL is enabled in db.py connect_args
        import re

        url = re.sub(r"[?&]sslmode=[^&]+", "", url)
    return url


def _parse_int(raw: str | None, name: str, default: int, problems: list[str],
               warnings: list[str], lo: int | None = None, hi: int | None = None,
               required: bool = False) -> int:
    if raw is None or raw.strip() == "":
        if required:
            problems.append(f"{name} is required but not set")
        return default
    try:
        value = int(raw)
    except ValueError:
        warnings.append(f"{name}={raw!r} is not an integer; falling back to {default}")
        return default
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        warnings.append(
            f"{name}={value} is outside range [{lo}, {hi}]; falling back to {default}"
        )
        return default
    return value


def _parse_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Load and validate settings. Raises ConfigurationError listing every problem.

    Args:
        env: optional mapping to read from (defaults to os.environ after loading .env).
             Passing an explicit mapping makes this testable (Property 22, 23).
    """
    if env is None:
        load_dotenv()
        env = dict(os.environ)

    problems: list[str] = []
    warnings: list[str] = []

    database_url = env.get("DATABASE_URL", "").strip()
    if not database_url:
        problems.append("DATABASE_URL is required but not set")

    provider = env.get("LLM_PROVIDER", "").strip().lower()
    base_url = env.get("LLM_BASE_URL", "").strip()
    chat_model = env.get("LLM_CHAT_MODEL", "").strip()
    embed_model = env.get("LLM_EMBED_MODEL", "").strip()
    api_credential = env.get("LLM_API_KEY", "").strip()

    if not provider:
        problems.append("LLM_PROVIDER is required but not set")
    elif provider not in _VALID_PROVIDERS:
        problems.append(
            f"LLM_PROVIDER={provider!r} is invalid (expected one of {sorted(_VALID_PROVIDERS)})"
        )
    if not base_url:
        problems.append("LLM_BASE_URL is required but not set")
    if not chat_model:
        problems.append("LLM_CHAT_MODEL is required but not set")
    # api_credential may legitimately be a placeholder for local Ollama, but must exist.
    if not api_credential:
        problems.append("LLM_API_KEY is required but not set (use any placeholder for Ollama)")

    long_term_enabled = _parse_bool(env.get("LONG_TERM_MEMORY_ENABLED"), False)
    if long_term_enabled and not embed_model:
        problems.append("LLM_EMBED_MODEL is required when LONG_TERM_MEMORY_ENABLED is true")

    short_term_n = _parse_int(
        env.get("SHORT_TERM_N"), "SHORT_TERM_N", default=20,
        problems=problems, warnings=warnings, lo=1, hi=100,
    )

    # LLM request timeout. Defaults to 30s (production target); raise it for slow
    # local CPU inference via the env var.
    llm_timeout_seconds = _parse_int(
        env.get("LLM_TIMEOUT_SECONDS"), "LLM_TIMEOUT_SECONDS", default=30,
        problems=problems, warnings=warnings, lo=1, hi=600,
    )

    auth_enabled = _parse_bool(env.get("AUTH_ENABLED"), False)
    api_keys = tuple(
        k.strip() for k in env.get("API_KEYS", "").split(",") if k.strip()
    )
    if auth_enabled and not api_keys:
        problems.append("API_KEYS is required when AUTH_ENABLED is true")

    rate_max = _parse_int(
        env.get("RATE_LIMIT_MAX_REQUESTS"), "RATE_LIMIT_MAX_REQUESTS",
        default=60, problems=problems, warnings=warnings, lo=1,
    )
    rate_window = _parse_int(
        env.get("RATE_LIMIT_WINDOW_SECONDS"), "RATE_LIMIT_WINDOW_SECONDS",
        default=60, problems=problems, warnings=warnings, lo=1,
    )

    persona_dir = Path(env.get("PERSONA_DIR", "app/personas/data"))

    # Telegram is optional; the webhook is only enabled when a token is configured.
    telegram_bot_token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_webhook_secret = env.get("TELEGRAM_WEBHOOK_SECRET", "").strip()

    if problems:
        raise ConfigurationError(problems)

    return Settings(
        database_url=_normalize_database_url(database_url),
        provider=ProviderConfig(
            provider=provider,
            base_url=base_url,
            chat_model=chat_model,
            embed_model=embed_model,
            api_credential=api_credential,
        ),
        short_term_n=short_term_n,
        long_term_memory_enabled=long_term_enabled,
        llm_timeout_seconds=llm_timeout_seconds,
        auth_enabled=auth_enabled,
        api_keys=api_keys,
        rate_limit_max_requests=rate_max,
        rate_limit_window_seconds=rate_window,
        persona_dir=persona_dir,
        telegram_bot_token=telegram_bot_token,
        telegram_webhook_secret=telegram_webhook_secret,
        warnings=tuple(warnings),
    )
