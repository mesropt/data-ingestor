"""Seeding the presets' starter aliases into the governed crosswalk
(SHEET-05, D-11-18), TDD RED-first.

THE WHOLE RISK OF THIS PLAN IS THE TOMBSTONE TRAP, and it is what most of this
file exists to pin. `add_alias` is `ON CONFLICT DO NOTHING` against a PARTIAL
unique index (`WHERE removed_at IS NULL`, D-10-15): a tombstoned alias does not
conflict, so a seeder routed through `add_alias` would happily INSERT a fresh
live row and RESURRECT an alias the curator deliberately deleted -- on every
single restart, silently, forever. That is why `SchemaStore.seed_alias` exists
and why it is the ONE read in this codebase that deliberately sees tombstoned
rows: it inserts only when NO row exists for (canonical field, vendor, source
column), live OR tombstoned.

The seeder is otherwise additive and curator-safe: it only ever inserts aliases.
It never creates a Schema (`seed_schemas` owns that), never calls
`add_or_update_fields`/`update_field`/`remove_field`/`remove_alias`, and never
restamps provenance -- a re-seed must be a no-op, not an audit-trail rewrite
(ALIAS-03).

Mirrors `tests/test_schema_store_tombstones.py`'s harness: the same
`schema_store` fixture, no second harness, one contract per test.
"""

from __future__ import annotations

from assayingest.domain.models import Alias
from assayingest.fields.models import Field
from assayingest.fields.presets import load_preset_aliases
from assayingest.learning.seed import seed_schema_aliases, seed_schemas

_PRESET_NAMES = {"assay-potency", "clinical-labs", "pk-parameters", "reagent-inventory"}


def _starter(preset: str, field: str) -> tuple[str, ...]:
    return load_preset_aliases()[preset][field]


def _live_columns(schema_store, schema_id: str) -> set[str]:
    return {alias.source_column for alias in schema_store.list_aliases_for(schema_id)}


# --- a fresh install ---------------------------------------------------------


def test_seeding_a_fresh_store_gives_every_preset_schema_its_starter_crosswalk(
    schema_store,
):
    """Without this, crosswalk coverage is 0/N for every Schema on every sheet,
    every sheet is proposed as skip, and SHEET-05 ships dead."""
    seed_schemas(schema_store)

    inserted = seed_schema_aliases(schema_store)

    assert inserted > 0
    for schema in schema_store.list_schemas():
        if schema.name not in _PRESET_NAMES:
            continue
        columns = _live_columns(schema_store, schema.id)
        for field_name, spellings in load_preset_aliases()[schema.name].items():
            assert set(spellings) <= columns, f"{schema.name}.{field_name} was not seeded"


def test_every_seeded_alias_carries_the_seeder_s_provenance_and_a_fixed_timestamp(
    schema_store,
):
    """`preset-seed` names WHO recorded the spelling (ALIAS-02), and the
    timestamp is a CONSTANT, never `now()` -- a per-restart timestamp would make
    every boot look like a fresh curation event in the audit trail."""
    seed_schemas(schema_store)
    seed_schema_aliases(schema_store)

    assay_potency = schema_store.get_schema("assay-potency")
    aliases = schema_store.list_aliases_for(assay_potency.id)

    assert aliases
    for alias in aliases:
        assert alias.vendor == "starter"
        assert alias.provenance_kind == "manual"
        assert alias.provenance_actor == "preset-seed"
        assert alias.created_at  # a real, stable timestamp -- asserted stable below


# --- the EXISTING install, whose Schemas were seeded field-only ---------------


def test_seeding_backfills_an_existing_field_only_schema_without_recreating_it(
    schema_store,
):
    """The builder's live database: `seed_schemas` created its four Schemas with
    fields and ZERO aliases. A restart must backfill the crosswalk in place --
    same Schema id, same fields, nothing recreated."""
    seed_schemas(schema_store)
    before = {s.name: (s.id, tuple(cf.field.name for cf in s.fields)) for s in schema_store.list_schemas()}
    assert all(cf.aliases == () for s in schema_store.list_schemas() for cf in s.fields)

    seed_schema_aliases(schema_store)

    after = {s.name: (s.id, tuple(cf.field.name for cf in s.fields)) for s in schema_store.list_schemas()}
    assert after == before  # no Schema recreated, no field added, removed, or renamed
    assert _live_columns(schema_store, before["assay-potency"][0])


def test_seeding_never_creates_a_schema_that_seed_schemas_did_not(schema_store):
    """`seed_schemas` owns creation. On a store with no Schemas at all, the alias
    seeder inserts nothing and creates nothing -- it does not quietly take over."""
    inserted = seed_schema_aliases(schema_store)

    assert inserted == 0
    assert schema_store.list_schemas() == []


# --- idempotence -------------------------------------------------------------


def test_a_second_seeding_run_inserts_nothing_and_does_not_restamp_provenance(
    schema_store,
):
    seed_schemas(schema_store)
    first = seed_schema_aliases(schema_store)
    assay_potency = schema_store.get_schema("assay-potency")
    before = {
        (a.vendor, a.source_column): (a.provenance_actor, a.created_at)
        for a in schema_store.list_aliases_for(assay_potency.id)
    }

    second = seed_schema_aliases(schema_store)  # a "restart"

    after = {
        (a.vendor, a.source_column): (a.provenance_actor, a.created_at)
        for a in schema_store.list_aliases_for(assay_potency.id)
    }
    assert first > 0
    assert second == 0
    assert after == before  # not one row re-minted, not one timestamp rewritten


