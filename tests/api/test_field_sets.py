"""FieldSetTemplateStore + SqliteFieldSetStore + /api/field-sets CRUD
(UI-01, D-03), TDD RED-first (04-03 Task 1).

Mirrors `tests/test_learning_loop_cli.py`'s store-level testing shape for
`SqliteProfileStore`, and `tests/api/test_upload.py`'s `TestClient` +
`app.dependency_overrides` idiom for the HTTP layer.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from assayingest.fields.models import Field, FieldSet
from assayingest.learning.sqlite_field_set_store import SqliteFieldSetStore


def _field_set() -> FieldSet:
    return FieldSet(
        name="novascreen-potency",
        fields=(
            Field(name="compound_id", type="text"),
            Field(name="value", type="number", min=0.0, max=1000.0),
        ),
    )


# --- SqliteFieldSetStore (store-level) ---------------------------------------


def test_save_returns_id_and_get_round_trips_to_an_equal_field_set(tmp_path):
    store = SqliteFieldSetStore(tmp_path / "profiles.db")
    field_set = _field_set()

    template_id = store.save("novascreen-potency", field_set)
    found = store.get(template_id)

    assert isinstance(template_id, str) and template_id
    assert found is not None
    assert found.to_dict() == field_set.to_dict()


def test_list_returns_id_name_tuples(tmp_path):
    store = SqliteFieldSetStore(tmp_path / "profiles.db")
    id1 = store.save("alpha", FieldSet(fields=(Field(name="x"),)))
    id2 = store.save("beta", FieldSet(fields=(Field(name="y"),)))

    listed = store.list()

    assert set(listed) == {(id1, "alpha"), (id2, "beta")}


def test_get_returns_none_for_an_unknown_id(tmp_path):
    store = SqliteFieldSetStore(tmp_path / "profiles.db")
    assert store.get("no-such-id") is None


def test_duplicate_name_upserts_never_duplicates(tmp_path):
    store = SqliteFieldSetStore(tmp_path / "profiles.db")
    store.save("novascreen-potency", _field_set())
    second_id = store.save(
        "novascreen-potency", FieldSet(fields=(Field(name="compound_id"),))
    )

    listed = store.list()

    assert len(listed) == 1
    assert listed[0] == (second_id, "novascreen-potency")
    found = store.get(second_id)
    assert found.field_names == ["compound_id"]


def test_field_set_name_with_sql_metacharacters_is_stored_and_retrieved_literally(
    tmp_path,
):
    """T-04-09: parameterized `?` placeholders only -- a name carrying SQL
    metacharacters must round-trip byte-for-byte, never corrupt the query or
    another row."""
    store = SqliteFieldSetStore(tmp_path / "profiles.db")
    hostile_name = "Robert'); DROP TABLE field_set_templates; --"

    template_id = store.save(hostile_name, FieldSet(fields=(Field(name="x"),)))

    listed = store.list()
    assert (template_id, hostile_name) in listed
    # The table must still exist and be queryable -- a real injection would
    # have dropped it.
    assert store.get(template_id) is not None


# --- /api/field-sets CRUD (HTTP layer) ----------------------------------------


def test_post_field_sets_persists_and_get_by_id_returns_the_field_set(tmp_path):
    from assayingest.api.app import app
    from assayingest.api.deps import get_field_set_store

    store = SqliteFieldSetStore(tmp_path / "profiles.db")
    app.dependency_overrides[get_field_set_store] = lambda: store
    client = TestClient(app)

    field_set = _field_set()
    post_response = client.post(
        "/api/field-sets",
        json={"name": "novascreen-potency", "field_set": field_set.to_dict()},
    )
    assert post_response.status_code == 200
    template_id = post_response.json()["id"]

    get_response = client.get(f"/api/field-sets/{template_id}")
    app.dependency_overrides.clear()

    assert get_response.status_code == 200
    assert get_response.json() == field_set.to_dict()


def test_get_field_sets_lists_saved_templates(tmp_path):
    from assayingest.api.app import app
    from assayingest.api.deps import get_field_set_store

    store = SqliteFieldSetStore(tmp_path / "profiles.db")
    app.dependency_overrides[get_field_set_store] = lambda: store
    client = TestClient(app)

    client.post(
        "/api/field-sets",
        json={"name": "novascreen-potency", "field_set": _field_set().to_dict()},
    )
    list_response = client.get("/api/field-sets")
    app.dependency_overrides.clear()

    assert list_response.status_code == 200
    body = list_response.json()
    assert len(body) == 1
    assert body[0]["name"] == "novascreen-potency"
    assert body[0]["field_set"]["fields"][0]["name"] == "compound_id"


def test_get_unknown_field_set_id_returns_404(tmp_path):
    from assayingest.api.app import app
    from assayingest.api.deps import get_field_set_store

    store = SqliteFieldSetStore(tmp_path / "profiles.db")
    app.dependency_overrides[get_field_set_store] = lambda: store
    client = TestClient(app)

    response = client.get("/api/field-sets/no-such-id")
    app.dependency_overrides.clear()

    assert response.status_code == 404


def test_post_field_sets_with_an_invalid_field_name_is_rejected_422(tmp_path):
    """T-04-11: reuses `fields.loader.from_dict`'s `_validated_name` guard --
    a name with no letter or digit (the same guard the CLI's `--fields` file
    loader enforces) is rejected before anything is persisted."""
    from assayingest.api.app import app
    from assayingest.api.deps import get_field_set_store

    store = SqliteFieldSetStore(tmp_path / "profiles.db")
    app.dependency_overrides[get_field_set_store] = lambda: store
    client = TestClient(app)

    response = client.post(
        "/api/field-sets",
        json={
            "name": "bad-field-name",
            "field_set": {"fields": [{"name": "***"}]},
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 422
    assert store.list() == []


def test_post_field_sets_body_must_be_valid_json_shape(tmp_path):
    """A body missing the required `name`/`field_set` keys is a 422 wire
    validation error from Pydantic, not a 500 crash."""
    from assayingest.api.app import app
    from assayingest.api.deps import get_field_set_store

    store = SqliteFieldSetStore(tmp_path / "profiles.db")
    app.dependency_overrides[get_field_set_store] = lambda: store
    client = TestClient(app)

    response = client.post("/api/field-sets", json={"name": "no-fields-key"})
    app.dependency_overrides.clear()

    assert response.status_code == 422


# --- WR-03: list_field_sets must not NPE on a list/get gap --------------------


class _RaceyStore:
    """Wraps a real store but makes `get()` report a miss for one
    specific id -- simulating a row deleted (or otherwise gone) between
    `list()` and the per-id `get()` a race window could hit."""

    def __init__(self, real_store, missing_id: str):
        self._real_store = real_store
        self._missing_id = missing_id

    def save(self, name, field_set):
        return self._real_store.save(name, field_set)

    def get(self, template_id: str):
        if template_id == self._missing_id:
            return None
        return self._real_store.get(template_id)

    def list(self):
        return self._real_store.list()


def test_list_field_sets_skips_a_row_that_disappeared_between_list_and_get(tmp_path):
    """WR-03: `FieldSetTemplateStore.get` is contractually allowed to
    return `None` on any miss -- a list/get race must be skipped, never
    dereferenced into an `AttributeError` (-> HTTP 500) on a public GET
    route."""
    from assayingest.api.app import app
    from assayingest.api.deps import get_field_set_store

    real_store = SqliteFieldSetStore(tmp_path / "profiles.db")
    present_id = real_store.save("present", _field_set())
    gone_id = real_store.save("gone", FieldSet(fields=(Field(name="x"),)))

    app.dependency_overrides[get_field_set_store] = lambda: _RaceyStore(
        real_store, gone_id
    )
    client = TestClient(app)

    response = client.get("/api/field-sets")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert [row["id"] for row in body] == [present_id]
