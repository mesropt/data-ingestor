"""Seed the shipped starter presets into a `FieldSetTemplateStore`
(FIELD-05, quick 260712-e0e) AND, since Phase 10 (D-10-14, INGEST-06), into a
`SchemaStore` as four governed Schemas -- both run from `_lifespan` at
startup.

`seed_presets` (the original field-set-template seeding) is UNTOUCHED and
kept exactly as it was: the `field_set_templates` rows it writes are neither
migrated nor deleted (10-RESEARCH.md Runtime State Inventory) -- the
underlying picker just no longer has a UI once Plan 06/07 delete it.
`seed_schemas` (Phase 10) is a NEW, parallel seeding step, not a widening of
`seed_presets` or a replacement of it: quick task 260712-e0e's field-set
seeding is RE-TARGETED (a second, additive seed onto a different store), not
extended in place.

Both seed functions share the SAME insert-if-absent, never-upsert discipline
(T-e0e-02): a store write that mints a fresh id on every call (`save` for
field sets, `create_schema` for Schemas) must never run unconditionally on
every restart, or it would both duplicate nothing (harmless) and silently
re-mint every preset's id (harmful -- breaks a persisted frontend reference,
and reverts any curator edit made under a preset's name). Reading the store
once and skipping already-present names is what keeps seeding idempotent and
id-stable for both stores alike.

`seed_schemas` skips a Schema by NAME alone -- never `add_or_update_fields`
on an already-seeded (or curator-created) Schema, even if that Schema is
later found to be "missing" a preset field. A curator's deliberately
tombstoned field is a fact about THAT Schema; resurrecting it on a restart
would be a genuine bug, and is exactly what the name-only insert-if-absent
check here structurally prevents (there is no code path that ever reaches a
field-level write against an existing Schema).

`learning` already imports `fields` elsewhere (`postgres_field_set_store.py`
imports `fields.loader`/`fields.models`); this keeps that same dependency
direction rather than making `fields` depend on `learning`.
"""

from __future__ import annotations

from ..fields.presets import load_presets
from .field_set_store import FieldSetTemplateStore
from .schema_store import SchemaStore


def seed_presets(store: FieldSetTemplateStore) -> list[str]:
    """Insert every shipped preset not already present in `store` by name.

    Returns the names actually seeded (empty on a store that already holds
    all of them, or a repeat call) -- callers that want to log/report what
    happened don't need a second `store.list()` diff.
    """
    existing_names = {name for _, name in store.list()}
    seeded: list[str] = []
    for name, field_set in load_presets():
        if name in existing_names:
            continue
        store.save(name, field_set)
        seeded.append(name)
    return seeded


def seed_schemas(store: SchemaStore) -> list[str]:
    """Insert every shipped preset not already present in `store`, as a
    governed Schema (D-10-14, INGEST-06) -- so a fresh sign-in has something
    to select immediately.

    Insert-if-absent BY NAME ONLY, exactly like `seed_presets` above: a
    Schema already present under a preset's name -- whether it was created
    by an earlier seeding pass, or by a curator who happened to choose that
    same name -- is left COMPLETELY untouched. This function never calls
    `add_or_update_fields`/`update_field`/`remove_field` on an existing
    Schema under any circumstance, so a curator's tombstoned field, added
    field, or edited constraint all survive every restart unchanged.
    `created_by=None`: a seeded Schema has no human author, it ships with
    the tool.

    Returns the names actually seeded (empty on a store that already holds
    all four, or a repeat call).
    """
    existing_names = {schema.name for schema in store.list_schemas()}
    seeded: list[str] = []
    for name, field_set in load_presets():
        if name in existing_names:
            continue
        store.create_schema(name, field_set.fields, None)
        seeded.append(name)
    return seeded
