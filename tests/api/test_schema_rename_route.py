"""PATCH /api/schemas/{name} -- renaming a governed Schema (quick 260712).

A Schema's name is its domain identity, unique per owner (SCHEMA-04): the
route must reject a rename that would collide with another Schema (409,
nothing renamed), reject a blank name (422), and 404 a Schema that does not
exist. Renaming must be identity-preserving: the Schema's `id`, canonical
fields, aliases, and provenance all survive untouched -- only the label
changes.

THE LOAD-BEARING INVARIANT here is the last test: learned profiles are keyed
by `FieldSet.signature`, which is computed from the FIELDS ONLY (never the
name, `fields/models.py::FieldSet.signature`) -- so a rename must never
orphan a learned profile. Silently losing every profile on a rename would be
exactly the kind of quiet damage this project refuses; this test pins it.

Mirrors `tests/api/test_schema_edit_routes.py`'s harness: override
`get_current_user` (not `require_verified_user`) so the real 401/403 logic
runs; override `get_schema_store` with the test-connection store.
"""

from __future__ import annotations

import uuid
from fastapi.testclient import TestClient

from assayingest import service
from assayingest.auth.models import User
from assayingest.learning.profile import LearnedProfile
from assayingest.learning.signature import column_signature


def _verified_user() -> User:
    return User(
        id="u-verified", email="curator@example.com", password_hash=None,
        is_verified=True, auth_provider="password", created_at="2026-07-12T00:00:00Z",
    )


def _unverified_user() -> User:
    return User(
        id="u-unverified", email="newbie@example.com", password_hash=None,
        is_verified=False, auth_provider="password", created_at="2026-07-12T00:00:00Z",
    )


def _client(schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_schema_store

    app.dependency_overrides[get_schema_store] = lambda: schema_store
    return TestClient(app)


def _clear():
    from assayingest.api.app import app

    app.dependency_overrides.clear()


def _sign_in(user: User) -> None:
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    app.dependency_overrides[get_current_user] = lambda: user


def _sign_out() -> None:
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user

    app.dependency_overrides.pop(get_current_user, None)


def _field_set_body(name: str) -> dict:
    return {
        "name": name,
        "fields": [
            {"name": "compound_id", "type": "text"},
            {"name": "value", "type": "number"},
        ],
    }


def _create_schema(client, name: str) -> dict:
    _sign_in(_verified_user())
    response = client.post(
        "/api/schemas", json={"name": name, "field_set": _field_set_body(name)}
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- Happy path ------------------------------------------------------------


def test_patch_schema_renames_it_preserving_id_fields_and_aliases(schema_store):
    client = _client(schema_store)
    created = _create_schema(client, "assay-potency")
    # An alias on the crosswalk must survive the rename verbatim.
    client.post(
        "/api/schemas/assay-potency/fields/value/aliases",
        json={"vendor": "NovaScreen", "source_column": "potency"},
    )

    response = client.patch("/api/schemas/assay-potency", json={"name": "potency-v2"})
    _clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "potency-v2"
    assert body["id"] == created["id"]
    assert [f["name"] for f in body["fields"]] == ["compound_id", "value"]
    value_field = next(f for f in body["fields"] if f["name"] == "value")
    assert {(a["vendor"], a["source_column"]) for a in value_field["aliases"]} == {
        ("NovaScreen", "potency")
    }
    # The old name resolves to nothing; the new one resolves to the SAME row.
    assert schema_store.get_schema("assay-potency") is None
    assert schema_store.get_schema("potency-v2").id == created["id"]


# --- Uniqueness: two Schemas never share a name (SCHEMA-04) -----------------


def test_rename_to_an_existing_schema_name_is_409_and_changes_nothing(schema_store):
    client = _client(schema_store)
    _create_schema(client, "assay-potency")
    _create_schema(client, "adme-panel")

    response = client.patch("/api/schemas/adme-panel", json={"name": "assay-potency"})
    _clear()

    assert response.status_code == 409
    assert "nothing was renamed" in response.json()["detail"].lower()
    # Both Schemas still exist under their original names -- no clobber.
    assert schema_store.get_schema("adme-panel") is not None
    assert schema_store.get_schema("assay-potency") is not None


def test_rename_to_its_own_current_name_is_a_200_no_op(schema_store):
    client = _client(schema_store)
    created = _create_schema(client, "assay-potency")

    response = client.patch("/api/schemas/assay-potency", json={"name": "assay-potency"})
    _clear()

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["name"] == "assay-potency"


# --- Input guards -----------------------------------------------------------


def test_rename_missing_schema_is_404(schema_store):
    client = _client(schema_store)
    _sign_in(_verified_user())

    response = client.patch("/api/schemas/no-such-schema", json={"name": "anything"})
    _clear()

    assert response.status_code == 404


def test_blank_new_name_is_422_and_changes_nothing(schema_store):
    client = _client(schema_store)
    _create_schema(client, "assay-potency")

    response = client.patch("/api/schemas/assay-potency", json={"name": "   "})
    _clear()

    assert response.status_code == 422
    assert schema_store.get_schema("assay-potency") is not None


# --- Auth gate (T-10-15's discipline applied to the new route) --------------


def test_rename_is_401_signed_out_and_403_unverified(schema_store):
    client = _client(schema_store)
    _create_schema(client, "assay-potency")

    _sign_out()
    signed_out = client.patch("/api/schemas/assay-potency", json={"name": "potency-v2"})
    assert signed_out.status_code == 401

    _sign_in(_unverified_user())
    unverified = client.patch("/api/schemas/assay-potency", json={"name": "potency-v2"})
    _clear()
    assert unverified.status_code == 403
    # Neither request changed the governed name.
    assert schema_store.get_schema("assay-potency") is not None


# --- The invariant that makes renaming safe: profiles survive ---------------


def test_renaming_a_schema_never_orphans_learned_profiles(schema_store, profile_store):
    """`FieldSet.signature` hashes the FIELDS ONLY (never the Schema's name),
    so a profile learned before a rename must still be found by the exact
    same lookup afterwards. If this test ever fails, a rename silently
    orphans every learned profile for the Schema -- quiet damage."""
    from assayingest.fields.models import Field, FieldSet

    field_set = FieldSet(
        name="assay-potency",
        fields=(Field(name="compound_id"), Field(name="value")),
    )
    schema = service.promote(
        field_set, created_by="curator@example.com", store=schema_store
    )

    headers = ["cmpd", "potency"]
    before = service.field_set_from_schema(schema)
    profile = LearnedProfile(
        profile_id=str(uuid.uuid4()),
        field_set_signature=before.signature,
        column_signature=column_signature(headers),
        field_mappings=(),
        structural_hint=None,
        created_at="2026-07-12T00:00:00+00:00",
        vendor="NovaScreen",
    )
    profile_store.save(profile)

    renamed = service.rename_schema(schema_store, "assay-potency", "potency-v2")

    after = service.field_set_from_schema(renamed)
    assert after.signature == before.signature
    found = profile_store.find(after.signature, column_signature(headers))
    assert found is not None
    assert found.profile_id == profile.profile_id
