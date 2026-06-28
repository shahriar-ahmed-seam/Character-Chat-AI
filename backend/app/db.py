"""Async database engine, session factory, and startup connection retry.

Implements Requirements 6.6 (all state in the datastore), 12.6 (3 connection
attempts within a 30-second window before reporting failure).
"""

from __future__ import annotations

import asyncio
import time

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text


def _engine_kwargs(database_url: str) -> dict:
    kwargs: dict = {"echo": False, "pool_pre_ping": True}
    # Managed Postgres (e.g. Neon) requires TLS; asyncpg takes it via connect_args.
    if database_url.startswith("postgresql+asyncpg://") and "localhost" not in database_url:
        kwargs["connect_args"] = {"ssl": True}
    return kwargs


def make_engine(database_url: str):
    return create_async_engine(database_url, **_engine_kwargs(database_url))


def make_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def verify_connection(engine, attempts: int = 3, window_seconds: int = 30) -> None:
    """Try to connect up to `attempts` times within `window_seconds`.

    Raises the last error if all attempts fail (Requirement 12.6).
    """
    deadline = time.monotonic() + window_seconds
    last_exc: Exception | None = None
    delay = 1.0
    for attempt in range(1, attempts + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return
        except Exception as exc:  # noqa: BLE001 - we re-raise after retries
            last_exc = exc
            if attempt == attempts or time.monotonic() >= deadline:
                break
            await asyncio.sleep(min(delay, max(0.0, deadline - time.monotonic())))
            delay *= 2
    raise ConnectionError(
        f"Could not connect to the database after {attempts} attempts"
    ) from last_exc
