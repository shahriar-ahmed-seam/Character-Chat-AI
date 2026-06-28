"""Consistent error envelope and domain exceptions.

Implements Requirements 13.4 (machine-readable + human-readable error structure),
13.2 (per-field validation detail), and 11.7 (secret redaction).
"""

from __future__ import annotations

import re

from pydantic import BaseModel


class FieldError(BaseModel):
    field: str
    reason: str


class ErrorResponse(BaseModel):
    error_id: str
    message: str
    fields: list[FieldError] | None = None


# Patterns used to scrub anything that looks like a secret out of error messages
# before they leave the process (Requirement 11.7).
_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|secret|credential)\s*[=:]\s*\S+"),
    re.compile(r"Bearer\s+\S+"),
    re.compile(r"gsk_[A-Za-z0-9]+"),  # Groq keys
    re.compile(r"sk-[A-Za-z0-9]+"),   # OpenAI-style keys
    re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^\s]+"),  # DB URLs with creds
]


def redact(text: str) -> str:
    """Remove secret-looking substrings from a message (Requirement 11.7)."""
    out = text
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub("[REDACTED]", out)
    return out


class AppError(Exception):
    """Base class for errors that map to a consistent ErrorResponse + HTTP status."""

    error_id: str = "internal_error"
    http_status: int = 500

    def __init__(self, message: str, fields: list[FieldError] | None = None,
                 extra: dict | None = None):
        self.message = message
        self.fields = fields
        self.extra = extra or {}
        super().__init__(message)

    def to_response(self) -> ErrorResponse:
        return ErrorResponse(
            error_id=self.error_id,
            message=redact(self.message),
            fields=self.fields,
        )


class ValidationFailed(AppError):
    error_id = "validation_error"
    http_status = 422


class MessageInvalid(AppError):
    error_id = "message_invalid"
    http_status = 422


class PersonaNotFound(AppError):
    error_id = "persona_not_found"
    http_status = 404


class SessionNotFound(AppError):
    error_id = "session_not_found"
    http_status = 404


class GenerationFailed(AppError):
    error_id = "generation_failed"
    http_status = 502


class ProviderUnreachable(AppError):
    error_id = "provider_unreachable"
    http_status = 504


class ProviderAuthFailed(AppError):
    error_id = "provider_auth_failed"
    http_status = 502


class PersistenceFailed(AppError):
    error_id = "persistence_failed"
    http_status = 500


class Unauthorized(AppError):
    error_id = "unauthorized"
    http_status = 401


class RateLimited(AppError):
    error_id = "rate_limited"
    http_status = 429

    def __init__(self, message: str, retry_after_seconds: int):
        super().__init__(message, extra={"retry_after_seconds": retry_after_seconds})
        self.retry_after_seconds = retry_after_seconds
