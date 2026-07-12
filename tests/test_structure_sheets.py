"""Tests for `parsing.structure.sheets.rank_sheets` — PARSE-04 sheet
selection, and the honest "no clear winner" case (D-09).

`orion_pk_report.xlsx` is the reference case for hesitation: RESEARCH.md
verified empirically that no structural signal separates `Summary` from
`Raw timepoints` (both are 100%-fill rectangular tables). A test asserting
a confident pick of `Summary` would be wrong — it must hesitate.
`meridian_cro_codes.xlsx` is the reference case for a confident pick: `DATA`
is genuinely wider than the narrow `LEGEND` sheet.
"""

from __future__ import annotations

from pathlib import Path

from assayingest.parsing.structure.sheets import SheetRanking, rank_sheets

_FIXTURES = Path(__file__).resolve().parent.parent / "data" / "synthetic"


def test_rank_sheets_orion_reports_no_confident_winner_with_top_two_candidates():
    ranking = rank_sheets(_FIXTURES / "orion_pk_report.xlsx")

    assert isinstance(ranking, SheetRanking)
    assert ranking.confident is False
    top_two = {name for name, _score in ranking.ranked[:2]}
    assert top_two == {"Summary", "Raw timepoints"}


def test_rank_sheets_orion_notes_ranks_below_the_top_two():
    ranking = rank_sheets(_FIXTURES / "orion_pk_report.xlsx")

    names_in_order = [name for name, _score in ranking.ranked]
    assert names_in_order[-1] == "Notes"


def test_rank_sheets_meridian_confident_with_data_as_winner():
    ranking = rank_sheets(_FIXTURES / "meridian_cro_codes.xlsx")

    assert ranking.confident is True
    assert ranking.winner == "DATA"


def test_rank_sheets_chartsheet_fixture_never_raises_and_excludes_chartsheet():
    ranking = rank_sheets(_FIXTURES / "nimbus_labs_chartsheet.xlsx")

    names = {name for name, _score in ranking.ranked}
    assert "Chart Overview" not in names
    assert names == {"Data"}


def test_rank_sheets_embedded_chart_fixture_ranks_the_data_sheet_normally():
    ranking = rank_sheets(_FIXTURES / "vantage_pk_with_chart.xlsx")

    assert ranking.winner == "Results"
    # A chart anchored on the sheet must not push its score down (D-16).
    assert ranking.ranked[0][1] > 0.9
