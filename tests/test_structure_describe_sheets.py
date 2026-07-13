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

from assayingest.parsing.structure.sheets import (
    SheetDescription,
    SheetStatus,
    describe_sheets,
)
from assayingest.parsing.table import parse

_FIXTURES = Path(__file__).resolve().parent.parent / "data" / "synthetic"


def _by_name(descriptions: list[SheetDescription]) -> dict[str, SheetDescription]:
    return {description.name: description for description in descriptions}


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
