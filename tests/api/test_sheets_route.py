"""The `kind="sheet_question"` 5th arm of `/api/upload`, the `kind="sheet_group"`
6th arm of `POST /api/sheets/resolve`, and the wire models both ride on
(SHEET-01/04/05, D-11-02/06/08/16/20).

TDD RED-first (11-07). Mirrors `tests/api/test_date_format_route.py`'s harness
idioms exactly -- `_client()` DI overrides, `_clear()`, a `_mapper()` stub
monkeypatched onto `service.propose_mapping`, and real fixture bytes posted
through `TestClient`.

NO OUTBOUND CALL CAN ESCAPE THIS FILE, and that is enforced structurally rather
than promised in prose. Plan 11-05 landed D-11-19's third stage: a sheet with
EXACTLY zero deterministic coverage escalates to Claude whenever a client
exists. This file's harness sets `ANTHROPIC_API_KEY` (the
`test_date_format_route.py` idiom), which would otherwise construct a REAL
client -- so orion's `Notes` (no headers at all... and therefore refused before
the call, 11-05) and any genuinely uncovered sheet would depend on 11-05's
exception degradation, after a live HTTP attempt with a fake key. That is a
flaky, network-dependent test. Two guards close it:

  * `get_anthropic_client` is DI-overridden to `None` for every test here, so
    `service._ranker_for` has no ranker to build; and
  * an autouse fixture explodes on `service.propose_schema_ranking` and
    `service.propose_mapping`'s ranking path, so a regression that reintroduced
    a client would fail loudly rather than silently dial out.

Stage 3's own behaviour is `tests/test_schema_ranker.py`'s to own, not this
file's.

Since 12-04 the manifest also carries the layout JUDGE's verdict, and the
`lambda: None` override honestly means NO JUDGE: every sheet reports
`layout_unknown` with no headers. Tests whose subject is the MANIFEST
(statuses, headers, badges) therefore inject the shared `judging_client`
fixture (conftest) — a duck-typed structured-output fake whose verdicts run
the REAL `_to_domain_verdicts`; tests whose subject is RESOLVE/ingestion or
the no-judge path keep the None override, because the resolve path re-parses
with its own gate chain and never reads the manifest's statuses.

THE FOUR SYNTHETIC WORKBOOKS ARE THE ACCEPTANCE TEST (11-CONTEXT.md):

  * zephyr   -- 3 data sheets, headers on row 4. The N-independent-datasets case.
  * meridian -- DATA + LEGEND. LEGEND is what `parse()` silently discards today.
  * orion    -- Summary / Raw timepoints / Notes. Notes resolves no header at all.
  * delta    -- one sheet per target, a different header spelling on each.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from assayingest import service
from assayingest.api.wire import SheetQuestionResponse
from assayingest.domain.models import FieldMapping, MappingProposal
from assayingest.learning.seed import seed_schema_aliases, seed_schemas
from assayingest.parsing.structure.layout import KeyValueBlock, LayoutKind, SheetLayout
from assayingest.service import SchemaProposal, SheetManifestEntry

from .conftest import verified_user

DATA = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic"
ZEPHYR = DATA / "zephyr_bio_ZB-2025.xlsx"
MERIDIAN = DATA / "meridian_cro_codes.xlsx"
ORION = DATA / "orion_pk_report.xlsx"
NOVASCREEN = DATA / "novascreen_batch01.csv"
#: The phase's driving file (D-12-13): `Patient Info` carries TWO side-by-side
#: key-value blocks belonging to one record -- labels col 0 / values col 1 AND
#: labels col 3 / values col 4, rows 1..10.
CASCADE = DATA / "lab_corpus" / "cascade_allergy_CS-2026-698392.xlsx"

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# --- the no-outbound-call guard (see the module docstring) --------------------


@pytest.fixture(autouse=True)
def _no_claude_anywhere(monkeypatch):
    """AUTOUSE. Stage 3 (D-11-19) must never fire from this file: a live call
    with a fake key would make the LEGEND/Notes assertions depend on 11-05's
    exception degradation and on the network. The DI override in `_client()`
    already removes the client; this explodes if anything ever rebuilds one."""

    def _explode(*_a, **_k):
        raise AssertionError(
            "propose_schema_ranking must NOT run: this file makes zero outbound calls"
        )

    monkeypatch.setattr(service, "propose_schema_ranking", _explode)


@pytest.fixture
def seeded(schema_store):
    """The real starter crosswalk (11-02/D-11-18) -- without it every sheet
    scores 0/N and the whole feature would look dead in these tests."""
    seed_schemas(schema_store)
    seed_schema_aliases(schema_store)
    return schema_store


def _client(profile_store, schema_store, anthropic_client=None):
    """`anthropic_client` is the 12-04 seam: pass the shared `judging_client`
    fixture wherever the test's subject is the MANIFEST (statuses, headers,
    badges) and needs the judge's verdicts; leave it `None` — which really
    does mean no judge, and therefore all-`layout_unknown` sheets — wherever
    the subject is the no-judge path or never reads the manifest at all."""
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
    # With anthropic_client=None this is the stage-3 neutralizer: no client ->
    # no ranker, no judge -> no outbound call, whatever ANTHROPIC_API_KEY says.
    # The judging_client fake is equally offline — it stops at the SDK boundary.
    app.dependency_overrides[get_anthropic_client] = lambda: anthropic_client
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


def _mapper(headers_map: dict[str, str] | None = None, *, needs_confirmation: bool = False):
    """A `propose_mapping` stub -- never a real Claude call. Maps each requested
    field to a fixed source column (or to nothing), mirroring
    `test_date_format_route.py::_mapper`."""
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
                    needs_confirmation=needs_confirmation or headers_map.get(name) is None,
                )
                for name in field_set.field_names
            ],
        )

    return _fn


def _explode_mapper(*_a, **_k):
    """Zero Claude calls: a fully-covered sheet resolves through the crosswalk
    alone (D-10-03). An exploding stub is the proof, not a promise."""
    raise AssertionError("propose_mapping must NOT run: the crosswalk covers every field")


def _post_workbook(client, source: Path | bytes, **data):
    """Post a workbook -- a real fixture (`Path`) or in-memory bytes (a
    purpose-built case with no in-tree fixture)."""
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


# =============================================================================
# Task 1 -- the wire arms, exercised directly (no HTTP): the pre-selection
# precedence and the tie/skip refusals are pure functions of the manifest.
# =============================================================================


def _proposal(name: str, matched: dict[str, str], total: int, source: str = "crosswalk") -> SchemaProposal:
    return SchemaProposal(
        schema_name=name,
        matched=matched,
        uncovered=tuple(f"f{i}" for i in range(total - len(matched))),
        total=total,
        source=source,
    )


def _entry(
    name: str,
    *proposals: SchemaProposal,
    status: str = "ok",
    headers=None,
    layout: SheetLayout | None = None,
) -> SheetManifestEntry:
    return SheetManifestEntry(
        name=name,
        headers=list(headers) if headers is not None else ["Compound ID", "Result"],
        row_count=8,
        column_signature="sig",
        status=status,
        proposals=tuple(proposals),
        layout=layout,
    )


def _not_a_table(reasoning: str = "a banner sheet with nothing to map") -> SheetLayout:
    """The verdict behind an `unsupported_shape` entry since 12-04: the status
    carries the GATE, the layout carries the KIND (RESEARCH Pitfall 7)."""
    return SheetLayout(kind=LayoutKind.NOT_A_TABLE, confidence=0.95, reasoning=reasoning)


def test_the_sheet_question_carries_every_sheet_and_its_manifest():
    manifest = (
        _entry("Week 1", _proposal("assay-potency", {"compound_id": "Compound ID"}, 7)),
        _entry("Week 2", _proposal("assay-potency", {"compound_id": "Compound ID"}, 7)),
    )

    response = SheetQuestionResponse.from_manifest(manifest, "tok", default_schema=None)
    body = json.loads(response.model_dump_json())

    assert body["kind"] == "sheet_question"
    assert body["upload_token"] == "tok"
    assert [s["sheet_name"] for s in body["sheets"]] == ["Week 1", "Week 2"]
    first = body["sheets"][0]
    assert first["row_count"] == 8
    assert first["headers"] == ["Compound ID", "Result"]
    assert first["column_signature"] == "sig"
    assert first["status"] == "ok"
    assert first["proposed_schema"] == "assay-potency"
    assert first["tie"] is False


def test_a_proposal_shows_which_field_matched_which_header():
    """D-11-03: the coverage must be VISIBLE. A proposal carrying only a name
    and a number asks the human to approve a verdict they cannot check."""
    manifest = (
        _entry("DATA", _proposal("assay-potency", {"compound_id": "CMP", "value": "VAL"}, 7)),
    )

    body = json.loads(
        SheetQuestionResponse.from_manifest(manifest, "tok", default_schema=None).model_dump_json()
    )
    proposal = body["sheets"][0]["proposals"][0]

    assert proposal["schema_name"] == "assay-potency"
    assert proposal["matched"] == [
        {"field": "compound_id", "header": "CMP"},
        {"field": "value", "header": "VAL"},
    ]
    assert proposal["matched_count"] == 2
    assert proposal["total_fields"] == 7
    assert len(proposal["uncovered"]) == 5
    assert proposal["source"] == "crosswalk"


def test_zero_coverage_proposes_skip_and_names_no_schema():
    """D-11-06: a sheet no Schema covers is proposed as SKIP, never
    force-mapped onto the least-bad Schema. An EMPTY `proposals` list IS the
    skip signal -- there is no zero-scored candidate waiting to be mistaken
    for one."""
    manifest = (_entry("Notes", status="header_uncertain", headers=[]),)

    body = json.loads(
        SheetQuestionResponse.from_manifest(manifest, "tok", default_schema=None).model_dump_json()
    )
    sheet = body["sheets"][0]

    assert sheet["proposals"] == []
    assert sheet["proposed_schema"] is None
    assert sheet["tie"] is False
    assert sheet["status"] == "header_uncertain"
    assert sheet["headers"] == []


def test_a_tie_is_shown_as_a_tie_and_broken_by_nobody():
    manifest = (
        _entry(
            "Week 1",
            _proposal("assay-potency", {"compound_id": "Compound ID"}, 7),
            _proposal("clinical-labs", {"compound_id": "Compound ID"}, 7),
        ),
    )

    body = json.loads(
        SheetQuestionResponse.from_manifest(manifest, "tok", default_schema=None).model_dump_json()
    )
    sheet = body["sheets"][0]

    assert sheet["tie"] is True
    assert sheet["proposed_schema"] is None  # the wire NEVER breaks a tie
    assert len(sheet["proposals"]) == 2  # but both are shown, with their coverage


def test_the_upload_dropdowns_schema_never_breaks_a_tie_either():
    """D-11-16 makes the Upload Schema a DEFAULT pre-selection. A default is
    not evidence: letting a stale dropdown value settle a genuine tie would be
    exactly the silent guess D-11-06 forbids."""
    manifest = (
        _entry(
            "Week 1",
            _proposal("assay-potency", {"compound_id": "Compound ID"}, 7),
            _proposal("clinical-labs", {"compound_id": "Compound ID"}, 7),
        ),
    )

    sheets = SheetQuestionResponse.from_manifest(
        manifest, "tok", default_schema="assay-potency"
    ).sheets

    assert sheets[0].tie is True
    assert sheets[0].proposed_schema is None


def test_the_scorers_proposal_outranks_the_upload_dropdowns_schema():
    manifest = (_entry("Week 1", _proposal("pk-parameters", {"compound_id": "Compound ID"}, 7)),)

    sheets = SheetQuestionResponse.from_manifest(
        manifest, "tok", default_schema="assay-potency"
    ).sheets

    assert sheets[0].proposed_schema == "pk-parameters"


def test_the_upload_dropdowns_schema_prefills_a_sheet_the_scorer_has_no_opinion_on():
    """The middle rung of the precedence (UI-SPEC Discretion 4): the human's own
    Upload pick, which is a stated intent rather than the tool's guess. It fills
    the Select only -- the sheet is still proposed as SKIP, because that is what
    an empty `proposals` list means and the tick state reads THAT, never this."""
    manifest = (_entry("Notes", status="header_uncertain", headers=[]),)

    sheets = SheetQuestionResponse.from_manifest(
        manifest, "tok", default_schema="assay-potency"
    ).sheets

    assert sheets[0].proposals == []  # still propose skip
    assert sheets[0].proposed_schema == "assay-potency"  # but the Select is not blank


def test_a_sheet_with_no_proposals_is_never_pre_filled_by_the_upload_dropdown():
    """The Upload dropdown's Schema is a DEFAULT, and a default is only a
    pre-selection where there is something to pre-select FROM.

    An `unsupported_shape` sheet -- since 12-04, one whose retained verdict is
    `not_a_table` (or another unreadable kind) -- has no headers (`sheets.py`
    suppresses them: the shape, not the location, is the problem, so there is
    nothing to map), therefore no coverage, therefore NO proposals at all.
    Pre-filling it with `assay-potency` would name a Schema for a sheet the
    tool has just proposed to SKIP -- a confident answer where it has none,
    which is the one thing this product exists not to do."""
    manifest = (
        _entry("Summary", status="unsupported_shape", headers=[], layout=_not_a_table()),
    )

    sheets = SheetQuestionResponse.from_manifest(
        manifest, "tok", default_schema="assay-potency"
    ).sheets

    assert sheets[0].proposals == []
    assert sheets[0].proposed_schema is None
    assert sheets[0].headers == []


def test_an_unreadable_shape_is_denied_the_fallback_but_an_answerable_one_keeps_it():
    """The fallback is DENIED, not deleted -- and the line it is denied at is the
    one the parser already draws.

    `unsupported_shape` and `header_uncertain` both reach the wire with zero
    proposals, and they are NOT the same case:

      * an unreadable SHAPE is terminal. There is nothing to map and nothing the
        human can point at to make it mappable -- which is exactly what
        `table.py::_shape_unsupported_question` says when it sets
        `answerable_by_hint=False`. A Schema pre-filled there would promise a
        mapping that could never happen.
      * an uncertain HEADER ROW is a question the human CAN answer. They point at
        the header row, the sheet maps normally, and the Schema they picked on
        Upload is precisely the right pre-fill for it (D-11-16). Nothing is
        promised that cannot be delivered.

    Collapsing the two would take the D-11-16 default away from every sheet that
    merely needs its header row pointed out."""
    unreadable = _entry(
        "Summary", status="unsupported_shape", headers=[], layout=_not_a_table()
    )
    answerable = _entry("Notes", status="header_uncertain", headers=[])

    sheets = SheetQuestionResponse.from_manifest(
        (unreadable, answerable), "tok", default_schema="assay-potency"
    ).sheets

    assert sheets[0].proposals == [] and sheets[1].proposals == []
    assert sheets[0].proposed_schema is None  # nothing to go on, nothing offered
    assert sheets[1].proposed_schema == "assay-potency"  # D-11-16, untouched


def test_a_key_value_sheet_keeps_its_schema_control_and_its_label_headers():
    """The phase's point, pinned on the wire (12-05): a `key_value` sheet is
    READABLE -- `status: ok`, its LABELS as headers, and its Schema control
    intact (rung 2 of the pre-selection still applies). It is never lumped in
    with the unreadable kinds, whose treatment the two tests above pin."""
    labels = ["Patient Name", "MRN", "Accession #"]
    entry = _entry(
        "Patient Info",
        status="ok",
        headers=labels,
        layout=SheetLayout(
            kind=LayoutKind.KEY_VALUE, confidence=0.95,
            reasoning="labels down the side, values beside them",
            key_value_blocks=(KeyValueBlock(0, (1,), 1, 3),),
        ),
    )

    sheets = SheetQuestionResponse.from_manifest(
        (entry,), "tok", default_schema="assay-potency"
    ).sheets

    assert sheets[0].headers == labels  # the labels ARE the detected headers
    assert sheets[0].proposed_schema == "assay-potency"  # the Schema control is KEPT


def test_the_scorers_proposal_still_wins_for_a_sheet_that_has_coverage():
    """The fallback's precedence is otherwise unchanged: a sheet the scorer has
    an opinion about pre-fills with THAT opinion, over the Upload pick."""
    covered = _entry("Week 1", _proposal("pk-parameters", {"compound_id": "Compound ID"}, 7))

    sheets = SheetQuestionResponse.from_manifest(
        (covered,), "tok", default_schema="assay-potency"
    ).sheets

    assert sheets[0].proposed_schema == "pk-parameters"


def test_a_claude_sourced_proposal_carries_its_reason():
    manifest = (
        _entry(
            "Week 1",
            SchemaProposal(
                schema_name="assay-potency", matched={}, uncovered=("a",), total=1,
                source="claude", reason="the headers read like potency results",
            ),
        ),
    )

    body = json.loads(
        SheetQuestionResponse.from_manifest(manifest, "tok", default_schema=None).model_dump_json()
    )
    proposal = body["sheets"][0]["proposals"][0]

    assert proposal["source"] == "claude"
    assert proposal["reason"] == "the headers read like potency results"
    assert proposal["matched"] == []
    assert proposal["matched_count"] == 0


# =============================================================================
# Task 2 -- /api/upload asks the sheet question, always, for a multi-sheet workbook
# =============================================================================


def test_zephyr_with_a_schema_chosen_still_asks_which_sheets(profile_store, seeded, judging_client):
    """D-11-16, and the C-1 blocker: the browser ALWAYS sends `schema_name`
    (`Upload.tsx` blocks submit until one is picked). Gating the question on
    "no Schema" would make the entire feature unreachable from the UI."""
    client = _client(profile_store, seeded, anthropic_client=judging_client)
    response = _post_workbook(client, ZEPHYR, schema_name="assay-potency")
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "sheet_question"
    assert [s["sheet_name"] for s in body["sheets"]] == ["Week 1", "Week 2", "Week 3"]
    for sheet in body["sheets"]:
        assert sheet["headers"][0] == "Compound ID"  # the row-4 header, not the banner
        assert sheet["row_count"] == 8
        assert sheet["status"] == "ok"
        assert sheet["proposed_schema"] == "assay-potency"
        assert sheet["proposals"][0]["matched_count"] == 7


def test_meridian_shows_the_legend_sheet_parse_silently_discards_today(
    profile_store, seeded, judging_client
):
    """The sheet `_resolve_sheet` throws away without a word. D-11-24: LEGEND
    honestly scores 1/7 (its `CMP` column is a real seeded alias of
    `compound_id`) -- so it is NOT suppressed and NOT unticked by a threshold
    that does not exist. The coverage NUMBER is what tells the human it is a
    legend: 1/7 beside DATA's 7/7."""
    client = _client(profile_store, seeded, anthropic_client=judging_client)
    response = _post_workbook(client, MERIDIAN, schema_name="assay-potency")
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "sheet_question"
    by_name = {s["sheet_name"]: s for s in body["sheets"]}
    assert set(by_name) == {"DATA", "LEGEND"}

    assert by_name["DATA"]["proposals"][0]["matched_count"] == 7
    assert by_name["DATA"]["status"] == "ok"

    legend = by_name["LEGEND"]
    assert legend["status"] == "header_uncertain"
    assert legend["proposals"][0]["matched_count"] == 1
    assert legend["proposals"][0]["total_fields"] == 7
    assert legend["proposals"][0]["matched"] == [{"field": "compound_id", "header": "CMP"}]


