"""Seeding the 4 shipped presets into the field-set template store at
startup (FIELD-05, quick task 260712-e0e), TDD RED-first.

Store-level tests exercise `seed_presets` directly against a
`SqliteFieldSetStore(tmp_path / "profiles.db")` -- never the real demo
database. HTTP-level tests prove the app's lifespan actually runs seeding
on startup, using the SAME `with TestClient(app) as client:` context-manager
form `tests/api/test_field_sets.py` never needs (bare `TestClient(app)` does
not run lifespan) so this test is the only one that exercises it.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from assayingest.fields.models import Field, FieldSet
from assayingest.learning.seed import seed_presets
from assayingest.learning.sqlite_field_set_store import SqliteFieldSetStore

_PRESET_NAMES = {"assay-potency", "clinical-labs", "pk-parameters", "reagent-inventory"}


# --- seed_presets (store-level) ----------------------------------------------


def test_seed_presets_on_an_empty_store_seeds_all_4(tmp_path):
    store = SqliteFieldSetStore(tmp_path / "profiles.db")

    seeded = seed_presets(store)

    listed = store.list()
    assert set(seeded) == _PRESET_NAMES
    assert {name for _, name in listed} == _PRESET_NAMES
    for template_id, _ in listed:
        field_set = store.get(template_id)
        assert field_set is not None
        assert len(field_set.field_names) > 0


def test_seed_presets_is_idempotent_and_id_stable(tmp_path):
    store = SqliteFieldSetStore(tmp_path / "profiles.db")

    seed_presets(store)
    first_ids = {name: tid for tid, name in store.list()}

    second_seeded = seed_presets(store)
    second_ids = {name: tid for tid, name in store.list()}

    assert second_seeded == []
    assert len(store.list()) == 4
    assert second_ids == first_ids


def test_seed_presets_leaves_a_pre_existing_user_row_untouched(tmp_path):
    store = SqliteFieldSetStore(tmp_path / "profiles.db")
    empty_named_id = store.save("", FieldSet(fields=(Field(name="x"),)))
    my_fields_id = store.save("my-fields", FieldSet(fields=(Field(name="y"),)))

    seed_presets(store)

    listed = store.list()
    assert len(listed) == 6
    ids_by_name = {name: tid for tid, name in listed}
    assert ids_by_name[""] == empty_named_id
    assert ids_by_name["my-fields"] == my_fields_id


def test_seed_presets_does_not_overwrite_a_user_row_sharing_a_preset_name(tmp_path):
    store = SqliteFieldSetStore(tmp_path / "profiles.db")
    custom_field_set = FieldSet(fields=(Field(name="custom_field"),))
    user_id = store.save("assay-potency", custom_field_set)

    seed_presets(store)

    listed = store.list()
    assert len(listed) == 4  # not 5 -- the user row was not duplicated
    ids_by_name = {name: tid for tid, name in listed}
    assert ids_by_name["assay-potency"] == user_id
    found = store.get(user_id)
    assert found.field_names == ["custom_field"]


# --- app lifespan (HTTP-level) ------------------------------------------------


def test_get_field_sets_returns_the_4_presets_after_a_fresh_startup(tmp_path):
    from assayingest.api.app import app
    from assayingest.api.deps import get_field_set_store

    store = SqliteFieldSetStore(tmp_path / "profiles.db")
    app.dependency_overrides[get_field_set_store] = lambda: store
    try:
        with TestClient(app) as client:
            response = client.get("/api/field-sets")
        assert response.status_code == 200
        names = {row["name"] for row in response.json()}
        assert _PRESET_NAMES <= names
    finally:
        app.dependency_overrides.clear()


def test_a_second_startup_against_the_same_store_does_not_duplicate_or_remint_ids(tmp_path):
    from assayingest.api.app import app
    from assayingest.api.deps import get_field_set_store

    store = SqliteFieldSetStore(tmp_path / "profiles.db")
    app.dependency_overrides[get_field_set_store] = lambda: store
    try:
        with TestClient(app) as client:
            first_response = client.get("/api/field-sets")
        first_ids = {row["name"]: row["id"] for row in first_response.json()}

        with TestClient(app) as client:
            second_response = client.get("/api/field-sets")
        second_ids = {row["name"]: row["id"] for row in second_response.json()}

        assert second_ids == first_ids
        assert len(second_response.json()) == 4
    finally:
        app.dependency_overrides.clear()
