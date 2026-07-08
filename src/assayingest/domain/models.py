"""Domain models — the target shape AssayIngest maps every CRO file into.

These are pure Python dataclasses with no dependency on pandas, the Anthropic
SDK, or any wire format. Infrastructure layers (parsing, mapping) map their own
models onto these at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TargetField(str, Enum):
    """The seven fields every ingested assay record must resolve to."""

    COMPOUND_ID = "compound_id"
    ASSAY_TYPE = "assay_type"
    VALUE = "value"
    UNIT = "unit"
    TARGET = "target"
    N_REPLICATES = "n_replicates"
    ASSAY_DATE = "assay_date"


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

    `source_column` is None when no column matched. In that case the mapper may
    still populate `inferred_value` (e.g. a unit inferred from the value range),
    but such a field is never silently trusted — `needs_confirmation` is set.
    """

    target_field: TargetField
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
        """True only when every target field is clear (no yellow flags left)."""
        return all(m.is_clear for m in self.field_mappings)

    @property
    def unclear_fields(self) -> list[FieldMapping]:
        return [m for m in self.field_mappings if not m.is_clear]