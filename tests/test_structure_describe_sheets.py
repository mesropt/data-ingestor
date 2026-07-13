"""Tests for `parsing.structure.describe_sheets` — the per-sheet manifest that
sits ABOVE `parse()` (11-CONTEXT.md D-11-21, SHEET-01/SHEET-04).

The four real multi-sheet workbooks in `data/synthetic/` ARE the acceptance
criteria, each for a different reason:

- `zephyr_bio_ZB-2025.xlsx` — three data sheets whose header is on row 4, under
  a banner. The description must report the RESOLVED header, never row 0: a
  manifest showing the banner would ask the human to pick a Schema for columns
  that do not exist.
- `delta_screening_per_target.xlsx` — one sheet per target, each spelling its
  columns differently. The description must keep each sheet's own headers, since
  the Schema scorer downstream scores each sheet on its own signature.
- `meridian_cro_codes.xlsx` — DATA + LEGEND. `rank_sheets` is confident about
  DATA here and today's `parse()` silently discards LEGEND. The description
  must still SHOW LEGEND, marked — SHEET-04: a sheet that fails a gate is
  surfaced, never dropped.
- `nimbus_labs_chartsheet.xlsx` — a chartsheet is not a worksheet and can never
  appear in the manifest (structural exclusion via `grid.list_worksheets`, D-17).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from assayingest.learning.signature import column_signature
from assayingest.parsing.structure.sheets import (
    SheetDescription,
    SheetStatus,
    describe_sheets,
)
from assayingest.parsing.table import parse

_FIXTURES = Path(__file__).resolve().parent.parent / "data" / "synthetic"


def _by_name(descriptions: list[SheetDescription]) -> dict[str, SheetDescription]:
    return {description.name: description for description in descriptions}


def _key_value_workbook(tmp_path: Path) -> Path:
    """A key-value `Summary` sheet — labels down column A, values in column B.

    Not a table, and no in-tree fixture is one. This is the shape a real
    clinical workbook's cover sheet takes, and the shape that produced the
    defect this test exists to pin: with the labels on row 0 and the values
    beside them, `detect_header` scores row 0 highest and hands back
    `['Patient Name', 'TAYLOR, James', ...]` — a PATIENT'S NAME presented to
    the curator as a column header.
    """
    import openpyxl

    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "Summary"
    for row in (
        ("Patient Name", "TAYLOR, James"),
        ("Accession #", "CS-2026-698392"),
        ("Collection Date", "14-Mar-2026"),
        ("Ordering Physician", "Dr. A. Reyes"),
        ("Specimen Type", "Serum"),
        ("Report Status", "Final"),
    ):
        worksheet.append(row)
    path = tmp_path / "key_value_summary.xlsx"
    workbook.save(path)
    return path


def test_describe_sheets_zephyr_describes_every_sheet_in_workbook_order():
    descriptions = describe_sheets(_FIXTURES / "zephyr_bio_ZB-2025.xlsx")

    assert [description.name for description in descriptions] == [
        "Week 1",
        "Week 2",
        "Week 3",
    ]
    assert all(description.status is SheetStatus.OK for description in descriptions)


def test_describe_sheets_zephyr_reports_the_resolved_header_not_the_banner_row():
    """Zephyr's header is on row 4; row 0 is a 'ZEPHYR BIOSCIENCES' banner."""
    week_one = _by_name(describe_sheets(_FIXTURES / "zephyr_bio_ZB-2025.xlsx"))["Week 1"]

    assert "ZEPHYR BIOSCIENCES" not in " ".join(week_one.headers)
    assert week_one.headers == [
        "Compound ID",
        "Assay",
        "Result",
        "Units",
        "Protein Target",
        "Replicates",
        "Run Date",
    ]


def test_describe_sheets_zephyr_row_count_counts_data_rows_not_the_raw_grid():
    """The grid is 13 rows tall; only 8 of them are data (5 precede the data,
    the banner block plus the header itself)."""
    week_one = _by_name(describe_sheets(_FIXTURES / "zephyr_bio_ZB-2025.xlsx"))["Week 1"]

    assert week_one.row_count == 8


def test_describe_sheets_never_disagrees_with_what_parse_resolves_for_that_sheet():
    """The description and `parse(path, sheet=X)` must reach the SAME header —
    two heuristics would mean two answers, and the manifest's headers are what
    the human is asked to choose a Schema for."""
    path = _FIXTURES / "zephyr_bio_ZB-2025.xlsx"
    described = _by_name(describe_sheets(path))["Week 2"]
    parsed = parse(path, sheet="Week 2")

    assert described.headers == parsed.headers
    assert described.row_count == len(parsed.rows)


