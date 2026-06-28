"""Property tests for memory windowing, N resolution, and context assembly."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.memory import (
    DEFAULT_N,
    ChatMsg,
    assemble_context,
    resolve_n,
    select_window,
)
from app.personas.schema import Persona
from tests.strategies import valid_persona_dict

ITER = settings(max_examples=100)


def _msgs(n):
    return [ChatMsg(role="user", content=str(i)) for i in range(n)]


# Feature: character-chat-ai, Property 8: Short-term memory is the correctly ordered most-recent-N window
@ITER
@given(st.integers(min_value=0, max_value=200), st.integers(min_value=1, max_value=100))
def test_property_8_window(history_len, n):
    messages = _msgs(history_len)
    window = select_window(messages, n)
    expected_len = min(history_len, n)
    assert len(window) == expected_len
    # window must be the most recent items, in original (oldest->newest) order
    assert window == messages[history_len - expected_len:]


# Feature: character-chat-ai, Property 9: Window size N resolves safely from configuration
@ITER
@given(st.one_of(
    st.none(),
    st.integers(min_value=-50, max_value=200),
    st.text(max_size=8),
))
def test_property_9_resolve_n(raw):
    n, warning = resolve_n(raw)
    # Determine whether raw represents a valid in-range integer (strings are parsed).
    is_unset = raw is None or (isinstance(raw, str) and raw.strip() == "")
    valid_int = False
    if not is_unset:
        try:
            valid_int = 1 <= int(raw) <= 100
        except (ValueError, TypeError):
            valid_int = False

    if valid_int:
        assert n == int(raw)
        assert warning is None
    else:
        assert n == DEFAULT_N
        if not is_unset:
            assert warning is not None


# Feature: character-chat-ai, Property 7: Assembled model request contains required persona context and the new message
@ITER
@given(valid_persona_dict(), st.integers(min_value=0, max_value=10), st.text(min_size=1, max_size=100))
def test_property_7_assemble(raw_persona, window_len, new_message):
    persona = Persona.model_validate(raw_persona)
    window = _msgs(window_len)
    result = assemble_context(persona, window, new_message)

    # First message is the system message carrying persona context.
    assert result[0].role == "system"
    assert persona.system_directive in result[0].content
    for pattern in persona.speech_patterns:
        assert pattern in result[0].content
    assert persona.example_dialogue[0].char in result[0].content
    # The window is preserved in order between system and the new message.
    assert result[1:1 + window_len] == window
    # Last message is the new user message.
    assert result[-1].role == "user"
    assert result[-1].content == new_message
