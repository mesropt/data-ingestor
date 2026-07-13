"""`service.describe_workbook` — the whole sheet manifest, assembled ABOVE
`parse()` (SHEET-01/04/05, D-11-21).

One call, before a single sheet is parsed, yields everything the sheet-selection
screen needs: every real worksheet, its resolved headers, its data-row count,
its column signature, the structural gate it passes or fails, and the ranked
Schema proposals for it — each carrying the coverage that produced it.

It sits ABOVE `parse()` and calls nothing inside it: `parse()` already
short-circuits sheet ranking when handed an explicit `sheet=`, so the flow is
describe → ask the human → `parse(path, sheet=X)` once per selected sheet.
`parse`, `_resolve_sheet`, `rank_sheets` and `SheetRanking` are therefore not
touched at all by this phase, and every existing parsing test stays green.

`column_signature` is computed HERE, in the service layer, and never inside the
parser — which is what keeps `parsing/` free of any import from `learning/`
(CLAUDE.md: dependencies point toward the domain).

The four synthetic workbooks ARE the acceptance test (11-CONTEXT.md):

  * zephyr — 3 data sheets, headers on row 4 under a banner. The
    N-independent-datasets case.
  * meridian — DATA + LEGEND. The "one sheet is not data at all" case: LEGEND
    is SHOWN, never silently discarded the way `parse()` discards it today.
  * orion — Summary / Raw timepoints / Notes. The header-uncertain case: Notes
    resolves no header at all and must be described, not dropped and not
    crashed on.
  * delta — one sheet per target, a different header spelling on each.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from assayingest import service
from assayingest.learning.seed import seed_schema_aliases, seed_schemas
from assayingest.learning.signature import column_signature
from assayingest.parsing.structure.layout import LayoutKind, SheetLayout
from assayingest.parsing.structure.sheets import SheetStatus

_FIXTURES = Path(__file__).resolve().parent.parent / "data" / "synthetic"


@pytest.fixture(autouse=True)
def _no_claude(monkeypatch):
    """AUTOUSE: the manifest is pure Python. Claude is D-11-19's third stage
    and belongs to plan 11-05 — no call may escape from this one."""

    def _explode(*_args, **_kwargs):
        raise AssertionError("propose_mapping must NOT be called: describe_workbook is pure Python")

    monkeypatch.setattr(service, "propose_mapping", _explode)


@pytest.fixture
def seeded_schemas(schema_store):
    seed_schemas(schema_store)
    seed_schema_aliases(schema_store)
    return schema_store.list_schemas()


def _by_name(entries) -> dict[str, service.SheetManifestEntry]:
    return {entry.name: entry for entry in entries}


def _describe(fixture: str, schemas, **kwargs):
    return service.describe_workbook(_FIXTURES / fixture, schemas, **kwargs)


# --- every sheet is described, and none is dropped -------------------------


def test_zephyr_yields_one_entry_per_sheet_in_workbook_order(seeded_schemas):
    entries = _describe("zephyr_bio_ZB-2025.xlsx", seeded_schemas)

    assert [entry.name for entry in entries] == ["Week 1", "Week 2", "Week 3"]


def test_zephyr_reads_the_resolved_header_row_not_the_banner(seeded_schemas):
    """The headers sit on row 4, under a three-line study banner. A manifest
    showing the banner would ask the human to choose a Schema for columns that
    do not exist."""
    week_one = _by_name(_describe("zephyr_bio_ZB-2025.xlsx", seeded_schemas))["Week 1"]

    assert week_one.headers == [
        "Compound ID", "Assay", "Result", "Units", "Protein Target", "Replicates", "Run Date",
    ]
    assert week_one.status == SheetStatus.OK.value
    assert week_one.row_count == 8


def test_zephyr_every_sheet_carries_a_ranked_proposal_with_visible_coverage(seeded_schemas):
    """The money shot of the phase: three sheets, each fully covered by the
    starter crosswalk seeded in plan 11-02, with zero Claude calls."""
    for entry in _describe("zephyr_bio_ZB-2025.xlsx", seeded_schemas):
        best = entry.proposals[0]
        assert best.schema_name == "assay-potency"
        assert best.score == 1.0
        assert best.matched["compound_id"] == "Compound ID"
        assert best.uncovered == ()


def test_every_entry_carries_the_column_signature_of_its_own_headers(seeded_schemas):
    """The key the learned-profile lookup needs, computed per SHEET — never per
    workbook. Two sheets with different columns must never share a signature."""
    entries = _by_name(_describe("orion_pk_report.xlsx", seeded_schemas))

    assert entries["Summary"].column_signature == column_signature(entries["Summary"].headers)
    assert entries["Summary"].column_signature != entries["Raw timepoints"].column_signature


# --- meridian: LEGEND is SHOWN, not silently discarded ---------------------


def test_meridian_shows_the_legend_sheet_that_parse_discards_today(seeded_schemas):
    entries = _by_name(_describe("meridian_cro_codes.xlsx", seeded_schemas))

    assert set(entries) == {"DATA", "LEGEND"}
    assert entries["DATA"].status == SheetStatus.OK.value
    assert entries["LEGEND"].status == SheetStatus.HEADER_UNCERTAIN.value


def test_meridian_data_is_fully_covered_and_legend_is_not(seeded_schemas):
    """LEGEND is a code table. Its one incidental hit (`CMP` is a real starter
    spelling for `compound_id`) is reported honestly as 1/7 rather than
    suppressed — but nothing about it is auto-applied, and the human sees both
    numbers side by side and decides."""
    entries = _by_name(_describe("meridian_cro_codes.xlsx", seeded_schemas))

    data = entries["DATA"].proposals[0]
    legend = entries["LEGEND"].proposals[0]
    assert data.schema_name == "assay-potency"
    assert data.score == 1.0
    assert legend.score == pytest.approx(1 / 7)
    assert legend.score < data.score


# --- orion: a sheet with no resolvable header proposes SKIP ----------------


def test_orion_describes_all_three_sheets_including_notes(seeded_schemas):
    entries = _by_name(_describe("orion_pk_report.xlsx", seeded_schemas))

    assert set(entries) == {"Summary", "Raw timepoints", "Notes"}


def test_orion_notes_has_no_headers_and_therefore_no_proposal(seeded_schemas):
    """No header could be resolved, so there is nothing to score. The honest
    answer is NO proposal — propose skip — never the least-bad Schema
    (D-11-06)."""
    notes = _by_name(_describe("orion_pk_report.xlsx", seeded_schemas))["Notes"]

    assert notes.headers == []
    assert notes.status == SheetStatus.HEADER_UNCERTAIN.value
    assert notes.proposals == ()


def test_orion_two_data_sheets_are_scored_independently_of_each_other(seeded_schemas):
    """Summary and Raw timepoints are two independent datasets, not two views of
    one (D-11-08). Each is scored on its OWN headers: Summary covers six of
    assay-potency's seven fields, Raw timepoints only two — one workbook, two
    genuinely different answers."""
    entries = _by_name(_describe("orion_pk_report.xlsx", seeded_schemas))

    summary = entries["Summary"].proposals[0]
    raw = entries["Raw timepoints"].proposals[0]
    assert summary.matched != raw.matched
    assert summary.score > raw.score
    assert "compound_id" in summary.matched and "compound_id" in raw.matched


def test_delta_each_panel_proposes_from_its_own_header_spelling(seeded_schemas):
    """Three sheets, three different spellings of the same four columns — each
    resolves to the same canonical fields through the crosswalk."""
    entries = _describe("delta_screening_per_target.xlsx", seeded_schemas)

    assert [entry.name for entry in entries] == ["EGFR panel", "JAK2 panel", "BRAF panel"]
    for entry in entries:
        best = entry.proposals[0]
        assert best.schema_name == "assay-potency"
        assert set(best.matched) == {"compound_id", "value", "n_replicates", "assay_date"}


# --- headers only, no LLM, no cell value (D-11-04, D-11-19) ----------------


def test_the_manifest_has_no_headers_only_parameter_because_it_reads_no_values(seeded_schemas):
    """`headers_only` restricts what is sent to Claude. `describe_workbook`
    sends nothing to Claude and reads no cell value, so there is no mode for it
    to have: the manifest is a pure function of the file's STRUCTURE, identical
    either way (D-11-04)."""
    import inspect

    parameters = inspect.signature(service.describe_workbook).parameters

    assert "headers_only" not in parameters


def test_no_claude_is_reached_when_a_proposal_exists(seeded_schemas):
    """D-11-19's ladder, pinned: the deterministic stages run FIRST, and the
    LLM seam is never touched for a sheet Python already resolved. `rank_fn`
    explodes if called; describing four covered sheets without tripping it IS
    the proof."""

    def _explode_rank(*_args, **_kwargs):
        raise AssertionError("rank_fn must NOT be called: the crosswalk already covers these sheets")

    entries = _describe("zephyr_bio_ZB-2025.xlsx", seeded_schemas, rank_fn=_explode_rank)

    assert all(entry.proposals for entry in entries)


def test_the_client_and_rank_fn_seams_exist_now_for_plans_11_05_and_11_07(seeded_schemas):
    """Accepted NOW and unused NOW, deliberately: plan 11-05 fills the Claude
    stage behind them and plan 11-07 threads the client through from the route.
    Declaring them here means neither plan changes this signature later."""
    import inspect

    parameters = inspect.signature(service.describe_workbook).parameters

    assert parameters["client"].default is None
    assert parameters["rank_fn"].default is None
    assert parameters["store"].default is None


def test_a_workbook_can_be_described_with_no_schemas_at_all(schema_store):
    """An empty store is not an error: every sheet is still described, and
    every one of them honestly proposes nothing."""
    entries = _describe("meridian_cro_codes.xlsx", [])

    assert {entry.name for entry in entries} == {"DATA", "LEGEND"}
    assert all(entry.proposals == () for entry in entries)


# --- stage 3 is PER SHEET, never per workbook (D-11-19, plan 11-05) --------
#
# A workbook is not a unit of escalation. One sheet the crosswalk resolves and
# one it does not must cost exactly ONE call — for the second sheet only.


@pytest.fixture
def mixed_workbook(tmp_path):
    """One sheet the seeded crosswalk fully covers, one it covers not at all.
    Built here rather than added to `data/synthetic/` because it exists to probe
    the escalation boundary, not to demo the product."""
    from openpyxl import Workbook

    workbook = Workbook()
    covered = workbook.active
    covered.title = "Run log"
    covered.append(["Compound ID", "Assay", "Result", "Units", "Protein Target", "Replicates", "Run Date"])
    for index in range(5):
        covered.append([f"CPD-{index}", "IC50", "12.5", "nM", "EGFR", "3", "2026-01-01"])

    uncovered = workbook.create_sheet("Logistics")
    uncovered.append(["timepoint", "aliquot barcode", "freezer shelf ref"])
    for index in range(5):
        uncovered.append(["T0", f"BC-{index}", "S3"])

    path = tmp_path / "mixed.xlsx"
    workbook.save(path)
    return path


def _ranker(result):
    calls: list[dict] = []

    def _fn(headers, schemas, *, sheet_name=None):
        calls.append({"headers": headers, "sheet_name": sheet_name})
        return result

    return _fn, calls


def test_only_the_coverage_less_sheet_reaches_claude(seeded_schemas, mixed_workbook):
    """The proof that the LLM spend is scoped to what Python could not resolve:
    two sheets, one call, and it is for the right one."""
    from assayingest.mapping.schema_ranker import RankedSchema

    rank_fn, calls = _ranker((RankedSchema(schema_name="assay-potency", reason="a guess worth checking", rank=1),))

    entries = _by_name(service.describe_workbook(mixed_workbook, seeded_schemas, rank_fn=rank_fn))

    assert len(calls) == 1
    assert calls[0]["sheet_name"] == "Logistics"
    assert calls[0]["headers"] == ["timepoint", "aliquot barcode", "freezer shelf ref"]
    assert entries["Run log"].proposals[0].source == "crosswalk"
    assert entries["Logistics"].proposals[0].source == "claude"
    assert entries["Logistics"].proposals[0].reason == "a guess worth checking"


def test_a_failing_ranker_never_breaks_the_manifest(seeded_schemas, mixed_workbook):
    """T-11-16: an LLM outage degrades the coverage-less sheet to "propose skip"
    and leaves every other sheet — and the manifest itself — untouched."""

    def _api_error(*_args, **_kwargs):
        raise RuntimeError("the API is down")

    entries = _by_name(service.describe_workbook(mixed_workbook, seeded_schemas, rank_fn=_api_error))

    assert entries["Logistics"].proposals == ()
    assert entries["Run log"].proposals[0].score == 1.0


def test_with_no_client_at_all_the_manifest_still_builds(seeded_schemas, mixed_workbook):
    """A missing API key must never break the sheet question (the success
    criterion of this plan, stated literally)."""
    entries = _by_name(service.describe_workbook(mixed_workbook, seeded_schemas))

    assert entries["Logistics"].proposals == ()
    assert entries["Run log"].proposals[0].score == 1.0


# --- the layout judge's seams: _judge_for / _judge_or_unknown (12-04) --------
#
# The seam mirrors `_ranker_for`/`_rank_or_none`, and the availability boundary
# is the CALLER's: `judge_workbook_layout` raises and never logs (12-02's
# recorded contract), so `_judge_or_unknown` owns the broad except. The two
# boundaries look identical and are NOT (D-12-16): a ranker failure costs a
# SUGGESTION (the human picks a Schema themselves); a judge failure costs a
# QUESTION (the human is asked about every sheet's layout). Neither guesses.


def _verdict(kind: LayoutKind = LayoutKind.ROW_PER_RECORD, **kwargs) -> SheetLayout:
    return SheetLayout(kind=kind, confidence=1.0, reasoning="test verdict", **kwargs)


def test_judge_for_prefers_the_injected_judge_fn():
    """The injected seam wins, exactly as `rank_fn` does for the ranker — a
    test's fake must never be silently bypassed by a real client."""

    def _sentinel(grids, *, headers_only):
        return {}

    assert service._judge_for(object(), _sentinel) is _sentinel


