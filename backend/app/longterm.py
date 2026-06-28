"""Optional long-term memory (RAG) logic.

Implements Requirements 5.1-5.5. The retrieval math and selection are pure functions
so they can be property-tested without a live vector database (Properties 13-15).

The production store is pgvector on PostgreSQL; an in-memory store implementing the
same interface is provided for development and tests. Long-term memory is config-gated
(LONG_TERM_MEMORY_ENABLED) and degrades gracefully on any embedding failure.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

logger = logging.getLogger("character_chat")

SIMILARITY_THRESHOLD = 0.75
RETRIEVAL_LIMIT = 10


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@dataclass
class StoredEmbedding:
    message_id: int
    content: str
    embedding: list[float]


def select_relevant(
    query_embedding: list[float],
    stored: list[StoredEmbedding],
    threshold: float = SIMILARITY_THRESHOLD,
    limit: int = RETRIEVAL_LIMIT,
) -> list[StoredEmbedding]:
    """Return up to `limit` stored items with similarity >= threshold,
    ordered most-similar first (Requirements 5.2, 5.3)."""
    scored = [(cosine_similarity(query_embedding, s.embedding), s) for s in stored]
    qualifying = [(score, s) for score, s in scored if score >= threshold]
    qualifying.sort(key=lambda pair: pair[0], reverse=True)
    return [s for _, s in qualifying[:limit]]


@dataclass
class InMemoryEmbeddingStore:
    """Reference store; the production adapter uses pgvector with the same interface."""

    items: list[StoredEmbedding] = field(default_factory=list)
    failures: list[int] = field(default_factory=list)

    def add(self, item: StoredEmbedding) -> None:
        self.items.append(item)

    def all_for(self) -> list[StoredEmbedding]:
        return list(self.items)


class LongTermMemory:
    def __init__(self, embedder, store: InMemoryEmbeddingStore, enabled: bool):
        self._embedder = embedder  # async callable: text -> list[float]
        self._store = store
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def embed_and_store(self, message_id: int, content: str) -> None:
        """Embed and store a message (Requirement 5.1). Failures are non-fatal and
        recorded; the message is retained regardless (Requirement 5.5)."""
        if not self._enabled:
            return
        try:
            embedding = await self._embedder(content)
        except Exception:  # noqa: BLE001
            logger.warning("embedding failed for message %s; continuing", message_id)
            self._store.failures.append(message_id)
            return
        self._store.add(StoredEmbedding(message_id, content, embedding))

    async def retrieve(self, query: str) -> list[StoredEmbedding]:
        """Retrieve relevant prior messages (Requirements 5.2, 5.3). Returns [] when
        disabled, on embedding failure, or when nothing meets the threshold."""
        if not self._enabled:
            return []
        try:
            query_embedding = await self._embedder(query)
        except Exception:  # noqa: BLE001
            logger.warning("query embedding failed; falling back to short-term memory")
            return []
        return select_relevant(query_embedding, self._store.all_for())


# ─────────────────── DB-backed long-term memory (production wiring) ───────────────────

import json  # noqa: E402

from sqlalchemy import select  # noqa: E402

from .models import EmbeddingRow  # noqa: E402


class LongTermMemoryService:
    """Persists message embeddings and retrieves relevant prior messages for a session.

    Config-gated by `enabled`. All operations degrade gracefully: any embedding or
    storage failure is logged and swallowed so a chat turn never breaks (Req 5.5).
    """

    def __init__(self, db, embedder, enabled: bool):
        self._db = db                # AsyncSession
        self._embedder = embedder    # async callable: text -> list[float]
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def store(self, message_id: int, session_id: str, content: str) -> None:
        if not self._enabled:
            return
        try:
            embedding = await self._embedder(content)
        except Exception:  # noqa: BLE001
            logger.warning("LTM embedding failed for message %s; skipping", message_id)
            return
        try:
            self._db.add(EmbeddingRow(
                message_id=message_id, session_id=session_id,
                content=content, embedding=json.dumps(embedding),
            ))
            await self._db.commit()
        except Exception:  # noqa: BLE001
            await self._db.rollback()
            logger.warning("LTM embedding store failed for message %s", message_id)

    async def retrieve(self, session_id: str, query: str,
                       exclude_ids: set[int] | None = None) -> list[StoredEmbedding]:
        if not self._enabled:
            return []
        try:
            query_embedding = await self._embedder(query)
        except Exception:  # noqa: BLE001
            logger.warning("LTM query embedding failed; using short-term only")
            return []
        exclude = exclude_ids or set()
        rows = (await self._db.execute(
            select(EmbeddingRow).where(EmbeddingRow.session_id == session_id)
        )).scalars().all()
        stored = [
            StoredEmbedding(r.message_id, r.content, json.loads(r.embedding))
            for r in rows if r.message_id not in exclude
        ]
        return select_relevant(query_embedding, stored)