def test_describe_sheets_delta_keeps_each_panel_its_own_header_spelling():
    descriptions = describe_sheets(_FIXTURES / "delta_screening_per_target.xlsx")

    assert [description.name for description in descriptions] == [
        "EGFR panel",
        "JAK2 panel",
        "BRAF panel",
    ]
    assert all(description.status is SheetStatus.OK for description in descriptions)
    header_lists = [tuple(description.headers) for description in descriptions]
    assert len(set(header_lists)) == 3


def test_describe_sheets_meridian_surfaces_the_legend_sheet_rather_than_dropping_it():
    """`rank_sheets` is confident DATA is the data sheet here, and `parse()`
    discards LEGEND without a word. The manifest must still show it (SHEET-01)
    and mark it (SHEET-04)."""
    descriptions = _by_name(describe_sheets(_FIXTURES / "meridian_cro_codes.xlsx"))

    assert set(descriptions) == {"DATA", "LEGEND"}
    assert descriptions["DATA"].status is SheetStatus.OK
    assert descriptions["LEGEND"].status is SheetStatus.HEADER_UNCERTAIN


def test_describe_sheets_excludes_a_chartsheet_structurally():
    descriptions = describe_sheets(_FIXTURES / "nimbus_labs_chartsheet.xlsx")

    assert [description.name for description in descriptions] == ["Data"]


def test_describe_sheets_orion_describes_both_data_sheets_with_their_own_headers():
    """Summary (7 columns) and Raw timepoints (4 columns) are two independent
    datasets, not two views of one — each keeps its own header list (D-11-08)."""
    descriptions = _by_name(describe_sheets(_FIXTURES / "orion_pk_report.xlsx"))

    assert descriptions["Summary"].status is SheetStatus.OK
    assert descriptions["Raw timepoints"].status is SheetStatus.OK
    assert len(descriptions["Summary"].headers) == 7
    assert len(descriptions["Raw timepoints"].headers) == 4


def test_describe_sheets_orion_notes_is_present_with_no_headers_and_marked():
    """`detect_header` returns `index=None, confident=False` for orion's Notes
    sheet. Indexing the grid with a None header index would crash the whole
    description — and dropping Notes would hide a sheet the human may want."""
    descriptions = _by_name(describe_sheets(_FIXTURES / "orion_pk_report.xlsx"))

    notes = descriptions["Notes"]
    assert notes.headers == []
    assert notes.row_count >= 0
    assert notes.status is SheetStatus.HEADER_UNCERTAIN


def test_describe_sheets_marks_a_drawing_only_sheet_and_claims_no_headers():
    descriptions = describe_sheets(_FIXTURES / "quantex_scanned_report.xlsx")

    assert len(descriptions) == 1
    scanned = descriptions[0]
    assert scanned.status is SheetStatus.DRAWING_ONLY
    assert scanned.headers == []
    assert scanned.row_count == 0


def test_describe_sheets_marks_a_wide_matrix_sheet_as_an_unsupported_shape():
    descriptions = describe_sheets(_FIXTURES / "apex_labs_wide_matrix.xlsx")

    assert descriptions[0].status is SheetStatus.UNSUPPORTED_SHAPE


def test_describe_sheets_gate_precedence_shape_outranks_header_confidence():
    """bionexus_transposed.xlsx fails BOTH gates — its header is unconfident
    (it has no real header row) and its shape is transposed. `table.py` checks
    shape first because it is the stronger, more specific diagnosis; the
    description must reach the same verdict, or it would tell the human one
    thing and `parse()` another."""
    descriptions = describe_sheets(_FIXTURES / "bionexus_transposed.xlsx")

    assert descriptions[0].status is SheetStatus.UNSUPPORTED_SHAPE


# --- a sheet whose SHAPE cannot be read claims no headers at all --------------
#
# The shape gate already rules these sheets out correctly. The failure this
# block pins is one of PRESENTATION: `detect_header` runs on a grid that is not
# a table, scores *some* row highest whatever it holds, and the description then
# ships those cells as `headers` — so the sheet-selection screen shows a
# confident answer for a sheet the tool has just proposed to skip.
#
# The shape, not the location, is the problem: there is nothing here for the
# human to point at, which is exactly what `table.py::_shape_unsupported_question`
# already encodes when it sets `answerable_by_hint=False`. `DRAWING_ONLY` is the
# precedent — it has claimed `headers == []` from the start.
#
# `HEADER_UNCERTAIN` is NOT the same case and must not be collapsed into it: an
# uncertain header ROW is a question the human CAN answer, so that sheet keeps
# its best guess (see the regression tests below).


