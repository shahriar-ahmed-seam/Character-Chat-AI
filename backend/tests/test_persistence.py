"""Property tests for persistence: unique ids, round-trip, ordering, not-found."""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.errors import SessionNotFound
from app.persistence.repositories import MessageRepository, SessionRepository

# DB-backed: function-scoped fixture, so suppress the function-scoped health check
# and keep iteration counts modest while still exercising many generated inputs.
DB_ITER = settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


# Feature: character-chat-ai, Property 16: Session creation produces unique persisted identifiers
@DB_ITER
@given(st.integers(min_value=1, max_value=8))
@pytest.mark.asyncio
async def test_property_16_unique_session_ids(session_factory, count):
    ids = set()
    async with session_factory() as db:
        repo = SessionRepository(db)
        for _ in range(count):
            s = await repo.create(persona_id="elias")
            ids.add(s.id)
    assert len(ids) == count
    # each created session is retrievable
    async with session_factory() as db:
        repo = SessionRepository(db)
        for sid in ids:
            assert await repo.get(sid) is not None


# Feature: character-chat-ai, Property 17: Message persistence round-trip preserves fields
@DB_ITER
@given(
    st.text(min_size=1, max_size=200).filter(lambda s: s.strip()),
    st.text(min_size=1, max_size=200).filter(lambda s: s.strip()),
)
@pytest.mark.asyncio
async def test_property_17_message_roundtrip(session_factory, user_text, assistant_text):
    async with session_factory() as db:
        srepo = SessionRepository(db)
        mrepo = MessageRepository(db)
        s = await srepo.create(persona_id="luna")
        await mrepo.add_turn(s.id, "luna", user_text, assistant_text)
        history = await mrepo.history(s.id)
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[0].content == user_text
    assert history[0].persona_id == "luna"
    assert history[1].role == "assistant"
    assert history[1].content == assistant_text


# Feature: character-chat-ai, Property 19: History ordering is deterministic
@DB_ITER
@given(st.integers(min_value=1, max_value=10))
@pytest.mark.asyncio
async def test_property_19_history_ordering(session_factory, turns):
    async with session_factory() as db:
        srepo = SessionRepository(db)
        mrepo = MessageRepository(db)
        s = await srepo.create(persona_id="elias")
        for i in range(turns):
            await mrepo.add_turn(s.id, "elias", f"u{i}", f"a{i}")
        history = await mrepo.history(s.id)
    # ascending by (created_at, id); ids are monotonically increasing
    ids = [m.id for m in history]
    assert ids == sorted(ids)
    assert len(history) == turns * 2


# Feature: character-chat-ai, Property 20: Unknown session history never creates a session
@DB_ITER
@given(st.text(min_size=1, max_size=40))
@pytest.mark.asyncio
async def test_property_20_unknown_session(session_factory, fake_id):
    async with session_factory() as db:
        srepo = SessionRepository(db)
        with pytest.raises(SessionNotFound):
            await srepo.require(fake_id)
        assert await srepo.get(fake_id) is None