def test_judge_for_with_no_client_is_none_a_legitimate_answer():
    """`None` is an answer, not an error: without credentials there is no
    judge, and every sheet honestly asks about its layout (D-12-16)."""
    assert service._judge_for(None, None) is None


def test_judge_for_binds_the_real_judge_to_the_callers_client(monkeypatch):
    captured: dict = {}

    def _fake_judge(grids, client=None, *, headers_only):
        captured.update(grids=grids, client=client, headers_only=headers_only)
        return {"S": _verdict()}

    monkeypatch.setattr(service, "judge_workbook_layout", _fake_judge)
    marker = object()

    judge = service._judge_for(marker, None)
    result = judge({"S": [("a",)]}, headers_only=True)

    assert captured["client"] is marker
    assert captured["headers_only"] is True
    assert result == {"S": _verdict()}


def test_judge_or_unknown_with_no_judge_degrades_every_sheet_to_unknown():
    verdicts = service._judge_or_unknown(
        None, {"A": [], "B": []}, headers_only=False, sheet_names=["A", "B"]
    )

    assert set(verdicts) == {"A", "B"}
    assert all(v.kind is LayoutKind.UNKNOWN for v in verdicts.values())
    assert all(v.confidence == 0.0 for v in verdicts.values())


def test_judge_or_unknown_swallows_any_judge_failure_logged_once_never_raised(caplog):
    """The availability boundary: EVERY way the remote call can fail lands on
    the same safe answer — all sheets UNKNOWN, logged exactly once with the
    traceback, never logged AND raised. The warning names the consequence,
    not the symptom."""

    def _api_down(grids, *, headers_only):
        raise RuntimeError("the API is down")

    with caplog.at_level(logging.WARNING, logger="assayingest.service"):
        verdicts = service._judge_or_unknown(
            _api_down, {"A": [], "B": []}, headers_only=False, sheet_names=["A", "B"]
        )

    assert all(v.kind is LayoutKind.UNKNOWN for v in verdicts.values())
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].exc_info is not None
    assert "ask about its layout" in warnings[0].getMessage()


def test_judge_or_unknown_passes_a_recorder_judges_verdicts_through(monkeypatch):
    """A working judge's verdicts arrive untouched — and a sheet it omitted is
    UNKNOWN-filled here too, a second closure behind 12-02's own fill."""
    verdict = _verdict()
    calls: list[dict] = []

    def _judge(grids, *, headers_only):
        calls.append({"grids": grids, "headers_only": headers_only})
        return {"A": verdict}

    verdicts = service._judge_or_unknown(
        _judge, {"A": [("x",)], "B": [("y",)]}, headers_only=True, sheet_names=["A", "B"]
    )

    assert len(calls) == 1
    assert calls[0]["headers_only"] is True
    assert verdicts["A"] is verdict
    assert verdicts["B"].kind is LayoutKind.UNKNOWN
    assert verdicts["B"].confidence == 0.0