# --- THE TOMBSTONE TRAP (D-10-15, T-11-04) -----------------------------------


def test_a_curator_removed_starter_alias_is_never_resurrected_by_a_later_seeding(
    schema_store,
):
    """THE test of this plan. A seeder routed through `add_alias` would pass every
    other test in this file and still fail this one: `ON CONFLICT DO NOTHING`
    against the PARTIAL live-only unique index does not see the tombstoned row, so
    it would insert a fresh live one and undo the curator's deletion on every
    restart."""
    seed_schemas(schema_store)
    seed_schema_aliases(schema_store)
    assay_potency = schema_store.get_schema("assay-potency")
    doomed = _starter("assay-potency", "compound_id")[0]
    assert doomed in _live_columns(schema_store, assay_potency.id)

    schema_store.remove_alias(
        assay_potency.id,
        "compound_id",
        "starter",
        doomed,
        removed_by="curator@example.com",
        removed_at="2026-07-13T00:00:00+00:00",
    )
    assert doomed not in _live_columns(schema_store, assay_potency.id)

    inserted = seed_schema_aliases(schema_store)  # a "restart"

    assert doomed not in _live_columns(schema_store, assay_potency.id)
    assert inserted == 0  # nothing came back -- not this alias, not any other


def test_a_removed_alias_stays_removed_across_many_restarts(schema_store):
    """Once is luck; the trap is that it comes back on the third boot."""
    seed_schemas(schema_store)
    seed_schema_aliases(schema_store)
    assay_potency = schema_store.get_schema("assay-potency")
    doomed = _starter("assay-potency", "target")[0]

    schema_store.remove_alias(
        assay_potency.id,
        "target",
        "starter",
        doomed,
        removed_by="curator@example.com",
        removed_at="2026-07-13T00:00:00+00:00",
    )

    for _ in range(3):
        seed_schema_aliases(schema_store)
        assert doomed not in _live_columns(schema_store, assay_potency.id)


def test_seeding_an_alias_for_a_tombstoned_field_neither_raises_nor_resurrects_it(
    schema_store,
):
    """A curator removed the field. That is their answer -- the seeder must accept
    it silently, not raise (which would abort the whole seeding pass) and not
    bring the field back."""
    seed_schemas(schema_store)
    assay_potency = schema_store.get_schema("assay-potency")
    schema_store.remove_field(
        assay_potency.id,
        "unit",
        removed_by="curator@example.com",
        removed_at="2026-07-13T00:00:00+00:00",
    )

    seed_schema_aliases(schema_store)  # must not raise

    reloaded = schema_store.get_schema("assay-potency")
    assert "unit" not in {cf.field.name for cf in reloaded.fields}
    # ...and the rest of the Schema was still seeded -- one dead field does not
    # take the whole pass down with it.
    assert _live_columns(schema_store, reloaded.id)


# --- the curator's own work survives -----------------------------------------


def test_a_curator_added_alias_survives_seeding_untouched(schema_store):
    seed_schemas(schema_store)
    assay_potency = schema_store.get_schema("assay-potency")
    schema_store.add_alias(
        assay_potency.id,
        "compound_id",
        Alias(
            vendor="AcmeLabs",
            source_column="Cmpd ID",
            provenance_kind="manual",
            provenance_actor="curator@example.com",
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )

    seed_schema_aliases(schema_store)

    curator_alias = next(
        a
        for a in schema_store.list_aliases_for(assay_potency.id)
        if a.vendor == "AcmeLabs"
    )
    assert curator_alias.source_column == "Cmpd ID"
    assert curator_alias.provenance_actor == "curator@example.com"
    assert curator_alias.created_at == "2026-01-01T00:00:00+00:00"


def test_seeding_leaves_a_curator_created_schema_under_a_preset_name_intact(
    schema_store,
):
    """A curator's Schema that happens to be named `assay-potency` has its OWN
    fields. The seeder adds aliases for the fields it does have and silently skips
    the rest -- it never adds a field, and never touches the ones there."""
    curator = schema_store.create_schema(
        "assay-potency",
        (Field(name="compound_id", type="text"), Field(name="custom_field")),
        "curator@example.com",
    )

    seed_schema_aliases(schema_store)

    reloaded = schema_store.get_schema("assay-potency")
    assert reloaded.id == curator.id
    assert [cf.field.name for cf in reloaded.fields] == ["compound_id", "custom_field"]
    columns = _live_columns(schema_store, reloaded.id)
    assert set(_starter("assay-potency", "compound_id")) <= columns
    # `value` is not a field of THIS Schema -- none of its spellings were seeded.
    assert not set(_starter("assay-potency", "value")) & columns


# --- SQL safety (T-11-07) -----------------------------------------------------


def test_seed_alias_binds_untrusted_spellings_as_parameters_never_as_sql(schema_store):
    hostile = "'; DROP TABLE alias; --"
    schema = schema_store.create_schema(
        "assay-potency", (Field(name="value"),), created_by="a@x.io"
    )
    alias = Alias(
        vendor=hostile,
        source_column=hostile,
        provenance_kind="manual",
        provenance_actor="preset-seed",
        created_at="2026-07-13T00:00:00+00:00",
    )

    assert schema_store.seed_alias(schema.id, "value", alias) is True
    assert schema_store.seed_alias(schema.id, "value", alias) is False  # already there

    stored = schema_store.list_aliases_for(schema.id)
    assert [a.source_column for a in stored] == [hostile]