def test_the_question_fires_even_though_rank_sheets_is_confident_here(profile_store, seeded):
    """D-11-06: ALWAYS shown. `rank_sheets` picks DATA confidently for meridian
    -- and the question is asked anyway. There is no threshold and no
    auto-apply, therefore no threshold to get wrong."""
    client = _client(profile_store, seeded)
    response = _post_workbook(client, MERIDIAN, schema_name="assay-potency")
    _clear()

    assert response.json()["kind"] == "sheet_question"


def test_orion_notes_is_described_and_marked_never_dropped(profile_store, seeded, judging_client):
    client = _client(profile_store, seeded, anthropic_client=judging_client)
    response = _post_workbook(client, ORION, schema_name="assay-potency")
    _clear()

    assert response.status_code == 200
    body = response.json()
    by_name = {s["sheet_name"]: s for s in body["sheets"]}
    assert set(by_name) == {"Summary", "Raw timepoints", "Notes"}

    notes = by_name["Notes"]
    assert notes["status"] == "header_uncertain"
    assert notes["headers"] == []
    assert notes["proposals"] == []  # no headers -> nothing to score -> propose skip


def test_a_multi_sheet_workbook_with_no_schema_at_all_asks_instead_of_422(
    profile_store, seeded, judging_client
):
    """D-11-16: `schema_name` is now genuinely optional for a multi-sheet
    workbook -- the sheet question resolves the Schema per sheet instead."""
    client = _client(profile_store, seeded, anthropic_client=judging_client)
    response = _post_workbook(client, ZEPHYR)
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "sheet_question"
    assert body["sheets"][0]["proposed_schema"] == "assay-potency"  # the scorer's own


