"""The structural-question contract — what the parser is unsure about, and why.

Pure Python dataclasses with no dependency on pandas, the Anthropic SDK, or
any wire format (D-04) — the deterministic layer must be testable without an
API key. These mirror `domain/models.py`'s "propose + confidence + gate"
shape one layer earlier: `StructureQuestion` is `FieldMapping`'s analog for
*structure* instead of *column meaning* (D-02, D-07). Every field is
JSON-serialisable because the same object is persisted with a learned
profile (LEARN-06, Phase 3) and travels over HTTP to the browser (UI-02,
Phase 4) — no CLI-only representation lives here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class TableShape(str, Enum):
    """The structural shapes the parser can classify a table's raw grid as.

    Only `row_per_record` produces a `RawTable` (D-10) — every other shape is
    unsupported in v1 and surfaces as a `StructureQuestion` instead of a
    silently-wrong table (D-11).
    """

    ROW_PER_RECORD = "row_per_record"
    WIDE_MATRIX = "wide_matrix"
    TRANSPOSED = "transposed"
    MULTIPLE_TABLES = "multiple_tables"
    UNKNOWN = "unknown"


class NumericLocale(str, Enum):
    """A column's inferred decimal-separator convention.

    Annotated per column, never per cell (D-13) — a single value cannot prove
    which convention is in use; only variance across the column can (D-14).
    """

    DECIMAL_COMMA = "decimal_comma"
    DECIMAL_POINT = "decimal_point"
    AMBIGUOUS = "ambiguous"
    NON_NUMERIC = "non_numeric"


@dataclass(frozen=True)
class StructuralHint:
    """The structural dimensions a human (or Claude) can pin down.

    Every field is optional so a hint can carry just the one dimension in
    question — e.g. only `header_row_index` when the header row is unclear
    but the delimiter and locale already resolved cleanly (D-06).
    """

    sheet_name: str | None = None
    header_row_index: int | None = None
    delimiter: str | None = None
    decimal_separator: str | None = None
    data_region: str | None = None
    table_shape: TableShape | None = None

    def to_dict(self) -> dict:
        """A plain JSON-safe dict — enum members coerced to their string value."""
        return _jsonable(asdict(self))


@dataclass(frozen=True)
class StructureQuestion:
    """What the tool is unsure about, and everything a human needs to answer it.

    `reason` describes the consequence of guessing wrong, not the symptom
    (project convention) — e.g. "guessing risks corrupting the value by
    1000x" rather than "the value looks odd". `proposal` pre-fills the likely
    answer (heuristics today, Claude in a later plan) but is never
    auto-applied (D-02) — only a human confirms or corrects it.
    `evidence_rows` carries enough of the raw grid for a human to answer
    without opening the file (D-07).

    `answerable_by_hint` is False when no `StructuralHint` can resolve the
    question at all — an unsupported table shape, say, where un-pivoting is
    deferred to v2 (D-11, PARSE-V2-01). Such a question still names the
    problem and shows its evidence; it just must not advertise an answer that
    would not work. Offering an unhelpful hint is a quieter kind of guessing.
    """

    unsure_about: str
    reason: str
    confidence: float
    proposal: StructuralHint | None = None
    alternatives: list[StructuralHint] = field(default_factory=list)
    evidence_rows: list[list[str]] = field(default_factory=list)
    answerable_by_hint: bool = True

    def to_dict(self) -> dict:
        """A plain JSON-safe dict — the shape that travels over HTTP (UI-02)."""
        return {
            "unsure_about": self.unsure_about,
            "reason": self.reason,
            "confidence": self.confidence,
            "proposal": self.proposal.to_dict() if self.proposal is not None else None,
            "alternatives": [alt.to_dict() for alt in self.alternatives],
            "evidence_rows": self.evidence_rows,
        }


def _jsonable(value: object) -> object:
    """Recursively coerce enum members (left as-is by `asdict`) to their value."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value
