"""PostgresFieldSetStore behaviour (D-03).

NEW coverage. The field-set store had no dedicated unit tests -- it was only
exercised indirectly through `tests/api/test_field_sets.py` and
`tests/api/test_preset_seeding.py`. That is the store STARTUP SEEDING depends on,
so leaving it unproven at the moment the DI flips to Postgres would be the one
place a silent break could hide (a blank field-set picker is exactly the
regression quick task 260712-e0e fixed).
"""

from __future__ import annotations

from assayingest.fields.models import Field, FieldSet


def _field_set(name: str | None = "demo", unit: str | None = "nM") -> FieldSet:
    return FieldSet(
        name=name,
        fields=(
            Field(name="compound_id", type="text"),
            Field(name="value", type="number", unit=unit, min=0.0, max=1000.0),
        ),
    )


def test_save_then_get_round_trips_the_field_set(field_set_store):
    template_id = field_set_store.save("demo", _field_set())

    got = field_set_store.get(template_id)

    assert got == _field_set()


def test_get_unknown_id_returns_none(field_set_store):
    assert field_set_store.get("no-such-template") is None


def test_list_returns_id_name_pairs_ordered_by_name(field_set_store):
    field_set_store.save("zebra", _field_set(name="zebra"))
    field_set_store.save("alpha", _field_set(name="alpha"))
    field_set_store.save("middle", _field_set(name="middle"))

    listed = field_set_store.list()

    assert [name for _, name in listed] == ["alpha", "middle", "zebra"]


def test_saving_the_same_name_again_updates_rather_than_duplicating(field_set_store):
    field_set_store.save("demo", _field_set(unit="nM"))

    # The upsert on UNIQUE(name) mints a FRESH id and returns it -- which is exactly
    # why `learning/seed.py` skips names already present instead of seeding
    # unconditionally, or every restart would silently re-mint every preset's id.
    second_id = field_set_store.save("demo", _field_set(unit="uM"))

    listed = field_set_store.list()
    assert len(listed) == 1
    assert listed[0][0] == second_id
    assert field_set_store.get(second_id).fields[1].unit == "uM"


def test_a_round_tripped_template_is_rebuilt_through_the_loader_guards(field_set_store):
    # Rebuilt via `fields.loader.from_dict`, never a bare `FieldSet(**...)`, so a
    # stored template gets the same name/length/type guards a freshly-declared one
    # did -- never a second, weaker reconstruction path.
    template_id = field_set_store.save("demo", _field_set())

    got = field_set_store.get(template_id)

    assert isinstance(got, FieldSet)
    assert got.field_names == ["compound_id", "value"]
    assert got.fields[1].min == 0.0
    assert got.fields[1].required is True
    assert got.signature == _field_set().signature
