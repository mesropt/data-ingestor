"""Domain models — the target shape every ingested file maps into.

These are pure Python dataclasses with no dependency on pandas, the Anthropic
SDK, or any wire format. Infrastructure layers (parsing, mapping) map their own
models onto these at the boundary. `target_field` is a plain string naming one
of the user's declared fields (`fields.models.FieldSet`) — no fixed field
vocabulary is compiled in here (D-19).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ColumnCandidate:
    """One alternative the mapper considered for a target field.

    Present when a column is ambiguous — instead of a bare guess, the mapper
    offers 2-3 ranked options for the curator to choose from.
    """

    source_column: str
    confidence: float


@dataclass
class FieldMapping:
    """How one target field was resolved from the source table.

    `target_field` names one of the user's declared fields as a plain
    string — there is no compile-time enum of allowed names (D-19); the
    field set the mapper was called with is the only source of truth for
    what a valid name is. `source_column` is None when no column matched. In
    that case the mapper may still populate `inferred_value` (e.g. a unit
    inferred from the value range), but such a field is never silently
    trusted — `needs_confirmation` is set.
    """

    target_field: str
    source_column: str | None
    confidence: float
    reasoning: str
    needs_confirmation: bool
    inferred_value: str | None = None
    alternatives: list[ColumnCandidate] = field(default_factory=list)

    @property
    def is_clear(self) -> bool:
        """A field is clear (green) only when nothing needs a human's eyes."""
        return not self.needs_confirmation


@dataclass
class MappingProposal:
    """The full proposed mapping for one source file.

    Claude proposes; a human disposes. Nothing is exported while any field is
    unclear — `is_ready` gates the confirm/export step.
    """

    source_columns: list[str]
    field_mappings: list[FieldMapping]

    @property
    def is_ready(self) -> bool:
        """True only when every target field is clear (no yellow flags left).

        A proposal holding no fields at all is not ready — `all([])` is True,
        and an empty mapping must never present itself as an exportable one.
        """
        return bool(self.field_mappings) and all(m.is_clear for m in self.field_mappings)

    @property
    def unclear_fields(self) -> list[FieldMapping]:
        return [m for m in self.field_mappings if not m.is_clear]
