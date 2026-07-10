"""Field-set domain model — the fields a user declares, not the tool (D-05..D-11).

Pure Python dataclasses with no dependency on pandas, the Anthropic SDK, or
any wire format — the deterministic layer must be testable without an API
key, mirroring `parsing/hint.py`'s "frozen dataclass, optional fields,
`to_dict()`" shape. A `FieldSet` also doubles as this project's stable
identity hook for Phase 3's learning-loop key `(field set, column
signature)` — `signature` must be order-independent so declaring the same
fields in a different order in a hand-edited YAML file does not invalidate a
learned profile.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

#: The only field types a field set may declare (D-06). This is what makes
#: Phase 1's `column_locales` actionable: a `decimal_comma` column declared
#: `number` is the one thing safe to convert (EXPORT-01, D-14).
FIELD_TYPES: tuple[str, ...] = ("number", "integer", "date", "text")


@dataclass(frozen=True)
class Field:
    """One target field a user declares — `name` is the only requirement.

    Every other attribute defaults to `None`/`True` (D-05..D-11): a field-set
    author supplies only the constraints they actually know about their
    data. Constraints are declared here and enforced by Phase 3's no-LLM
    validator; `type` and `date_format` are the two exceptions the canonical
    form (EXPORT-01) needs immediately in order to normalise anything at all.
    """

    name: str
    description: str | None = None
    type: str | None = None
    allowed_values: tuple[str, ...] | None = None
    unit: str | None = None
    required: bool = True
    min: float | None = None
    max: float | None = None
    date_format: str | None = None

    def to_dict(self) -> dict:
        """A plain JSON-safe dict — the shape a field set round-trips through."""
        data = asdict(self)
        if data["allowed_values"] is not None:
            data["allowed_values"] = list(data["allowed_values"])
        return data


@dataclass(frozen=True)
class FieldSet:
    """The complete set of fields a user wants extracted from a source file."""

    fields: tuple[Field, ...]
    name: str | None = None

    @property
    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]

    @property
    def signature(self) -> str:
        """An order-independent identity for this exact set of field declarations.

        Phase 3 keys a learned profile on `(field set, column signature)`
        (STATE.md decision) — renaming, adding, or removing a field must
        change this value; reordering the same fields in a hand-edited YAML
        file must not, so every field is normalised and the resulting list
        is sorted before hashing.
        """
        normalised = sorted(
            json.dumps(_normalise_field(f), sort_keys=True) for f in self.fields
        )
        digest = hashlib.sha256(json.dumps(normalised, sort_keys=True).encode("utf-8"))
        return digest.hexdigest()

    def to_dict(self) -> dict:
        """A plain JSON-safe dict — the shape that travels over HTTP (Phase 4)."""
        return {"name": self.name, "fields": [f.to_dict() for f in self.fields]}


def _normalise_field(f: Field) -> dict:
    """The subset of a field's declaration that defines its identity.

    `name` is lower-cased to match D-07's own case-insensitive comparison
    convention for `allowed_values` — a field renamed only in case is still
    considered the same field for signature purposes.
    """
    return {
        "name": f.name.lower(),
        "type": f.type,
        "unit": f.unit,
        "allowed_values": sorted(f.allowed_values) if f.allowed_values else None,
        "required": f.required,
        "min": f.min,
        "max": f.max,
        "date_format": f.date_format,
    }
