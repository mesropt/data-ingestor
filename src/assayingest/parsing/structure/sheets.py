"""Sheet ranking — and the honest "no clear winner" case (D-09, PARSE-04) —
plus `describe_sheets`, the per-sheet manifest that sits ABOVE `parse()`
(11-CONTEXT.md D-11-21, SHEET-01/SHEET-04).

The two are siblings, not layers. `rank_sheets` answers "which ONE sheet is
the data sheet" and discards the rest — the right question when the tool must
pick for itself. `describe_sheets` answers "what is in EVERY sheet" and
discards nothing — the right question when the human is about to pick, and the
one a multi-sheet workbook (several plates, several weeks, one batch per sheet)
actually poses.

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
from enum import Enum
from pathlib import Path

from ..hint import TableShape
from .grid import is_drawing_only_sheet, list_worksheets
from .header import HeaderDetection, detect_header
from .shape import classify_shape

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


class SheetStatus(str, Enum):
    """What a structural gate said about one sheet — never a reason to hide it.

    `OK` means the sheet would parse as a table today. Every other member names
    a gate the sheet fails, and exists so the manifest can SAY SO rather than
    drop the sheet: the human still sees it, and may still select it, in which
    case `parse(path, sheet=X)` raises that sheet's own `StructureQuestion`
    (SHEET-04 — a sheet that fails a gate is surfaced, never dropped).
    """

    OK = "ok"
    DRAWING_ONLY = "drawing_only"
    UNSUPPORTED_SHAPE = "unsupported_shape"
    HEADER_UNCERTAIN = "header_uncertain"


@dataclass(frozen=True)
class SheetDescription:
    """One worksheet as the sheet-selection screen must show it (SHEET-01).

    `headers` are the RESOLVED headers — the row `detect_header` picked, not
    row 0 (zephyr_bio_ZB-2025.xlsx's headers sit on row 4, under a banner; a
    manifest showing the banner would ask the human to choose a Schema for
    columns that do not exist). `row_count` counts the DATA rows below that
    header, never the raw grid height.

    A sheet whose header cannot be resolved at all has `headers == []` — an
    empty header list is an honest "no headers were resolved", never a claim
    that the sheet is empty. `status` says which gate it failed.
    """

    name: str
    headers: list[str]
    row_count: int
    status: SheetStatus


def describe_sheets(path: str | Path) -> list[SheetDescription]:
    """Describe EVERY real worksheet of a workbook, in workbook order.

    Chartsheets never appear — `grid.list_worksheets` structurally excludes
    them (D-17). Nothing else is ever excluded: a broken sheet is described and
    marked, not dropped (SHEET-04).
    """
    worksheets = list_worksheets(path)
    return [
        _describe_one_sheet(worksheet, list(worksheet.iter_rows(values_only=True)))
        for worksheet in worksheets
    ]


def _describe_one_sheet(worksheet, rows: list[tuple]) -> SheetDescription:
    """Run the same structural gates on one sheet that `parse()` will run on it
    later (`table.py::_parse_excel_structurally`), and report the verdict
    instead of raising it.

    Gate order is `table.py`'s exactly — drawing-only, then shape, then header
    confidence. It is not an arbitrary order: shape is the stronger, more
    specific diagnosis than "which row is the header", and a description that
    disagreed with the verdict `parse(path, sheet=X)` reaches would be a second
    heuristic answering the same question a second way.
    """
    if is_drawing_only_sheet(worksheet):
        return SheetDescription(
            name=worksheet.title,
            headers=[],
            row_count=0,
            status=SheetStatus.DRAWING_ONLY,
        )

    detection = detect_header(rows)
    # `index` is None only when no row scored at all (an entirely blank grid).
    # It is never an offset to index with until that case is answered.
    headers = [] if detection.index is None else _header_texts(rows[detection.index])
    data_region = rows if detection.index is None else rows[detection.index + 1 :]

    return SheetDescription(
        name=worksheet.title,
        headers=headers,
        row_count=len(data_region),
        status=_sheet_status(detection, data_region),
    )


def _sheet_status(detection: HeaderDetection, data_region: list[tuple]) -> SheetStatus:
    """Which gate this sheet fails, if any — the shape gate first (see
    `_describe_one_sheet`), then header confidence.

    An unconfident header is not a failure to fix here: `HeaderDetection.index`
    is always the top-scoring row when one exists, so the manifest still shows
    the best guess — it just refuses to present it as settled (D-02).
    """
    if classify_shape(data_region) is not TableShape.ROW_PER_RECORD:
        return SheetStatus.UNSUPPORTED_SHAPE
    if detection.index is None or not detection.confident:
        return SheetStatus.HEADER_UNCERTAIN
    return SheetStatus.OK


def _header_texts(header_row: tuple) -> list[str]:
    """The resolved header row as the strings-only shape a `RawTable` carries.

    Mirrors `table.py::_clean_header`'s contract — a blank header stays a blank
    string, because an unlabelled column is signal, not noise. The parity is
    pinned by a test (`describe_sheets` and `parse(path, sheet=X)` must reach
    the same headers; two answers to one question would let the human choose a
    Schema for a header list the parser never produces).
    """
    return ["" if cell is None else str(cell).strip() for cell in header_row]
