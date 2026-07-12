"""POST /api/confirm requires a vendor (source label) -- quick 260712.

The crosswalk and the learned profile both record WHOSE format a confirmed
file was; a confirm with no vendor would pass the gate and silently learn
nothing, defeating the loop the product is built around. So the API route
rejects a missing or whitespace-only vendor with a 422 naming the
consequence and the remedy -- BEFORE any registry or gate work, so the
pending review survives for the corrected retry. The vendor is trimmed;
surrounding whitespace never reaches the crosswalk.

The CLI path is out of scope by design: `service.confirm`'s own signature
keeps `vendor` optional (nothing there changes), and `tests/test_cli*.py`
pin that path separately.

Harness mirrors `test_confirm_aliases_route.py` exactly.
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

    service.promote(_field_set(), created_by="seed@example.com", store=schema_store)
    app.dependency_overrides[get_profile_store] = lambda: profile_store
    app.dependency_overrides[get_schema_store] = lambda: schema_store
    app.dependency_overrides[require_verified_user] = lambda: User(
        id="t", email="curator@example.com", password_hash=None,
        is_verified=True, auth_provider="password", created_at="2026-07-12T00:00:00Z",
    )
    return TestClient(app)


def _clear():
    from assayingest.api.app import app

    app.dependency_overrides.clear()


def _body(field_set: FieldSet, token: str, **extra) -> dict:
    return {
        "upload_token": token,
        "field_set": field_set.to_dict(),
        "field_mappings": _ready_mapping_body(),
        "schema_name": _SCHEMA_NAME,
        **extra,
    }


# --- a confirm without a vendor is refused, and nothing happens --------------


def test_confirm_without_vendor_is_422_naming_the_consequence(profile_store, schema_store):
    field_set = _field_set()
    token = _seed_upload(field_set, _table())
    client = _client(profile_store, schema_store)

    response = client.post("/api/confirm", json=_body(field_set, token))
    _clear()

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "nothing was saved" in detail.lower()
    assert "vendor" in detail.lower()
    schema = schema_store.get_schema(_SCHEMA_NAME)
    assert schema_store.list_aliases_for(schema.id) == []


def test_confirm_with_whitespace_only_vendor_is_422(profile_store, schema_store):
    field_set = _field_set()
    token = _seed_upload(field_set, _table())
    client = _client(profile_store, schema_store)

    response = client.post("/api/confirm", json=_body(field_set, token, vendor="   "))
    _clear()

    assert response.status_code == 422
    assert "vendor" in response.json()["detail"].lower()


def test_a_vendor_rejection_leaves_the_pending_review_intact_for_a_retry(profile_store, schema_store):
    """The rejection must not consume the upload: the SAME token, resubmitted
    WITH a vendor, confirms cleanly -- the 422 was a gate, not a purge."""
    field_set = _field_set()
    token = _seed_upload(field_set, _table())
    client = _client(profile_store, schema_store)

    rejected = client.post("/api/confirm", json=_body(field_set, token))
    assert rejected.status_code == 422

    retried = client.post("/api/confirm", json=_body(field_set, token, vendor="NovaScreen"))
    _clear()

    assert retried.status_code == 200
    assert retried.json()["ready"] is True


# --- the vendor that IS recorded is the trimmed one --------------------------


def test_vendor_is_trimmed_before_it_reaches_the_crosswalk(profile_store, schema_store):
    field_set = _field_set()
    token = _seed_upload(field_set, _table())
    client = _client(profile_store, schema_store)

    response = client.post(
        "/api/confirm", json=_body(field_set, token, vendor="  NovaScreen  ")
    )
    _clear()

    assert response.status_code == 200
    schema = schema_store.get_schema(_SCHEMA_NAME)
    aliases = schema_store.list_aliases_for(schema.id)
    assert aliases, "the confirm should have recorded crosswalk aliases"
    assert {a.vendor for a in aliases} == {"NovaScreen"}
