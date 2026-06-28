"""Telegram bot integration (aiogram webhook mode).

Implements Requirements 10.1-10.11. The bot is a thin translation layer: it parses
Telegram commands, maps chat_id <-> Session, and delegates all chat logic to the
backend's Chat_Service. It contains no persona/memory/model-routing logic itself.

The command-parsing and selection logic is written as pure functions so it can be
property-tested without a live Telegram connection (Properties 28, 29).
"""

from __future__ import annotations

from dataclasses import dataclass

from .chat import ChatService
from .errors import AppError
from .personas.manager import PersonaManager
from .persistence.repositories import (
    SessionRepository,
    TelegramRepository,
)


@dataclass
class ParsedCommand:
    kind: str  # "start" | "use" | "chat" | "help"
    arg: str | None = None


def parse_command(text: str) -> ParsedCommand:
    """Parse an incoming Telegram message into an intent."""
    stripped = (text or "").strip()
    if not stripped:
        return ParsedCommand("help")
    if stripped.startswith("/start"):
        return ParsedCommand("start")
    if stripped.startswith("/help"):
        return ParsedCommand("help")
    if stripped.startswith("/use"):
        parts = stripped.split(maxsplit=1)
        return ParsedCommand("use", parts[1].strip() if len(parts) > 1 else "")
    return ParsedCommand("chat", stripped)


def is_valid_selection(persona_id: str, available_ids: set[str]) -> bool:
    """A selection is valid only if it is in the presented set (Requirement 10.9)."""
    return persona_id in available_ids


def render_persona_list(personas) -> str:
    lines = ["Choose a character with /use <id>:"]
    for p in personas:
        lines.append(f"• {p.name} — {p.archetype}  (/use {p.id})")
    return "\n".join(lines)


class TelegramService:
    """Orchestrates a Telegram interaction using backend components only."""

    def __init__(
        self,
        persona_manager: PersonaManager,
        telegram_repo: TelegramRepository,
        session_repo: SessionRepository,
        chat_service: ChatService,
    ):
        self._personas = persona_manager
        self._tg = telegram_repo
        self._sessions = session_repo
        self._chat = chat_service

    async def handle(self, chat_id: str, text: str) -> str:
        cmd = parse_command(text)
        personas = self._personas.list_personas()

        if cmd.kind in ("start", "help"):
            return render_persona_list(personas)

        if cmd.kind == "use":
            available = {p.id for p in personas}
            if not is_valid_selection(cmd.arg or "", available):
                return (
                    f"'{cmd.arg}' is not a valid character. "
                    + render_persona_list(personas)
                )
            session = await self._sessions.create(persona_id=cmd.arg, owner_key=f"tg:{chat_id}")
            await self._tg.set_session_id(chat_id, session.id)
            persona = self._personas.require(cmd.arg)
            return f"You are now chatting with {persona.name}. Say hello!"

        # cmd.kind == "chat"
        session_id = await self._tg.get_session_id(chat_id)
        if session_id is None:
            # No session yet -> create one (Requirement 10.3) by prompting selection.
            return "Pick a character first.\n" + render_persona_list(personas)
        try:
            result = await self._chat.handle_turn(session_id, cmd.arg)
            return result.assistant_message.content
        except AppError as exc:
            # Notify the user; leave session state unchanged (Requirement 10.6).
            return f"Sorry, I couldn't process that ({exc.error_id}). Please try again."
