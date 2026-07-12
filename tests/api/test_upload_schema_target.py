"""`POST /api/upload` targets a governed Schema (D-10-02, INGEST-01) and
reports the Python-vs-Claude escalation split (D-10-03, INGEST-02).

TDD RED-first (10-05 Task 1). Reuses `tests/api/test_upload.py`'s exact
harness idioms: monkeypatch `service.propose_mapping` (never a route-level
reimplementation of the mapper), override `get_profile_store`/
`get_schema_store` with the test's own Postgres-on-the-test-connection
fixtures (`tests/conftest.py`), and drive a real synthetic CSV through
`TestClient`.

`novascreen_batch01.csv`'s headers (`cmpd,assay,potency,,target_gene,
replicates,date`) are reused throughout -- its `date` column is already ISO
(`2025-11-03`), so no date_question (Plan 05 Task 2) is ever triggered here;
this file's tests are scoped purely to the Schema-targeting/escalation wire,
not date resolution.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from assayingest import service
from assayingest.domain.models import Alias, MappingProposal, FieldMapping
from assayingest.fields.models import Field, FieldSet

DATA = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic"
NOVASCREEN_01 = DATA / "novascreen_batch01.csv"

_TS = datetime.now(UTC).isoformat()


def _alias(vendor: str, source_column: str) -> Alias:
    return Alias(
        vendor=vendor, source_column=source_column, provenance_kind="manual",
        provenance_actor="curator@example.com", created_at=_TS,
    )


def _make_schema(schema_store, name: str, fields: tuple[Field, ...]):
    field_set = FieldSet(name=name, fields=fields)
    schema = service.promote(field_set, created_by="curator@example.com", store=schema_store)
    return schema


def _add_alias(schema_store, schema_id: str, field_name: str, vendor: str, source_column: str) -> None:
    schema_store.add_alias(schema_id, field_name, _alias(vendor, source_column))


def _client(profile_store, schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_profile_store, get_schema_store

    app.dependency_overrides[get_profile_store] = lambda: profile_store
    app.dependency_overrides[get_schema_store] = lambda: schema_store
    return TestClient(app)


def _clear():
    from assayingest.api.app import app

    app.dependency_overrides.clear()


def _explode(*_a, **_k):
    raise AssertionError("propose_mapping must NOT run when the crosswalk covers everything")


def _spy(recorder: list[str]):
    """A propose_mapping_fn recording which fields it was asked for, returning
    a NOT-pre-filled (confidence 0.5) mapping for each -- distinguishable from
    the Python pre-fill's confidence 1.0/needs_confirmation=False result."""

    def _fn(table, field_set, client=None, *, headers_only=False):
        recorder.extend(field_set.field_names)
        return MappingProposal(
            source_columns=list(table.headers),
            field_mappings=[
                FieldMapping(
                    target_field=name, source_column=None, confidence=0.5,
                    reasoning="claude filled the remainder", needs_confirmation=True,
                )
                for name in field_set.field_names
            ],
        )

    return _fn


def _post_upload(client, *, schema_name=None, field_set=None, **extra_data):
    data = dict(extra_data)
    if schema_name is not None:
        data["schema_name"] = schema_name
    if field_set is not None:
        data["field_set"] = json.dumps(field_set)
    with open(NOVASCREEN_01, "rb") as f:
        return client.post(
            "/api/upload",
            files={"file": ("novascreen_batch01.csv", f, "text/csv")},
            data=data,
        )


# --- 1. schema_name derives the field set; full crosswalk = zero Claude calls


def test_upload_with_schema_name_targets_exactly_that_schemas_fields(monkeypatch, profile_store, schema_store):
    schema = _make_schema(
        schema_store, "assay-potency",
        (Field(name="compound_id"), Field(name="value", type="number"), Field(name="target")),
    )
    _add_alias(schema_store, schema.id, "compound_id", "novascreen", "cmpd")
    _add_alias(schema_store, schema.id, "value", "novascreen", "potency")
    _add_alias(schema_store, schema.id, "target", "novascreen", "target_gene")
    monkeypatch.setattr(service, "propose_mapping", _explode)

    client = _client(profile_store, schema_store)
    response = _post_upload(client, schema_name="assay-potency")
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "mapping"
    assert {m["target_field"] for m in body["field_mappings"]} == {"compound_id", "value", "target"}


def test_full_crosswalk_coverage_calls_the_mapper_zero_times_and_reports_escalation(
    monkeypatch, profile_store, schema_store
):
    schema = _make_schema(
        schema_store, "assay-potency",
        (Field(name="compound_id"), Field(name="value", type="number"), Field(name="target")),
    )
    _add_alias(schema_store, schema.id, "compound_id", "novascreen", "cmpd")
    _add_alias(schema_store, schema.id, "value", "novascreen", "potency")
    _add_alias(schema_store, schema.id, "target", "novascreen", "target_gene")
    monkeypatch.setattr(service, "propose_mapping", _explode)

    client = _client(profile_store, schema_store)
    response = _post_upload(client, schema_name="assay-potency")
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert body["escalation"] == {"python": 3, "claude": 0, "total": 3}
    assert all(m["confidence"] == 1.0 and not m["needs_confirmation"] for m in body["field_mappings"])


# --- 2. partial coverage: escalation reports the real split ------------------


