"""Property tests for authentication and rate limiting."""

from __future__ import annotations

import string

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.errors import RateLimited, Unauthorized
from app.security import Authenticator, RateLimiter

ITER = settings(max_examples=100)

_key = st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=20)


# Feature: character-chat-ai, Property 24: Authentication is enforced on protected endpoints
@ITER
@given(
    st.lists(_key, min_size=1, max_size=5, unique=True),
    st.one_of(st.just(""), _key),
)
def test_property_24_auth(valid_keys, presented):
    auth = Authenticator(enabled=True, api_keys=tuple(valid_keys))
    headers = {"authorization": f"Bearer {presented}"} if presented else {}
    if presented in set(valid_keys):
        assert auth.authenticate(headers) == presented
    else:
        with pytest.raises(Unauthorized):
            auth.authenticate(headers)


# Feature: character-chat-ai, Property 24: auth disabled allows anonymous access
@ITER
@given(st.text(max_size=10))
def test_property_24_auth_disabled(_garbage):
    auth = Authenticator(enabled=False, api_keys=())
    assert auth.authenticate({}) == "anonymous"


# Feature: character-chat-ai, Property 25: Rate limiting triggers past the threshold with remaining time
@ITER
@given(st.integers(min_value=1, max_value=20))
def test_property_25_rate_limit(max_requests):
    limiter = RateLimiter(max_requests=max_requests, window_seconds=60)
    # The first `max_requests` calls within the window succeed.
    for _ in range(max_requests):
        limiter.check("cred", now=100.0)
    # The next one is rejected with a positive retry-after.
    with pytest.raises(RateLimited) as exc:
        limiter.check("cred", now=100.0)
    assert exc.value.retry_after_seconds > 0


# Feature: character-chat-ai, Property 26: Rate-limit window resets
@ITER
@given(st.integers(min_value=1, max_value=10), st.integers(min_value=1, max_value=120))
def test_property_26_window_reset(max_requests, window):
    limiter = RateLimiter(max_requests=max_requests, window_seconds=window)
    for _ in range(max_requests):
        limiter.check("cred", now=0.0)
    with pytest.raises(RateLimited):
        limiter.check("cred", now=0.0)
    # After the window elapses, the count resets and requests are accepted again.
    limiter.check("cred", now=float(window))  # should not raise


# Feature: character-chat-ai, Property 25: limits are independent per credential
@ITER
@given(st.integers(min_value=1, max_value=5))
def test_property_25_per_credential(max_requests):
    limiter = RateLimiter(max_requests=max_requests, window_seconds=60)
    for _ in range(max_requests):
        limiter.check("a", now=0.0)
    # A different credential is unaffected by a's exhausted quota.
    limiter.check("b", now=0.0)  # should not raise
