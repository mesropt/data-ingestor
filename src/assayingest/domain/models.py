"""Domain models — the target shape every ingested file maps into.

These are pure Python dataclasses with no dependency on pandas, the Anthropic
SDK, or any wire format. Infrastructure layers (parsing, mapping) map their own
models onto these at the boundary. `target_field` is a plain string naming one
of the user's declared fields (`fields.models.FieldSet`) — no fixed field
vocabulary is compiled in here (D-19).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..fields.loader import from_dict as _field_set_from_dict
from ..fields.models import Field

#: The two provenances an alias may carry (ALIAS-03): a human confirmation
#: (`manual`, actor = the authenticated user email) or an imported master map
#: file (`from_map_file`, actor = the file's declared/derived source name).
#: This is the audit trail — it must never be overwritten on re-observation.
ProvenanceKind = Literal["manual", "from_map_file"]


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
    #: The no-LLM validator's own deterministic verdict (VAL-01/02/03) — kept
    #: as a separate field, not concatenated into `reasoning`, so the tool's
    #: mechanical check stays textually distinct from Claude's own reasoning
    #: (mirrors `mapping.mapper._with_hallucination_note`'s "tool note, kept
    #: separate" precedent, but as a field instead of a string append).
    #: `None` until `validation.validator.validate()` runs.
    validator_note: str | None = None

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


# --- Phase 07: canonical schema + vendor-alias crosswalk (D-07-01) ----------


@dataclass(frozen=True)
class Alias:
    """A vendor's raw column name for one canonical field, with provenance.

    Provenance (who/when) is the crosswalk's audit trail (ALIAS-03): once an
    alias is first observed its `provenance_actor` and `created_at` are
    immutable — a later re-observation never overwrites who recorded it or
    when. `vendor` and `source_column` are untrusted request/file input, so
    they only ever reach SQL through parameterised placeholders (never SQL
    string interpolation) in the store layer.
    """

    vendor: str
    source_column: str
    provenance_kind: ProvenanceKind
    provenance_actor: str
    created_at: str
    confidence: float | None = None
    note: str | None = None

    def to_dict(self) -> dict:
        """The five provenance-bearing keys, plus confidence/note only when set.

        Round-trips exactly: `Alias(**alias.to_dict())` reconstructs an equal
        alias, so the master map file is a lossless serialization.
        """
        data = {
            "vendor": self.vendor,
            "source_column": self.source_column,
            "provenance_kind": self.provenance_kind,
            "provenance_actor": self.provenance_actor,
            "created_at": self.created_at,
        }
        if self.confidence is not None:
            data["confidence"] = self.confidence
        if self.note is not None:
            data["note"] = self.note
        return data


@dataclass(frozen=True)
class CanonicalField:
    """One canonical field in a Schema: an existing `Field` plus its aliases.

    Composition, not subclassing (D-07-01): the reusable `fields.models.Field`
    is left entirely untouched and carries the name + constraints, while the
    parallel `aliases` tuple carries every vendor's name for it (ALIAS-01).
    """

    field: Field
    aliases: tuple[Alias, ...] = ()

    def to_dict(self) -> dict:
        """`Field.to_dict()` with an added `aliases` list — the per-field
        shape embedded in a Schema's master map envelope."""
        return {**self.field.to_dict(), "aliases": [a.to_dict() for a in self.aliases]}


@dataclass(frozen=True)
class Schema:
    """One governed canonical model per domain — its JSON export is the
    downloadable master map file (SCHEMA-01/02/03).

    `name` is the domain identity (unique per owner); `fields` are the
    canonical fields with their vendor aliases. Two Schemas never share
    fields or aliases (SCHEMA-04) — the store enforces that structurally.
    """

    id: str
    name: str
    fields: tuple[CanonicalField, ...]
    created_by: str | None
    created_at: str

    def to_master_map(self) -> dict:
        """A versioned envelope so a future VER-* milestone can bump the
        format without breaking older readers (D-07-01 Discretion)."""
        return {
            "schema_version": 1,
            "id": self.id,
            "name": self.name,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "fields": [f.to_dict() for f in self.fields],
        }

    @classmethod
    def from_master_map(cls, envelope: dict) -> Schema:
        """Rebuild a Schema from a master map envelope.

        Each field's name/type/constraints are re-validated through the SAME
        `fields.loader` guard the CLI `--fields` flag enforces (`from_dict` →
        `_validated_name`) — an imported field name carrying a newline or
        control character raises `ValueError` before it can ever reach a
        prompt (T-07-03), never a second, weaker check here. Aliases are
        re-attached to their field by name after validation.
        """
        raw_fields = envelope["fields"]
        bare_fields = []
        aliases_by_name: dict[str, tuple[Alias, ...]] = {}
        for raw in raw_fields:
            bare = {key: value for key, value in raw.items() if key != "aliases"}
            bare_fields.append(bare)
            aliases_by_name[bare["name"]] = tuple(
                Alias(**alias) for alias in raw.get("aliases", [])
            )

        field_set = _field_set_from_dict({"name": envelope["name"], "fields": bare_fields})
        canonical = tuple(
            CanonicalField(field=f, aliases=aliases_by_name.get(f.name, ()))
            for f in field_set.fields
        )
        return cls(
            id=envelope["id"],
            name=envelope["name"],
            fields=canonical,
            created_by=envelope.get("created_by"),
            created_at=envelope["created_at"],
        )


# --- Phase 08: reconcile-on-upload conflict types (D-08-02/04) ---------------


@dataclass(frozen=True)
class ReconcileConflict:
    """One alias-target disagreement between an uploaded map file and the master.

    The master already crosswalks `(vendor, source_column)` to `master_field`,
    while the uploaded map file asserts the SAME `(vendor, source_column)` pair
    resolves to a DIFFERENT canonical field (`map_file_field`). Per P1, the tool
    never silently picks a side — this disagreement is surfaced for the human to
    resolve (keep master / take map file). Identity is the exact
    `(vendor, source_column)` pair (D-08-04, no fuzzy matching in v1).
    """

    vendor: str
    source_column: str
    master_field: str
    map_file_field: str

    def to_dict(self) -> dict:
        """The four-key wire shape 08-02 serialises verbatim into the reconcile
        question response (mirrors how `StructureQuestion.to_dict` is reused)."""
        return {
            "vendor": self.vendor,
            "source_column": self.source_column,
            "master_field": self.master_field,
            "map_file_field": self.map_file_field,
        }


@dataclass(frozen=True)
class ReconcileQuestion:
    """The set of alias-target disagreements a reconcile must resolve before it
    may augment or map (P1). An empty `conflicts` tuple means the map file and
    master agree everywhere — the flow proceeds straight to augment + pre-fill."""

    conflicts: tuple[ReconcileConflict, ...]

    @property
    def has_conflicts(self) -> bool:
        """True when at least one disagreement must be resolved by a human."""
        return bool(self.conflicts)

    def to_dict(self) -> dict:
        """The wire shape 08-02 returns as the `reconcile_question` response
        kind (D-08-03), each conflict carrying its keep-master/take-map-file
        options at the route layer."""
        return {"conflicts": [c.to_dict() for c in self.conflicts]}
