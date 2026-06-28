"""API key authentication and per-credential rate limiting.

Implements Requirements 11.1-11.4. Auth/rate-limiting is gated by AUTH_ENABLED so
local development stays frictionless; production sets AUTH_ENABLED=true.

Note: the rate limiter here is a process-local fixed-window counter suitable for a
single instance. Phase 5 task 16.2 replaces it with a Postgres-backed counter so the
limit is correct across a horizontally scaled, stateless deployment.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .errors import RateLimited, Unauthorized


def extract_credential(headers) -> str | None:
    auth = headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    api_key = headers.get("x-api-key")
    if api_key:
        return api_key.strip()
    return None


@dataclass
class _Window:
    start: float
    count: int


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self._max = max_requests
        self._window = window_seconds
        self._state: dict[str, _Window] = {}

    def check(self, credential_id: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        win = self._state.get(credential_id)
        if win is None or (now - win.start) >= self._window:
            self._state[credential_id] = _Window(start=now, count=1)
            return
        if win.count >= self._max:
            retry_after = max(1, int(self._window - (now - win.start)))
            raise RateLimited(
                "Rate limit exceeded", retry_after_seconds=retry_after
            )
        win.count += 1


class Authenticator:
    def __init__(self, enabled: bool, api_keys: tuple[str, ...]):
        self._enabled = enabled
        self._keys = set(api_keys)

    def authenticate(self, headers) -> str:
        """Return the credential id, or raise Unauthorized (Requirements 11.1, 11.2)."""
        if not self._enabled:
            return "anonymous"
        credential = extract_credential(headers)
        if credential is None or credential not in self._keys:
            raise Unauthorized("A valid API credential is required")
        return credential