def test_headers_still_cross_the_wire_under_headers_only(profile_store, seeded, judging_client):
    """D-10-05: a header is not a cell value. `headers_only` restricts what
    CLAUDE sees — since 12-04 that means the judge's evidence grid renders
    type buckets — never what the manifest may show the human: the manifest's
    headers still cross the wire in private mode."""
    client = _client(profile_store, seeded, anthropic_client=judging_client)
    response = _post_workbook(client, ZEPHYR, schema_name="assay-potency", headers_only="true")
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "sheet_question"
    assert body["sheets"][0]["headers"][0] == "Compound ID"


# --- the judging fixture: one shared fake, proven against the REAL chain ------
#
# A `judge_fn` fake is MECHANICALLY UNREACHABLE over HTTP: `_client()` overrides
# `get_anthropic_client -> lambda: None`, and `_judge_for(client=None,
# judge_fn=None)` short-circuits to None BEFORE any seam or monkeypatch could
# bind a judge. The only lever an API test has is a fake CLIENT at the DI seam —
# `judging_client` in conftest — whose parsed_output is a REAL instance of the
# judge's wire model, so it must survive the REAL `_to_domain_verdicts`.


def test_the_judging_client_survives_the_real_to_domain_through_the_real_chain(
    profile_store, seeded, judging_client
):
    """The fixture's self-test: through the REAL /api/upload chain — real
    judge, real wire model, real `_to_domain_verdicts` — the fake's verdicts
    become `row_per_record` manifest entries with real headers. A fake that
    only satisfied a fake would prove nothing."""
    from assayingest.api.state import registry
    from assayingest.parsing.structure.layout import LayoutKind

    client = _client(profile_store, seeded, anthropic_client=judging_client)
    response = _post_workbook(client, ZEPHYR, schema_name="assay-potency")
    token = response.json()["upload_token"]
    manifest = registry.get(token).sheet_manifest
    _clear()

    body = response.json()
    assert body["kind"] == "sheet_question"
    assert all(s["status"] == "ok" for s in body["sheets"])
    assert all(s["headers"][0] == "Compound ID" for s in body["sheets"])
    assert all(
        entry.layout is not None and entry.layout.kind is LayoutKind.ROW_PER_RECORD
        for entry in manifest
    )
    assert all(entry.layout.confidence == 1.0 for entry in manifest)


def test_no_client_really_does_mean_no_judge(profile_store, seeded):
    """The paired contract, named so a future reader can tell which behaviour
    a test is about: a test that KEEPS the `lambda: None` override gets
    all-`layout_unknown` sheets with no headers — because that IS production
    behaviour with no credentials, not a test artifact (D-12-16)."""
    client = _client(profile_store, seeded)
    response = _post_workbook(client, ZEPHYR, schema_name="assay-potency")
    _clear()

    body = response.json()
    assert body["kind"] == "sheet_question"
    assert all(s["status"] == "layout_unknown" for s in body["sheets"])
    assert all(s["headers"] == [] for s in body["sheets"])


# --- no regression: the single-sheet path is untouched ------------------------


def test_a_csv_upload_still_returns_a_mapping(monkeypatch, profile_store, seeded):
    monkeypatch.setattr(service, "propose_mapping", _mapper({"compound_id": "cmpd"}))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store, seeded)
    with open(NOVASCREEN, "rb") as fh:
        response = client.post(
            "/api/upload",
            files={"file": ("novascreen_batch01.csv", fh, "text/csv")},
            data={"schema_name": "assay-potency"},
        )
    _clear()

    assert response.status_code == 200
    assert response.json()["kind"] == "mapping"


def test_a_csv_with_no_target_still_422s_exactly_as_today(profile_store, seeded):
    client = _client(profile_store, seeded)
    with open(NOVASCREEN, "rb") as fh:
        response = client.post(
            "/api/upload", files={"file": ("novascreen_batch01.csv", fh, "text/csv")}, data={},
        )
    _clear()

    assert response.status_code == 422
    assert "schema_name" in response.json()["detail"]


def test_an_explicit_sheet_bypasses_the_question_entirely(monkeypatch, profile_store, seeded):
    """The single-sheet path includes "any upload with an explicit `sheet=`"
    (D-11-16). It must return today's arms, byte for byte."""
    monkeypatch.setattr(service, "propose_mapping", _mapper())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store, seeded)
    response = _post_workbook(client, ZEPHYR, schema_name="assay-potency", sheet="Week 2")
    _clear()

    assert response.status_code == 200
    assert response.json()["kind"] == "mapping"


def test_an_anonymous_multi_sheet_upload_is_still_401(profile_store, seeded):
    """D-10-13: the new branch sits behind the SAME gate. Closing `/api/upload`
    for a CSV but not for a workbook would be a hole, not a gate."""
    client = _anonymous_client(profile_store, seeded)
    response = _post_workbook(client, ZEPHYR, schema_name="assay-potency")
    _clear()

    assert response.status_code == 401


def test_the_sheet_question_retains_the_workbook_for_the_resolve(profile_store, seeded):
    from assayingest.api.state import registry

    client = _client(profile_store, seeded)
    token = _post_workbook(client, ZEPHYR, schema_name="assay-potency").json()["upload_token"]
    entry = registry.get(token)
    _clear()

    assert entry is not None
    assert entry.tmp_path is not None and os.path.exists(entry.tmp_path)
    assert entry.sheet_manifest is not None
    assert [e.name for e in entry.sheet_manifest] == ["Week 1", "Week 2", "Week 3"]
    assert entry.schema_name == "assay-potency"  # the human's pre-selection, retained
    assert entry.source_file_name == ZEPHYR.name


# =============================================================================
# Task 3 -- POST /api/sheets/resolve: N selected sheets become N INDEPENDENT
# datasets. Nothing is merged, ever (D-11-08).
# =============================================================================


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
    export: bool = False,
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


def _workbook(sheets: dict[str, list[list]]) -> bytes:
    """An in-memory workbook, for the two cases no in-tree fixture provides."""
    import io

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
    """BOTH sheets fail the header gate, so BOTH members are question-bearing --
    which is the only way to prove the per-member temp-file lifecycle (Pitfall
    3). No in-tree fixture has two, and a single question-bearing member cannot
    show that one member's unlink spares another's file."""
    prose = ["Vehicle: 0.5% MC. Route: PO. Species: mouse."]
    return _workbook({"Alpha": [prose], "Beta": [prose]})


def _ambiguous_date_workbook() -> bytes:
    """Two sheets whose date column is GENUINELY order-ambiguous -- every value
    has day<=12 AND month<=12, so nothing in the column disambiguates it.

    The four in-tree fixtures cannot produce a date question, and for an honest
    reason: every preset Schema DECLARES a `date_format`, and a declared format
    covers the column, so there is no ambiguity left to ask about (a
    non-conforming value goes amber instead -- fail-closed, not a question). The
    date question fires only for a date field with NO declared format, which is
    what `_undeclared_date_schema` below builds."""
    def rows(prefix: str) -> list[list]:
        header = [["compound_id", "assay_type", "value", "assay_date"]]
        return header + [
            [f"{prefix}-{100 + i}", "IC50", round(1.5 + i * 0.3, 2), f"{(i % 9) + 1:02d}/11/2025"]
            for i in range(1, 11)
        ]

    return _workbook({"One": rows("CPD"), "Two": rows("XPD")})


def _undeclared_date_schema(schema_store) -> str:
    """A governed Schema whose date field declares NO format -- so an ambiguous
    column has nothing to resolve it and must raise the date question.

    D-11-17 (a canonical field's own name is an implicit alias of itself) is what
    makes this cover 2/2 deterministically, so no Claude call is needed to reach
    the branch under test."""
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


def _resolved_unit(mapping_body: dict) -> dict:
    """The curator's own resolution of zephyr's one amber field, as the Review
    screen makes it: `Units` holds `uM` (an ASCII u), which is not one of the
    Schema's allowed values (`µM`, `nM`, `%`) -- so the human maps the field to
    the constant they know it to be, instead of a column the tool refuses to
    read as valid. This is the amber gate being ANSWERED, never bypassed."""
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


# --- N independent datasets ---------------------------------------------------


def test_selecting_every_sheet_yields_n_independent_datasets(monkeypatch, profile_store, seeded):
    """SHEET-01/D-11-08. Three sheets in, three SEPARATE datasets out -- each
    with its own upload token, its own mapping, its own gate. Nothing combines
    them, and there is no arm on which anything could."""
    monkeypatch.setattr(service, "propose_mapping", _explode_mapper)

    client = _client(profile_store, seeded)
    token = _ask(client, ZEPHYR, schema_name="assay-potency")
    response = _resolve(
        client, token,
        [("Week 1", "assay-potency"), ("Week 2", "assay-potency"), ("Week 3", "assay-potency")],
    )
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "sheet_group"
    assert body["group_id"]
    assert body["source_name"] == ZEPHYR.name
    assert [m["sheet_name"] for m in body["members"]] == ["Week 1", "Week 2", "Week 3"]

    members = _members(body)
    tokens = {m["upload_token"] for m in members.values()}
    assert len(tokens) == 3  # three DISTINCT datasets, not one table three times
    for member in members.values():
        assert member["kind"] == "mapping"
        assert member["escalation"] == {"python": 7, "claude": 0, "total": 7}


def test_the_group_response_has_no_merged_table_and_no_group_level_gate():
    """D-11-07: merging is struck from the PRODUCT. There must be no aggregate
    readiness field on the group arm for anything downstream to mistake for a
    confirm -- a group gate would either weaken or strengthen a member's amber
    gate, and both are wrong."""
    from assayingest.api.wire import SheetGroupResponse

    assert set(SheetGroupResponse.model_fields) == {
        "kind", "group_id", "source_name", "members",
    }


def test_a_member_with_an_amber_field_still_422s_at_confirm(monkeypatch, profile_store, seeded):
    """The amber gate is never weakened by membership of a group -- there is no
    group-level bypass anywhere, because there is no group-level gate at all.

    Zephyr proves it without any contrivance: its `Units` column holds `uM` (an
    ASCII u), which is not one of the Schema's allowed values (`µM`, `nM`, `%`).
    The member maps cleanly on six of seven fields and goes AMBER on the
    seventh -- and Confirm refuses it. Fail-closed, per dataset."""
    monkeypatch.setattr(service, "propose_mapping", _explode_mapper)
    field_set = _field_set_dict(seeded, "assay-potency")

    client = _client(profile_store, seeded)
    token = _ask(client, ZEPHYR, schema_name="assay-potency")
    members = _members(_resolve(client, token, [("Week 1", "assay-potency")]).json())
    response = _confirm(client, members["Week 1"], field_set, vendor="zephyr")
    _clear()

    assert members["Week 1"]["ready"] is False
    assert response.status_code == 422
    assert response.json()["detail"]["unclear_fields"] == ["unit"]


def test_each_member_confirms_on_its_own_gate_and_mints_its_own_run(
    monkeypatch, profile_store, seeded
):
    """The confirm gate is PER DATASET and never aggregated (D-11-08). Each
    member's amber field is answered on its own, each confirm passes on its own,
    and each export lands in its OWN run directory -- so nothing about one
    member's readiness can speak for another's."""
    monkeypatch.setattr(service, "propose_mapping", _explode_mapper)
    field_set = _field_set_dict(seeded, "assay-potency")

    client = _client(profile_store, seeded)
    token = _ask(client, ZEPHYR, schema_name="assay-potency")
    members = _members(
        _resolve(client, token, [("Week 1", "assay-potency"), ("Week 2", "assay-potency")]).json()
    )

    first = _confirm(
        client, members["Week 1"], field_set, vendor="zephyr", export=True,
        field_mappings=_resolved_unit(members["Week 1"]),
    )
    second = _confirm(
        client, members["Week 2"], field_set, vendor="zephyr", export=True,
        field_mappings=_resolved_unit(members["Week 2"]),
    )
    _clear()

    assert first.status_code == 200
    assert second.status_code == 200
    # Separate runs, separate export directories -- the fixed per-run filenames
    # (`export.csv`...) are only safe because each member owns its own dir.
    assert first.json()["export"]["csv_url"] != second.json()["export"]["csv_url"]


def test_confirming_one_member_leaves_the_others_pending(monkeypatch, profile_store, seeded):
    from assayingest.api.state import registry

    monkeypatch.setattr(service, "propose_mapping", _explode_mapper)
    field_set = _field_set_dict(seeded, "assay-potency")

    client = _client(profile_store, seeded)
    token = _ask(client, ZEPHYR, schema_name="assay-potency")
    members = _members(
        _resolve(client, token, [("Week 1", "assay-potency"), ("Week 2", "assay-potency")]).json()
    )
    confirmed = _confirm(
        client, members["Week 1"], field_set, vendor="zephyr",
        field_mappings=_resolved_unit(members["Week 1"]),
    )
    still_pending = registry.get(members["Week 2"]["upload_token"])
    _clear()

    assert confirmed.status_code == 200
    assert still_pending is not None  # untouched by its sibling's confirm
    assert still_pending.table is not None


def test_different_sheets_may_use_different_schemas(monkeypatch, profile_store, seeded):
    """SHEET-05: orion's `Summary` and `Raw timepoints` are not the same kind of
    table, and the human is entitled to say so. The Schema rides per selection."""
    monkeypatch.setattr(service, "propose_mapping", _mapper())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store, seeded)
    token = _ask(client, ORION, schema_name="assay-potency")
    response = _resolve(
        client, token,
        [("Summary", "assay-potency"), ("Raw timepoints", "pk-parameters")],
    )
    _clear()

    assert response.status_code == 200
    members = _members(response.json())
    summary_fields = {m["target_field"] for m in members["Summary"]["field_mappings"]}
    raw_fields = {m["target_field"] for m in members["Raw timepoints"]["field_mappings"]}
    assert summary_fields != raw_fields  # each mapped against its OWN Schema
    assert summary_fields == set(
        service.field_set_from_schema(seeded.get_schema("assay-potency")).field_names
    )
    assert raw_fields == set(
        service.field_set_from_schema(seeded.get_schema("pk-parameters")).field_names
    )


def test_selecting_only_one_sheet_is_first_class(monkeypatch, profile_store, seeded):
    """N=1 is a group of one, not a special case -- it behaves exactly like a
    normal single-dataset review."""
    monkeypatch.setattr(service, "propose_mapping", _explode_mapper)

    client = _client(profile_store, seeded)
    token = _ask(client, ZEPHYR, schema_name="assay-potency")
    response = _resolve(client, token, [("Week 2", "assay-potency")])
    _clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body["members"]) == 1
    assert body["members"][0]["response"]["kind"] == "mapping"


# --- SHEET-04: a gate-failing sheet raises ITS OWN question, never dropped -----


def test_a_gate_failing_sheet_raises_its_own_question_inside_its_member(
    monkeypatch, profile_store, seeded
):
    """SHEET-04. meridian's LEGEND fails the header gate. The human may insist
    on it anyway -- and it must then raise its OWN structural question in its
    OWN member, never be silently dropped from the group."""
    monkeypatch.setattr(service, "propose_mapping", _mapper())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store, seeded)
    token = _ask(client, MERIDIAN, schema_name="assay-potency")
    response = _resolve(
        client, token, [("DATA", "assay-potency"), ("LEGEND", "assay-potency")]
    )
    _clear()

    assert response.status_code == 200
    members = _members(response.json())
    assert set(members) == {"DATA", "LEGEND"}
    assert members["LEGEND"]["kind"] == "structural_question"
    assert members["LEGEND"]["upload_token"]


def test_one_group_carries_members_on_different_arms_at_once(monkeypatch, profile_store, seeded):
    """The recursive member arm is the point: `response` is one of the four
    EXISTING arms, so a group is honest about a member that still has a question
    while its sibling is already a mapping. meridian is exactly that -- DATA maps,
    LEGEND asks."""
    monkeypatch.setattr(service, "propose_mapping", _explode_mapper)

    client = _client(profile_store, seeded)
    token = _ask(client, MERIDIAN, schema_name="assay-potency")
    members = _members(
        _resolve(client, token, [("DATA", "assay-potency"), ("LEGEND", "assay-potency")]).json()
    )
    _clear()

    assert members["DATA"]["kind"] == "mapping"
    assert members["LEGEND"]["kind"] == "structural_question"


def test_a_declared_date_format_is_enforced_per_member_not_silently_coerced(
    monkeypatch, profile_store, seeded
):
    """meridian's DATA dates are `01-01-2025`-style, and assay-potency DECLARES
    `%Y-%m-%d`. A declared format leaves nothing to ASK about -- so this is not
    a date question, it is a VIOLATION, and the field goes amber rather than
    being coerced into whichever reading happens to parse. Fail-closed, per
    member."""
    monkeypatch.setattr(service, "propose_mapping", _explode_mapper)

    client = _client(profile_store, seeded)
    token = _ask(client, MERIDIAN, schema_name="assay-potency")
    members = _members(_resolve(client, token, [("DATA", "assay-potency")]).json())
    _clear()

    assay_date = next(
        m for m in members["DATA"]["field_mappings"] if m["target_field"] == "assay_date"
    )
    assert assay_date["needs_confirmation"] is True
    assert members["DATA"]["ready"] is False


def test_a_members_genuinely_ambiguous_date_raises_the_date_question_for_it_alone(
    monkeypatch, profile_store, schema_store
):
    """The date-question member arm (D-10-07 inside D-11-08): a date field with
    NO declared format, over a column where every value has day<=12 AND
    month<=12, has nothing to resolve it -- so THAT member raises the date
    question, and its sibling, selected in the same request, does not.

    Each sheet resolves its own column's order for itself (D-11-09): they are
    independent datasets, and a disagreement between them is not a contradiction
    to surface, because there is nothing they could contradict each other about."""
    monkeypatch.setattr(service, "propose_mapping", _explode_mapper)
    schema_name = _undeclared_date_schema(schema_store)

    client = _client(profile_store, schema_store)
    token = _ask(client, _ambiguous_date_workbook(), schema_name=schema_name)
    body = _resolve(client, token, [("One", schema_name), ("Two", schema_name)]).json()
    members = _members(body)
    _clear()

    assert members["One"]["kind"] == "date_question"
    assert members["Two"]["kind"] == "date_question"
    assert members["One"]["upload_token"] != members["Two"]["upload_token"]
    assert [c["target_field"] for c in members["One"]["columns"]] == ["assay_date"]


def test_answering_one_members_date_question_completes_that_member_only(
    monkeypatch, profile_store, schema_store
):
    monkeypatch.setattr(service, "propose_mapping", _explode_mapper)
    from assayingest.api.state import registry

    schema_name = _undeclared_date_schema(schema_store)

    client = _client(profile_store, schema_store)
    token = _ask(client, _ambiguous_date_workbook(), schema_name=schema_name)
    members = _members(_resolve(client, token, [("One", schema_name), ("Two", schema_name)]).json())

    resolved = client.post(
        "/api/date-format/resolve",
        json={
            "upload_token": members["One"]["upload_token"],
            "choices": [{"target_field": "assay_date", "order": "day_first"}],
        },
    )
    sibling = registry.get(members["Two"]["upload_token"])
    _clear()

    assert resolved.status_code == 200
    assert resolved.json()["kind"] == "mapping"
    assert sibling is not None  # still awaiting its OWN answer
    assert sibling.proposal is not None


# --- Pitfall 3: one file, N lifecycles ----------------------------------------


def test_two_question_bearing_members_own_distinct_temp_files(profile_store, seeded):
    """Pitfall 3/T-11-24: with N members sharing ONE temp path, the first
    member's resolve (which unlinks on success AND on every error branch) would
    delete the file out from under the others. Each question-bearing member gets
    its OWN copy, so every existing unlink and the registry's own eviction-unlink
    stay correct with ZERO changes."""
    from assayingest.api.state import registry

    client = _client(profile_store, seeded)
    token = _ask(client, _two_question_workbook(), schema_name="assay-potency")
    members = _members(
        _resolve(client, token, [("Alpha", "assay-potency"), ("Beta", "assay-potency")]).json()
    )
    alpha = registry.get(members["Alpha"]["upload_token"])
    beta = registry.get(members["Beta"]["upload_token"])
    _clear()

    assert members["Alpha"]["kind"] == "structural_question"
    assert members["Beta"]["kind"] == "structural_question"
    assert alpha.tmp_path is not None and beta.tmp_path is not None
    assert alpha.tmp_path != beta.tmp_path
    assert os.path.exists(alpha.tmp_path)
    assert os.path.exists(beta.tmp_path)


