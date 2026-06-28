"""Shared Hypothesis strategies for the test suite."""

from __future__ import annotations

from hypothesis import strategies as st

# Non-blank text within a length bound.
def bounded_text(min_size: int, max_size: int):
    return st.text(min_size=min_size, max_size=max_size).filter(lambda s: s.strip() != "")


def valid_persona_dict(persona_id: str | None = None):
    """A persona definition guaranteed to satisfy the Persona schema."""
    id_strategy = (
        st.just(persona_id) if persona_id is not None else bounded_text(1, 64)
    )
    return st.fixed_dictionaries(
        {
            "id": id_strategy,
            "name": bounded_text(1, 200),
            "archetype": bounded_text(1, 200),
            "system_directive": bounded_text(1, 8000),
            "example_dialogue": st.lists(
                st.fixed_dictionaries(
                    {"user": bounded_text(1, 200), "char": bounded_text(1, 200)}
                ),
                min_size=1,
                max_size=3,
            ),
            "speech_patterns": st.lists(bounded_text(1, 50), min_size=1, max_size=4),
        }
    )
