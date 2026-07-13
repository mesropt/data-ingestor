"""/api/schemas create/list/export/import routes (D-07-03/04, SCHEMA-01/02/03,
P1 gate), TDD RED-first (07-02 Task 2).

Mirrors `tests/api/test_confirm_auth_gate.py`: override `get_current_user` (not
`require_verified_user`) so the real `require_user`/`require_verified_user`
401/403 logic actually runs on the two MUTATION routes; override
`get_schema_store` with a tmp-path store so no test touches the real demo DB.
"""

from __future__ import annotations

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


def _field_set_body() -> dict:
    return {
        "name": "assay-potency",
        "fields": [
            {"name": "compound_id", "type": "text"},
            {"name": "value", "type": "number"},
        ],
    }


def _envelope_with_alias() -> dict:
    """A hand-crafted master-map file declaring a manual alias on `value` --
    the import must re-stamp it as from_map_file with the file's source name."""
    return {
        "schema_version": 1,
        "id": "src-id",
        "name": "novascreen-map",
        "created_by": "someone@lab.com",
        "created_at": "2026-01-01T00:00:00Z",
        "fields": [
            {"name": "compound_id", "type": "text", "aliases": []},
            {
                "name": "value",
                "type": "number",
                "aliases": [
                    {
                        "vendor": "NovaScreen",
                        "source_column": "potency",
                        "provenance_kind": "manual",
                        "provenance_actor": "orig@lab.com",
                        "created_at": "2026-01-01T00:00:00Z",
                    }
                ],
            },
        ],
    }


# --- POST /api/schemas: the P1 gate -------------------------------------------


def test_post_schemas_signed_out_returns_401_and_persists_nothing(schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    client, store = _client(schema_store)
    app.dependency_overrides[get_current_user] = lambda: None

    response = client.post(
        "/api/schemas", json={"name": "assay-potency", "field_set": _field_set_body()}
    )
    _clear()

    assert response.status_code == 401
    assert store.list_schemas() == []


def test_post_schemas_unverified_returns_403_and_persists_nothing(schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    client, store = _client(schema_store)
    app.dependency_overrides[get_current_user] = lambda: _unverified_user()

    response = client.post(
        "/api/schemas", json={"name": "assay-potency", "field_set": _field_set_body()}
    )
    _clear()

    assert response.status_code == 403
    assert store.list_schemas() == []


def test_post_schemas_verified_creates_with_server_resolved_created_by(schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    client, _store = _client(schema_store)
    app.dependency_overrides[get_current_user] = lambda: _verified_user()

    # A client attempt to set created_by must be IGNORED (T-07-06).
    response = client.post(
        "/api/schemas",
        json={
            "name": "assay-potency",
            "field_set": _field_set_body(),
            "created_by": "attacker@evil.com",
        },
    )
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "assay-potency"
    assert body["created_by"] == "curator@example.com"
    assert [f["name"] for f in body["fields"]] == ["compound_id", "value"]


def test_post_schemas_with_invalid_field_name_is_rejected_422(schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    client, store = _client(schema_store)
    app.dependency_overrides[get_current_user] = lambda: _verified_user()

    response = client.post(
        "/api/schemas",
        json={"name": "bad", "field_set": {"fields": [{"name": "***"}]}},
    )
    _clear()

    assert response.status_code == 422
    assert store.list_schemas() == []


# --- GET /api/schemas + GET master-map (SCHEMA-02) ----------------------------


def test_get_schemas_lists_created_schemas(schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    client, _store = _client(schema_store)
    app.dependency_overrides[get_current_user] = lambda: _verified_user()
    client.post(
        "/api/schemas", json={"name": "assay-potency", "field_set": _field_set_body()}
    )

    response = client.get("/api/schemas")
    _clear()

    assert response.status_code == 200
    assert [s["name"] for s in response.json()] == ["assay-potency"]


def test_get_master_map_returns_versioned_envelope(schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    client, _store = _client(schema_store)
    app.dependency_overrides[get_current_user] = lambda: _verified_user()
    client.post(
        "/api/schemas", json={"name": "assay-potency", "field_set": _field_set_body()}
    )

    response = client.get("/api/schemas/assay-potency/master-map")
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == 1
    assert [f["name"] for f in body["fields"]] == ["compound_id", "value"]


def test_get_master_map_for_unknown_schema_returns_404(schema_store):
    client, _store = _client(schema_store)

    response = client.get("/api/schemas/nope/master-map")
    _clear()

    assert response.status_code == 404


# --- POST master-map (SCHEMA-03, import augment) ------------------------------


def test_post_master_map_signed_out_returns_401(schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    client, _store = _client(schema_store)
    app.dependency_overrides[get_current_user] = lambda: None

    response = client.post(
        "/api/schemas/assay-potency/master-map", json=_envelope_with_alias()
    )
    _clear()

    assert response.status_code == 401


def test_post_master_map_unverified_returns_403(schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    client, _store = _client(schema_store)
    app.dependency_overrides[get_current_user] = lambda: _unverified_user()

    response = client.post(
        "/api/schemas/assay-potency/master-map", json=_envelope_with_alias()
    )
    _clear()

    assert response.status_code == 403


def test_post_master_map_verified_augments_and_records_from_map_file_provenance(schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    client, _store = _client(schema_store)
    app.dependency_overrides[get_current_user] = lambda: _verified_user()
    client.post(
        "/api/schemas", json={"name": "assay-potency", "field_set": _field_set_body()}
    )

    response = client.post(
        "/api/schemas/assay-potency/master-map", json=_envelope_with_alias()
    )
    _clear()

    assert response.status_code == 200
    body = response.json()
    value_field = next(f for f in body["fields"] if f["name"] == "value")
    aliases = value_field["aliases"]
    assert len(aliases) == 1
    assert aliases[0]["source_column"] == "potency"
    assert aliases[0]["provenance_kind"] == "from_map_file"
    assert aliases[0]["provenance_actor"] == "novascreen-map"


def test_post_master_map_into_unknown_schema_returns_404(schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    client, _store = _client(schema_store)
    app.dependency_overrides[get_current_user] = lambda: _verified_user()

    response = client.post(
        "/api/schemas/does-not-exist/master-map", json=_envelope_with_alias()
    )
    _clear()

    assert response.status_code == 404
