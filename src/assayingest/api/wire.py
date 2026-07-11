"""HTTP wire models -- the Pydantic siblings of `mapping/schema.py`'s
Claude-facing wire models, but for the browser instead of Claude (Pattern
4/5). These live at the HTTP boundary only; they are never mixed into
`domain/models.py` (the same wire<->domain discipline `mapping/schema.py`'s
own module docstring states, applied in the opposite direction).

`MappingResponse`/`FieldMappingOut` are populated FROM
`cli.proposal_to_dict()` (never a second, hand-derived shape) plus
`validator_note`, which that dict omits (PATTERNS.md api/wire.py notes) --
the one place this module extends rather than mirrors byte-for-byte.
`StructuralQuestionResponse` reuses `StructureQuestion.to_dict()` verbatim,
adding only `kind` and `upload_token` (Pattern 5).
"""

from __future__ import annotations

from pydantic import BaseModel

from ..cli import proposal_to_dict
from ..domain.models import MappingProposal
from ..parsing.hint import StructureQuestion


class AlternativeOut(BaseModel):
    """Mirrors `mapping/schema.py::WireCandidate` -- the HTTP-facing shape
    for one ranked alternative column (D-02's chip UI)."""

    source_column: str
    confidence: float


class FieldMappingOut(BaseModel):
    """One target field's resolution -- field names identical to
    `cli._field_to_dict`'s dict keys, plus `validator_note` (that dict
    omits it; the wire model must add it, PATTERNS.md api/wire.py notes)."""

    target_field: str
    source_column: str | None
    confidence: float
    reasoning: str
    needs_confirmation: bool
    inferred_value: str | None = None
    alternatives: list[AlternativeOut]
    validator_note: str | None = None


class MappingResponse(BaseModel):
    """The `kind="mapping"` half of `/api/upload`'s discriminated response
    (Pattern 5). Built FROM `cli.proposal_to_dict()`'s dict so the CLI's
    JSON draft and this HTTP body never drift apart (Pattern 4)."""

    kind: str = "mapping"
    ready: bool
    source_columns: list[str]
    field_mappings: list[FieldMappingOut]
    provenance: str | None
    upload_token: str

    @classmethod
    def from_proposal(
        cls, proposal: MappingProposal, provenance: str | None, upload_token: str
    ) -> "MappingResponse":
        base = proposal_to_dict(proposal, provenance)
        notes_by_field = {m.target_field: m.validator_note for m in proposal.field_mappings}
        field_mappings = [
            FieldMappingOut(**field_dict, validator_note=notes_by_field[field_dict["target_field"]])
            for field_dict in base["field_mappings"]
        ]
        return cls(
            ready=base["ready"],
            source_columns=base["source_columns"],
            field_mappings=field_mappings,
            provenance=base["provenance"],
            upload_token=upload_token,
        )


class StructuralQuestionResponse(BaseModel):
    """The `kind="structural_question"` half of `/api/upload`'s
    discriminated response (Pattern 5) -- `StructureQuestion.to_dict()`'s
    shape plus `kind` and `upload_token`."""

    kind: str = "structural_question"
    unsure_about: str
    reason: str
    confidence: float
    proposal: dict | None
    alternatives: list[dict]
    evidence_rows: list[list[str]]
    answerable_by_hint: bool
    upload_token: str

    @classmethod
    def from_question(
        cls, question: StructureQuestion, upload_token: str
    ) -> "StructuralQuestionResponse":
        return cls(upload_token=upload_token, **question.to_dict())
