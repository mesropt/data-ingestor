"""`GET /api/export/group/{group_id}/archive` + the `record_run` hook in
`/api/confirm` (11-08, SHEET-01/D-11-10) -- one action downloads every
confirmed member's result set as a single zip, one directory per sheet.

TDD RED-first. Mirrors `tests/api/test_sheets_route.py`'s harness idioms
exactly -- `_client()` DI overrides, `_clear()`, `_mapper()`/`_explode_mapper`
stubs on `service.propose_mapping`, real fixture bytes through `TestClient`,
and the same structural no-outbound-call guard.

THE ARCHIVE IS A CONVENIENCE OVER THE PER-MEMBER GATES, NEVER A BYPASS
(D-11-08, T-11-31): every member confirms on `service.confirm`'s existing
`NotReadyError` gate, a `run_id` exists only because that gate passed, and the
archive route merely LOOKS UP recorded runs -- it adds no readiness logic of
its own and refuses, loudly, while any member has none.

THE QUESTION-HOP PINS ARE THE 11-07 HANDOFF CLOSED (its SUMMARY's "READ THIS"
section): a member that answers a structural or date question is re-put under
a FRESH token, and the re-puts in `structural_hint.py` and `date_format.py`
did not carry `group_id`/`sheet` forward -- so exactly the members that needed
a question would silently vanish from "Download All". Each re-put is pinned
here: the still-ambiguous hop, the hint-resolved-to-mapping hop, the
hint-resolved-to-date-question hop, and the answered-date-question hop (the
last proved end-to-end, all the way into the archive's own bytes).
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from assayingest import service
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.learning.seed import seed_schema_aliases, seed_schemas

from .conftest import verified_user

DATA = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic"
ZEPHYR = DATA / "zephyr_bio_ZB-2025.xlsx"

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_MEMBER_FILES = ("export.csv", "export.xlsx", "export.json", "manifest.json")


# --- the no-outbound-call guard (test_sheets_route.py's own, verbatim) --------


@pytest.fixture(autouse=True)
def _no_claude_anywhere(monkeypatch):
    """AUTOUSE. Stage 3 (D-11-19) must never fire from this file -- a live call
    with a fake key would make these tests depend on the network."""

    def _explode(*_a, **_k):
        raise AssertionError(
            "propose_schema_ranking must NOT run: this file makes zero outbound calls"
        )

    monkeypatch.setattr(service, "propose_schema_ranking", _explode)


@pytest.fixture
def seeded(schema_store):
    seed_schemas(schema_store)
    seed_schema_aliases(schema_store)
    return schema_store


def _client(profile_store, schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import (
        get_anthropic_client,
        get_current_user,
        get_profile_store,
        get_schema_store,
    )

    app.dependency_overrides[get_profile_store] = lambda: profile_store
    app.dependency_overrides[get_schema_store] = lambda: schema_store
    app.dependency_overrides[get_current_user] = lambda: verified_user()
    app.dependency_overrides[get_anthropic_client] = lambda: None
    return TestClient(app)


def _anonymous_client(profile_store, schema_store):
    from assayingest.api.app import app
    from assayingest.api.deps import (
        get_anthropic_client,
        get_current_user,
        get_profile_store,
        get_schema_store,
    )

    app.dependency_overrides[get_profile_store] = lambda: profile_store
    app.dependency_overrides[get_schema_store] = lambda: schema_store
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_anthropic_client] = lambda: None
    return TestClient(app)


def _clear():
    from assayingest.api.app import app

    app.dependency_overrides.clear()


def _mapper(headers_map: dict[str, str] | None = None):
    headers_map = headers_map or {}

    def _fn(table, field_set, client=None, *, headers_only=False):
        return MappingProposal(
            source_columns=list(table.headers),
            field_mappings=[
                FieldMapping(
                    target_field=name,
                    source_column=headers_map.get(name),
                    confidence=1.0 if headers_map.get(name) else 0.4,
                    reasoning="fixture",
                    needs_confirmation=headers_map.get(name) is None,
                )
                for name in field_set.field_names
            ],
        )

    return _fn


def _explode_mapper(*_a, **_k):
    raise AssertionError("propose_mapping must NOT run: the crosswalk covers every field")


def _post_workbook(client, source: Path | bytes, **data):
    if isinstance(source, bytes):
        return client.post(
            "/api/upload",
            files={"file": ("synthetic.xlsx", source, _XLSX_MIME)},
            data={k: v for k, v in data.items() if v is not None},
        )
    with open(source, "rb") as fh:
        return client.post(
            "/api/upload",
            files={"file": (source.name, fh, _XLSX_MIME)},
            data={k: v for k, v in data.items() if v is not None},
        )


def _ask(client, source: Path | bytes, **data) -> str:
    response = _post_workbook(client, source, **data)
    assert response.json()["kind"] == "sheet_question", response.json()
    return response.json()["upload_token"]


def _resolve(client, token: str, selections: list[tuple[str, str]]):
    return client.post(
        "/api/sheets/resolve",
        json={
            "upload_token": token,
            "selections": [
                {"sheet_name": sheet, "schema_name": schema} for sheet, schema in selections
            ],
        },
    )


def _members(body) -> dict[str, dict]:
    return {m["sheet_name"]: m["response"] for m in body["members"]}


def _field_set_dict(schema_store, name: str) -> dict:
    return service.field_set_from_schema(schema_store.get_schema(name)).to_dict()


def _confirm(
    client,
    mapping_body: dict,
    field_set: dict,
    *,
    vendor: str,
    export: bool = True,
    field_mappings: list[dict] | None = None,
):
    return client.post(
        "/api/confirm",
        json={
            "upload_token": mapping_body["upload_token"],
            "field_set": field_set,
            "field_mappings": field_mappings
            if field_mappings is not None
            else [
                {k: v for k, v in m.items() if k != "validator_note"}
                for m in mapping_body["field_mappings"]
            ],
            "vendor": vendor,
            "export": export,
        },
    )


def _resolved_unit(mapping_body: dict) -> list[dict]:
    """The curator's own resolution of zephyr's one amber field (`Units` holds
    `uM`, an ASCII u, not one of the Schema's `µM`/`nM`/`%`) -- the amber gate
    being ANSWERED, never bypassed (test_sheets_route.py's idiom, verbatim)."""
    resolved = []
    for mapping in mapping_body["field_mappings"]:
        mapping = {k: v for k, v in mapping.items() if k != "validator_note"}
        if mapping["target_field"] == "unit":
            mapping |= {
                "source_column": None,
                "inferred_value": "µM",
                "needs_confirmation": False,
            }
        resolved.append(mapping)
    return resolved


def _archive(client, group_id: str):
    return client.get(f"/api/export/group/{group_id}/archive")


def _workbook(sheets: dict[str, list[list]]) -> bytes:
    import openpyxl

    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        worksheet = workbook.create_sheet(name)
        for row in rows:
            worksheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _two_question_workbook() -> bytes:
    """Both sheets fail the header gate, so both members are question-bearing
    (test_sheets_route.py's own fixture, verbatim)."""
    prose = ["Vehicle: 0.5% MC. Route: PO. Species: mouse."]
    return _workbook({"Alpha": [prose], "Beta": [prose]})


def _ambiguous_date_workbook() -> bytes:
    """Two sheets whose date column is GENUINELY order-ambiguous -- every value
    has day<=12 AND month<=12 (test_sheets_route.py's own fixture, verbatim)."""

    def rows(prefix: str) -> list[list]:
        header = [["compound_id", "assay_type", "value", "assay_date"]]
        return header + [
            [f"{prefix}-{100 + i}", "IC50", round(1.5 + i * 0.3, 2), f"{(i % 9) + 1:02d}/11/2025"]
            for i in range(1, 11)
        ]

    return _workbook({"One": rows("CPD"), "Two": rows("XPD")})


def _undeclared_date_schema(schema_store) -> str:
    """A governed Schema whose date field declares NO format -- an ambiguous
    column has nothing to resolve it and must raise the date question."""
    from assayingest.fields.models import Field, FieldSet

    service.promote(
        FieldSet(
            name="undeclared-dates",
            fields=(
                Field(name="compound_id"),
                Field(name="assay_type"),
                Field(name="value", type="number"),
                Field(name="assay_date", type="date"),
            ),
        ),
        created_by="curator@example.com",
        store=schema_store,
    )
    return "undeclared-dates"


# =============================================================================
# The end-to-end money shot: N confirmed members, one zip, each sheet's own
# provenance in its own rows (SHEET-01 closed; SHEET-03 proved across a group).
# =============================================================================


def test_a_confirmed_group_downloads_as_one_zip_with_each_sheets_own_provenance(
    monkeypatch, profile_store, seeded
):
    """Upload zephyr -> resolve 3 sheets -> confirm all 3 -> ONE archive holding
    three directories, four files each -- and each member's `export.csv` carries
    its OWN `__source_sheet` value, which is SHEET-03's provenance proved end to
    end across a group."""
    monkeypatch.setattr(service, "propose_mapping", _explode_mapper)
    field_set = _field_set_dict(seeded, "assay-potency")
    sheets = ["Week 1", "Week 2", "Week 3"]

    client = _client(profile_store, seeded)
    token = _ask(client, ZEPHYR, schema_name="assay-potency")
    body = _resolve(client, token, [(sheet, "assay-potency") for sheet in sheets]).json()
    members = _members(body)
    for sheet in sheets:
        confirmed = _confirm(
            client, members[sheet], field_set, vendor="zephyr",
            field_mappings=_resolved_unit(members[sheet]),
        )
        assert confirmed.status_code == 200, confirmed.json()
    response = _archive(client, body["group_id"])
    _clear()

    assert response.status_code == 200, response.json()
    assert response.headers["content-type"].startswith("application/zip")
    assert "zephyr_bio_ZB-2025" in response.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {
            f"{sheet}/{filename}" for sheet in sheets for filename in _MEMBER_FILES
        }
        for sheet in sheets:
            rows = list(
                csv.DictReader(io.StringIO(archive.read(f"{sheet}/export.csv").decode("utf-8")))
            )
            assert rows, sheet
            assert {row["__source_sheet"] for row in rows} == {sheet}


# =============================================================================
# The gate: the archive is a convenience over the per-member gates, never a
# bypass of any of them (D-11-08, T-11-31).
# =============================================================================


def test_the_archive_refuses_while_any_member_is_unconfirmed(
    monkeypatch, profile_store, seeded
):
    """With 2 of 3 confirmed, the archive is REFUSED (409, naming how many
    datasets are still unconfirmed) -- and each CONFIRMED member's own per-run
    download still works. The group route never substitutes for a member's
    confirm, and never punishes the members that did confirm."""
    monkeypatch.setattr(service, "propose_mapping", _explode_mapper)
    field_set = _field_set_dict(seeded, "assay-potency")

    client = _client(profile_store, seeded)
    token = _ask(client, ZEPHYR, schema_name="assay-potency")
    body = _resolve(
        client, token,
        [("Week 1", "assay-potency"), ("Week 2", "assay-potency"), ("Week 3", "assay-potency")],
    ).json()
    members = _members(body)
    confirmed_urls = []
    for sheet in ("Week 1", "Week 2"):
        confirmed = _confirm(
            client, members[sheet], field_set, vendor="zephyr",
            field_mappings=_resolved_unit(members[sheet]),
        )
        assert confirmed.status_code == 200
        confirmed_urls.append(confirmed.json()["export"]["csv_url"])
    refusal = _archive(client, body["group_id"])
    downloads = [client.get(url) for url in confirmed_urls]
    _clear()

    assert refusal.status_code == 409
    detail = refusal.json()["detail"]
    assert "still unconfirmed" in detail
    assert "1" in detail  # names HOW MANY, not just that some are
    for download in downloads:
        assert download.status_code == 200  # per-member downloads unharmed


def test_a_member_with_an_unresolved_amber_field_still_422s_at_confirm(
    monkeypatch, profile_store, seeded
):
    """No group-level path can confirm a member: the amber gate is per dataset
    and `/api/confirm` is the ONLY way through it (D-11-08). This plan adds a
    lookup, never a second gate -- and never a bypass of the first."""
    monkeypatch.setattr(service, "propose_mapping", _explode_mapper)
    field_set = _field_set_dict(seeded, "assay-potency")

    client = _client(profile_store, seeded)
    token = _ask(client, ZEPHYR, schema_name="assay-potency")
    body = _resolve(client, token, [("Week 1", "assay-potency")]).json()
    members = _members(body)
    refused = _confirm(client, members["Week 1"], field_set, vendor="zephyr")
    archive = _archive(client, body["group_id"])
    _clear()

    assert refused.status_code == 422
    assert refused.json()["detail"]["unclear_fields"] == ["unit"]
    assert archive.status_code == 409  # the unconfirmed member blocks the archive


# =============================================================================
# The boundary: auth (D-10-13), traversal (T-11-29), unknown group.
# =============================================================================


def test_an_anonymous_archive_request_is_401(profile_store, seeded):
    """D-10-13/T-11-30: a signed-out client must not download a group's
    exported cell values, exactly as it must not drive any retained upload."""
    client = _anonymous_client(profile_store, seeded)
    response = _archive(client, "11111111-1111-1111-1111-111111111111")
    _clear()

    assert response.status_code == 401


def test_a_group_id_that_is_not_a_uuid4_is_404_before_any_filesystem_access(
    monkeypatch, profile_store, seeded
):
    """T-11-29: `group_id` is only ever a server-minted uuid4 -- anything else
    is rejected by the same regex discipline `_RUN_ID_PATTERN` applies to
    `run_id`, BEFORE any path join or archive build. The exploding builder is
    the proof the filesystem was never reached."""
    from assayingest.api.routes import export as export_route

    def _explode(*_a, **_k):
        raise AssertionError("build_group_archive must NOT run for an invalid group_id")

    monkeypatch.setattr(export_route, "build_group_archive", _explode)

    client = _client(profile_store, seeded)
    response = _archive(client, "..sneaky-not-a-uuid")
    _clear()

    assert response.status_code == 404


def test_an_unknown_group_is_404_naming_the_consequence(profile_store, seeded):
    client = _client(profile_store, seeded)
    response = _archive(client, "33333333-3333-3333-3333-333333333333")
    _clear()

    assert response.status_code == 404
    assert "nothing was downloaded" in response.json()["detail"].lower()


# =============================================================================
# The 11-07 handoff, closed and pinned: group membership SURVIVES a question
# hop. Without these, "Download All" would silently lose exactly the members
# that needed a question -- the least forgivable set to lose.
# =============================================================================


def test_a_member_that_answered_a_date_question_still_appears_in_the_archive(
    monkeypatch, profile_store, schema_store
):
    """END TO END: both members raise their own date question, both are
    answered, both confirm -- and the archive holds BOTH. This is the
    `date_format.py` re-put carrying `group_id`/`sheet` forward, proved in the
    archive's own bytes rather than asserted on a field."""
    monkeypatch.setattr(service, "propose_mapping", _explode_mapper)
    from assayingest.api.state import registry

    schema_name = _undeclared_date_schema(schema_store)
    field_set = _field_set_dict(schema_store, schema_name)

    client = _client(profile_store, schema_store)
    token = _ask(client, _ambiguous_date_workbook(), schema_name=schema_name)
    body = _resolve(client, token, [("One", schema_name), ("Two", schema_name)]).json()
    members = _members(body)
    assert members["One"]["kind"] == "date_question"

    for sheet in ("One", "Two"):
        answered = client.post(
            "/api/date-format/resolve",
            json={
                "upload_token": members[sheet]["upload_token"],
                "choices": [{"target_field": "assay_date", "order": "day_first"}],
            },
        ).json()
        assert answered["kind"] == "mapping"
        # The re-put entry is still a MEMBER -- the defect was exactly here.
        hopped = registry.get(answered["upload_token"])
        assert hopped.group_id == body["group_id"]
        assert hopped.sheet == sheet
        confirmed = _confirm(client, answered, field_set, vendor="acme")
        assert confirmed.status_code == 200, confirmed.json()

    response = _archive(client, body["group_id"])
    _clear()

    assert response.status_code == 200, response.json()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        directories = {name.partition("/")[0] for name in archive.namelist()}
    assert directories == {"One", "Two"}


def test_group_membership_survives_a_still_ambiguous_hint_re_put(profile_store, seeded):
    """`structural_hint.py`'s FIRST re-put (still ambiguous, fresh token, same
    retained file): the fresh entry must still know whose member it is."""
    from assayingest.api.state import registry

    client = _client(profile_store, seeded)
    token = _ask(client, _two_question_workbook(), schema_name="assay-potency")
    body = _resolve(
        client, token, [("Alpha", "assay-potency"), ("Beta", "assay-potency")]
    ).json()
    members = _members(body)
    assert members["Alpha"]["kind"] == "structural_question"

    still_asking = client.post(
        "/api/structural-hint/resolve",
        json={"upload_token": members["Alpha"]["upload_token"], "hint": {}},
    ).json()
    hopped = registry.get(still_asking["upload_token"])
    _clear()

    assert still_asking["kind"] == "structural_question"
    assert hopped.group_id == body["group_id"]
    assert hopped.sheet == "Alpha"


def test_group_membership_survives_a_hint_resolved_to_a_mapping(
    monkeypatch, tmp_path, profile_store, seeded
):
    """`structural_hint.py`'s resolved-mapping re-put: a member whose hint
    resolves straight to a mapping arrives at Confirm still knowing its group,
    so its run is recorded and the archive does not lose it.

    Seeded directly at the registry (the `test_hint_and_export.py` idiom)
    because it needs a question a hint DETERMINISTICALLY resolves -- the
    ambiguous decimal locale, whose separator answer settles it outright. The
    two-question workbook's prose sheet never resolves to a mapping (a
    header hint still leaves it shapeless), so it cannot exercise this hop."""
    from assayingest.api.state import UploadEntry, registry
    from assayingest.fields.models import Field, FieldSet

    monkeypatch.setattr(
        service, "propose_mapping",
        _mapper({"compound_id": "Compound", "value": "Value"}),
    )

    csv_path = tmp_path / "ambiguous.csv"
    csv_path.write_text("Compound;Value\nA-1;1,234\nA-2;5,678\n", encoding="utf-8")
    field_set = FieldSet(fields=(Field(name="compound_id"), Field(name="value")))
    token = registry.put(
        UploadEntry(
            field_set=field_set, headers_only=False, tmp_path=str(csv_path),
            group_id="g-map", sheet="Two",
        )
    )

    client = _client(profile_store, seeded)
    resolved = client.post(
        "/api/structural-hint/resolve",
        json={"upload_token": token, "hint": {"decimal_separator": ","}},
    ).json()
    hopped = registry.get(resolved["upload_token"])
    _clear()

    assert resolved["kind"] == "mapping"
    assert hopped.group_id == "g-map"
    assert hopped.sheet == "Two"


def test_group_membership_survives_a_hint_resolved_to_a_date_question(
    monkeypatch, tmp_path, profile_store, seeded
):
    """`structural_hint.py`'s THIRD re-put (hint resolves the parse, but a date
    ambiguity surfaces BEHIND it): seeded directly at the registry, the
    `test_hint_and_export.py` idiom -- an ambiguous decimal CSV whose date
    column is also genuinely order-ambiguous, against a field set whose date
    field declares no format."""
    from assayingest.api.state import UploadEntry, registry
    from assayingest.fields.models import Field, FieldSet

    monkeypatch.setattr(
        service, "propose_mapping",
        _mapper({"compound_id": "Compound", "value": "Value", "assay_date": "Date"}),
    )

    csv_path = tmp_path / "ambiguous.csv"
    csv_path.write_text(
        "Compound;Value;Date\nA-1;1,234;01/02/2025\nA-2;5,678;03/04/2025\n",
        encoding="utf-8",
    )
    field_set = FieldSet(
        fields=(
            Field(name="compound_id"),
            Field(name="value", type="number"),
            Field(name="assay_date", type="date"),
        )
    )
    token = registry.put(
        UploadEntry(
            field_set=field_set, headers_only=False, tmp_path=str(csv_path),
            group_id="g-test", sheet="One",
        )
    )

    client = _client(profile_store, seeded)
    response = client.post(
        "/api/structural-hint/resolve",
        json={"upload_token": token, "hint": {"decimal_separator": ","}},
    ).json()
    hopped = registry.get(response["upload_token"])
    _clear()

    assert response["kind"] == "date_question"
    assert hopped.group_id == "g-test"
    assert hopped.sheet == "One"
