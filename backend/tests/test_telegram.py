"""Property/behaviour tests for the Telegram service mapping and selection."""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.chat import ChatService
from app.memory import MemoryManager
from app.personas.manager import PersonaManager
from app.persistence.repositories import (
    MessageRepository,
    SessionRepository,
    TelegramRepository,
)
from app.telegram import TelegramService, is_valid_selection, parse_command

DB_ITER = settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


class FakeLLM:
    async def chat_completion(self, messages, **opts):
        return "fake reply"


def _persona_manager():
    pm = PersonaManager()
    raw = {
        "id": "luna",
        "name": "Luna",
        "archetype": "Astronomer",
        "system_directive": "You are Luna.",
        "example_dialogue": [{"user": "hi", "char": "hello"}],
        "speech_patterns": ["warm"],
    }
    result = pm.load_and_validate([("t", raw)])
    pm._personas = {p.id: p for p in result.loaded}
    pm._ready = True
    return pm


def _service(db, pm):
    messages = MessageRepository(db)
    chat = ChatService(
        persona_manager=pm,
        memory=MemoryManager(messages, 20),
        llm=FakeLLM(),
        sessions=SessionRepository(db),
        messages=messages,
    )
    return TelegramService(
        persona_manager=pm,
        telegram_repo=TelegramRepository(db),
        session_repo=SessionRepository(db),
        chat_service=chat,
    )


# Feature: character-chat-ai, Property 28: Telegram chat_id maps consistently to a session
@DB_ITER
@given(st.integers(min_value=1, max_value=10_000_000))
@pytest.mark.asyncio
async def test_property_28_chat_id_mapping(session_factory, chat_id_int):
    chat_id = str(chat_id_int)
    pm = _persona_manager()
    async with session_factory() as db:
        svc = _service(db, pm)
        # Select a persona -> creates + maps a session.
        await svc.handle(chat_id, "/use luna")
        sid1 = await TelegramRepository(db).get_session_id(chat_id)
        assert sid1 is not None
        # A subsequent chat reuses the same mapped session.
        await svc.handle(chat_id, "hello there")
        sid2 = await TelegramRepository(db).get_session_id(chat_id)
        assert sid1 == sid2


# Feature: character-chat-ai, Property 29: Selecting a persona outside the presented list is rejected
@DB_ITER
@given(st.text(min_size=1, max_size=20).filter(lambda s: s.strip() and s.strip() != "luna"))
@pytest.mark.asyncio
async def test_property_29_invalid_selection(session_factory, bad_id):
    pm = _persona_manager()
    async with session_factory() as db:
        svc = _service(db, pm)
        reply = await svc.handle("555", f"/use {bad_id}")
        assert "not a valid character" in reply
        # No session mapped for an invalid selection.
        assert await TelegramRepository(db).get_session_id("555") is None


def test_parse_command_variants():
    assert parse_command("/start").kind == "start"
    assert parse_command("/use luna") == type(parse_command("/use luna"))(kind="use", arg="luna")
    assert parse_command("hello").kind == "chat"
    assert parse_command("   ").kind == "help"


def test_is_valid_selection():
    assert is_valid_selection("luna", {"luna", "elias"})
    assert not is_valid_selection("ghost", {"luna", "elias"})
