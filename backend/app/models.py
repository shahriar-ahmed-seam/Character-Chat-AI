"""SQLAlchemy ORM models.

Implements the relational schema from the design: characters, sessions, messages,
telegram_map (Phase 1) and embeddings (Phase 5, optional long-term memory).

Requirements: 6.1 (unique session id), 6.2 (message fields), 6.4 (insertion-order
tiebreaker via autoincrement id), 5.1 (embedding storage), 10.2/10.3 (telegram map).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# SQLite only autoincrements an INTEGER PRIMARY KEY (rowid alias); Postgres uses BIGINT.
_PK_BIGINT = BigInteger().with_variant(Integer, "sqlite")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class CharacterRow(Base):
    """Projection of a validated persona, kept for referential integrity + listings."""

    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    archetype: Mapped[str] = mapped_column(String(200), nullable=False)
    system_directive: Mapped[str] = mapped_column(Text, nullable=False)


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    persona_id: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    messages: Mapped[list["MessageRow"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class MessageRow(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(_PK_BIGINT, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    persona_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    session: Mapped["SessionRow"] = relationship(back_populates="messages")


class TelegramMapRow(Base):
    __tablename__ = "telegram_map"

    chat_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )


class EmbeddingRow(Base):
    """Stores a message embedding for optional long-term (RAG) memory.

    The vector is stored as JSON text for portability across SQLite (dev) and
    Postgres (prod) without requiring the pgvector extension. Similarity is computed
    in Python, which is ample for per-session retrieval at this scale.
    """

    __tablename__ = "embeddings"

    message_id: Mapped[int] = mapped_column(_PK_BIGINT, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded float list
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )
