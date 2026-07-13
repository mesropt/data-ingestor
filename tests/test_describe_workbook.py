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

from pathlib import Path

import pytest

from assayingest import service
from assayingest.learning.seed import seed_schema_aliases, seed_schemas
from assayingest.learning.signature import column_signature
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
