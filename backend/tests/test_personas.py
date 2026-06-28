"""Property tests for persona validation, loading, and listing."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.personas.manager import PersonaManager
from app.personas.schema import Persona
from tests.strategies import valid_persona_dict

ITER = settings(max_examples=100)


# Feature: character-chat-ai, Property 1: Persona validation accepts iff well-formed
@ITER
@given(valid_persona_dict())
def test_property_1_valid_persona_accepted(raw):
    persona = Persona.model_validate(raw)
    assert persona.id == raw["id"]
    assert persona.system_directive == raw["system_directive"]


# Feature: character-chat-ai, Property 1: Persona validation accepts iff well-formed
@ITER
@given(valid_persona_dict(), st.sampled_from(
    ["id", "name", "archetype", "system_directive", "example_dialogue", "speech_patterns"]
))
def test_property_1_missing_field_rejected(raw, drop_field):
    broken = dict(raw)
    del broken[drop_field]
    try:
        Persona.model_validate(broken)
        assert False, f"expected rejection when {drop_field} is missing"
    except Exception:
        pass


# Feature: character-chat-ai, Property 1: Persona validation accepts iff well-formed
@ITER
@given(valid_persona_dict())
def test_property_1_overlong_id_rejected(raw):
    broken = dict(raw)
    broken["id"] = "x" * 65  # exceeds 64-char limit
    try:
        Persona.model_validate(broken)
        assert False, "expected rejection for overlong id"
    except Exception:
        pass


# Feature: character-chat-ai, Property 2: Batch loading retains valid and reports invalid fields
@ITER
@given(st.lists(valid_persona_dict(), min_size=0, max_size=5))
def test_property_2_batch_loading(valid_defs):
    # Make ids unique so no duplicate-rejection interferes with this property.
    for i, d in enumerate(valid_defs):
        d["id"] = f"valid-{i}"
    # Add some definitions that are guaranteed invalid (missing required field).
    invalid_defs = [{"id": f"bad-{i}", "name": "x"} for i in range(2)]
    raw = [("src", d) for d in valid_defs] + [("src", d) for d in invalid_defs]

    pm = PersonaManager()
    result = pm.load_and_validate(raw)

    loaded_ids = {p.id for p in result.loaded}
    assert loaded_ids == {f"valid-{i}" for i in range(len(valid_defs))}
    assert len(result.rejected) == len(invalid_defs)
    for rej in result.rejected:
        assert rej.fields  # each rejection names the failing field(s)


# Feature: character-chat-ai, Property 3: Duplicate ids reject all conflicting definitions
@ITER
@given(valid_persona_dict(), st.integers(min_value=2, max_value=4))
def test_property_3_duplicate_ids_all_rejected(base, copies):
    raw = []
    for _ in range(copies):
        d = dict(base)
        d["id"] = "collision"
        raw.append(("src", d))
    # plus one unique persona that should survive
    unique = dict(base)
    unique["id"] = "unique-one"
    raw.append(("src", unique))

    pm = PersonaManager()
    result = pm.load_and_validate(raw)

    loaded_ids = {p.id for p in result.loaded}
    assert "collision" not in loaded_ids
    assert "unique-one" in loaded_ids
    assert any(r.persona_id == "collision" for r in result.rejected)


# Feature: character-chat-ai, Property 4: Persona listing exposes summary fields only
@ITER
@given(st.lists(valid_persona_dict(), min_size=0, max_size=5))
def test_property_4_listing_summary_only(defs):
    for i, d in enumerate(defs):
        d["id"] = f"p-{i}"
    pm = PersonaManager()
    result = pm.load_and_validate([("src", d) for d in defs])
    pm._personas = {p.id: p for p in result.loaded}

    summaries = pm.list_personas()
    assert len(summaries) == len(defs)
    for s in summaries:
        fields = s.model_dump()
        assert set(fields.keys()) == {"id", "name", "archetype"}
        assert "system_directive" not in fields
