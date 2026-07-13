"""ROADMAP Phase 12 Success Criterion 5, as a RUNNABLE test rather than a claim:

    "Every existing row-per-record file in data/synthetic/ still ingests
     exactly as it does today — removing the Python classifier regresses
     nothing."

SC5 is a claim about EVERY file, so a single-workbook assertion does not
discharge it. This module sweeps every worksheet in `data/synthetic/` and
asserts, under a confident `row_per_record` judge, that each one parses to a
`RawTable` whose headers and row count are IDENTICAL to the ones it produced
BEFORE this phase touched the parse path.

THE BASELINE WAS CAPTURED ON PRE-CHANGE CODE, and that is the whole point. A
parity test written after the change can only prove that the code agrees with
itself. `_BASELINE` below was produced by running today's `parse()` against
every worksheet at commit `465e135` (2026-07-13) — the last commit before
12-09's promotion rule and the CLI judge landed, and, more importantly, while
`parsing/structure/shape.py`'s heuristic classifier was still the thing doing
the reading. Wave C (12-07) deletes that classifier. If any of these numbers
move afterwards, that is a REGRESSION and the phase stops — it is NOT a
baseline to update.

Capture method (reproducible):

    for each .xlsx in data/synthetic/, for each worksheet list_worksheets yields:
        outcome = parse(path, sheet=name)          # no hint, no verdict
        record (headers, row_count) when it is a RawTable

Offline: the verdict is supplied by a judge FAKE in `judge_workbook_layout`'s
exact shape, and driven through the REAL production chain
(`service._judge_target_sheet` → `service._apply_null_hypothesis` → `parse`) —
so the sweep exercises the same code a credentialed run does, and makes no
network call. Part of the default suite: SC5 is a standing regression guard,
not a one-off check someone ran once and wrote a paragraph about.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from assayingest import service
from assayingest.parsing.hint import StructureQuestion
from assayingest.parsing.structure.grid import list_worksheets
from assayingest.parsing.structure.layout import LayoutKind, SheetLayout
from assayingest.parsing.table import RawTable, parse

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"


# --- The baseline: today's truth, captured before the change (commit 465e135) -----
#
# (file, sheet, header_row_index, row_count, headers)
#
# `header_row_index` is the row TODAY'S detector resolves for that sheet — it is
# what a real judge naming the header row would have to agree with for parity to
# hold, so it is pinned here alongside the output it produces.

_BASELINE: list[tuple[str, str, int, int, list[str]]] = [
    ("cascade_assays_nounit.xlsx", "Sheet1", 0, 12,
     ["cmpd", "potency", "", "target_gene", "#", "run"]),
    ("castlebio_native_dates.xlsx", "Results", 0, 10,
     ["Compound", "Assay", "Result", "Unit", "Target", "Replicates", "Tested On"]),
    ("delta_screening_per_target.xlsx", "EGFR panel", 0, 9,
     ["Compound", "IC50 (nM)", "Reps", "Date"]),
    ("delta_screening_per_target.xlsx", "JAK2 panel", 0, 9,
     ["Cmpd ID", "IC50 nM", "# runs", "Tested on"]),
    ("delta_screening_per_target.xlsx", "BRAF panel", 0, 9,
     ["compound_id", "ic50_nm", "n", "date"]),
    ("helix_genomics_DE.xlsx", "Ergebnisse", 0, 13,
     ["Substanz", "Methode", "Konz. (µM)", "Zielprotein", "Wdh.", "Datum"]),
    ("meridian_cro_codes.xlsx", "DATA", 0, 14,
     ["CMP", "ASY", "VAL", "UOM", "TGT", "NREP", "DT"]),
    # nimbus's CHARTSHEET is structurally excluded by list_worksheets (D-17); its
    # one real worksheet is an ordinary table and has always ingested. See
    # test_the_excluded_fixtures_are_excluded_for_a_reason for why it is swept
    # rather than skipped.
    ("nimbus_labs_chartsheet.xlsx", "Data", 0, 10,
     ["Compound", "Assay", "Result", "Unit", "Target", "Replicates", "Date"]),
    ("orion_pk_report.xlsx", "Summary", 0, 10,
     ["Test Article", "Parameter", "Mean", "Unit", "Molecular Target",
      "N animals", "Study Day"]),
    ("orion_pk_report.xlsx", "Raw timepoints", 0, 50,
     ["Test Article", "Timepoint (h)", "Conc", "Unit"]),
    ("summit_discovery_mixed.xlsx", "results", 0, 15,
     ["id", "readout", "measurement", "gene", "reps", "date"]),
    ("vantage_pk_with_chart.xlsx", "Results", 0, 10,
     ["Compound", "Assay", "Result", "Unit", "Target", "Replicates", "Date"]),
    ("vertex_pk_eu_format.xlsx", "Ergebnisse", 0, 12,
     ["Verbindung", "Parameter", "Wert (ng*h/mL)", "Zielprotein", "Wdh.", "Datum"]),
    ("zephyr_bio_ZB-2025.xlsx", "Week 1", 4, 8,
     ["Compound ID", "Assay", "Result", "Units", "Protein Target", "Replicates",
      "Run Date"]),
    ("zephyr_bio_ZB-2025.xlsx", "Week 2", 4, 8,
     ["Compound ID", "Assay", "Result", "Units", "Protein Target", "Replicates",
      "Run Date"]),
    ("zephyr_bio_ZB-2025.xlsx", "Week 3", 4, 8,
     ["Compound ID", "Assay", "Result", "Units", "Protein Target", "Replicates",
      "Run Date"]),
]


# --- The stated scope: what is NOT swept, by name, with its reason ----------------
#
# An exclusion list is only honest if it is a STATED SCOPE rather than a silent
# omission — so every worksheet in data/synthetic/ that the sweep does not cover
# is named here with the reason, and gets its own assertion below that it is
# refused (never silently ingested). The two lists together must account for
# EVERY worksheet in the directory; `test_the_sweep_covers_every_worksheet`
# fails if a newly-added fixture escapes both.

_NOT_ROW_PER_RECORD: dict[tuple[str, str], str] = {
    ("apex_labs_wide_matrix.xlsx", "IC50 matrix (nM)"):
        "a wide matrix — compounds down, targets across; v1 does not un-pivot it",
    ("bionexus_transposed.xlsx", "Sheet1"):
        "transposed — fields down the side, records across; not one row per record",
    ("triton_screening_two_tables.xlsx", "Combined"):
        "two tables stacked in one sheet, separated by a blank row",
    ("quantex_scanned_report.xlsx", "Scanned Report"):
        "drawing-only — the table is a pasted image; the tool cannot read pixels",
}

_HEADER_NOT_RESOLVABLE: dict[tuple[str, str], str] = {
    ("verity_reagents_stock.xlsx", "Stock on hand"):
        "row-per-record, but no header row scores clearly — it asks WHICH ROW is "
        "the header (and the answer is the --hint the replay test saves)",
    ("meridian_cro_codes.xlsx", "LEGEND"):
        "a code legend, not the data sheet — no resolvable header row",
    ("orion_pk_report.xlsx", "Notes"):
        "free prose, not a table — no resolvable header row",
}


def _worksheets() -> list[tuple[str, str]]:
    return [
        (path.name, worksheet.title)
        for path in sorted(DATA.glob("*.xlsx"))
        for worksheet in list_worksheets(path)
    ]


def _row_per_record_judge(sheet: str, header_row_index: int):
    """A judge fake in `judge_workbook_layout`'s exact shape, returning the
    CONFIDENT `row_per_record` verdict a real judge returns for an ordinary
    table — naming the header row, and nothing else. `first/last_data_row` are
    deliberately left unset: "read it the ordinary way" means exactly that, and
    inventing a row range here would be the sweep flattering itself."""

    def _judge(grids, *, headers_only):
        return {
            sheet: SheetLayout(
                kind=LayoutKind.ROW_PER_RECORD,
                confidence=0.97,
                reasoning="an ordinary table with a header row",
                header_row_index=header_row_index,
            )
        }

    return _judge


def _ingest_under_the_judge(path: Path, sheet: str, header_row_index: int):
    """Drive the REAL production chain a credentialed run drives — the judge
    seam, then D-12-15's null hypothesis, then parse — with only the SDK call
    faked. Nothing here reimplements the rule it is testing."""
    verdict = service._judge_target_sheet(
        path, sheet, None,
        client=None,
        judge_fn=_row_per_record_judge(sheet, header_row_index),
        headers_only=False,
    )
    assert verdict is not None, "the judge fake must reach the seam"

    hint = service._apply_null_hypothesis(path, sheet, None, verdict)
    assert not isinstance(hint, StructureQuestion), (
        f"a CONFIDENT row_per_record verdict must never raise a question "
        f"({sheet}) — that is the null hypothesis (D-12-15)"
    )
    # NON-VACUITY, and it matters at THIS wave. Without this the sweep could
    # pass through the heuristic classifier — which still exists here — and so
    # would prove nothing about the verdict path it claims to be testing. A hint
    # carrying a layout ALWAYS goes through `_table_from_layout` (12-03's
    # dispatch contract), so pinning the layout onto the hint pins that the
    # VERDICT is what read this file.
    assert hint is not None and hint.layout is not None, (
        f"the verdict must reach parse() as a layout ({sheet}) — otherwise this "
        f"sweep is measuring the classifier Wave C deletes"
    )
    assert hint.layout.kind is LayoutKind.ROW_PER_RECORD

    return parse(path, sheet=sheet, hint=hint)


@pytest.mark.parametrize(
    ("file_name", "sheet", "header_row_index", "row_count", "headers"),
    _BASELINE,
    ids=[f"{name}::{sheet}" for name, sheet, _h, _r, _c in _BASELINE],
)
def test_sc5_every_row_per_record_sheet_ingests_exactly_as_it_does_today(
    file_name, sheet, header_row_index, row_count, headers
):
    """SC5, one case per row-per-record worksheet in data/synthetic/.

    Under a confident `row_per_record` judge, the sheet parses to a `RawTable`
    whose headers and row count are byte-for-byte the ones captured on the
    pre-change code. Removing the classifier regresses nothing — asserted, per
    file, rather than asserted once and generalised."""
    outcome = _ingest_under_the_judge(DATA / file_name, sheet, header_row_index)

    assert isinstance(outcome, RawTable), (
        f"{file_name}::{sheet} ingests today and must keep ingesting (SC5)"
    )
    assert outcome.headers == headers, f"{file_name}::{sheet}: headers moved"
    assert outcome.row_count == row_count, f"{file_name}::{sheet}: row count moved"


@pytest.mark.parametrize(
    ("file_name", "sheet", "header_row_index", "row_count", "headers"),
    _BASELINE,
    ids=[f"{name}::{sheet}" for name, sheet, _h, _r, _c in _BASELINE],
)
def test_sc5_the_baseline_is_todays_truth_not_the_new_codes_opinion(
    file_name, sheet, header_row_index, row_count, headers
):
    """The baseline's own guard, and the reason this file is worth anything.

    The numbers above are asserted against the VERDICT-LESS parse — the path
    the heuristic classifier still owns at this commit. So a typo'd or
    self-serving baseline cannot hide: it must agree with what the OLD code
    does, today, right now, with no verdict in sight.

    Wave C (12-07) deletes that classifier and this test necessarily goes with
    it — at which point the sweep above, which does NOT depend on it, is what
    carries SC5 forward. That is the handoff, and it is deliberate."""
    outcome = parse(DATA / file_name, sheet=sheet)

    assert isinstance(outcome, RawTable)
    assert outcome.headers == headers
    assert outcome.row_count == row_count


def test_the_sweep_covers_every_worksheet_in_data_synthetic():
    """A newly-added fixture cannot silently escape SC5.

    Every worksheet in data/synthetic/ is either swept for parity or named in
    an exclusion list WITH ITS REASON. A fixture that is in neither fails here,
    loudly, instead of quietly enjoying no coverage at all."""
    swept = {(name, sheet) for name, sheet, _h, _r, _c in _BASELINE}
    excluded = set(_NOT_ROW_PER_RECORD) | set(_HEADER_NOT_RESOLVABLE)
    accounted = swept | excluded

    unaccounted = set(_worksheets()) - accounted
    assert unaccounted == set(), (
        f"these worksheets are in neither the SC5 sweep nor a named exclusion: "
        f"{sorted(unaccounted)} — add them to one, with a reason"
    )
    # And nothing is claimed that does not exist (a stale baseline entry would
    # otherwise sit here passing vacuously for ever).
    assert accounted - set(_worksheets()) == set(), "the lists name a sheet that is gone"

    assert len(swept) == 16, "the SC5 sweep's size is pinned — it must not shrink silently"


@pytest.mark.parametrize(
    ("file_name", "sheet"),
    sorted(_NOT_ROW_PER_RECORD),
    ids=[f"{name}::{sheet}" for name, sheet in sorted(_NOT_ROW_PER_RECORD)],
)
def test_the_excluded_shape_fixtures_are_refused_never_silently_ingested(
    file_name, sheet
):
    """The other half of the stated scope: each excluded shape fixture is
    REFUSED — a `StructureQuestion`, never a clean-looking table with every
    field wrong. Excluding a file from a parity sweep is only honest if the
    file's actual behaviour is asserted somewhere, and this is where."""
    outcome = parse(DATA / file_name, sheet=sheet)

    assert isinstance(outcome, StructureQuestion), _NOT_ROW_PER_RECORD[
        (file_name, sheet)
    ]
    assert not isinstance(outcome, RawTable)


@pytest.mark.parametrize(
    ("file_name", "sheet"),
    sorted(_HEADER_NOT_RESOLVABLE),
    ids=[f"{name}::{sheet}" for name, sheet in sorted(_HEADER_NOT_RESOLVABLE)],
)
def test_the_header_uncertain_sheets_ask_rather_than_ingest(file_name, sheet):
    """These are NOT shape fixtures — they are sheets whose HEADER ROW cannot be
    resolved, and they have never ingested. They are excluded from the parity
    sweep because there is no baseline table to be at parity WITH, and that is
    said out loud here rather than left as a gap in a list.

    (verity is the interesting one: it is a perfectly ordinary row-per-record
    table whose header sits under a banner. It asks WHICH ROW — and the human's
    `--hint header-row=2` answer is exactly what 12-09's promotion rule now
    resolves it with, which is the subject of tests/test_hint_replay_cli.py.)"""
    outcome = parse(DATA / file_name, sheet=sheet)

    assert isinstance(outcome, StructureQuestion), _HEADER_NOT_RESOLVABLE[
        (file_name, sheet)
    ]
