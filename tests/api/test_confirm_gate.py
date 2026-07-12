"""POST /api/confirm -- the server-side P1 gate (API-02), TDD RED-first
(04-03 Task 2). Mirrors `tests/test_service.py`'s
`test_confirm_never_trusts_a_client_claimed_ready_flag` at the HTTP boundary:
the same tampered-`needs_confirmation=False`-over-a-real-violation scenario,
this time crossing the wire.

Seeds `api.state.registry` directly (the same registry
`tests/api/test_upload.py::test_upload_returns_structural_question_and_retains_temp_file`
already reads from) rather than round-tripping through a real `/api/upload`
call -- this targets `confirm.py`'s own contract in isolation.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from assayingest.fields.models import Field, FieldSet
from assayingest.learning.signature import column_signature
from assayingest.parsing.table import RawTable


def _table() -> RawTable:
    return RawTable(
        headers=["cmpd", "potency"],
        rows=[["NVS-1", "12.5"], ["NVS-2", "8.0"]],
        source_name="batch.csv",
    )


def _seed_upload(field_set: FieldSet, table: RawTable, headers_only: bool = False) -> str:
    from assayingest.api.state import UploadEntry, registry

    return registry.put(
        UploadEntry(field_set=field_set, headers_only=headers_only, tmp_path=None, table=table)
    )


def _ready_field_set() -> FieldSet:
    return FieldSet(fields=(Field(name="compound_id"), Field(name="value")))


def _ready_mapping_body() -> list[dict]:
    return [
        {
            "target_field": "compound_id",
            "source_column": "cmpd",
            "confidence": 1.0,
            "reasoning": "exact match",
            "needs_confirmation": False,
            "inferred_value": None,
            "alternatives": [],
        },
        {
            "target_field": "value",
            "source_column": "potency",
            "confidence": 1.0,
            "reasoning": "exact match",
            "needs_confirmation": False,
            "inferred_value": None,
            "alternatives": [],
        },
    ]


def _client(profile_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_profile_store, require_verified_user
    from assayingest.auth.models import User

    app.dependency_overrides[get_profile_store] = lambda: profile_store
    # 06-02: /api/confirm is now gated by require_verified_user. These P1-gate
    # tests exercise the mapping gate, not the auth gate, so they inject an
    # authenticated verified curator; the dedicated auth-gate 401/403 cases live
    # in test_confirm_auth_gate.py.
    app.dependency_overrides[require_verified_user] = lambda: User(
        id="t", email="curator@example.com", password_hash=None,
        is_verified=True, auth_provider="password", created_at="2026-07-11T00:00:00Z",
    )
    return TestClient(app), profile_store


# --- happy path (LEARN-02) ----------------------------------------------------


def test_confirm_happy_path_persists_one_profile_and_returns_manifest_and_export_urls(profile_store):
    field_set = _ready_field_set()
    table = _table()
    token = _seed_upload(field_set, table)
    client, store = _client(profile_store)

    response = client.post(
        "/api/confirm",
        json={
            "upload_token": token,
            "field_set": field_set.to_dict(),
            "field_mappings": _ready_mapping_body(),
            "save_profile": True,
            "export": True,
        },
    )
    from assayingest.api.app import app

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["manifest"]["provenance"] == "fresh-claude"
    assert body["manifest"]["confirmed_by"] == "curator@example.com"  # AUTH-04
    assert body["profile_id"] is not None
    assert set(body["export"]) == {"csv_url", "xlsx_url", "json_url", "manifest_url"}

    found = store.find(field_set.signature, column_signature(table.headers))
    assert found is not None
    assert found.profile_id == body["profile_id"]
    # Exactly one profile -- a second confirm for the same signature upserts,
    # never duplicates (the store's own UNIQUE constraint, not re-tested here).
    assert len(store.list_for_field_set(field_set.signature)) == 1


# --- THE P1 test: tampered yellow ---------------------------------------------


def test_confirm_rejects_a_tampered_ready_claim_over_a_real_constraint_violation(profile_store):
    """A field whose declared `min=100` is violated by the actual mapped
    value (12.5) but whose wire body claims `needs_confirmation=False` --
    the server must recompute and reject with 422, persisting nothing."""
    field_set = FieldSet(fields=(Field(name="value", min=100),))
    table = _table()
    token = _seed_upload(field_set, table)
    client, store = _client(profile_store)

    response = client.post(
        "/api/confirm",
        json={
            "upload_token": token,
            "field_set": field_set.to_dict(),
            "field_mappings": [
                {
                    "target_field": "value",
                    "source_column": "potency",
                    "confidence": 1.0,
                    "reasoning": "curator says so",
                    "needs_confirmation": False,  # tampered/stale claim
                    "inferred_value": None,
                    "alternatives": [],
                },
            ],
            "save_profile": True,
        },
    )
    from assayingest.api.app import app

    app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"]["unclear_fields"] == ["value"]
    assert store.find(field_set.signature, column_signature(table.headers)) is None


# --- CR-01: gate must validate against the RETAINED field set, not the body ---


def test_confirm_rejects_a_client_field_set_that_weakens_a_declared_constraint(profile_store):
    """A field whose declared `min=100` is violated by the actual mapped
    value (12.5) but whose confirm body carries a WEAKENED field_set (the
    `min` constraint dropped) plus a claimed `needs_confirmation=False` --
    the server must validate against `entry.field_set` (the one the upload
    was actually resolved against), never the client's own copy, so the
    weakened field_set can never make the violation invisible. Nothing may
    be persisted or exported."""
    field_set = FieldSet(fields=(Field(name="value", min=100),))
    table = _table()
    token = _seed_upload(field_set, table)
    client, store = _client(profile_store)

    weakened_field_set = FieldSet(fields=(Field(name="value"),))  # min dropped

    response = client.post(
        "/api/confirm",
        json={
            "upload_token": token,
            "field_set": weakened_field_set.to_dict(),
            "field_mappings": [
                {
                    "target_field": "value",
                    "source_column": "potency",
                    "confidence": 1.0,
                    "reasoning": "curator says so",
                    "needs_confirmation": False,  # would pass under the weakened field set
                    "inferred_value": None,
                    "alternatives": [],
                },
            ],
            "save_profile": True,
            "export": True,
        },
    )
    from assayingest.api.app import app

    app.dependency_overrides.clear()

    assert response.status_code == 422
    assert store.find(field_set.signature, column_signature(table.headers)) is None


# --- CR-02: gate must reject a confirm body that omits a field ----------------


def test_confirm_rejects_a_body_that_omits_a_still_yellow_required_field(profile_store):
    """CR-02: `is_ready` is only ever computed over the mappings a client
    chooses to send. A tampering client that drops a still-yellow required
    field from the body entirely (rather than sending it with
    `needs_confirmation=True`) must not unlock export/save -- the server
    must reject on missing field coverage, never silently export `None`
    for the dropped field."""
    field_set = FieldSet(fields=(Field(name="compound_id"), Field(name="value")))
    table = _table()
    token = _seed_upload(field_set, table)
    client, store = _client(profile_store)

    response = client.post(
        "/api/confirm",
        json={
            "upload_token": token,
            "field_set": field_set.to_dict(),
            "field_mappings": [
                {
                    "target_field": "compound_id",
                    "source_column": "cmpd",
                    "confidence": 1.0,
                    "reasoning": "exact match",
                    "needs_confirmation": False,
                    "inferred_value": None,
                    "alternatives": [],
                },
                # "value" entirely omitted -- never sent as yellow, just absent.
            ],
            "save_profile": True,
            "export": True,
        },
    )
    from assayingest.api.app import app

    app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"]["missing_fields"] == ["value"]
    assert store.find(field_set.signature, column_signature(table.headers)) is None


# --- never-trust-client-headers ------------------------------------------------


def test_confirm_ignores_client_sent_headers_and_uses_the_retained_table(profile_store):
    """A confirm body carrying an (unsupported-by-the-wire-model, but
    attempted) mismatched `source_columns` must not influence validation --
    the server only ever reads `entry.table.headers` from the registry."""
    field_set = _ready_field_set()
    table = _table()
    token = _seed_upload(field_set, table)
    client, store = _client(profile_store)

    response = client.post(
        "/api/confirm",
        json={
            "upload_token": token,
            "field_set": field_set.to_dict(),
            "field_mappings": _ready_mapping_body(),
            "save_profile": True,
            # Not part of ConfirmRequest's schema -- must be silently ignored,
            # never influence which table the gate validates against.
            "source_columns": ["totally", "different", "headers"],
        },
    )
    from assayingest.api.app import app

    app.dependency_overrides.clear()

    assert response.status_code == 200
    found = store.find(field_set.signature, column_signature(table.headers))
    assert found is not None
    assert found.column_signature == column_signature(table.headers)


# --- field_set.signature always re-derived -------------------------------------


def test_confirm_ignores_a_client_sent_field_set_signature(profile_store):
    field_set = _ready_field_set()
    table = _table()
    token = _seed_upload(field_set, table)
    client, store = _client(profile_store)

    tampered_field_set_dict = dict(field_set.to_dict())
    tampered_field_set_dict["signature"] = "totally-fake-signature"

    response = client.post(
        "/api/confirm",
        json={
            "upload_token": token,
            "field_set": tampered_field_set_dict,
            "field_mappings": _ready_mapping_body(),
            "save_profile": True,
        },
    )
    from assayingest.api.app import app

    app.dependency_overrides.clear()

    assert response.status_code == 200
    found = store.find(field_set.signature, column_signature(table.headers))
    assert found is not None  # found under the REAL signature, not the fake one


# --- WR-04: manifest must use the RETAINED provenance, never the client's ------


def test_confirm_manifest_uses_the_retained_provenance_not_a_lying_client_body(profile_store):
    """WR-04: `ConfirmRequest.provenance` is a free-form client string that
    flows straight into the written audit manifest. The server must retain
    the REAL provenance from upload/resolve time (the API already knows
    which branch -- auto-applied vs fresh-Claude -- it took) and use THAT
    for the manifest, regardless of what the confirm body claims."""
    field_set = _ready_field_set()
    table = _table()
    token = _seed_upload(field_set, table)
    # Simulates what /api/upload or /api/structural-hint/resolve actually
    # retains once WR-04's fix adds a real `provenance` field to
    # `UploadEntry` -- set directly here since this test targets the
    # confirm route's own contract, not the upload path.
    from assayingest.api.state import registry

    registry.get(token).provenance = "auto-applied-from-profile"

    client, store = _client(profile_store)

    response = client.post(
        "/api/confirm",
        json={
            "upload_token": token,
            "field_set": field_set.to_dict(),
            "field_mappings": _ready_mapping_body(),
            "provenance": "fresh-claude",  # lying claim -- must be ignored
        },
    )
    from assayingest.api.app import app

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["manifest"]["provenance"] == "auto-applied-from-profile"


# --- unknown upload_token -------------------------------------------------------


def test_confirm_with_unknown_upload_token_returns_404(profile_store):
    client, _store = _client(profile_store)

    response = client.post(
        "/api/confirm",
        json={
            "upload_token": "no-such-token",
            "field_set": _ready_field_set().to_dict(),
            "field_mappings": _ready_mapping_body(),
        },
    )
    from assayingest.api.app import app

    app.dependency_overrides.clear()

    assert response.status_code == 404
