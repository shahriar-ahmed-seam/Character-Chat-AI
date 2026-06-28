"""Property tests for message validation, config resolution/fail-fast, and redaction."""

from __future__ import annotations

import string

from hypothesis import given, settings
from hypothesis import strategies as st

from app.chat import MAX_MESSAGE_CHARS, validate_message
from app.config import ConfigurationError, load_settings, _normalize_database_url
from app.errors import MessageInvalid, redact

ITER = settings(max_examples=100)

# Tokens without surrounding/embedded whitespace, matching real identifiers/keys.
_token = st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=40)


def _base_env():
    return {
        "DATABASE_URL": "sqlite+aiosqlite:///./dev.db",
        "LLM_PROVIDER": "ollama",
        "LLM_BASE_URL": "http://localhost:11434/v1",
        "LLM_CHAT_MODEL": "gemma3:4b",
        "LLM_EMBED_MODEL": "nomic-embed-text",
        "LLM_API_KEY": "ollama",
        "API_KEYS": "k1",
        "RATE_LIMIT_MAX_REQUESTS": "60",
        "RATE_LIMIT_WINDOW_SECONDS": "60",
    }


# Feature: character-chat-ai, Property 11: Invalid message is rejected with no side effects
@ITER
@given(st.text())
def test_property_11_validate_message(content):
    stripped_empty = content.strip() == ""
    too_long = len(content) > MAX_MESSAGE_CHARS
    if stripped_empty or too_long:
        try:
            validate_message(content)
            assert False, "expected MessageInvalid"
        except MessageInvalid:
            pass
    else:
        validate_message(content)  # should not raise


# Feature: character-chat-ai, Property 22: Provider configuration resolves from environment
@ITER
@given(
    st.sampled_from(["ollama", "groq", "openrouter", "hf"]),
    _token,
    _token,
)
def test_property_22_provider_config(provider, chat_model, api_key):
    env = _base_env()
    env.update({
        "LLM_PROVIDER": provider,
        "LLM_CHAT_MODEL": chat_model,
        "LLM_API_KEY": api_key,
    })
    settings_obj = load_settings(env)
    assert settings_obj.provider.provider == provider
    assert settings_obj.provider.chat_model == chat_model
    assert settings_obj.provider.api_credential == api_key
    assert settings_obj.provider.base_url == env["LLM_BASE_URL"]


# Feature: character-chat-ai, Property 23: Missing required configuration fails fast and names what is missing
@ITER
@given(st.lists(
    st.sampled_from(["DATABASE_URL", "LLM_PROVIDER", "LLM_BASE_URL", "LLM_CHAT_MODEL", "LLM_API_KEY"]),
    min_size=1, unique=True,
))
def test_property_23_missing_config_fails(missing_keys):
    env = _base_env()
    for k in missing_keys:
        del env[k]
    try:
        load_settings(env)
        assert False, "expected ConfigurationError"
    except ConfigurationError as exc:
        joined = "\n".join(exc.problems)
        for k in missing_keys:
            assert k in joined


# Feature: character-chat-ai, Property 27: Error responses redact secrets
@ITER
@given(st.text(alphabet=string.ascii_letters + string.digits, min_size=3, max_size=30))
def test_property_27_redaction(secret):
    samples = [
        f"connection failed for postgresql://user:{secret}@host/db",
        f"Authorization: Bearer {secret}xyz",
        f"api_key={secret}",
        f"gsk_{secret}abc",
    ]
    for s in samples:
        out = redact(s)
        assert "[REDACTED]" in out
        assert secret not in out


def test_normalize_neon_pooled_url():
    raw = (
        "postgresql://authenticator:pw@ep-x-pooler.c-9.us-east-1.aws.neon.tech/"
        "neondb?sslmode=require&channel_binding=require"
    )
    out = _normalize_database_url(raw)
    assert out.startswith("postgresql+asyncpg://")
    assert "sslmode" not in out
    assert "channel_binding" not in out
    assert out.endswith("/neondb")


def test_normalize_keeps_sqlite():
    raw = "sqlite+aiosqlite:///./dev.db"
    assert _normalize_database_url(raw) == raw


def test_normalize_strips_only_known_params():
    raw = "postgresql://u:p@host/db?sslmode=require"
    out = _normalize_database_url(raw)
    assert out == "postgresql+asyncpg://u:p@host/db"