def test_resolving_one_members_hint_leaves_the_other_members_file_intact(
    monkeypatch, profile_store, seeded
):
    monkeypatch.setattr(service, "propose_mapping", _mapper())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from assayingest.api.state import registry

    client = _client(profile_store, seeded)
    token = _ask(client, _two_question_workbook(), schema_name="assay-potency")
    members = _members(
        _resolve(client, token, [("Alpha", "assay-potency"), ("Beta", "assay-potency")]).json()
    )
    beta_path = registry.get(members["Beta"]["upload_token"]).tmp_path

    client.post(
        "/api/structural-hint/resolve",
        json={
            "upload_token": members["Alpha"]["upload_token"],
            "hint": {"header_row_index": 0},
        },
    )
    _clear()

    # Alpha's resolve unlinked Alpha's OWN copy. Beta's file is untouched and
    # Beta is still resolvable -- which is the whole point of the per-member copy.
    assert os.path.exists(beta_path)


def test_the_original_workbook_leaves_disk_once_every_member_is_parsed(
    monkeypatch, profile_store, seeded
):
    from assayingest.api.state import registry

    monkeypatch.setattr(service, "propose_mapping", _explode_mapper)

    client = _client(profile_store, seeded)
    token = _ask(client, ZEPHYR, schema_name="assay-potency")
    original = registry.get(token).tmp_path
    _resolve(client, token, [("Week 1", "assay-potency")])
    _clear()

    assert not os.path.exists(original)
    assert registry.get(token) is None  # the sheet-question entry is popped


# --- untrusted input (T-11-22) and the auth gate (T-11-23) --------------------


def test_a_sheet_name_not_in_the_manifest_is_422_naming_the_consequence(profile_store, seeded):
    """Pitfall 6/T-11-22: a client-supplied `sheet_name` reaches `parse()`,
    which raises `ValueError` for an unknown sheet -- and the generic catch
    would map that to a 500, reporting a client input error as a server error.
    Validate against the SERVER-RETAINED manifest first."""
    client = _client(profile_store, seeded)
    token = _ask(client, ZEPHYR, schema_name="assay-potency")
    response = _resolve(client, token, [("Week 9", "assay-potency")])
    _clear()

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "Week 9" in detail
    assert "nothing was ingested" in detail.lower()


def test_an_unknown_schema_name_is_404(profile_store, seeded):
    client = _client(profile_store, seeded)
    token = _ask(client, ZEPHYR, schema_name="assay-potency")
    response = _resolve(client, token, [("Week 1", "does-not-exist")])
    _clear()

    assert response.status_code == 404


def test_an_empty_selections_list_is_422_fail_closed(profile_store, seeded):
    """Nothing would be ingested. A request that ingests nothing is a mistake
    worth naming, never a success worth returning."""
    client = _client(profile_store, seeded)
    token = _ask(client, ZEPHYR, schema_name="assay-potency")
    response = _resolve(client, token, [])
    _clear()

    assert response.status_code == 422


def test_a_rejected_selection_never_touches_the_filesystem(profile_store, seeded):
    """Validate-before-filesystem: an unknown sheet name must be refused BEFORE
    any per-member copy is made, so a bad request leaves no temp files behind."""
    from assayingest.api.state import registry

    client = _client(profile_store, seeded)
    token = _ask(client, ZEPHYR, schema_name="assay-potency")
    original = registry.get(token).tmp_path
    _resolve(client, token, [("Week 1", "assay-potency"), ("Week 9", "assay-potency")])
    _clear()

    assert not os.path.exists(original)  # the retained file is cleaned up, not leaked


def test_an_unknown_upload_token_is_404(profile_store, seeded):
    client = _client(profile_store, seeded)
    response = _resolve(client, "no-such-token", [("Week 1", "assay-potency")])
    _clear()

    assert response.status_code == 404


def test_a_token_that_carries_no_sheet_manifest_is_404(monkeypatch, profile_store, seeded):
    """A token from an ORDINARY upload is not a sheet question, and the resolve
    route must say so rather than reach for a manifest that was never built."""
    monkeypatch.setattr(service, "propose_mapping", _mapper({"compound_id": "cmpd"}))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    client = _client(profile_store, seeded)
    with open(NOVASCREEN, "rb") as fh:
        token = client.post(
            "/api/upload",
            files={"file": ("novascreen_batch01.csv", fh, "text/csv")},
            data={"schema_name": "assay-potency"},
        ).json()["upload_token"]
    response = _resolve(client, token, [("Week 1", "assay-potency")])
    _clear()

    assert response.status_code == 404


def test_an_anonymous_sheets_resolve_is_401(profile_store, seeded):
    """D-10-13/T-11-23: closing `/api/upload` alone would leave the
    CONTINUATION open -- a signed-out client must not be able to drive a
    retained upload to completion here either."""
    client = _client(profile_store, seeded)
    token = _ask(client, ZEPHYR, schema_name="assay-potency")
    _clear()

    anonymous = _anonymous_client(profile_store, seeded)
    response = _resolve(anonymous, token, [("Week 1", "assay-potency")])
    _clear()

    assert response.status_code == 401


# --- the group index ----------------------------------------------------------


def test_the_group_indexes_every_member_by_its_sheet_name(monkeypatch, profile_store, seeded):
    from assayingest.api.state import groups

    monkeypatch.setattr(service, "propose_mapping", _explode_mapper)

    client = _client(profile_store, seeded)
    token = _ask(client, ZEPHYR, schema_name="assay-potency")
    body = _resolve(
        client, token, [("Week 1", "assay-potency"), ("Week 3", "assay-potency")]
    ).json()
    _clear()

    group = groups.get(body["group_id"])
    assert group is not None
    assert set(group.members) == {"Week 1", "Week 3"}
    assert group.source_file_name == ZEPHYR.name
    assert group.runs == {}  # filled at confirm, by plan 11-08


def test_every_member_entry_knows_which_group_and_which_sheet_it_is(
    monkeypatch, profile_store, seeded
):
    """The member entry -- not the group's token map -- is what carries the
    membership forward: a member that resolves a structural or date question is
    re-put under a FRESH token, so `group_id`/`sheet` on the entry are what
    survive that hop."""
    from assayingest.api.state import registry

    monkeypatch.setattr(service, "propose_mapping", _explode_mapper)

    client = _client(profile_store, seeded)
    token = _ask(client, ZEPHYR, schema_name="assay-potency")
    body = _resolve(client, token, [("Week 2", "assay-potency")]).json()
    entry = registry.get(_members(body)["Week 2"]["upload_token"])
    _clear()

    assert entry.group_id == body["group_id"]
    assert entry.sheet == "Week 2"
    assert entry.schema_name == "assay-potency"


