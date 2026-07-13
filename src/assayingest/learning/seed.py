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

`seed_schema_aliases` (Phase 11, D-11-18) is the THIRD seeding step, and the
only one that writes into a Schema that may already exist. It is additive and
tombstone-safe by construction -- it inserts aliases and nothing else, through
`seed_alias` and never `add_alias` (see its own docstring for why that
distinction is load-bearing rather than stylistic).

`learning` already imports `fields` elsewhere (`postgres_field_set_store.py`
imports `fields.loader`/`fields.models`); this keeps that same dependency
direction rather than making `fields` depend on `learning`.
"""

from __future__ import annotations

from ..domain.models import Alias
from ..fields.presets import load_preset_aliases, load_presets
from .field_set_store import FieldSetTemplateStore
from .schema_store import SchemaStore

#: The vendor every seeded starter spelling is recorded under (D-11-18). Not a
#: real CRO: these spellings are the tool's opening offer, drawn from what labs
#: commonly write, and a curator can retire any of them. A single shared vendor
#: also means two starter spellings claiming the same header would COLLIDE in
#: `_vendor_agnostic_alias_index` and match nothing -- which is why the shipped
#: data is pinned collision-free by `tests/test_preset_aliases.py`.
_SEED_VENDOR = "starter"

#: WHO recorded these (ALIAS-02) -- the tool itself, not a human curator.
_SEED_ACTOR = "preset-seed"

#: A CONSTANT, never `datetime.now()`. Seeding runs on every boot; a fresh
#: timestamp each time would either rewrite the audit trail (if seeding upserted)
#: or, worse, make each restart look like a new curation event. The date the
#: starter sets shipped is the honest answer and it never changes (ALIAS-03).
_SEED_CREATED_AT = "2026-07-13T00:00:00+00:00"


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


def seed_schema_aliases(store: SchemaStore) -> int:
    """Seed each preset Schema's vendor crosswalk with the starter header
    spellings its YAML declares (SHEET-05, D-11-18). Returns the number of
    aliases actually inserted -- 0 on a repeat run.

    Without this the crosswalk is EMPTY on a fresh install: the Schema scorer
    finds 0/N coverage for every Schema on every sheet, proposes "skip"
    everywhere, and SHEET-05 ships dead. It also backfills the EXISTING install,
    whose Schemas `seed_schemas` created field-only.

    ADDITIVE AND CURATOR-SAFE, structurally:

      * It only ever INSERTS aliases. There is no code path from here to
        `add_or_update_fields`, `update_field`, `remove_field`, or
        `remove_alias` -- so a curator's edited constraint, added field,
        tombstoned field and deleted alias all survive every restart (T-11-05).
      * It never CREATES a Schema. `seed_schemas` owns creation; a preset whose
        Schema is absent is skipped, not conjured.
      * It goes through `seed_alias`, NEVER `add_alias`. `add_alias`'s
        ON CONFLICT is scoped to the partial live-only unique index and does not
        see a tombstoned row, so it would resurrect a curator-deleted starter
        alias on every boot (D-10-15, T-11-04). `seed_alias` refuses to insert
        when ANY row exists, tombstoned included.
      * It reads Schemas ONLY through `SchemaStore.get_schema`, whose tombstone
        filtering is structural (D-11-23) -- never by a second route.
    """
    inserted = 0
    for preset_name, field_aliases in load_preset_aliases().items():
        schema = store.get_schema(preset_name)
        if schema is None:
            continue
        for field_name, spellings in field_aliases.items():
            for spelling in spellings:
                if store.seed_alias(schema.id, field_name, _starter_alias(spelling)):
                    inserted += 1
    return inserted


def _starter_alias(source_column: str) -> Alias:
    return Alias(
        vendor=_SEED_VENDOR,
        source_column=source_column,
        provenance_kind="manual",
        provenance_actor=_SEED_ACTOR,
        created_at=_SEED_CREATED_AT,
    )
