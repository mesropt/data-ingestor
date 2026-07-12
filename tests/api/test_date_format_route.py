"""The `kind="date_question"` 4th arm of `/api/upload`'s discriminated
response, and `POST /api/date-format/resolve` (D-10-07, INGEST-04).

TDD RED-first (10-05 Task 2). Reuses `tests/api/test_upload.py`'s exact
monkeypatch/DI-override idioms. Every scenario is built against a plain
`field_set` (no `schema_name`) -- the date-question mechanism is independent
of Task 1's Schema-targeting/escalation wiring, since `resolve_date_formats`
runs on both the plain and the Schema-targeted path identically.

The ambiguous-date scenarios below use an INLINE CSV fixture carrying the
same genuinely-ambiguous values as `data/synthetic/helixbio_export.csv`'s
`Experiment Date` column (`03/11/2025`, `04/11/2025`, ... -- every value has
day<=12 AND month<=12, so nothing in the column disambiguates it, verified
independently in `tests/test_date_escalation.py`, Plan 03) rather than the
real fixture file itself: the real file's `# Reps` header column trips a
genuine, PRE-EXISTING, unrelated parser bug in
`parsing/structure/delimiter.py` (pandas' `comment='#'` truncates a data row
wherever a literal `#` appears ANYWHERE in a line, not only at its start --
out of this plan's `files_modified` scope; logged to this phase's
`deferred-items.md` rather than fixed here). `pinnacle_labs_export.csv` has
no such column and is used directly -- its `Date` column contains
`13/01/2025`, proving DAY_FIRST unambiguously (verified real-file parsing
already covered by `tests/test_parse_entry_csv.py`).

Security-critical (T-10-21): `DateFormatChoiceIn` carries only an `order`
Literal -- there is no `date_format` field on the wire model AT ALL, so a
client cannot smuggle a format string through; the server always re-derives
it from the retained column's own classification.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from assayingest import service
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.fields.models import Field, FieldSet
from assayingest.parsing.hint import StructuralHint, StructureQuestion

DATA = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic"
PINNACLE = DATA / "pinnacle_labs_export.csv"

#: Mirrors helixbio_export.csv's real, genuinely-ambiguous "Experiment Date"
#: column values (every one has day<=12 AND month<=12) -- see the module
#: docstring for why this is inline rather than the real fixture file.
_AMBIGUOUS_ONE_DATE_CSV = (
    b"Compound Name,Experiment Date\n"
    b"HLX-100,03/11/2025\n"
    b"HLX-101,03/11/2025\n"
    b"HLX-102,04/11/2025\n"
    b"HLX-110,04/11/2025\n"
    b"HLX-111,05/11/2025\n"
    b"HLX-112,05/11/2025\n"
)

_AMBIGUOUS_TWO_DATE_CSV = (
    b"Compound Name,Start Date,End Date\n"
    b"CPD-1,03/04/2025,04/05/2025\n"
    b"CPD-2,04/05/2025,05/06/2025\n"
    b"CPD-3,05/06/2025,06/07/2025\n"
)


def _field_set(*, date_format: str | None = None, extra: tuple[Field, ...] = ()) -> FieldSet:
    return FieldSet(
        fields=(
            Field(name="compound_id"),
            Field(name="assay_date", type="date", date_format=date_format),
        )
        + extra
    )


def _mapper(headers_map: dict[str, str]):
    """A propose_mapping_fn mapping each field name straight to a fixed
    source column (never a real Claude call) -- confidence 1.0,
    needs_confirmation=False, mirroring a confident Claude proposal."""

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


def _client(profile_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_profile_store

    app.dependency_overrides[get_profile_store] = lambda: profile_store
    return TestClient(app)


def _clear():
    from assayingest.api.app import app

    app.dependency_overrides.clear()


def _post_upload_file(client, path: Path, *, field_set: FieldSet, headers_only: bool = False):
    data = {"field_set": json.dumps(field_set.to_dict())}
    if headers_only:
        data["headers_only"] = "true"
    with open(path, "rb") as f:
        return client.post(
            "/api/upload",
            files={"file": (path.name, f, "text/csv")},
            data=data,
        )


def _post_upload_bytes(
    client, content: bytes, filename: str, *, field_set: FieldSet, headers_only: bool = False
):
    data = {"field_set": json.dumps(field_set.to_dict())}
    if headers_only:
        data["headers_only"] = "true"
    return client.post(
        "/api/upload",
        files={"file": (filename, content, "text/csv")},
        data=data,
    )


# --- 1. the 4th arm: a genuinely ambiguous column asks once per column ------


def test_ambiguous_date_column_returns_date_question_not_mapping(monkeypatch, profile_store):
    monkeypatch.setattr(
        service, "propose_mapping",
        _mapper({"compound_id": "Compound Name", "assay_date": "Experiment Date"}),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store)
    response = _post_upload_bytes(
        client, _AMBIGUOUS_ONE_DATE_CSV, "ambiguous_dates.csv", field_set=_field_set()
    )
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "date_question"
    assert body["upload_token"]
    assert len(body["columns"]) == 1
    column = body["columns"][0]
    assert column["target_field"] == "assay_date"
    assert column["source_column"] == "Experiment Date"
    assert column["day_first_format"]
    assert column["month_first_format"]
    assert column["example_values"]
    assert column["ambiguous_row_count"] > 0


def test_ambiguous_upload_retains_no_tmp_path_the_table_is_already_in_memory(monkeypatch, profile_store):
    from assayingest.api.state import registry

    monkeypatch.setattr(
        service, "propose_mapping",
        _mapper({"compound_id": "Compound Name", "assay_date": "Experiment Date"}),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store)
    response = _post_upload_bytes(
        client, _AMBIGUOUS_ONE_DATE_CSV, "ambiguous_dates.csv", field_set=_field_set()
    )
    token = response.json()["upload_token"]
    entry = registry.get(token)
    _clear()

    assert entry is not None
    assert entry.tmp_path is None  # nothing left to re-parse
    assert entry.table is not None
    assert entry.proposal is not None


def test_unambiguous_date_column_maps_straight_through_with_no_question(monkeypatch, profile_store):
    monkeypatch.setattr(
        service, "propose_mapping", _mapper({"compound_id": "Compound", "assay_date": "Date"}),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store)
    response = _post_upload_file(client, PINNACLE, field_set=_field_set())
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "mapping"
    assay_date = next(m for m in body["field_mappings"] if m["target_field"] == "assay_date")
    assert assay_date["needs_confirmation"] is False
    assert "no constraint violation" in assay_date["validator_note"]


def test_multiple_ambiguous_date_columns_are_bundled_into_one_question(monkeypatch, profile_store):
    """Discretion #2: two ambiguous date columns in ONE file surface as ONE
    date_question carrying BOTH columns, not two sequential questions."""
    field_set = _field_set(extra=(Field(name="end_date", type="date"),))
    monkeypatch.setattr(
        service, "propose_mapping",
        _mapper(
            {"compound_id": "Compound Name", "assay_date": "Start Date", "end_date": "End Date"}
        ),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store)
    response = _post_upload_bytes(
        client, _AMBIGUOUS_TWO_DATE_CSV, "two_dates.csv", field_set=field_set
    )
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "date_question"
    assert {c["target_field"] for c in body["columns"]} == {"assay_date", "end_date"}


def test_structural_question_still_takes_precedence_over_date_question(monkeypatch, profile_store):
    question = StructureQuestion(
        unsure_about="which row is the real header",
        reason="no candidate header row scored clearly ahead of the others",
        confidence=0.5,
        proposal=StructuralHint(header_row_index=0),
        evidence_rows=[["a", "b"]],
    )
    monkeypatch.setattr(service, "resolve_or_map", lambda *a, **kw: question)

    client = _client(profile_store)
    response = _post_upload_bytes(
        client, _AMBIGUOUS_ONE_DATE_CSV, "ambiguous_dates.csv", field_set=_field_set()
    )
    _clear()

    assert response.status_code == 200
    assert response.json()["kind"] == "structural_question"


# --- 2. headers_only redacts the evidence, never the detection --------------


def test_headers_only_strips_the_evidence_values_from_the_date_question(monkeypatch, profile_store):
    monkeypatch.setattr(
        service, "propose_mapping",
        _mapper({"compound_id": "Compound Name", "assay_date": "Experiment Date"}),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store)
    response = _post_upload_bytes(
        client, _AMBIGUOUS_ONE_DATE_CSV, "ambiguous_dates.csv",
        field_set=_field_set(), headers_only=True,
    )
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "date_question"  # detection is unaffected (D-10-05)
    column = body["columns"][0]
    assert column["example_values"] == []
    assert column["ambiguous_row_count"] > 0  # the count still crosses, honestly

    serialized = json.dumps(body)
    assert "03/11/2025" not in serialized
    assert "04/11/2025" not in serialized


# --- 3. POST /api/date-format/resolve ----------------------------------------


def _get_date_question_token(client) -> str:
    response = _post_upload_bytes(
        client, _AMBIGUOUS_ONE_DATE_CSV, "ambiguous_dates.csv", field_set=_field_set()
    )
    assert response.json()["kind"] == "date_question"
    return response.json()["upload_token"]


def test_resolve_with_a_valid_order_returns_mapping_resolved_cleanly(monkeypatch, profile_store):
    monkeypatch.setattr(
        service, "propose_mapping",
        _mapper({"compound_id": "Compound Name", "assay_date": "Experiment Date"}),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store)
    token = _get_date_question_token(client)

    response = client.post(
        "/api/date-format/resolve",
        json={"upload_token": token, "choices": [{"target_field": "assay_date", "order": "day_first"}]},
    )
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "mapping"
    assay_date = next(m for m in body["field_mappings"] if m["target_field"] == "assay_date")
    assert assay_date["needs_confirmation"] is False
    assert "no constraint violation" in assay_date["validator_note"]


def test_resolve_rejects_an_invalid_order_literal_at_the_boundary(monkeypatch, profile_store):
    monkeypatch.setattr(
        service, "propose_mapping",
        _mapper({"compound_id": "Compound Name", "assay_date": "Experiment Date"}),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store)
    token = _get_date_question_token(client)

    response = client.post(
        "/api/date-format/resolve",
        json={"upload_token": token, "choices": [{"target_field": "assay_date", "order": "sideways"}]},
    )
    _clear()

    assert response.status_code == 422


def test_a_client_supplied_date_format_extra_key_is_dropped_and_ignored(monkeypatch, profile_store):
    """T-10-21: DateFormatChoiceIn carries NO date_format field at all -- an
    extra key in the body is simply dropped by Pydantic, and the server
    still derives its own format from the column + the chosen order,
    resolving cleanly regardless of what the client tried to smuggle in."""
    monkeypatch.setattr(
        service, "propose_mapping",
        _mapper({"compound_id": "Compound Name", "assay_date": "Experiment Date"}),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store)
    token = _get_date_question_token(client)

    response = client.post(
        "/api/date-format/resolve",
        json={
            "upload_token": token,
            "choices": [
                {"target_field": "assay_date", "order": "day_first", "date_format": "%Y/%m/%d"}
            ],
        },
    )
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "mapping"
    assay_date = next(m for m in body["field_mappings"] if m["target_field"] == "assay_date")
    assert assay_date["needs_confirmation"] is False


def test_date_format_choice_in_has_no_date_format_field_by_design():
    from assayingest.api.wire import DateFormatChoiceIn

    choice = DateFormatChoiceIn(target_field="x", order="day_first", **{"date_format": "%Y-%m-%d"})

    assert not hasattr(choice, "date_format")
    assert choice.model_dump() == {"target_field": "x", "order": "day_first"}


def test_resolve_fails_closed_when_a_column_is_left_undecided(monkeypatch, profile_store):
    field_set = _field_set(extra=(Field(name="end_date", type="date"),))
    monkeypatch.setattr(
        service, "propose_mapping",
        _mapper(
            {"compound_id": "Compound Name", "assay_date": "Start Date", "end_date": "End Date"}
        ),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store)
    upload_response = _post_upload_bytes(
        client, _AMBIGUOUS_TWO_DATE_CSV, "two_dates.csv", field_set=field_set
    )
    token = upload_response.json()["upload_token"]

    # Only answers ONE of the two ambiguous columns -- fail closed.
    response = client.post(
        "/api/date-format/resolve",
        json={"upload_token": token, "choices": [{"target_field": "assay_date", "order": "day_first"}]},
    )
    _clear()

    assert response.status_code == 422
    assert "end_date" in response.json()["detail"]


def test_resolve_with_an_empty_choices_list_fails_closed(monkeypatch, profile_store):
    monkeypatch.setattr(
        service, "propose_mapping",
        _mapper({"compound_id": "Compound Name", "assay_date": "Experiment Date"}),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store)
    token = _get_date_question_token(client)

    response = client.post(
        "/api/date-format/resolve", json={"upload_token": token, "choices": []},
    )
    _clear()

    assert response.status_code == 422
    assert "assay_date" in response.json()["detail"]


def test_resolve_unknown_token_is_404(profile_store):
    client = _client(profile_store)
    response = client.post(
        "/api/date-format/resolve",
        json={"upload_token": "no-such-token", "choices": []},
    )
    _clear()

    assert response.status_code == 404


def test_resolve_returns_a_fresh_token_whose_entry_still_carries_no_tmp_path(monkeypatch, profile_store):
    """The resolved entry re-put under a fresh token (mirroring
    structural_hint.py/reconcile.py's own "re-put under a fresh token"
    pattern) still carries no tmp_path -- the RawTable was already in
    memory throughout; nothing was ever written to or read from disk on
    this branch."""
    from assayingest.api.state import registry

    monkeypatch.setattr(
        service, "propose_mapping",
        _mapper({"compound_id": "Compound Name", "assay_date": "Experiment Date"}),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store)
    token = _get_date_question_token(client)

    response = client.post(
        "/api/date-format/resolve",
        json={"upload_token": token, "choices": [{"target_field": "assay_date", "order": "day_first"}]},
    )
    new_token = response.json()["upload_token"]
    entry = registry.get(new_token)
    _clear()

    assert response.status_code == 200
    assert entry is not None
    assert entry.tmp_path is None
