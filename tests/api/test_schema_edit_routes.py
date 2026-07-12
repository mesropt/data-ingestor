"""The explicit governed-Schema edit surface (D-10-12, INGEST-05): add /
edit / remove a canonical field, add / remove a vendor alias -- all gated by
`require_verified_user`, all living BESIDE the augment-only master-map
import route (D-07-04), never through it.

TDD RED-first (10-04 Task 1). Mirrors `tests/api/test_schemas_routes.py`'s
harness exactly: override `get_current_user` (not `require_verified_user`)
so the real `require_user`/`require_verified_user` 401/403 logic actually
runs on every new route; override `get_schema_store` with the test's own
`schema_store` fixture (a `PostgresSchemaStore` on the test connection, from
`tests/conftest.py`) so no test touches the real dev database.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from assayingest.auth.models import User


def _verified_user() -> User:
    return User(
        id="u-verified", email="curator@example.com", password_hash=None,
        is_verified=True, auth_provider="password", created_at="2026-07-11T00:00:00Z",
    )


def _unverified_user() -> User:
    return User(
        id="u-unverified", email="newbie@example.com", password_hash=None,
        is_verified=False, auth_provider="password", created_at="2026-07-11T00:00:00Z",
    )


def _client(schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_schema_store

    app.dependency_overrides[get_schema_store] = lambda: schema_store
    return TestClient(app), schema_store


def _clear():
    from assayingest.api.app import app

    app.dependency_overrides.clear()


def _sign_in(app, user: User) -> None:
    from assayingest.api.deps import get_current_user

    app.dependency_overrides[get_current_user] = lambda: user


def _field_set_body(name: str = "assay-potency") -> dict:
    return {
        "name": name,
        "fields": [
            {"name": "compound_id", "type": "text"},
            {"name": "value", "type": "number"},
        ],
    }


def _create_schema(client, app, name: str = "assay-potency") -> dict:
    """Sign in as a verified curator and POST a fresh 2-field Schema
    (`compound_id`, `value`) named `name`. Returns the `SchemaOut` body."""
    _sign_in(app, _verified_user())
    response = client.post(
        "/api/schemas", json={"name": name, "field_set": _field_set_body(name)}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _route_cases(schema_name: str) -> list[dict]:
    """(method, path, json, params) for each of the five gated edit routes,
    all targeting the `value` field of an already-created Schema."""
    return [
        {
            "method": "post",
            "path": f"/api/schemas/{schema_name}/fields",
            "json": {"field": {"name": "new_field", "type": "text"}},
        },
        {
            "method": "patch",
            "path": f"/api/schemas/{schema_name}/fields/value",
            "json": {"field": {"name": "value", "type": "number", "unit": "mg"}},
        },
        {
            "method": "delete",
            "path": f"/api/schemas/{schema_name}/fields/value",
        },
        {
            "method": "post",
            "path": f"/api/schemas/{schema_name}/fields/value/aliases",
            "json": {"vendor": "NovaScreen", "source_column": "potency"},
        },
        {
            "method": "delete",
            "path": f"/api/schemas/{schema_name}/fields/value/aliases",
            "params": {"vendor": "NovaScreen", "source_column": "potency"},
        },
    ]


# --- Happy paths ---------------------------------------------------------


def test_post_field_adds_it_with_every_submitted_constraint(schema_store):
    from assayingest.api.app import app

    client, _store = _client(schema_store)
    schema = _create_schema(client, app)

    response = client.post(
        f"/api/schemas/{schema['name']}/fields",
        json={
            "field": {
                "name": "n_replicates",
                "type": "integer",
                "required": False,
                "min": 1,
                "max": 10,
            }
        },
    )
    _clear()

    assert response.status_code == 200, response.text
    body = response.json()
    added = next(f for f in body["fields"] if f["name"] == "n_replicates")
    assert added["type"] == "integer"
    assert added["required"] is False
    assert added["min"] == 1
    assert added["max"] == 10


def test_patch_field_overwrites_every_submitted_constraint(schema_store):
    from assayingest.api.app import app

    client, _store = _client(schema_store)
    schema = _create_schema(client, app)

    response = client.patch(
        f"/api/schemas/{schema['name']}/fields/value",
        json={
            "field": {
                "name": "value",
                "type": "number",
                "unit": "nM",
                "min": 0,
                "max": 1000,
                "required": True,
            }
        },
    )
    _clear()

    assert response.status_code == 200, response.text
    body = response.json()
    value_field = next(f for f in body["fields"] if f["name"] == "value")
    assert value_field["unit"] == "nM"
    assert value_field["min"] == 0
    assert value_field["max"] == 1000


def test_patch_field_rename_preserves_its_aliases(schema_store):
    from assayingest.api.app import app

    client, _store = _client(schema_store)
    schema = _create_schema(client, app)
    client.post(
        f"/api/schemas/{schema['name']}/fields/value/aliases",
        json={"vendor": "NovaScreen", "source_column": "potency"},
    )

    response = client.patch(
        f"/api/schemas/{schema['name']}/fields/value",
        json={"field": {"name": "potency_value", "type": "number"}},
    )
    _clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert not any(f["name"] == "value" for f in body["fields"])
    renamed = next(f for f in body["fields"] if f["name"] == "potency_value")
    assert [a["source_column"] for a in renamed["aliases"]] == ["potency"]


def test_delete_field_with_two_aliases_removes_field_and_both_aliases(schema_store):
    from assayingest.api.app import app

    client, _store = _client(schema_store)
    schema = _create_schema(client, app)
    client.post(
        f"/api/schemas/{schema['name']}/fields/value/aliases",
        json={"vendor": "NovaScreen", "source_column": "potency"},
    )
    client.post(
        f"/api/schemas/{schema['name']}/fields/value/aliases",
        json={"vendor": "Reaction Biology", "source_column": "IC50 (nM)"},
    )

    response = client.delete(f"/api/schemas/{schema['name']}/fields/value")
    export_response = client.get(f"/api/schemas/{schema['name']}/master-map")
    _clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert [f["name"] for f in body["fields"]] == ["compound_id"]

    assert export_response.status_code == 200
    export_body = export_response.json()
    assert [f["name"] for f in export_body["fields"]] == ["compound_id"]


def test_post_alias_records_manual_provenance_from_the_signed_in_user_ignoring_body_actor(
    schema_store,
):
    from assayingest.api.app import app

    client, _store = _client(schema_store)
    schema = _create_schema(client, app)

    # A body attempt to set the actor must be IGNORED (T-07-06 mirror).
    response = client.post(
        f"/api/schemas/{schema['name']}/fields/value/aliases",
        json={
            "vendor": "NovaScreen",
            "source_column": "potency",
            "provenance_actor": "attacker@evil.com",
        },
    )
    _clear()

    assert response.status_code == 200, response.text
    body = response.json()
    value_field = next(f for f in body["fields"] if f["name"] == "value")
    alias = value_field["aliases"][0]
    assert alias["provenance_kind"] == "manual"
    assert alias["provenance_actor"] == "curator@example.com"


def test_delete_alias_removes_it_from_schema_and_master_map(schema_store):
    from assayingest.api.app import app

    client, _store = _client(schema_store)
    schema = _create_schema(client, app)
    client.post(
        f"/api/schemas/{schema['name']}/fields/value/aliases",
        json={"vendor": "NovaScreen", "source_column": "potency"},
    )

    response = client.delete(
        f"/api/schemas/{schema['name']}/fields/value/aliases",
        params={"vendor": "NovaScreen", "source_column": "potency"},
    )
    export_response = client.get(f"/api/schemas/{schema['name']}/master-map")
    _clear()

    assert response.status_code == 200, response.text
    value_field = next(f for f in response.json()["fields"] if f["name"] == "value")
    assert value_field["aliases"] == []

    export_value_field = next(
        f for f in export_response.json()["fields"] if f["name"] == "value"
    )
    assert export_value_field["aliases"] == []


# --- Auth gate: one test per route, both tiers --------------------------


@pytest.mark.parametrize("index", range(5))
def test_each_edit_route_signed_out_returns_401_and_persists_nothing(schema_store, index):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    client, store = _client(schema_store)
    schema = _create_schema(client, app)
    # Pre-record an alias so the delete-alias route has something to (not) delete.
    client.post(
        f"/api/schemas/{schema['name']}/fields/value/aliases",
        json={"vendor": "NovaScreen", "source_column": "potency"},
    )
    before = store.get_schema(schema["name"])

    case = _route_cases(schema["name"])[index]
    app.dependency_overrides[get_current_user] = lambda: None
    response = client.request(
        case["method"], case["path"], json=case.get("json"), params=case.get("params")
    )
    _clear()

    assert response.status_code == 401
    assert store.get_schema(schema["name"]) == before


@pytest.mark.parametrize("index", range(5))
def test_each_edit_route_unverified_returns_403_and_persists_nothing(schema_store, index):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    client, store = _client(schema_store)
    schema = _create_schema(client, app)
    client.post(
        f"/api/schemas/{schema['name']}/fields/value/aliases",
        json={"vendor": "NovaScreen", "source_column": "potency"},
    )
    before = store.get_schema(schema["name"])

    case = _route_cases(schema["name"])[index]
    app.dependency_overrides[get_current_user] = lambda: _unverified_user()
    response = client.request(
        case["method"], case["path"], json=case.get("json"), params=case.get("params")
    )
    _clear()

    assert response.status_code == 403
    assert store.get_schema(schema["name"]) == before


# --- Input validation (V5, T-07-08) --------------------------------------


def test_post_field_with_control_character_name_returns_422(schema_store):
    from assayingest.api.app import app

    client, _store = _client(schema_store)
    schema = _create_schema(client, app)

    response = client.post(
        f"/api/schemas/{schema['name']}/fields",
        json={"field": {"name": "bad\nname", "type": "text"}},
    )
    _clear()

    assert response.status_code == 422


def test_patch_field_with_control_character_name_returns_422(schema_store):
    from assayingest.api.app import app

    client, _store = _client(schema_store)
    schema = _create_schema(client, app)

    response = client.patch(
        f"/api/schemas/{schema['name']}/fields/value",
        json={"field": {"name": "bad\nname", "type": "number"}},
    )
    _clear()

    assert response.status_code == 422


def test_patch_field_with_invalid_type_returns_422(schema_store):
    from assayingest.api.app import app

    client, _store = _client(schema_store)
    schema = _create_schema(client, app)

    response = client.patch(
        f"/api/schemas/{schema['name']}/fields/value",
        json={"field": {"name": "value", "type": "not-a-real-type"}},
    )
    _clear()

    assert response.status_code == 422


def test_post_field_when_schema_at_max_fields_returns_422_naming_the_cap(schema_store):
    from assayingest.api.app import app
    from assayingest.fields.loader import MAX_FIELDS

    client, _store = _client(schema_store)
    _sign_in(app, _verified_user())
    fields = [{"name": f"field_{i}", "type": "text"} for i in range(MAX_FIELDS)]
    create_response = client.post(
        "/api/schemas",
        json={"name": "big-schema", "field_set": {"name": "big-schema", "fields": fields}},
    )
    assert create_response.status_code == 200, create_response.text

    response = client.post(
        "/api/schemas/big-schema/fields",
        json={"field": {"name": "one_too_many", "type": "text"}},
    )
    _clear()

    assert response.status_code == 422
    assert str(MAX_FIELDS) in response.json()["detail"]


# --- Misses ----------------------------------------------------------------


def test_post_field_unknown_schema_returns_404(schema_store):
    from assayingest.api.app import app

    client, _store = _client(schema_store)
    _sign_in(app, _verified_user())

    response = client.post(
        "/api/schemas/does-not-exist/fields",
        json={"field": {"name": "x", "type": "text"}},
    )
    _clear()

    assert response.status_code == 404
    assert "does-not-exist" in response.json()["detail"]


def test_patch_field_unknown_schema_returns_404(schema_store):
    from assayingest.api.app import app

    client, _store = _client(schema_store)
    _sign_in(app, _verified_user())

    response = client.patch(
        "/api/schemas/does-not-exist/fields/value",
        json={"field": {"name": "value", "type": "number"}},
    )
    _clear()

    assert response.status_code == 404
    assert "does-not-exist" in response.json()["detail"]


def test_delete_field_unknown_schema_returns_404(schema_store):
    from assayingest.api.app import app

    client, _store = _client(schema_store)
    _sign_in(app, _verified_user())

    response = client.delete("/api/schemas/does-not-exist/fields/value")
    _clear()

    assert response.status_code == 404
    assert "does-not-exist" in response.json()["detail"]


def test_post_alias_unknown_schema_returns_404(schema_store):
    from assayingest.api.app import app

    client, _store = _client(schema_store)
    _sign_in(app, _verified_user())

    response = client.post(
        "/api/schemas/does-not-exist/fields/value/aliases",
        json={"vendor": "NovaScreen", "source_column": "potency"},
    )
    _clear()

    assert response.status_code == 404
    assert "does-not-exist" in response.json()["detail"]


def test_delete_alias_unknown_schema_returns_404(schema_store):
    from assayingest.api.app import app

    client, _store = _client(schema_store)
    _sign_in(app, _verified_user())

    response = client.delete(
        "/api/schemas/does-not-exist/fields/value/aliases",
        params={"vendor": "NovaScreen", "source_column": "potency"},
    )
    _clear()

    assert response.status_code == 404
    assert "does-not-exist" in response.json()["detail"]


def test_patch_unknown_field_name_returns_404(schema_store):
    from assayingest.api.app import app

    client, _store = _client(schema_store)
    schema = _create_schema(client, app)

    response = client.patch(
        f"/api/schemas/{schema['name']}/fields/nope",
        json={"field": {"name": "nope", "type": "text"}},
    )
    _clear()

    assert response.status_code == 404
    assert "nope" in response.json()["detail"]


def test_delete_unknown_field_name_returns_404(schema_store):
    from assayingest.api.app import app

    client, _store = _client(schema_store)
    schema = _create_schema(client, app)

    response = client.delete(f"/api/schemas/{schema['name']}/fields/nope")
    _clear()

    assert response.status_code == 404
    assert "nope" in response.json()["detail"]


def test_delete_already_tombstoned_field_returns_404(schema_store):
    from assayingest.api.app import app

    client, _store = _client(schema_store)
    schema = _create_schema(client, app)

    first = client.delete(f"/api/schemas/{schema['name']}/fields/value")
    assert first.status_code == 200, first.text

    second = client.delete(f"/api/schemas/{schema['name']}/fields/value")
    _clear()

    assert second.status_code == 404
    assert "value" in second.json()["detail"]


def test_delete_unknown_alias_returns_404(schema_store):
    from assayingest.api.app import app

    client, _store = _client(schema_store)
    schema = _create_schema(client, app)

    response = client.delete(
        f"/api/schemas/{schema['name']}/fields/value/aliases",
        params={"vendor": "NoSuchVendor", "source_column": "nope"},
    )
    _clear()

    assert response.status_code == 404
    assert "NoSuchVendor" in response.json()["detail"]


# --- Cross-schema isolation (SCHEMA-04) -----------------------------------


def test_delete_field_never_touches_a_same_named_field_in_a_different_schema(schema_store):
    from assayingest.api.app import app

    client, store = _client(schema_store)
    schema_a = _create_schema(client, app, name="schema-a")
    schema_b = _create_schema(client, app, name="schema-b")

    response = client.delete(f"/api/schemas/{schema_a['name']}/fields/value")
    _clear()

    assert response.status_code == 200, response.text
    b_after = store.get_schema(schema_b["name"])
    assert any(cf.field.name == "value" for cf in b_after.fields)


def test_patch_field_never_touches_a_same_named_field_in_a_different_schema(schema_store):
    from assayingest.api.app import app

    client, store = _client(schema_store)
    schema_a = _create_schema(client, app, name="schema-a")
    schema_b = _create_schema(client, app, name="schema-b")

    response = client.patch(
        f"/api/schemas/{schema_a['name']}/fields/value",
        json={"field": {"name": "value", "type": "number", "unit": "mg"}},
    )
    _clear()

    assert response.status_code == 200, response.text
    b_after = store.get_schema(schema_b["name"])
    b_value = next(cf for cf in b_after.fields if cf.field.name == "value")
    assert b_value.field.unit is None


# --- The invariant that must not be allowed to rot (D-07-04) --------------


def test_the_master_map_import_route_is_still_augment_only(schema_store):
    """POST .../master-map may only ADD -- a map file that omits a field the
    Schema already has, and asserts a DIFFERENT constraint for an existing
    field, must never remove or overwrite anything. This route is provably
    untouched by this plan."""
    from assayingest.api.app import app

    client, _store = _client(schema_store)
    schema = _create_schema(client, app)

    envelope = {
        "schema_version": 1,
        "name": "attempted-override",
        "fields": [
            # Omits `compound_id` entirely, and asserts a DIFFERENT type for
            # the existing `value` field.
            {"name": "value", "type": "text", "unit": "totally-different-unit", "aliases": []},
        ],
    }
    response = client.post(f"/api/schemas/{schema['name']}/master-map", json=envelope)
    _clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert sorted(f["name"] for f in body["fields"]) == ["compound_id", "value"]
    value_field = next(f for f in body["fields"] if f["name"] == "value")
    assert value_field["type"] == "number"  # unchanged, NOT overwritten to "text"
