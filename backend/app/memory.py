"""Short-term memory windowing and model-request assembly.

Implements Requirements 3.1, 3.2 (assembled request content), 4.1-4.6 (sliding
window + safe N resolution), 5.4 (short-term-only when long-term disabled).

The core windowing and assembly logic is written as pure functions so it can be
property-tested directly (design Properties 7, 8, 9).
"""

from __future__ import annotations

from dataclasses import dataclass

from .personas.schema import Persona

DEFAULT_N = 20
MIN_N = 1
MAX_N = 100


@dataclass
class ChatMsg:
    role: str  # "system" | "user" | "assistant"
    content: str


def resolve_n(raw: object) -> tuple[int, str | None]:
    """Resolve the effective window size N (Requirements 4.1, 4.5, 4.6).

    Returns (effective_n, warning_or_None). Any unset, non-integer, or out-of-range
    value falls back to DEFAULT_N and produces a warning string.
    """
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return DEFAULT_N, None
    try:
        value = int(raw)
    except (ValueError, TypeError):
        return DEFAULT_N, f"N={raw!r} is not an integer; using default {DEFAULT_N}"
    if value < MIN_N or value > MAX_N:
        return DEFAULT_N, f"N={value} out of range [{MIN_N},{MAX_N}]; using default {DEFAULT_N}"
    return value, None


def select_window(messages: list, n: int) -> list:
    """Return the most recent min(len, N) messages, preserving oldest->newest order.

    `messages` must already be ordered oldest-to-newest (Requirements 4.2-4.4).
    """
    if n <= 0:
        return []
    return messages[-n:]


def assemble_context(
    persona: Persona, window: list[ChatMsg], new_message: str
) -> list[ChatMsg]:
    """Build the ordered model request (Requirements 3.1, 3.2).

    Includes the persona's system_directive, example_dialogue, and speech_patterns
    in the system message, the short-term window, then the new user message.
    """
    patterns = "\n".join(f"- {p}" for p in persona.speech_patterns)
    examples = "\n".join(
        f"User: {ex.user}\n{persona.name}: {ex.char}" for ex in persona.example_dialogue
    )
    system_text = (
        f"{persona.system_directive}\n\n"
        f"Speech patterns:\n{patterns}\n\n"
        f"Example dialogue:\n{examples}"
    )
    messages: list[ChatMsg] = [ChatMsg(role="system", content=system_text)]
    messages.extend(window)
    messages.append(ChatMsg(role="user", content=new_message))
    return messages


class MemoryManager:
    def __init__(self, message_repo, effective_n: int, ltm=None):
        self._repo = message_repo
        self._n = effective_n
        self._ltm = ltm  # optional LongTermMemoryService

    @property
    def effective_n(self) -> int:
        return self._n

    async def short_term(self, session_id: str) -> list[ChatMsg]:
        recent = await self._repo.recent(session_id, self._n)
        return [ChatMsg(role=m.role, content=m.content) for m in recent]

    async def assemble(
        self, persona: Persona, session_id: str, new_message: str
    ) -> list[ChatMsg]:
        recent = await self._repo.recent(session_id, self._n)
        window = [ChatMsg(role=m.role, content=m.content) for m in recent]
        context = assemble_context(persona, window, new_message)

        # Optional long-term recall: pull in relevant older messages that have already
        # scrolled out of the short-term window (Requirements 5.2, 5.3).
        if self._ltm is not None and self._ltm.enabled:
            exclude_ids = {m.id for m in recent}
            relevant = await self._ltm.retrieve(session_id, new_message, exclude_ids)
            if relevant:
                note = "Relevant earlier moments from this conversation:\n" + "\n".join(
                    f"- {r.content}" for r in relevant
                )
                context.insert(1, ChatMsg(role="system", content=note))
        return context
