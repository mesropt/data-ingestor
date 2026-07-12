"""`parse()`'s Excel branch selects the data sheet structurally before
header detection — a genuinely tied workbook asks (D-09), a confident
workbook auto-selects, an explicit `sheet=` is always honored (proceed-on-
hint), and a drawing-only sheet asks instead of the old silent "no data
rows" skip (D-18). Wires plan 03's `structure/sheets.py` and
`grid.is_drawing_only_sheet` into the same end-to-end vertical slice plans
01/02 established for CSV and header detection."""

from __future__ import annotations

from pathlib import Path

from assayingest.cli import run
from assayingest.parsing.hint import StructuralHint, StructureQuestion
from assayingest.parsing.table import RawTable, parse

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"


def test_parse_orion_with_no_sheet_hesitates_with_summary_and_raw_as_alternatives():
    outcome = parse(DATA / "orion_pk_report.xlsx")

    assert isinstance(outcome, StructureQuestion)
    alt_sheet_names = {
        hint.sheet_name for hint in outcome.alternatives if hint.sheet_name
    }
    assert {"Summary", "Raw timepoints"} <= alt_sheet_names


def test_parse_orion_explicit_sheet_proceeds_to_a_raw_table():
    outcome = parse(DATA / "orion_pk_report.xlsx", sheet="Summary")

    assert isinstance(outcome, RawTable)
    assert outcome.sheet_name == "Summary"
    assert "Test Article" in outcome.headers


def test_parse_meridian_with_no_sheet_auto_selects_data():
    outcome = parse(DATA / "meridian_cro_codes.xlsx")

    assert isinstance(outcome, RawTable)
    assert outcome.sheet_name == "DATA"
    assert outcome.headers == ["CMP", "ASY", "VAL", "UOM", "TGT", "NREP", "DT"]


def test_parse_image_only_sheet_returns_structure_question_not_empty_table():
    outcome = parse(DATA / "quantex_scanned_report.xlsx")

    assert isinstance(outcome, StructureQuestion)


def test_parse_chartsheet_workbook_single_data_sheet_resolves_without_asking():
    """Only one real worksheet ('Data'); the chartsheet is structurally
    excluded, so no ranking ambiguity should even arise (D-17)."""
    outcome = parse(DATA / "nimbus_labs_chartsheet.xlsx")

    assert isinstance(outcome, RawTable)
    assert outcome.sheet_name is None  # single real worksheet, no tag needed


def test_parse_chart_embedded_sheet_resolves_normally():
    """A chart on the data sheet must not disqualify it (D-16)."""
    outcome = parse(DATA / "vantage_pk_with_chart.xlsx")

    assert isinstance(outcome, RawTable)
    assert "Compound" in outcome.headers


def test_parse_hint_sheet_name_overrides_ranking():
    outcome = parse(
        DATA / "orion_pk_report.xlsx", hint=StructuralHint(sheet_name="Raw timepoints")
    )

    assert isinstance(outcome, RawTable)
    assert outcome.sheet_name == "Raw timepoints"


def test_cli_run_on_image_only_sheet_asks_and_never_prints_the_old_skip_message(
    capsys,
):
    exit_code = run(str(DATA / "quantex_scanned_report.xlsx"))

    out = capsys.readouterr().out
    assert exit_code == 4
    assert "no data rows" not in out
    assert "BLOCKED" in out
