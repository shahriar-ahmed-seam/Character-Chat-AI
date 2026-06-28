"""Pydantic Persona schema.

Implements Requirements 1.1 (required, non-empty fields) and 1.2 (length constraints).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DialogueExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: str = Field(min_length=1, max_length=4000)
    char: str = Field(min_length=1, max_length=4000)


class Persona(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    archetype: str = Field(min_length=1, max_length=200)
    system_directive: str = Field(min_length=1, max_length=8000)
    example_dialogue: list[DialogueExample] = Field(min_length=1)
    speech_patterns: list[str] = Field(min_length=1)

    @field_validator("id", "name", "archetype", "system_directive")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v

    @field_validator("speech_patterns")
    @classmethod
    def _patterns_not_blank(cls, v: list[str]) -> list[str]:
        if any(not s.strip() for s in v):
            raise ValueError("speech_patterns entries must not be blank")
        return v


class PersonaSummary(BaseModel):
    """Listing projection that excludes system_directive (Requirements 2.1, 2.2)."""

    id: str
    name: str
    archetype: str
