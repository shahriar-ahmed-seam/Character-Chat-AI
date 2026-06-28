"""Persona loading, validation, and serving.

Implements Requirements 1.3-1.7 (validate, reject invalid individually, reject
duplicate ids, startup gating) and 2.1-2.3, 2.6 (listing + lookup).
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from ..errors import FieldError, PersonaNotFound
from .schema import Persona, PersonaSummary


@dataclass
class PersonaLoadError:
    source: str
    persona_id: str | None
    fields: list[FieldError]
    reason: str


@dataclass
class LoadResult:
    loaded: list[Persona] = field(default_factory=list)
    rejected: list[PersonaLoadError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.rejected


def _flatten_pydantic_errors(exc: ValidationError) -> list[FieldError]:
    out: list[FieldError] = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ())) or "(root)"
        out.append(FieldError(field=loc, reason=err.get("msg", "invalid")))
    return out


class PersonaManager:
    def __init__(self) -> None:
        self._personas: dict[str, Persona] = {}
        self._ready: bool = False
        self._startup_errors: list[PersonaLoadError] = []

    @property
    def ready(self) -> bool:
        """False if startup validation failed; gates chat serving (Requirement 1.7)."""
        return self._ready

    @property
    def startup_errors(self) -> list[PersonaLoadError]:
        return list(self._startup_errors)

    def load_and_validate(self, raw_defs: list[tuple[str, dict]]) -> LoadResult:
        """Validate a batch of (source, definition) pairs.

        - Invalid definitions are rejected individually with field-level reasons,
          valid ones are retained (Requirement 1.4).
        - Every definition sharing a duplicate id is rejected (Requirement 1.5).
        """
        result = LoadResult()

        # First pass: schema-validate each definition.
        validated: list[tuple[str, Persona]] = []
        for source, raw in raw_defs:
            try:
                persona = Persona.model_validate(raw)
            except ValidationError as exc:
                result.rejected.append(
                    PersonaLoadError(
                        source=source,
                        persona_id=raw.get("id") if isinstance(raw, dict) else None,
                        fields=_flatten_pydantic_errors(exc),
                        reason="schema validation failed",
                    )
                )
                continue
            validated.append((source, persona))

        # Second pass: reject all definitions whose id collides (Requirement 1.5).
        id_counts = Counter(p.id for _, p in validated)
        for source, persona in validated:
            if id_counts[persona.id] > 1:
                result.rejected.append(
                    PersonaLoadError(
                        source=source,
                        persona_id=persona.id,
                        fields=[FieldError(field="id", reason="duplicate id")],
                        reason=f"duplicate persona id {persona.id!r}",
                    )
                )
            else:
                result.loaded.append(persona)

        return result

    def load_from_dir(self, directory: Path) -> LoadResult:
        raw_defs: list[tuple[str, dict]] = []
        if directory.is_dir():
            for path in sorted(directory.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    raw_defs.append((path.name, {"__parse_error__": str(exc)}))
                    continue
                items = data if isinstance(data, list) else [data]
                for item in items:
                    raw_defs.append((path.name, item))
        return self.load_and_validate(raw_defs)

    def initialize(self, directory: Path) -> LoadResult:
        """Load at startup; the manager only becomes ready if every def is valid.

        Requirement 1.6 (validate before serving) and 1.7 (refuse if any fails).
        """
        result = self.load_from_dir(directory)
        self._personas = {p.id: p for p in result.loaded}
        if result.ok and result.loaded:
            self._ready = True
            self._startup_errors = []
        else:
            self._ready = False
            self._startup_errors = result.rejected
        return result

    def list_personas(self) -> list[PersonaSummary]:
        return [
            PersonaSummary(id=p.id, name=p.name, archetype=p.archetype)
            for p in self._personas.values()
        ]

    def get(self, persona_id: str) -> Persona | None:
        return self._personas.get(persona_id)

    def require(self, persona_id: str) -> Persona:
        persona = self._personas.get(persona_id)
        if persona is None:
            raise PersonaNotFound(f"Unknown persona id: {persona_id!r}")
        return persona
