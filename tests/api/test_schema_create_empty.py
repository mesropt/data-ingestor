"""POST /api/schemas can create a brand-new, EMPTY Schema (INGEST-05,
gap-closure 10-08 Task 2). TDD RED-first.

Mirrors `test_schemas_routes.py`'s auth-override `_client` idiom exactly --
this file targets the ONE new opt-in call site (`create_schema`), not the
whole `/api/schemas` surface (already covered there).

Today `POST /api/schemas` builds its `FieldSet` via
`fields.loader.from_dict`, which rejects an empty `fields: []` list with a
422 ("the file declares no fields") -- the exact body
`frontend/src/screens/Schemas.tsx:152` already sends for "Create Schema".
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from assayingest.auth.models import User
from assayingest.fields.loader import from_dict


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
    return TestClient(app)


def _clear():
    from assayingest.api.app import app

    app.dependency_overrides.clear()


def _empty_field_set_body() -> dict:
    """The EXACT body `Schemas.tsx:152`'s `handleCreateSchema` already sends."""
    return {"name": None, "fields": []}


def _non_empty_field_set_body() -> dict:
    return {
        "name": "assay-potency",
        "fields": [
            {"name": "compound_id", "type": "text"},
            {"name": "value", "type": "number"},
        ],
    }


# --- Test 1: the gap -- creating an empty Schema must succeed ----------------


def test_post_schemas_with_an_empty_field_set_creates_an_empty_schema(schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    client = _client(schema_store)
    app.dependency_overrides[get_current_user] = lambda: _verified_user()

    response = client.post(
        "/api/schemas", json={"name": "my-schema", "field_set": _empty_field_set_body()}
    )
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "my-schema"
    assert body["fields"] == []
    assert body["created_by"] == "curator@example.com"


# --- Test 2: it is a usable starting state, not a dead end --------------------


def test_an_empty_schema_can_then_be_populated_with_add_schema_field(schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    client = _client(schema_store)
    app.dependency_overrides[get_current_user] = lambda: _verified_user()

    create_response = client.post(
        "/api/schemas", json={"name": "my-schema", "field_set": _empty_field_set_body()}
    )
    assert create_response.json()["fields"] == []

    add_field_response = client.post(
        "/api/schemas/my-schema/fields",
        json={"field": {"name": "compound_id", "type": "text"}},
    )
    _clear()

    assert add_field_response.status_code == 200
    body = add_field_response.json()
    assert [f["name"] for f in body["fields"]] == ["compound_id"]


# --- Test 3: the guard is INTACT where it belongs -----------------------------


def test_post_field_sets_with_an_empty_field_set_still_422s(field_set_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_field_set_store

    app.dependency_overrides[get_field_set_store] = lambda: field_set_store
    client = TestClient(app)

    response = client.post(
        "/api/field-sets",
        json={"name": "some-template", "field_set": {"fields": []}},
    )
    _clear()

    assert response.status_code == 422


def test_from_dict_direct_call_with_an_empty_fields_list_still_raises():
    import pytest

    with pytest.raises(ValueError):
        from_dict({"fields": []})


def test_confirm_drift_check_with_an_empty_field_set_still_422s(profile_store, schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_profile_store, get_schema_store, require_verified_user
    from assayingest.api.state import UploadEntry, registry
    from assayingest.fields.models import Field, FieldSet
    from assayingest.parsing.table import RawTable

    field_set = FieldSet(fields=(Field(name="compound_id"),))
    table = RawTable(headers=["cmpd"], rows=[["NVS-1"]], source_name="batch.csv")
    token = registry.put(
        UploadEntry(field_set=field_set, headers_only=False, tmp_path=None, table=table)
    )

    app.dependency_overrides[get_profile_store] = lambda: profile_store
    app.dependency_overrides[get_schema_store] = lambda: schema_store
    app.dependency_overrides[require_verified_user] = lambda: _verified_user()
    client = TestClient(app)

    response = client.post(
        "/api/confirm",
        json={
            "upload_token": token,
            "vendor": "test-vendor",
            "field_set": {"fields": []},  # drifted to empty -- must be rejected
            "field_mappings": [
                {
                    "target_field": "compound_id", "source_column": "cmpd",
                    "confidence": 1.0, "reasoning": "x", "needs_confirmation": False,
                    "inferred_value": None, "alternatives": [],
                },
            ],
        },
    )
    _clear()

    assert response.status_code == 422


# --- Test 4: auth gate holds ---------------------------------------------------


def test_post_schemas_empty_field_set_signed_out_returns_401(schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    client = _client(schema_store)
    app.dependency_overrides[get_current_user] = lambda: None

    response = client.post(
        "/api/schemas", json={"name": "my-schema", "field_set": _empty_field_set_body()}
    )
    _clear()

    assert response.status_code == 401
    assert schema_store.list_schemas() == []


def test_post_schemas_empty_field_set_unverified_returns_403(schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    client = _client(schema_store)
    app.dependency_overrides[get_current_user] = lambda: _unverified_user()

    response = client.post(
        "/api/schemas", json={"name": "my-schema", "field_set": _empty_field_set_body()}
    )
    _clear()

    assert response.status_code == 403
    assert schema_store.list_schemas() == []


# --- Test 5: the existing promote path is untouched ---------------------------


def test_post_schemas_with_a_non_empty_field_set_still_works(schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    client = _client(schema_store)
    app.dependency_overrides[get_current_user] = lambda: _verified_user()

    response = client.post(
        "/api/schemas",
        json={"name": "assay-potency", "field_set": _non_empty_field_set_body()},
    )
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert [f["name"] for f in body["fields"]] == ["compound_id", "value"]
