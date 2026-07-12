"""Sheet ranking — and the honest "no clear winner" case (D-09, PARSE-04).

Ranks a multi-sheet workbook's real worksheets (chartsheets structurally
excluded by `grid.list_worksheets` — D-17) by structural signals only: fill
density, a width-saturation score (relative to the workbook's widest
candidate), a minimum-row-count gate, and first-column uniqueness ratio as a
weak, non-load-bearing tie-breaker (01-RESEARCH.md Pattern 4). `confident`
is False whenever the top two scores are within the named tie margin — this
is the correct outcome for `orion_pk_report.xlsx`'s `Summary` vs
`Raw timepoints`, which RESEARCH.md verified empirically have no
distinguishing structural signal at all (D-09): hesitation there is honest
behaviour, not a heuristic failure to fix.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .grid import list_worksheets

#: Sheets scoring within this margin of the top score are a tie — rank
#: honestly reports "no clear winner" rather than picking the marginally
#: higher score (D-03/D-09). Corpus-tuned against orion_pk_report.xlsx
#: (Summary vs Raw timepoints, diff ~0.078 — must hesitate) and
#: meridian_cro_codes.xlsx (DATA vs LEGEND, diff ~0.171 — must be confident);
#: see 01-RESEARCH.md Pattern 4.
_CONFIDENCE_MARGIN = 0.1

#: A candidate sheet at least this fraction as wide as the workbook's widest
#: candidate scores "full width" (1.0) on the column signal; narrower sheets
#: score proportionally lower. Saturating, not linear, so two genuinely
#: full-width sheets (Summary/Raw timepoints) tie on this signal even though
#: their raw column counts differ.
_WIDTH_SATURATION_FACTOR = 0.5

#: A sheet needs at least this many rows (header + >=1 data row) to be
#: plausible at all; fewer rows saturate the row-count signal down sharply.
_MIN_PLAUSIBLE_ROWS = 2


@dataclass(frozen=True)
class SheetRanking:
    """Ranked candidate sheets for PARSE-04 sheet selection.

    `ranked` is sorted highest score first, as `(sheet_name, score)` pairs.
    `confident` is False whenever the top two scores are within
    `_CONFIDENCE_MARGIN` — the caller must not auto-pick `ranked[0]` in that
    case; a `StructureQuestion` with the ranked candidates is the correct
    response instead (D-09).
    """

    ranked: list[tuple[str, float]]
    confident: bool

    @property
    def winner(self) -> str | None:
        """The top-ranked sheet name, regardless of confidence.

        Callers must still check `confident` before trusting this as an
        auto-applied answer (D-02) — it exists so an uncertain
        `StructureQuestion` can pre-fill a best guess.
        """
        return self.ranked[0][0] if self.ranked else None


def rank_sheets(path: str | Path) -> SheetRanking:
    """Rank a workbook's real worksheets by how data-sheet-like they look.

    Chartsheets never appear here — `grid.list_worksheets` structurally
    excludes them (D-17), so ranking cannot crash on one. A single-worksheet
    workbook ranks trivially confident.
    """
    worksheets = list_worksheets(path)
    rows_by_sheet = {ws.title: list(ws.iter_rows(values_only=True)) for ws in worksheets}
    max_cols = max((_col_count(rows) for rows in rows_by_sheet.values()), default=0)

    scored = [
        (title, _score_sheet(rows, max_cols)) for title, rows in rows_by_sheet.items()
    ]
    scored.sort(key=lambda item: item[1], reverse=True)

    confident = len(scored) <= 1 or (scored[0][1] - scored[1][1]) >= _CONFIDENCE_MARGIN
    return SheetRanking(ranked=scored, confident=confident)


def _score_sheet(rows: list[tuple], max_cols: int) -> float:
    """Weighted structural score: fill density (0.3) + width saturation
    (0.4) + row-count saturation (0.2) + first-column uniqueness (0.1, a
    weak tie-breaker only — never load-bearing, per 01-RESEARCH.md
    Pattern 4's finding that it reveals record granularity, not
    correctness)."""
    return (
        0.3 * _fill_ratio(rows)
        + 0.4 * _width_score(rows, max_cols)
        + 0.2 * _row_count_score(rows)
        + 0.1 * _first_column_uniqueness(rows)
    )


def _col_count(rows: list[tuple]) -> int:
    return max((len(row) for row in rows), default=0)


def _fill_ratio(rows: list[tuple]) -> float:
    cols = _col_count(rows)
    total = len(rows) * cols
    if total == 0:
        return 0.0
    filled = sum(
        1 for row in rows for cell in row if cell is not None and str(cell).strip()
    )
    return filled / total


def _width_score(rows: list[tuple], max_cols: int) -> float:
    threshold = max_cols * _WIDTH_SATURATION_FACTOR
    if threshold == 0:
        return 0.0
    return min(_col_count(rows) / threshold, 1.0)


def _row_count_score(rows: list[tuple]) -> float:
    return min(len(rows) / _MIN_PLAUSIBLE_ROWS, 1.0)


def _first_column_uniqueness(rows: list[tuple]) -> float:
    values = [row[0] for row in rows if row and row[0] is not None]
    if not values:
        return 0.0
    return len(set(values)) / len(values)
