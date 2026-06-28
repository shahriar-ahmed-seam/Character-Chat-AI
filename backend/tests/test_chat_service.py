"""Property tests for Chat_Service turn orchestration (success and failure paths)."""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.chat import ChatService
from app.errors import GenerationFailed, ProviderUnreachable
from app.memory import MemoryManager
from app.personas.manager import PersonaManager
from app.persistence.repositories import MessageRepository, SessionRepository
from tests.strategies import valid_persona_dict

DB_ITER = settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


class FakeLLM:
    def __init__(self, reply=None, error=None):
        self._reply = reply
        self._error = error

    async def chat_completion(self, messages, **opts):
        if self._error is not None:
            raise self._error
        return self._reply


def _persona_manager():
    pm = PersonaManager()
    raw = {
        "id": "tester",
        "name": "Tester",
        "archetype": "QA",
        "system_directive": "You are a test persona.",
        "example_dialogue": [{"user": "hi", "char": "hello"}],
        "speech_patterns": ["concise"],
    }
    result = pm.load_and_validate([("t", raw)])
    pm._personas = {p.id: p for p in result.loaded}
    pm._ready = True
    return pm


async def _new_session(session_factory):
    async with session_factory() as db:
        s = await SessionRepository(db).create(persona_id="tester")
        return s.id


def _service(db, pm, llm):
    messages = MessageRepository(db)
    return ChatService(
        persona_manager=pm,
        memory=MemoryManager(messages, effective_n=20),
        llm=llm,
        sessions=SessionRepository(db),
        messages=messages,
    )


# Feature: character-chat-ai, Property 10: Successful turn persists user and assistant messages
@DB_ITER
@given(
    st.text(min_size=1, max_size=200).filter(lambda s: s.strip()),
    st.text(min_size=1, max_size=200).filter(lambda s: s.strip()),
)
@pytest.mark.asyncio
async def test_property_10_success_persists_both(session_factory, user_msg, reply):
    pm = _persona_manager()
    sid = await _new_session(session_factory)
    async with session_factory() as db:
        service = _service(db, pm, FakeLLM(reply=reply))
        result = await service.handle_turn(sid, user_msg)
        assert result.assistant_message.content == reply
    async with session_factory() as db:
        history = await MessageRepository(db).history(sid)
    roles = [m.role for m in history]
    assert roles == ["user", "assistant"]
    assert history[0].content == user_msg
    assert history[1].content == reply


# Feature: character-chat-ai, Property 12: Failed generation persists only the user message
@DB_ITER
@given(
    st.text(min_size=1, max_size=200).filter(lambda s: s.strip()),
    st.sampled_from([ProviderUnreachable("timeout"), GenerationFailed("boom")]),
)
@pytest.mark.asyncio
async def test_property_12_failure_persists_user_only(session_factory, user_msg, error):
    pm = _persona_manager()
    sid = await _new_session(session_factory)
    async with session_factory() as db:
        service = _service(db, pm, FakeLLM(error=error))
        with pytest.raises((ProviderUnreachable, GenerationFailed)):
            await service.handle_turn(sid, user_msg)
    async with session_factory() as db:
        history = await MessageRepository(db).history(sid)
    assert [m.role for m in history] == ["user"]
    assert history[0].content == user_msg
