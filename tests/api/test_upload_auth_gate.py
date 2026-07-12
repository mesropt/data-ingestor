"""Server-side sign-in gate on the three Anthropic-reaching routes (D-10-13,
INGEST-06, gap-closure 10-09 Task 2). TDD RED-first.

`POST /api/upload` currently accepts `user: User | None = Depends(get_current_user)`
-- an anonymous client gets a 200 and burns an Anthropic call. D-10-13 locks
"sign-in is required to use the tool; there is no anonymous upload path" --
but that gate has only ever existed in the UI. This file pins the exact
semantics the fix must deliver:

  - anonymous -> 401, and the mapper is NEVER invoked (proving the credit-burn
    hole is closed, not merely that the response code changed)
  - signed-in but UNVERIFIED -> 200 -- the gate is sign-in, not verification
  - the same two-arm coverage for the resolve routes (`/api/structural-hint/
    resolve`, `/api/date-format/resolve`): a signed-out client must not be
    able to drive a retained upload to completion either.

Mirrors `tests/api/test_upload.py`/`test_upload_schema_target.py`'s exact
monkeypatch/DI-override idioms; reuses `tests/api/conftest.py`'s shared
`verified_user()`/`unverified_user()` builders (lifted from
`test_reconcile.py`, the file that already had exactly this shape).
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from assayingest import service
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.fields.loader import load as load_field_set
from assayingest.fields.models import Field, FieldSet

from .conftest import unverified_user

DATA = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic"
PRESET = Path(__file__).resolve().parent.parent.parent / "presets" / "assay-potency.yaml"
NOVASCREEN_01 = DATA / "novascreen_batch01.csv"


def _explode(*_a, **_k):
    raise AssertionError("service.propose_mapping must NOT run for an anonymous request")


def _client(profile_store, *, user):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user, get_profile_store

    app.dependency_overrides[get_profile_store] = lambda: profile_store
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _clear():
    from assayingest.api.app import app

    app.dependency_overrides.clear()


# --- POST /api/upload ---------------------------------------------------------


def test_anonymous_upload_is_401_and_never_reaches_the_mapper(monkeypatch, profile_store):
    """The point of the gate: an anonymous client cannot burn Anthropic
    credits. Proving 401 alone is not enough -- the mapper spy proves the
    request never reached the point where an API call would be made."""
    monkeypatch.setattr(service, "propose_mapping", _explode)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    field_set = load_field_set(PRESET)
    client = _client(profile_store, user=None)

    with open(NOVASCREEN_01, "rb") as f:
        response = client.post(
            "/api/upload",
            files={"file": ("novascreen_batch01.csv", f, "text/csv")},
            data={"field_set": json.dumps(field_set.to_dict())},
        )
    _clear()

    assert response.status_code == 401


def test_signed_in_unverified_user_can_still_upload(monkeypatch, profile_store):
    """D-10-13: the gate is sign-in, NOT verification. A freshly signed-up
    (unverified) user must still be able to use the tool -- hardening this
    to require_verified_user would be scope creep the locked decision does
    not ask for, and would lock a fresh signup out entirely."""
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

    field_set = FieldSet(fields=(Field(name="compound_id"),))
    client = _client(profile_store, user=unverified_user())

    with open(NOVASCREEN_01, "rb") as f:
        response = client.post(
            "/api/upload",
            files={"file": ("novascreen_batch01.csv", f, "text/csv")},
            data={"field_set": json.dumps(field_set.to_dict())},
        )
    _clear()

    assert response.status_code == 200
    assert response.json()["kind"] == "mapping"


# --- POST /api/structural-hint/resolve ----------------------------------------


def _seed_ambiguous_upload(tmp_path) -> str:
    from assayingest.api.state import UploadEntry, registry

    csv_path = tmp_path / "ambiguous.csv"
    csv_path.write_text("Compound;Value\nA-1;1,234\nA-2;5,678\n", encoding="utf-8")
    field_set = FieldSet(fields=(Field(name="compound_id"), Field(name="value")))
    return registry.put(
        UploadEntry(field_set=field_set, headers_only=False, tmp_path=str(csv_path))
    )


def test_anonymous_structural_hint_resolve_is_401(tmp_path, profile_store):
    """A signed-out client must not be able to drive a retained upload to
    completion via the structural-hint resolve path either."""
    token = _seed_ambiguous_upload(tmp_path)
    client = _client(profile_store, user=None)

    response = client.post(
        "/api/structural-hint/resolve",
        json={"upload_token": token, "hint": {"decimal_separator": ","}},
    )
    _clear()

    assert response.status_code == 401


# --- POST /api/date-format/resolve --------------------------------------------


def _seed_date_question_upload(profile_store, monkeypatch) -> tuple[str, TestClient]:
    """Uploads a genuinely-ambiguous-date CSV as a verified user to retrieve
    a real date_question token, mirroring test_date_format_route.py's own
    fixture -- then hands back a FRESH, signed-out client for the resolve
    call itself, so the resolve route's own gate is what is under test."""
    from .conftest import verified_user

    def _mapper(table, field_set, client=None, *, headers_only=False):
        headers_map = {"compound_id": "Compound Name", "assay_date": "Experiment Date"}
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

    monkeypatch.setattr(service, "propose_mapping", _mapper)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    field_set = FieldSet(
        fields=(Field(name="compound_id"), Field(name="assay_date", type="date"))
    )
    ambiguous_csv = (
        b"Compound Name,Experiment Date\n"
        b"HLX-100,03/11/2025\n"
        b"HLX-101,04/11/2025\n"
    )
    signed_in_client = _client(profile_store, user=verified_user())
    upload_response = signed_in_client.post(
        "/api/upload",
        files={"file": ("ambiguous_dates.csv", ambiguous_csv, "text/csv")},
        data={"field_set": json.dumps(field_set.to_dict())},
    )
    assert upload_response.json()["kind"] == "date_question"
    return upload_response.json()["upload_token"], profile_store


def test_anonymous_date_format_resolve_is_401(monkeypatch, profile_store):
    """A signed-out client must not be able to drive a retained,
    date-question-pending upload to completion either."""
    token, store = _seed_date_question_upload(profile_store, monkeypatch)
    _clear()
    client = _client(store, user=None)

    response = client.post(
        "/api/date-format/resolve",
        json={"upload_token": token, "choices": [{"target_field": "assay_date", "order": "day_first"}]},
    )
    _clear()

    assert response.status_code == 401
