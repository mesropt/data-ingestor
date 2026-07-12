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
    the server must recompute and reject with 422, persisting nothing.

    Guards BOTH the unchanged legacy `unclear_fields` name-only key AND the
    new `unclear_details` key that carries the no-LLM validator's actual
    `validator_note` -- the human must never be left guessing which field
    was rejected or why."""
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
    detail = response.json()["detail"]
    assert detail["unclear_fields"] == ["value"]  # legacy key, byte-identical
    assert detail["unclear_details"] == [
        {
            "field": "value",
            "reason": "column 'potency': 12.5 is below the declared minimum 100",
            "source_column": "potency",
        }
    ]
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


# --- CR-01: the Schema changed after the upload ----------------------------------


def _as_javascript_would_send(body: object) -> object:
    """Collapse every integral float to an int, exactly as a browser does.

    JavaScript has ONE number type. A field set read off `GET /api/schemas`
    carrying `{"min": 0.0}` is re-serialized by `JSON.stringify` as
    `{"min": 0}` -- the float is not recoverable, and the client cannot be
    asked to recover it. Every confirm the UI sends arrives shaped like this,
    which is why a pure-Python round-trip (`json.loads` preserves `0.0`) never
    reproduced the CR-01 rejection the curator hit in the browser.
    """
    if isinstance(body, float):
        return int(body) if body.is_integer() else body
    if isinstance(body, dict):
        return {k: _as_javascript_would_send(v) for k, v in body.items()}
    if isinstance(body, list):
        return [_as_javascript_would_send(v) for v in body]
    return body


def test_confirm_accepts_the_int_bounds_a_browser_sends_for_an_unchanged_schema(profile_store):
    """The gate must identify a bound by its VALUE, not the Python type of it.

    The upload is retained against float bounds (a preset declares `min: 0.0`;
    the DB stores it as a Double). The browser sends the SAME field set back
    with `min: 0`, because JS cannot say otherwise. That is not a changed
    Schema and must confirm cleanly -- before the `_normalise_field` float
    coercion, this 422'd with "the Schema was changed after the file was
    uploaded" on every single browser confirm against every shipped preset.
    """
    retained = FieldSet(
        fields=(Field(name="compound_id"), Field(name="value", type="number", min=0.0, max=1000.0))
    )
    token = _seed_upload(retained, _table())
    submitted = _as_javascript_would_send(retained.to_dict())
    assert submitted["fields"][1]["min"] == 0 and isinstance(submitted["fields"][1]["min"], int)
    client, _store = _client(profile_store)

    response = client.post(
        "/api/confirm",
        json={
            "upload_token": token,
            "field_set": submitted,
            "field_mappings": _ready_mapping_body(),
            "save_profile": False,
            "export": False,
        },
    )
    from assayingest.api.app import app

    app.dependency_overrides.clear()

    assert response.status_code == 200, response.json()
    assert response.json()["ready"] is True


def test_confirm_against_a_schema_edited_after_upload_is_refused_and_says_to_re_upload(profile_store):
    """The reachable CR-01 case, hit in real UAT: the curator edits the target
    Schema (here: a field renamed) after uploading, then confirms from a Review
    screen still holding the mapping made against the OLD Schema. The gate must
    refuse -- a file mapped against one Schema is never assembled against
    another -- and the 422 must name the consequence AND the remedy, not merely
    report that two signatures differ.
    """
    uploaded_against = _ready_field_set()
    token = _seed_upload(uploaded_against, _table())
    # What the curator's Schemas-page edit produced, and what the stale Review
    # screen now sends back: the same Schema with `compound_id` renamed.
    edited_since = FieldSet(fields=(Field(name="compound_id_new"), Field(name="value")))
    assert edited_since.signature != uploaded_against.signature
    client, _store = _client(profile_store)

    response = client.post(
        "/api/confirm",
        json={
            "upload_token": token,
            "field_set": edited_since.to_dict(),
            "field_mappings": _ready_mapping_body(),
        },
    )
    from assayingest.api.app import app

    app.dependency_overrides.clear()

    assert response.status_code == 422
    detail = response.json()["detail"]
    # A plain string, so `lib/api.ts::confirm` re-raises it as an ApiError the
    # Review screen shows verbatim (it names no field, so there is nothing for
    # `applyGateRejection` to re-flag amber).
    assert isinstance(detail, str)
    assert "Nothing was saved" in detail
    assert "changed after the file was uploaded" in detail
    assert "Upload the file again" in detail


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