def test_partial_crosswalk_coverage_calls_the_mapper_only_for_the_uncovered_remainder(
    monkeypatch, profile_store, schema_store
):
    schema = _make_schema(
        schema_store, "assay-potency",
        (Field(name="compound_id"), Field(name="value", type="number"), Field(name="target")),
    )
    _add_alias(schema_store, schema.id, "compound_id", "novascreen", "cmpd")
    _add_alias(schema_store, schema.id, "value", "novascreen", "potency")
    # "target" has NO alias -- it must escalate to Claude.
    recorder: list[str] = []
    monkeypatch.setattr(service, "propose_mapping", _spy(recorder))

    client = _client(profile_store, schema_store)
    response = _post_upload(client, schema_name="assay-potency")
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert recorder == ["target"]
    assert body["escalation"] == {"python": 2, "claude": 1, "total": 3}
    target_mapping = next(m for m in body["field_mappings"] if m["target_field"] == "target")
    assert target_mapping["confidence"] == 0.5


# --- 3. tombstones are honoured on both read paths ---------------------------


def test_a_tombstoned_field_is_absent_from_the_target_field_list(monkeypatch, profile_store, schema_store):
    schema = _make_schema(
        schema_store, "assay-potency",
        (Field(name="compound_id"), Field(name="value", type="number"), Field(name="target")),
    )
    _add_alias(schema_store, schema.id, "compound_id", "novascreen", "cmpd")
    _add_alias(schema_store, schema.id, "value", "novascreen", "potency")
    _add_alias(schema_store, schema.id, "target", "novascreen", "target_gene")
    schema_store.remove_field(schema.id, "target", removed_by="curator@example.com", removed_at=_TS)
    monkeypatch.setattr(service, "propose_mapping", _explode)

    client = _client(profile_store, schema_store)
    response = _post_upload(client, schema_name="assay-potency")
    _clear()

    assert response.status_code == 200
    body = response.json()
    target_fields = {m["target_field"] for m in body["field_mappings"]}
    assert "target" not in target_fields
    assert target_fields == {"compound_id", "value"}
    assert body["escalation"] == {"python": 2, "claude": 0, "total": 2}


def test_a_tombstoned_alias_no_longer_prefills_and_escalates_to_claude(monkeypatch, profile_store, schema_store):
    schema = _make_schema(
        schema_store, "assay-potency",
        (Field(name="compound_id"), Field(name="value", type="number"), Field(name="target")),
    )
    _add_alias(schema_store, schema.id, "compound_id", "novascreen", "cmpd")
    _add_alias(schema_store, schema.id, "value", "novascreen", "potency")
    _add_alias(schema_store, schema.id, "target", "novascreen", "target_gene")
    schema_store.remove_alias(
        schema.id, "target", "novascreen", "target_gene",
        removed_by="curator@example.com", removed_at=_TS,
    )
    recorder: list[str] = []
    monkeypatch.setattr(service, "propose_mapping", _spy(recorder))

    client = _client(profile_store, schema_store)
    response = _post_upload(client, schema_name="assay-potency")
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert recorder == ["target"]
    target_mapping = next(m for m in body["field_mappings"] if m["target_field"] == "target")
    assert target_mapping["confidence"] == 0.5  # NOT the 1.0 pre-fill confidence


# --- 4. an unknown schema_name is a 404 --------------------------------------


def test_unknown_schema_name_is_404(profile_store, schema_store):
    client = _client(profile_store, schema_store)
    response = _post_upload(client, schema_name="does-not-exist")
    _clear()

    assert response.status_code == 404


# --- 5. backward compatibility: field_set with no schema_name is untouched --


def test_field_set_json_with_no_schema_name_behaves_as_today(monkeypatch, profile_store, schema_store):
    monkeypatch.setattr(
        service, "propose_mapping",
        lambda table, fs, client=None, **kw: MappingProposal(
            source_columns=table.headers,
            field_mappings=[
                FieldMapping(
                    target_field="compound_id", source_column="cmpd", confidence=1.0,
                    reasoning="exact match", needs_confirmation=False,
                ),
            ],
        ),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store, schema_store)
    response = _post_upload(
        client, field_set={"fields": [{"name": "compound_id", "type": "text"}]}
    )
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "mapping"
    assert body["provenance"] == "fresh-claude"
    assert body["escalation"] is None  # no Schema was targeted


# --- 6. neither field_set nor schema_name nor template_id -> 422 ------------


def test_no_target_provided_is_422_and_names_schema_name(profile_store, schema_store):
    client = _client(profile_store, schema_store)
    response = _post_upload(client)
    _clear()

    assert response.status_code == 422
    assert "schema_name" in response.json()["detail"]


# --- 7. precedence: schema_name wins when both are sent ---------------------


def test_schema_name_wins_precedence_over_field_set_when_both_are_sent(
    monkeypatch, profile_store, schema_store
):
    schema = _make_schema(schema_store, "assay-potency", (Field(name="compound_id"),))
    _add_alias(schema_store, schema.id, "compound_id", "novascreen", "cmpd")
    monkeypatch.setattr(service, "propose_mapping", _explode)

    client = _client(profile_store, schema_store)
    response = _post_upload(
        client, schema_name="assay-potency",
        field_set={"fields": [{"name": "bogus_field", "type": "text"}]},
    )
    _clear()

    assert response.status_code == 200
    body = response.json()
    target_fields = {m["target_field"] for m in body["field_mappings"]}
    assert target_fields == {"compound_id"}
    assert "bogus_field" not in target_fields
