"""POST /api/confirm's server-side auth gate (AUTH-01/04, D-06-06), TDD
RED-first (06-02 Task 3).

The gate is on the ENDPOINT, not the UI (T-06-06): a signed-out request is 401
and a signed-in-but-unverified request is 403, BEFORE any registry/gate work --
proven by asserting nothing is persisted. A verified request succeeds and
stamps `confirmed_by = user.email` into the manifest (AUTH-04, T-06-07): the
identity comes from the server-resolved `User`, never a client body field.

These tests override `get_current_user` (not `require_verified_user`) so the
real `require_user`/`require_verified_user` 401/403 logic actually runs -- the
four pre-existing confirm test files instead override `require_verified_user`
directly, since they only need an authenticated user attached, not to exercise
the gate itself.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from assayingest.auth.models import User
from assayingest.fields.models import Field, FieldSet
from assayingest.learning.signature import column_signature
from assayingest.learning.sqlite_store import SqliteProfileStore
from assayingest.parsing.table import RawTable


def _table() -> RawTable:
    return RawTable(
        headers=["cmpd", "potency"],
        rows=[["NVS-1", "12.5"], ["NVS-2", "8.0"]],
        source_name="batch.csv",
    )


def _ready_field_set() -> FieldSet:
    return FieldSet(fields=(Field(name="compound_id"), Field(name="value")))


def _ready_mapping_body() -> list[dict]:
    return [
        {
            "target_field": "compound_id", "source_column": "cmpd", "confidence": 1.0,
            "reasoning": "exact match", "needs_confirmation": False,
            "inferred_value": None, "alternatives": [],
        },
        {
            "target_field": "value", "source_column": "potency", "confidence": 1.0,
            "reasoning": "exact match", "needs_confirmation": False,
            "inferred_value": None, "alternatives": [],
        },
    ]


def _seed_upload(field_set: FieldSet, table: RawTable) -> str:
    from assayingest.api.state import UploadEntry, registry

    return registry.put(
        UploadEntry(field_set=field_set, headers_only=False, tmp_path=None, table=table)
    )


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


def _client(tmp_path):
    from assayingest.api.app import app
    from assayingest.api.deps import get_profile_store

    store = SqliteProfileStore(tmp_path / "profiles.db")
    app.dependency_overrides[get_profile_store] = lambda: store
    return TestClient(app), store


def _clear():
    from assayingest.api.app import app

    app.dependency_overrides.clear()


def _confirm_body(field_set: FieldSet, token: str) -> dict:
    return {
        "upload_token": token,
        "field_set": field_set.to_dict(),
        "field_mappings": _ready_mapping_body(),
        "save_profile": True,
    }


# --- 401: signed out ----------------------------------------------------------


def test_confirm_signed_out_returns_401_and_persists_nothing(tmp_path):
    from assayingest.api.deps import get_current_user

    field_set = _ready_field_set()
    table = _table()
    token = _seed_upload(field_set, table)
    client, store = _client(tmp_path)
    app_overrides_signed_out = get_current_user  # explicit: no user resolved
    from assayingest.api.app import app

    app.dependency_overrides[app_overrides_signed_out] = lambda: None

    response = client.post("/api/confirm", json=_confirm_body(field_set, token))
    _clear()

    assert response.status_code == 401
    assert store.find(field_set.signature, column_signature(table.headers)) is None


# --- 403: signed in but unverified --------------------------------------------


def test_confirm_signed_in_unverified_returns_403_and_persists_nothing(tmp_path):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    field_set = _ready_field_set()
    table = _table()
    token = _seed_upload(field_set, table)
    client, store = _client(tmp_path)
    app.dependency_overrides[get_current_user] = lambda: _unverified_user()

    response = client.post("/api/confirm", json=_confirm_body(field_set, token))
    _clear()

    assert response.status_code == 403
    assert store.find(field_set.signature, column_signature(table.headers)) is None


# --- 200: verified -> confirmed_by stamped ------------------------------------


def test_confirm_verified_user_records_confirmed_by_email_in_the_manifest(tmp_path):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    field_set = _ready_field_set()
    table = _table()
    token = _seed_upload(field_set, table)
    client, _store = _client(tmp_path)
    app.dependency_overrides[get_current_user] = lambda: _verified_user()

    response = client.post("/api/confirm", json=_confirm_body(field_set, token))
    _clear()

    assert response.status_code == 200
    assert response.json()["manifest"]["confirmed_by"] == "curator@example.com"