# =============================================================================
# 12-05 -- the verdict reaches resolve time: it rides the retained manifest
# (zero extra Claude calls), UNKNOWN attaches (never dropped to None), the
# key-value blocks survive the handoff, and ask_layout is the disagree path.
# =============================================================================


class _RecordingNeverClient:
    """A DI client that records (and refuses) every Claude call -- the HTTP
    sibling of the service-level recording judge. Recording matters more than
    raising: the availability boundaries swallow a raising judge, so only
    `calls == []` is a real zero-calls proof."""

    def __init__(self):
        self.calls: list[dict] = []
        outer = self

        class _Messages:
            def parse(self, **kwargs):
                outer.calls.append(kwargs)
                raise AssertionError(
                    "no Claude call may happen while resolving ticked sheets: "
                    "the verdict rides the retained manifest (D-12-02/D-12-14)"
                )

        self.messages = _Messages()


def test_resolving_ticked_sheets_makes_no_claude_call_at_all(
    monkeypatch, profile_store, seeded, judging_client
):
    """The zero-extra-calls truth at the HTTP boundary: the judge ran ONCE at
    upload (the judging_client fake); resolving the ticked sheets afterwards
    touches no Claude client of any kind -- the verdicts ride the retained
    SheetManifestEntry.layout. NOTE: passes by design at RED -- it pins the
    invariant the 12-05 seam must preserve (the 12-03 verdict-less-invariant
    precedent)."""
    monkeypatch.setattr(service, "propose_mapping", _explode_mapper)

    client = _client(profile_store, seeded, anthropic_client=judging_client)
    token = _ask(client, ZEPHYR, schema_name="assay-potency")
    _clear()

    recorder = _RecordingNeverClient()
    client = _client(profile_store, seeded, anthropic_client=recorder)
    response = _resolve(
        client, token,
        [("Week 1", "assay-potency"), ("Week 2", "assay-potency"), ("Week 3", "assay-potency")],
    )
    _clear()

    assert response.status_code == 200
    assert all(m["kind"] == "mapping" for m in _members(response.json()).values())
    assert recorder.calls == []


def test_an_unknown_verdict_attaches_and_the_member_question_says_why(
    monkeypatch, profile_store, seeded
):
    """UNKNOWN ATTACHES: with no judge (the honest no-client manifest), the
    retained layout_unknown verdict rides the member's layout question -- it
    is never dropped to a bare None that silently means 'ask'. The question
    carries the verdict's reasoning, so the human is told WHY they are being
    asked (post-Wave-C both routes end at the same question, but only the
    attached verdict can say why)."""
    monkeypatch.setattr(service, "propose_mapping", _explode_mapper)

    client = _client(profile_store, seeded)  # None client: no judge, all unknown
    token = _ask(client, ZEPHYR, schema_name="assay-potency")
    members = _members(_resolve(client, token, [("Week 1", "assay-potency")]).json())
    _clear()

    question = members["Week 1"]
    assert question["kind"] == "structural_question"
    assert question["answerable_by_hint"] is True
    layout = question["proposal"]["layout"]
    assert layout["kind"] == "unknown"
    assert layout["reasoning"]  # the WHY rides the question, never a bare None
    assert layout["reasoning"] in question["reason"]


def test_the_key_value_blocks_survive_the_manifest_handoff(profile_store, seeded):
    """THE BLOCKS SURVIVE (SHAPE-02's multi-sheet lifeline): ticking the
    cascade `Patient Info` sheet yields a StructureQuestion whose
    proposal.layout carries the D-12-13 key_value_blocks with their REAL
    label/value column indices. Those blocks are the un-pivot's ONLY input --
    if they are dropped anywhere along entry.layout -> hint -> dispatch, the
    panel can never offer 'Labels down the side' and round trip A starves,
    silently, with every other test still green."""
    from assayingest.api.state import UploadEntry, registry

    blocks = (KeyValueBlock(0, (1,), 1, 10), KeyValueBlock(3, (4,), 1, 10))
    verdict = SheetLayout(
        kind=LayoutKind.KEY_VALUE, confidence=0.96,
        reasoning="labels down the side, two blocks, one record",
        key_value_blocks=blocks,
    )

    def _cascade_judge(grids, *, headers_only):
        return {"Patient Info": verdict}  # every other sheet UNKNOWN-fills

    manifest = service.describe_workbook(CASCADE, [], store=None, judge_fn=_cascade_judge)
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_copy = tmp.name
    shutil.copyfile(CASCADE, tmp_copy)
    token = registry.put(
        UploadEntry(
            field_set=None, headers_only=False, tmp_path=tmp_copy,
            sheet_manifest=manifest, source_file_name=CASCADE.name,
        )
    )

    client = _client(profile_store, seeded)
    response = _resolve(client, token, [("Patient Info", "assay-potency")])
    _clear()

    assert response.status_code == 200
    question = _members(response.json())["Patient Info"]
    assert question["kind"] == "structural_question"
    assert question["answerable_by_hint"] is True
    layout = question["proposal"]["layout"]
    assert layout["kind"] == "key_value"
    assert layout["key_value_blocks"] == [
        {"label_column": 0, "value_columns": [1], "first_row": 1, "last_row": 10},
        {"label_column": 3, "value_columns": [4], "first_row": 1, "last_row": 10},
    ]


def test_ask_layout_routes_the_member_to_the_one_answer_surface(
    monkeypatch, profile_store, seeded, judging_client
):
    """The disagree path (12-UI-SPEC Discretion 2): ask_layout=true on a
    selection means that member does NOT apply the retained verdict -- it gets
    the layout StructureQuestion (proposal = Claude's read, so the panel can
    render it) in its Review tab, while its sibling maps normally. The loop
    then CLOSES on the one answer surface: answering 'one row per record'
    with the real header row ends in a mapped dataset, not the same question."""
    monkeypatch.setattr(service, "propose_mapping", _explode_mapper)

    client = _client(profile_store, seeded, anthropic_client=judging_client)
    token = _ask(client, ZEPHYR, schema_name="assay-potency")
    response = client.post(
        "/api/sheets/resolve",
        json={
            "upload_token": token,
            "selections": [
                {"sheet_name": "Week 1", "schema_name": "assay-potency", "ask_layout": True},
                {"sheet_name": "Week 2", "schema_name": "assay-potency"},
            ],
        },
    )
    members = _members(response.json())

    assert members["Week 2"]["kind"] == "mapping"
    week_one = members["Week 1"]
    assert week_one["kind"] == "structural_question"
    assert week_one["answerable_by_hint"] is True
    assert week_one["proposal"]["layout"]["kind"] == "row_per_record"

    answered = client.post(
        "/api/structural-hint/resolve",
        json={"upload_token": week_one["upload_token"], "hint": {"header_row_index": 3}},
    )
    _clear()

    assert answered.status_code == 200
    assert answered.json()["kind"] == "mapping"  # the disagree loop terminates
