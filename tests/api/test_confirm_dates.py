"""The resolve -> confirm end-to-end date gate (INGEST-04, gap-closure 10-08
Task 1). TDD RED-first.

Today `POST /api/date-format/resolve` clears an ambiguous date field, but
`POST /api/confirm` re-validates from scratch WITHOUT the human's answer --
re-flagging the field amber and 422ing the gate. This file proves the whole
resolve -> confirm -> export loop, not just the resolve step in isolation
(`test_date_format_route.py` already covers that).

Mirrors `test_date_format_route.py`'s inline-CSV/fixed-mapper idiom (never a
real Claude call) and `test_confirm_gate.py`'s auth-override `_client`
idiom -- both reused here because this test exercises the SEAM between the
two routes, not either route's own contract in isolation.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from assayingest import service
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.fields.models import Field, FieldSet

from .conftest import verified_user

#: A single ambiguous value (day=3, month=4 -- neither exceeds 12) is enough
#: evidence on its own for `classify_column` to call the column AMBIGUOUS
#: (date_order.py's own docstring). Chosen so day_first and month_first
#: produce two DIFFERENT, individually correct ISO dates from the same raw
#: value -- the only way to prove `canonical.assemble` (not just `validate`)
#: received the override (Test 2).
_AMBIGUOUS_DATE_CSV = (
    b"Compound Name,Date\n"
    b"CPD-1,03/04/2025\n"
    b"CPD-2,03/04/2025\n"
)

#: day=13 proves DAY_FIRST outright (13 cannot be a month) -- no question is
#: ever raised for this column at all (the "free half" of the gap, Test 5).
_UNAMBIGUOUS_DATE_CSV = (
    b"Compound Name,Date\n"
    b"CPD-1,13/01/2025\n"
    b"CPD-2,14/02/2025\n"
)

#: No date-typed field at all -- the regression pin (Test 6).
_NO_DATE_CSV = (
    b"Compound Name,Value\n"
    b"CPD-1,12.5\n"
    b"CPD-2,8.0\n"
)


def _field_set() -> FieldSet:
    return FieldSet(
        fields=(
            Field(name="compound_id"),
            Field(name="assay_date", type="date"),
        )
    )


def _no_date_field_set() -> FieldSet:
    return FieldSet(
        fields=(
            Field(name="compound_id"),
            Field(name="value", type="number"),
        )
    )


def _mapper(headers_map: dict[str, str]):
    """A propose_mapping_fn mapping each field name straight to a fixed
    source column -- confidence 1.0, needs_confirmation=False, mirroring a
    confident Claude proposal, never a real network call."""

    def _fn(table, field_set, client=None, *, headers_only=False):
        return MappingProposal(
            source_columns=list(table.headers),
            field_mappings=[
                FieldMapping(
                    target_field=name, source_column=headers_map.get(name),
                    confidence=1.0, reasoning="fixture", needs_confirmation=False,
                )
                for name in field_set.field_names
            ],
        )

    return _fn


def _client(profile_store, schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user, get_profile_store, get_schema_store

    app.dependency_overrides[get_profile_store] = lambda: profile_store
    app.dependency_overrides[get_schema_store] = lambda: schema_store
    # 10-09: overriding get_current_user (the single root dependency) satisfies
    # BOTH the new require_user gate on /api/upload and the pre-existing
    # require_verified_user gate on /api/confirm -- one seam instead of two.
    app.dependency_overrides[get_current_user] = lambda: verified_user()
    return TestClient(app)


def _clear():
    from assayingest.api.app import app

    app.dependency_overrides.clear()


def _post_upload_bytes(client, content: bytes, filename: str, *, field_set: FieldSet):
    data = {"field_set": json.dumps(field_set.to_dict())}
    return client.post(
        "/api/upload",
        files={"file": (filename, content, "text/csv")},
        data=data,
    )


def _confirm_mappings_from_response(body: dict) -> list[dict]:
    """A `MappingResponse`'s `field_mappings` already carry exactly the keys
    `ConfirmFieldMappingIn` accepts, plus `validator_note` (an extra key
    Pydantic silently drops) -- built here rather than hand-rolled so this
    test proves the whole wire round-trip, not a synthetic shortcut."""
    mappings = []
    for m in body["field_mappings"]:
        mappings.append(
            {
                "target_field": m["target_field"],
                "source_column": m["source_column"],
                "confidence": m["confidence"],
                "reasoning": m["reasoning"],
                "needs_confirmation": m["needs_confirmation"],
                "inferred_value": m["inferred_value"],
                "alternatives": m["alternatives"],
            }
        )
    return mappings


def _resolve_ambiguous_upload(client, field_set: FieldSet, *, order: str) -> dict:
    """Upload the ambiguous-date CSV, answer its one date question with
    `order`, and return the resolved `mapping` response body."""
    upload_response = _post_upload_bytes(
        client, _AMBIGUOUS_DATE_CSV, "ambiguous.csv", field_set=field_set
    )
    assert upload_response.json()["kind"] == "date_question"
    token = upload_response.json()["upload_token"]

    resolve_response = client.post(
        "/api/date-format/resolve",
        json={"upload_token": token, "choices": [{"target_field": "assay_date", "order": order}]},
    )
    assert resolve_response.status_code == 200
    body = resolve_response.json()
    assert body["kind"] == "mapping"
    return body


# --- Test 1: the gap -- resolve then confirm must SUCCEED --------------------


def test_resolve_then_confirm_succeeds_with_date_field_clear(monkeypatch, profile_store, schema_store):
    monkeypatch.setattr(
        service, "propose_mapping",
        _mapper({"compound_id": "Compound Name", "assay_date": "Date"}),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store, schema_store)
    field_set = _field_set()
    resolved = _resolve_ambiguous_upload(client, field_set, order="day_first")

    assay_date = next(m for m in resolved["field_mappings"] if m["target_field"] == "assay_date")
    assert assay_date["needs_confirmation"] is False

    response = client.post(
        "/api/confirm",
        json={
            "upload_token": resolved["upload_token"],
            "vendor": "test-vendor",
            "field_set": field_set.to_dict(),
            "field_mappings": _confirm_mappings_from_response(resolved),
        },
    )
    _clear()

    assert response.status_code == 200
    assert response.json()["ready"] is True


# --- Test 2: the value is actually right --------------------------------------


def _exported_assay_date(client, resolved: dict, field_set: FieldSet) -> str:
    response = client.post(
        "/api/confirm",
        json={
            "upload_token": resolved["upload_token"],
            "vendor": "test-vendor",
            "field_set": field_set.to_dict(),
            "field_mappings": _confirm_mappings_from_response(resolved),
            "export": True,
        },
    )
    assert response.status_code == 200
    export_urls = response.json()["export"]
    json_response = client.get(export_urls["json_url"])
    assert json_response.status_code == 200
    records = json_response.json()
    return records[0]["assay_date"]


def test_confirm_exports_iso_date_converted_under_the_chosen_order(monkeypatch, profile_store, schema_store):
    monkeypatch.setattr(
        service, "propose_mapping",
        _mapper({"compound_id": "Compound Name", "assay_date": "Date"}),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store, schema_store)

    day_first_resolved = _resolve_ambiguous_upload(client, _field_set(), order="day_first")
    day_first_value = _exported_assay_date(client, day_first_resolved, _field_set())

    month_first_resolved = _resolve_ambiguous_upload(client, _field_set(), order="month_first")
    month_first_value = _exported_assay_date(client, month_first_resolved, _field_set())
    _clear()

    assert day_first_value == "2025-04-03"
    assert month_first_value == "2025-03-04"
    assert day_first_value != month_first_value


# --- Test 3: fail-closed is NOT weakened ---------------------------------------


def test_confirm_without_resolving_an_ambiguous_date_still_422s(monkeypatch, profile_store, schema_store):
    monkeypatch.setattr(
        service, "propose_mapping",
        _mapper({"compound_id": "Compound Name", "assay_date": "Date"}),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store, schema_store)
    field_set = _field_set()
    upload_response = _post_upload_bytes(
        client, _AMBIGUOUS_DATE_CSV, "ambiguous.csv", field_set=field_set
    )
    assert upload_response.json()["kind"] == "date_question"
    token = upload_response.json()["upload_token"]

    # Never resolved -- confirm directly with the date field's raw mapping.
    response = client.post(
        "/api/confirm",
        json={
            "upload_token": token,
            "vendor": "test-vendor",
            "field_set": field_set.to_dict(),
            "field_mappings": [
                {
                    "target_field": "compound_id", "source_column": "Compound Name",
                    "confidence": 1.0, "reasoning": "fixture", "needs_confirmation": False,
                    "inferred_value": None, "alternatives": [],
                },
                {
                    "target_field": "assay_date", "source_column": "Date",
                    "confidence": 1.0, "reasoning": "fixture", "needs_confirmation": False,
                    "inferred_value": None, "alternatives": [],
                },
            ],
        },
    )
    _clear()

    assert response.status_code == 422
    assert "assay_date" in response.json()["detail"]["unclear_fields"]


# --- Test 4: no client smuggling (T-10-30) ------------------------------------


def test_confirm_request_has_no_date_field_and_ignores_an_injected_one(monkeypatch, profile_store, schema_store):
    from assayingest.api.wire import ConfirmRequest

    assert "date_format" not in ConfirmRequest.model_fields
    assert "date_formats" not in ConfirmRequest.model_fields
    assert "date_answers" not in ConfirmRequest.model_fields

    monkeypatch.setattr(
        service, "propose_mapping",
        _mapper({"compound_id": "Compound Name", "assay_date": "Date"}),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store, schema_store)
    field_set = _field_set()
    resolved = _resolve_ambiguous_upload(client, field_set, order="day_first")

    response = client.post(
        "/api/confirm",
        json={
            "upload_token": resolved["upload_token"],
            "vendor": "test-vendor",
            "field_set": field_set.to_dict(),
            "field_mappings": _confirm_mappings_from_response(resolved),
            "date_format": "%Y/%m/%d",  # a tampered client's smuggling attempt
        },
    )
    _clear()

    assert response.status_code == 200
    assert response.json()["ready"] is True


# --- Test 5: the free half of the fix -----------------------------------------


def test_unambiguous_undeclared_date_column_confirms_and_exports_iso(monkeypatch, profile_store, schema_store):
    monkeypatch.setattr(
        service, "propose_mapping",
        _mapper({"compound_id": "Compound Name", "assay_date": "Date"}),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store, schema_store)
    field_set = _field_set()
    upload_response = _post_upload_bytes(
        client, _UNAMBIGUOUS_DATE_CSV, "unambiguous.csv", field_set=field_set
    )
    body = upload_response.json()
    assert body["kind"] == "mapping"  # no question was ever raised
    assay_date = next(m for m in body["field_mappings"] if m["target_field"] == "assay_date")
    assert assay_date["needs_confirmation"] is False

    response = client.post(
        "/api/confirm",
        json={
            "upload_token": body["upload_token"],
            "vendor": "test-vendor",
            "field_set": field_set.to_dict(),
            "field_mappings": _confirm_mappings_from_response(body),
            "export": True,
        },
    )
    _clear()

    assert response.status_code == 200
    assert response.json()["ready"] is True
    export_urls = response.json()["export"]
    json_response = client.get(export_urls["json_url"])
    records = json_response.json()
    assert records[0]["assay_date"] == "2025-01-13"
    assert records[1]["assay_date"] == "2025-02-14"


# --- Test 6: regression pin -- no date field at all, unaffected ---------------


def test_confirm_with_no_date_field_behaves_exactly_as_today(monkeypatch, profile_store, schema_store):
    monkeypatch.setattr(
        service, "propose_mapping",
        _mapper({"compound_id": "Compound Name", "value": "Value"}),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store, schema_store)
    field_set = _no_date_field_set()
    upload_response = _post_upload_bytes(
        client, _NO_DATE_CSV, "no_date.csv", field_set=field_set
    )
    body = upload_response.json()
    assert body["kind"] == "mapping"

    response = client.post(
        "/api/confirm",
        json={
            "upload_token": body["upload_token"],
            "vendor": "test-vendor",
            "field_set": field_set.to_dict(),
            "field_mappings": _confirm_mappings_from_response(body),
        },
    )
    _clear()

    assert response.status_code == 200
    assert response.json()["ready"] is True
