"""Load a user-declared field set from a YAML or JSON file (D-01/D-02).

Mirrors `parsing/table.py`'s `parse_file`/`sheet_names` shape: normalise the
path, check it exists, dispatch on suffix, and raise a named error for
anything broken — a malformed field-set file is broken input, not
structural uncertainty (`parsing/table.py`'s own framing: "only a genuinely
broken file... still raises").

Security-critical: YAML is parsed exclusively via `yaml.safe_load`, never
`yaml.load` (D-03, T-02-01). `yaml.load`/`FullLoader` can construct
arbitrary Python objects from a malicious document (CVE-2020-1747,
CVE-2020-14343) — an obvious remote-code path in a tool whose entire purpose
is ingesting files from strangers. This is the phase's highest-priority
security control.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from .models import FIELD_TYPES, Field, FieldSet

#: A field set holding more than this many fields is rejected before any
#: schema or Field is built (D-04, T-02-02) — an accidental 200-field set
#: must fail with a named error, not an opaque SDK/context-limit failure.
MAX_FIELDS: int = 50

_YAML_SUFFIXES = {".yaml", ".yml"}


def load(path: str | Path) -> FieldSet:
    """Load a field set from a `.yaml`/`.yml` or `.json` file.

    Raises `FileNotFoundError` for a missing path, `ValueError` for an
    unsupported extension, a field missing its required `name`, an unknown
    declared `type`, or more than `MAX_FIELDS` fields declared.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Cannot load field set: no file at {path}")

    suffix = path.suffix.lower()
    if suffix in _YAML_SUFFIXES:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    elif suffix == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
    else:
        raise ValueError(
            f"Cannot load field set {path.name}: expected a .yaml or .json "
            f"file, got '{path.suffix}'"
        )
    return _build_field_set(raw)


def _build_field_set(raw: dict) -> FieldSet:
    """Build a `FieldSet` from the parsed document, enforcing the field cap
    before any `Field` is constructed (fail fast, D-04)."""
    field_specs = raw.get("fields", [])
    count = len(field_specs)
    if count > MAX_FIELDS:
        raise ValueError(
            f"Cannot load field set: {count} fields declared, exceeds the "
            f"{MAX_FIELDS}-field limit."
        )
    return FieldSet(
        fields=tuple(_build_field(spec) for spec in field_specs),
        name=raw.get("name"),
    )


def _build_field(raw: dict) -> Field:
    """Build one `Field`, validating the two constraints the loader itself
    must enforce: a required `name` and a `type` from `FIELD_TYPES`."""
    name = raw.get("name")
    if not name:
        raise ValueError("Cannot load field set: every field requires a 'name'.")

    field_type = raw.get("type")
    if field_type is not None and field_type not in FIELD_TYPES:
        raise ValueError(
            f"Cannot load field set: field '{name}' declares unknown type "
            f"'{field_type}' — expected one of: {', '.join(FIELD_TYPES)}."
        )

    allowed_values = raw.get("allowed_values")
    return Field(
        name=name,
        description=raw.get("description"),
        type=field_type,
        allowed_values=tuple(allowed_values) if allowed_values is not None else None,
        unit=raw.get("unit"),
        required=raw.get("required", True),
        min=raw.get("min"),
        max=raw.get("max"),
        date_format=raw.get("date_format"),
    )
