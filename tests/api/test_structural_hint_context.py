"""The structural-hint resolve path keeps its full context (11-06, D-11-22).

`POST /api/structural-hint/resolve` used to call `service.resolve_or_map`
WITHOUT `schema=`, `sheet=` or `strictness=`, and never checked
`result.date_question` -- four confirmed consequences (RESEARCH.md Pitfall
4): the Python-first crosswalk prefill never ran on the hint path, the
escalation line silently disappeared, the vendor pre-fill (which
`/api/confirm` REQUIRES) was never computed, and an ambiguous date column
behind a structural question stranded the field amber forever -- the exact
Confirm dead-end quick task `260712-qgc` fixed on `/api/upload`, re-created
one route over.

Task 1 pins the retention half: the structural-question `UploadEntry` must
keep `schema_name`, `sheet` and `strictness` alive across the question, and
`sheet` must round-trip the `pending_uploads` persistence boundary with the
`.get()` idiom (an old persisted row without the key still rehydrates).

Task 2 pins the resolve half: each of the four consequences gets its own
regression test, plus the Phase 11 load-bearing one -- resolving a hint on a
multi-sheet workbook re-parses the sheet the human chose, never the
workbook's re-ranked winner.

Harness copied from `tests/api/test_date_format_route.py` (the DI-override +
`_mapper` stub + `monkeypatch.setenv` idiom); registry assertions mirror
`tests/api/test_state.py`'s direct-registry idiom. Never a live Claude call.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from assayingest import service
from assayingest.api.state import UploadEntry, _entry_from_json, _entry_to_json
from assayingest.fields.models import Field, FieldSet
from assayingest.parsing.table import RawTable

from .conftest import verified_user

_SCHEMA_NAME = "assay-potency"

#: Every comma is followed by exactly 3 digits -- thousands grouping and a
#: 3-decimal comma display are indistinguishable, so D-14 asks (mirrors
#: `tests/api/test_hint_and_export.py::_write_ambiguous_csv`). Headers spell
#: the canonical field names, so the D-11-17 implicit self-alias covers them.
_AMBIGUOUS_LOCALE_CSV = b"compound_id;value\nA-1;1,234\nA-2;5,678\n"


def _field_set() -> FieldSet:
    return FieldSet(
        name=_SCHEMA_NAME,
        fields=(Field(name="compound_id"), Field(name="value")),
    )


def _client(profile_store, schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import get_current_user, get_profile_store, get_schema_store

    app.dependency_overrides[get_profile_store] = lambda: profile_store
    app.dependency_overrides[get_schema_store] = lambda: schema_store
    app.dependency_overrides[get_current_user] = lambda: verified_user()
    return TestClient(app)


def _clear():
    from assayingest.api.app import app

    app.dependency_overrides.clear()


def _upload_ambiguous_with_schema_and_sheet(client) -> dict:
    """Upload a file that raises a StructureQuestion, with a `schema_name`
    and an explicit `sheet` supplied -- the exact request shape a sheet-group
    member re-enters this flow with (D-11-22)."""
    return client.post(
        "/api/upload",
        files={"file": ("ambiguous.csv", _AMBIGUOUS_LOCALE_CSV, "text/csv")},
        data={"schema_name": _SCHEMA_NAME, "sheet": "Week 2"},
    ).json()


# --- Task 1: the structural-question entry retains schema/sheet/strictness ---


def test_structural_question_entry_retains_schema_name_sheet_and_strictness(
    profile_store, schema_store
):
    """The resolve route can only pass what the question branch kept: ALL
    THREE of `schema_name`, `sheet`, `strictness` must survive on the
    retained `UploadEntry` (asserted directly against the registry, the
    `tests/api/test_state.py` idiom)."""
    from assayingest.api.state import registry

    service.promote(_field_set(), created_by="seed@example.com", store=schema_store)
    client = _client(profile_store, schema_store)

    body = _upload_ambiguous_with_schema_and_sheet(client)
    entry = registry.get(body["upload_token"])
    _clear()

    assert body["kind"] == "structural_question"
    assert entry is not None
    assert entry.schema_name == _SCHEMA_NAME
    assert entry.sheet == "Week 2"
    assert entry.strictness == "strict"


# --- Task 1: `sheet` round-trips the pending_uploads persistence boundary ----


def _review_ready_entry(sheet: str | None) -> UploadEntry:
    return UploadEntry(
        field_set=FieldSet(fields=(Field(name="compound_id"),)),
        headers_only=False,
        tmp_path=None,
        table=RawTable(headers=["cmpd"], rows=[["NVS-1"]], source_name="tmpxyz.xlsx"),
        provenance="fresh-claude",
        sheet=sheet,
    )


def test_entry_json_round_trip_preserves_the_retained_sheet():
    rehydrated = _entry_from_json(_entry_to_json(_review_ready_entry("Week 2")))

    assert rehydrated.sheet == "Week 2"


def test_an_old_persisted_row_without_the_sheet_key_still_rehydrates():
    """The `.get()` idiom: a row persisted before the `sheet` key existed has
    nothing truthful to offer and must rehydrate rather than destroy a
    curator's mid-review upload on the deploy that ADDED the key."""
    raw = json.loads(_entry_to_json(_review_ready_entry(None)))
    raw.pop("sheet", None)  # simulate a pre-11-06 persisted row

    rehydrated = _entry_from_json(json.dumps(raw))

    assert rehydrated.sheet is None
