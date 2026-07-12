"""The learned-profile domain model (pure) -- what a curator's one-time
confirmation of a fully-clear mapping persists (LEARN-02/06, D-06/D-07/D-08).

Mirrors `parsing/hint.py::StructuralHint`'s "frozen dataclass + `to_dict()`"
shape: no dependency on pandas, a database driver, or the Anthropic SDK -- the
deterministic identity of a learned profile must be testable without a
database connection. No driver is imported in this module; the one
infrastructure module that touches the database is `learning/postgres_store.py`
(D-01 repository seam).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..parsing.hint import StructuralHint


@dataclass(frozen=True)
class StoredFieldMapping:
    """One field's resolved mapping, as persisted -- enough to reconstruct a
    `domain.models.FieldMapping` at confidence 1.0 without calling Claude.

    `source_column_normalised` stores the NORMALISED header (via
    `learning.signature._normalise_header`), never the raw original-cased
    string (D-05 auto-apply hazard, Pitfall 2): a signature match only
    proves the new file's columns are the same case/whitespace-tolerant
    multiset, not that any header is byte-identical to the one the profile
    was saved against. `source_column_occurrence` disambiguates duplicate
    or blank headers deterministically by left-to-right position.
    """

    target_field: str
    source_column_normalised: str | None
    source_column_occurrence: int
    inferred_value: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LearnedProfile:
    """A confirmed mapping, saved only when the proposal was fully clear
    (D-06). Keyed by `(field_set_signature, column_signature)` -- one
    vendor's format may drift over time, so one vendor may hold several
    profiles, one per format version (LEARN-05).
    """

    profile_id: str
    field_set_signature: str
    column_signature: str
    field_mappings: tuple[StoredFieldMapping, ...]
    structural_hint: StructuralHint | None
    created_at: str  # ISO-8601, e.g. datetime.now(UTC).isoformat()

    def to_dict(self) -> dict:
        """The exact shape EXPORT-04's manifest reuses (D-09).

        Recurses manually rather than a bare `asdict()`: `asdict()` alone
        would not call `StoredFieldMapping.to_dict()`/`StructuralHint.to_dict()`
        for the nested fields, so each is rendered explicitly here.
        """
        return {
            "profile_id": self.profile_id,
            "field_set_signature": self.field_set_signature,
            "column_signature": self.column_signature,
            "field_mappings": [m.to_dict() for m in self.field_mappings],
            "structural_hint": self.structural_hint.to_dict()
            if self.structural_hint is not None
            else None,
            "created_at": self.created_at,
        }
