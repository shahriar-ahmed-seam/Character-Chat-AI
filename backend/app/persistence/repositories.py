"""Async repositories for sessions and messages.

Implements Requirements 6.1-6.5: unique session ids, message persistence with all
fields, atomic turn writes, deterministic ordering, and not-found handling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import PersistenceFailed, SessionNotFound
from ..models import MessageRow, SessionRow, TelegramMapRow

logger = logging.getLogger("character_chat")


@dataclass
class MessageDTO:
    id: int
    role: str
    content: str
    persona_id: str
    created_at: datetime


@dataclass
class SessionDTO:
    id: str
    persona_id: str
    created_at: datetime


def _to_message_dto(row: MessageRow) -> MessageDTO:
    return MessageDTO(
        id=row.id,
        role=row.role,
        content=row.content,
        persona_id=row.persona_id,
        created_at=row.created_at,
    )


class SessionRepository:
    def __init__(self, session: AsyncSession):
        self._db = session

    async def create(self, persona_id: str, owner_key: str | None = None) -> SessionDTO:
        row = SessionRow(persona_id=persona_id, owner_key=owner_key)
        self._db.add(row)
        try:
            await self._db.commit()
        except Exception as exc:  # noqa: BLE001
            await self._db.rollback()
            logger.exception("session persistence failed")
            raise PersistenceFailed("Failed to persist session") from exc
        await self._db.refresh(row)
        return SessionDTO(id=row.id, persona_id=row.persona_id, created_at=row.created_at)

    async def get(self, session_id: str) -> SessionDTO | None:
        row = await self._db.get(SessionRow, session_id)
        if row is None:
            return None
        return SessionDTO(id=row.id, persona_id=row.persona_id, created_at=row.created_at)

    async def require(self, session_id: str) -> SessionDTO:
        dto = await self.get(session_id)
        if dto is None:
            raise SessionNotFound(f"Unknown session id: {session_id!r}")
        return dto


class MessageRepository:
    def __init__(self, session: AsyncSession):
        self._db = session

    async def add_turn(
        self,
        session_id: str,
        persona_id: str,
        user_content: str,
        assistant_content: str | None,
    ) -> list[MessageDTO]:
        """Persist a user message and (optionally) an assistant message atomically.

        On generation failure assistant_content is None, so only the user message is
        stored (Requirement 3.7). A DB failure rolls back entirely (Requirement 6.3).
        """
        rows = [
            MessageRow(
                session_id=session_id, role="user",
                content=user_content, persona_id=persona_id,
            )
        ]
        if assistant_content is not None:
            rows.append(
                MessageRow(
                    session_id=session_id, role="assistant",
                    content=assistant_content, persona_id=persona_id,
                )
            )
        self._db.add_all(rows)
        try:
            await self._db.commit()
        except Exception as exc:  # noqa: BLE001
            await self._db.rollback()
            logger.exception("message persistence failed")
            raise PersistenceFailed("Failed to persist messages") from exc
        for row in rows:
            await self._db.refresh(row)
        return [_to_message_dto(r) for r in rows]

    async def recent(self, session_id: str, limit: int) -> list[MessageDTO]:
        """Most recent `limit` messages, returned oldest-to-newest (Requirement 4.2)."""
        stmt = (
            select(MessageRow)
            .where(MessageRow.session_id == session_id)
            .order_by(MessageRow.created_at.desc(), MessageRow.id.desc())
            .limit(limit)
        )
        rows = (await self._db.execute(stmt)).scalars().all()
        return [_to_message_dto(r) for r in reversed(rows)]

    async def history(self, session_id: str) -> list[MessageDTO]:
        """Full history ordered by timestamp, ties by insertion id (Requirement 6.4)."""
        stmt = (
            select(MessageRow)
            .where(MessageRow.session_id == session_id)
            .order_by(MessageRow.created_at.asc(), MessageRow.id.asc())
        )
        rows = (await self._db.execute(stmt)).scalars().all()
        return [_to_message_dto(r) for r in rows]


class TelegramRepository:
    """Maps a Telegram chat_id to a Session (Requirements 10.2, 10.3)."""

    def __init__(self, session: AsyncSession):
        self._db = session

    async def get_session_id(self, chat_id: str) -> str | None:
        row = await self._db.get(TelegramMapRow, chat_id)
        return row.session_id if row else None

    async def set_session_id(self, chat_id: str, session_id: str) -> None:
        row = await self._db.get(TelegramMapRow, chat_id)
        if row is None:
            self._db.add(TelegramMapRow(chat_id=chat_id, session_id=session_id))
        else:
            row.session_id = session_id
        try:
            await self._db.commit()
        except Exception as exc:  # noqa: BLE001
            await self._db.rollback()
            logger.exception("telegram map persistence failed")
            raise PersistenceFailed("Failed to persist telegram mapping") from exc
