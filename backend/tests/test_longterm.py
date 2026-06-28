"""Property tests for optional long-term memory (RAG)."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.longterm import (
    RETRIEVAL_LIMIT,
    SIMILARITY_THRESHOLD,
    InMemoryEmbeddingStore,
    LongTermMemory,
    StoredEmbedding,
    cosine_similarity,
    select_relevant,
)

ITER = settings(max_examples=100, deadline=None)

# Embeddings as small fixed-length vectors.
vec = st.lists(st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
               min_size=4, max_size=4)


def _make_embedder(mapping):
    async def embedder(text):
        if text == "__fail__":
            raise RuntimeError("embedding boom")
        return mapping.get(text, [1.0, 0.0, 0.0, 0.0])
    return embedder


# Feature: character-chat-ai, Property 13: Long-term memory embeds every persisted message when enabled
@ITER
@given(st.lists(st.text(min_size=1, max_size=20).filter(lambda s: s != "__fail__"),
                min_size=0, max_size=8))
@pytest.mark.asyncio
async def test_property_13_embeds_all(contents):
    store = InMemoryEmbeddingStore()
    ltm = LongTermMemory(_make_embedder({}), store, enabled=True)
    for i, c in enumerate(contents):
        await ltm.embed_and_store(i, c)
    assert len(store.items) == len(contents)
    assert {it.message_id for it in store.items} == set(range(len(contents)))


# Feature: character-chat-ai, Property 14: Long-term retrieval respects threshold, ordering, and limit
@ITER
@given(st.lists(vec, min_size=0, max_size=30), vec)
@pytest.mark.asyncio
async def test_property_14_retrieval(stored_vecs, query):
    store = InMemoryEmbeddingStore()
    for i, v in enumerate(stored_vecs):
        store.add(StoredEmbedding(i, f"m{i}", v))
    result = select_relevant(query, store.all_for())

    assert len(result) <= RETRIEVAL_LIMIT
    sims = [cosine_similarity(query, r.embedding) for r in result]
    # all above threshold
    assert all(s >= SIMILARITY_THRESHOLD for s in sims)
    # ordered most-similar first
    assert sims == sorted(sims, reverse=True)


# Feature: character-chat-ai, Property 15: Long-term memory degrades gracefully
@ITER
@given(st.booleans())
@pytest.mark.asyncio
async def test_property_15_graceful(enabled):
    store = InMemoryEmbeddingStore()
    ltm = LongTermMemory(_make_embedder({}), store, enabled=enabled)

    # Disabled -> retrieval returns nothing (short-term only path).
    if not enabled:
        assert await ltm.retrieve("anything") == []
        await ltm.embed_and_store(1, "x")
        assert store.items == []
        return

    # Enabled but embedding fails -> message retained as a recorded failure, no crash.
    await ltm.embed_and_store(99, "__fail__")
    assert 99 in store.failures
    assert all(it.message_id != 99 for it in store.items)
    # Query embedding failure -> empty retrieval (fallback to short-term).
    assert await ltm.retrieve("__fail__") == []


# ---- DB-backed long-term memory service (production wiring) ----

import pytest  # noqa: E402

from app.longterm import LongTermMemoryService  # noqa: E402
from app.persistence.repositories import MessageRepository, SessionRepository  # noqa: E402


def _orthogonal_embedder():
    # Map distinct phrases to near-orthogonal vectors so similarity is controllable.
    table = {
        "my cat is named pixel": [1.0, 0.0, 0.0, 0.0],
        "what is my cat called": [0.98, 0.02, 0.0, 0.0],
        "the weather is nice": [0.0, 1.0, 0.0, 0.0],
    }

    async def embed(text):
        return table.get(text, [0.0, 0.0, 1.0, 0.0])
    return embed


@pytest.mark.asyncio
async def test_ltm_service_store_and_retrieve(session_factory):
    async with session_factory() as db:
        s = await SessionRepository(db).create(persona_id="luna")
        mrepo = MessageRepository(db)
        msgs = await mrepo.add_turn(s.id, "luna", "my cat is named pixel", "Lovely name!")
        svc = LongTermMemoryService(db, _orthogonal_embedder(), enabled=True)
        for m in msgs:
            await svc.store(m.id, s.id, m.content)

        # A semantically related query retrieves the relevant stored message.
        results = await svc.retrieve(s.id, "what is my cat called", exclude_ids=set())
        contents = [r.content for r in results]
        assert "my cat is named pixel" in contents


@pytest.mark.asyncio
async def test_ltm_service_disabled_is_noop(session_factory):
    async with session_factory() as db:
        s = await SessionRepository(db).create(persona_id="luna")
        svc = LongTermMemoryService(db, _orthogonal_embedder(), enabled=False)
        await svc.store(1, s.id, "my cat is named pixel")
        assert await svc.retrieve(s.id, "what is my cat called") == []
