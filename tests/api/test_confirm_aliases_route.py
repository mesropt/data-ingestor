"""POST /api/confirm records crosswalk aliases (ALIAS-04, D-07-05/06), TDD
RED-first (07-03 Task 2).

The confirm route already gates on `require_verified_user` and stamps
`confirmed_by = user.email` (06-02, AUTH-04). This adds the additive crosswalk
write: when the body carries a `schema_name` + `vendor`, each resolved source
column becomes a `manual` alias whose `provenance_actor` is the SERVER-resolved
`user.email` (T-07-10), never a client body field. As of quick 260712 the
vendor is MANDATORY on this route: a confirm without one is rejected outright
(422, nothing saved, nothing written) rather than silently learning nothing --
see `test_confirm_vendor_required.py` for the full rejection contract.

Overrides `get_profile_store`, `get_schema_store`, and `require_verified_user`
with tmp-path stores / an injected verified curator -- the same idiom
`test_confirm_gate.py` uses, extended with the schema store seam (07-02).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from assayingest import service
from assayingest.fields.models import Field, FieldSet
from assayingest.parsing.table import RawTable

_SCHEMA_NAME = "assay-potency"


def _table() -> RawTable:
    return RawTable(
        headers=["cmpd", "potency"],
        rows=[["NVS-1", "12.5"], ["NVS-2", "8.0"]],
        source_name="batch.csv",
    )


def _field_set() -> FieldSet:
    return FieldSet(
        name=_SCHEMA_NAME,
        fields=(Field(name="compound_id"), Field(name="value")),
    )


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


def _client(profile_store, schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import (
        get_profile_store,
        get_schema_store,
        require_verified_user,
    )
    from assayingest.auth.models import User
    service.promote(_field_set(), created_by="ignored@seed.com", store=schema_store)

    app.dependency_overrides[get_profile_store] = lambda: profile_store
    app.dependency_overrides[get_schema_store] = lambda: schema_store
    app.dependency_overrides[require_verified_user] = lambda: User(
        id="t", email="curator@example.com", password_hash=None,
        is_verified=True, auth_provider="password", created_at="2026-07-11T00:00:00Z",
    )
    return TestClient(app), schema_store


def _clear():
    from assayingest.api.app import app

    app.dependency_overrides.clear()


# --- ALIAS-04: schema_name + vendor -> manual, server-attributed aliases -------


def test_confirm_with_schema_and_vendor_records_manual_server_attributed_aliases(profile_store, schema_store):
    field_set = _field_set()
    token = _seed_upload(field_set, _table())
    client, schema_store = _client(profile_store, schema_store)

    response = client.post(
        "/api/confirm",
        json={
            "upload_token": token,
            "field_set": field_set.to_dict(),
            "field_mappings": _ready_mapping_body(),
            "schema_name": _SCHEMA_NAME,
            "vendor": "NovaScreen",
            # A client body cannot dictate the actor -- provenance_actor must be
            # the server-resolved curator@example.com, never this:
            "provenance_actor": "attacker@evil.com",
        },
    )
    _clear()

    assert response.status_code == 200
    schema = schema_store.get_schema(_SCHEMA_NAME)
    aliases = schema_store.list_aliases_for(schema.id)
    assert {(a.vendor, a.source_column) for a in aliases} == {
        ("NovaScreen", "cmpd"),
        ("NovaScreen", "potency"),
    }
    assert all(a.provenance_kind == "manual" for a in aliases)
    assert all(a.provenance_actor == "curator@example.com" for a in aliases)


# --- no vendor -> the confirm is refused and nothing is written ---------------


def test_confirm_without_schema_name_or_vendor_records_no_alias(profile_store, schema_store):
    """Originally pinned "no vendor -> confirm succeeds, no alias written";
    quick 260712 strengthened the contract: a vendor-less confirm is now
    REJECTED outright (the vendor is mandatory), and still writes nothing."""
    field_set = _field_set()
    token = _seed_upload(field_set, _table())
    client, schema_store = _client(profile_store, schema_store)

    response = client.post(
        "/api/confirm",
        json={
            "upload_token": token,
            "field_set": field_set.to_dict(),
            "field_mappings": _ready_mapping_body(),
        },
    )
    _clear()

    assert response.status_code == 422
    schema = schema_store.get_schema(_SCHEMA_NAME)
    assert schema_store.list_aliases_for(schema.id) == []
