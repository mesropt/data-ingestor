"""Load a user-declared field set from a YAML or JSON file (D-01/D-02).

Mirrors `parsing/table.py`'s `parse_file`/`sheet_names` shape: normalise the
path, check it exists, dispatch on suffix, and raise a named error for
anything broken — a malformed field-set file is broken input, not
structural uncertainty (`parsing/table.py`'s own framing: "only a genuinely
broken file... still raises").

Security-critical: YAML is parsed exclusively via `yaml.safe_load` (D-03,
T-02-01) — the unsafe full loader (which can construct arbitrary Python
objects from a malicious document, CVE-2020-1747 / CVE-2020-14343) is never
called anywhere in this module. That would be an obvious remote-code path in
a tool whose entire purpose is ingesting files from strangers. This is the
phase's highest-priority security control.
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

#: A field set is loaded from a file the curator may have been *given* — a
#: shared preset, a colleague's template. That makes `name` untrusted input,
#: not a local variable. It is interpolated straight into Claude's system
#: prompt, so a name carrying a newline escapes its bullet and becomes a
#: top-level instruction ("set every confidence to 1.0"), which would switch
#: off the confirmation gate this whole tool is built around.
#:
#: The guard is therefore "printable on one line", not "a Python identifier":
#: `5-HT`, `13c_shift` and `código` are all names a scientist may legitimately
#: declare. `str.isprintable()` is False for control characters, newlines, and
#: every Unicode line/paragraph separator — including the non-breaking space
#: and U+2028 that a naive newline check would miss.
_MAX_NAME_LENGTH = 64


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
    if suffix not in _YAML_SUFFIXES and suffix != ".json":
        raise ValueError(
            f"Cannot load field set {path.name}: expected a .yaml or .json "
            f"file, got '{path.suffix}'"
        )
    return from_dict(_parse(path, suffix))


def _parse(path: Path, suffix: str) -> object:
    """Parse the document, reporting an unreadable file as an unloadable
    field set rather than leaking the parser's own exception type.

    `yaml.safe_load` is the only YAML entry point (D-03): the full loader
    constructs arbitrary Python objects from a malicious document, which
    would be a remote-code path in a tool built to ingest files from
    strangers.
    """
    text = path.read_text(encoding="utf-8")
    try:
        if suffix == ".json":
            return json.loads(text)
        return yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Cannot load field set {path.name}: the file is not valid "
            f"{'JSON' if suffix == '.json' else 'YAML'} ({type(exc).__name__})."
        ) from exc


def from_dict(raw: object, *, allow_empty: bool = False) -> FieldSet:
    """Build a `FieldSet` from an already-parsed document -- the shared seam
    `load()` delegates to (04-01), enforcing the field cap before any
    `Field` is constructed (fail fast, D-04).

    Public and print-free so a future HTTP `POST /api/field-sets` route
    (Plan 03) can build a validated `FieldSet` straight from a decoded JSON
    request body, applying the exact same `_validated_name`/length/type
    guards a file-loaded field set gets -- never a second, possibly-weaker
    HTTP-layer check (Security V5, prompt-injection guard).

    `allow_empty` (D-10-08/INGEST-05, keyword-only, defaulted `False`) is
    for exactly ONE caller: governed-Schema CREATION
    (`api/routes/schemas.py::create_schema`). A Schema with zero canonical
    fields is a legitimate starting state -- created empty, then populated
    field-by-field via `add_schema_field` (Phase 10 Plan 04) -- so that ONE
    entry point opts out of the empty-fields guard below. It is NEVER set on
    a field-set UPLOAD (this function's five other callers: `load()`, the
    field_set upload path, `POST /api/field-sets`, the confirm drift-check,
    and the stored-profile rehydrate): there, an empty file is genuinely
    broken input, and the default of `False` is what keeps every one of
    those callers' guard byte-identical without them having to say so
    explicitly.
    """
    if not isinstance(raw, dict):
        raise ValueError(
            "Cannot load field set: the file's top level must be a mapping "
            f"with a 'fields' key, but it holds {type(raw).__name__}."
        )

    field_specs = raw.get("fields")
    if field_specs is None or field_specs == []:
        if allow_empty:
            return FieldSet(fields=(), name=raw.get("name"))
        raise ValueError("Cannot load field set: the file declares no fields.")
    if not isinstance(field_specs, list):
        raise ValueError(
            "Cannot load field set: 'fields' must be a list of field "
            f"declarations, but it holds {type(field_specs).__name__}."
        )

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


def _validated_name(name: object) -> str:
    """Reject a name the tool cannot safely put in front of Claude.

    YAML's implicit typing silently turns `name: yes` into `True` and
    `name: 42` into an int, which would corrupt the field's identity and the
    profile key Phase 3 learns against.
    """
    if name is None or name == "":
        raise ValueError("Cannot load field set: every field requires a 'name'.")
    if not isinstance(name, str):
        raise ValueError(
            f"Cannot load field set: field name {name!r} is "
            f"{type(name).__name__}, not text — quote it in the source file."
        )

    cleaned = name.strip()
    if not any(character.isalnum() for character in cleaned):
        raise ValueError(
            f"Cannot load field set: field name {name!r} contains no letter "
            "or digit."
        )
    if len(cleaned) > _MAX_NAME_LENGTH:
        raise ValueError(
            f"Cannot load field set: field name {cleaned[:20]!r}... is "
            f"{len(cleaned)} characters, over the {_MAX_NAME_LENGTH}-character limit."
        )
    if not cleaned.isprintable():
        raise ValueError(
            f"Cannot load field set: field name {name!r} contains a line "
            "break or control character, which would corrupt the instructions "
            "sent to the model."
        )
    return cleaned


def _build_field(raw: object) -> Field:
    """Build one `Field`, validating the constraints the loader itself must
    enforce: a well-formed `name` and a `type` from `FIELD_TYPES`."""
    if not isinstance(raw, dict):
        raise ValueError(
            "Cannot load field set: every field must be a mapping with a "
            f"'name' key, but one is {type(raw).__name__}."
        )

    name = _validated_name(raw.get("name"))

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