def test_a_key_value_sheet_claims_no_headers_rather_than_naming_a_patient(tmp_path):
    """The defect, exactly as the builder found it: a key-value `Summary` sheet
    is correctly ruled `unsupported_shape` — and was STILL showing
    `Patient Name · TAYLOR, James · …` as its "detected headers"."""
    description = describe_sheets(_key_value_workbook(tmp_path))[0]

    assert description.status is SheetStatus.UNSUPPORTED_SHAPE
    assert description.headers == []
    assert "TAYLOR, James" not in " ".join(description.headers)


def test_a_key_value_sheet_is_still_described_never_dropped(tmp_path):
    """Suppressing the headers must not suppress the SHEET (SHEET-04). It keeps
    its name, its row count, and its status — the human may still insist on it,
    and gets that sheet's own structural question if they do."""
    descriptions = describe_sheets(_key_value_workbook(tmp_path))

    assert [description.name for description in descriptions] == ["Summary"]
    assert descriptions[0].row_count > 0


def test_a_transposed_sheet_does_not_present_its_compound_ids_as_headers():
    """bionexus_transposed.xlsx is the same lie in a different costume: its
    "headers" were `Compound · BNX-001 · BNX-002 · …` — a row of compound IDs,
    which are VALUES."""
    description = describe_sheets(_FIXTURES / "bionexus_transposed.xlsx")[0]

    assert description.status is SheetStatus.UNSUPPORTED_SHAPE
    assert description.headers == []


def test_a_wide_matrix_sheet_claims_no_headers_however_plausible_they_look():
    """apex_labs_wide_matrix.xlsx's top row (`Cmpd · EGFR · JAK2 · …`) reads
    like a perfectly good header list — and that is the trap. The tool cannot
    read the shape, so it has nothing to map, and a plausible-looking header
    list is the most dangerous thing it could show."""
    description = describe_sheets(_FIXTURES / "apex_labs_wide_matrix.xlsx")[0]

    assert description.status is SheetStatus.UNSUPPORTED_SHAPE
    assert description.headers == []


def test_an_unsupported_shapes_signature_is_never_computed_from_fabricated_headers(tmp_path):
    """`service._manifest_entry` derives `column_signature` from exactly these
    headers, and a signature is what the learning store keys a saved mapping on.
    A signature computed from `TAYLOR, James` would let one patient's name teach
    the tool a mapping — so the suppression has to reach the signature too, and
    it does, because the signature is a pure function of the headers."""
    description = describe_sheets(_key_value_workbook(tmp_path))[0]
    fabricated = ["Patient Name", "TAYLOR, James"]

    assert column_signature(description.headers) != column_signature(fabricated)
    assert column_signature(description.headers) == column_signature([])


# --- the regressions: only SHAPE suppresses headers ---------------------------


def test_an_ok_sheet_still_reports_its_real_headers():
    week_one = _by_name(describe_sheets(_FIXTURES / "zephyr_bio_ZB-2025.xlsx"))["Week 1"]

    assert week_one.status is SheetStatus.OK
    assert week_one.headers[0] == "Compound ID"
    assert len(week_one.headers) == 7


def test_a_header_uncertain_sheet_still_reports_the_headers_it_found():
    """meridian's LEGEND is `header_uncertain`, NOT `unsupported_shape` — and the
    two are not the same thing. An uncertain header ROW is a question the human
    can answer (they can point at the right row); an unreadable SHAPE is not.
    Collapsing them would blind the human to LEGEND's real 1/7 coverage, which
    D-11-24 made the only thing telling them it is a legend."""
    legend = _by_name(describe_sheets(_FIXTURES / "meridian_cro_codes.xlsx"))["LEGEND"]

    assert legend.status is SheetStatus.HEADER_UNCERTAIN
    assert legend.headers == ["CMP", "compound identifier"]


def test_describe_sheets_gate_precedence_drawing_only_outranks_header_confidence():
    """A drawing-only sheet has no rows at all, so its header is trivially
    unresolvable — but 'this sheet is a scanned image' is the honest diagnosis,
    not 'which row is the header'. Same precedence as `table.py:325-345`."""
    scanned = describe_sheets(_FIXTURES / "quantex_scanned_report.xlsx")[0]

    assert scanned.status is SheetStatus.DRAWING_ONLY


@pytest.mark.parametrize(
    "workbook", sorted(_FIXTURES.glob("*.xlsx")), ids=lambda path: path.name
)
def test_describe_sheets_never_crashes_on_any_workbook_in_the_corpus(workbook: Path):
    """However broken a sheet is, describing a workbook is not allowed to fail:
    the sheet-selection screen cannot ask about a workbook it could not read."""
    descriptions = describe_sheets(workbook)

    assert descriptions
    assert all(isinstance(d, SheetDescription) for d in descriptions)
    assert all(d.row_count >= 0 for d in descriptions)
