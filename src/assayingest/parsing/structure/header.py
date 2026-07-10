"""Header-row detection: width-consistency + type-mismatch scoring
(01-RESEARCH.md Pattern 1).

Two independent, real prior-art approaches (`messytables`' modal-column-count
heuristic and DuckDB's CSV-sniffer type-mismatch check) converge on the same
two signals; this module combines them with width-consistency and
uniqueness. No canonical scoring library exists for this problem (01-RESEARCH.md
Open Question 1) -- this heuristic is grounded in that prior art, not
invented from nothing, and its threshold is a named, corpus-tuned constant a
future plan can revisit, never a magic number.

Pure module: no I/O, no network, no `anthropic` import (D-04) -- every signal
is computed from the native-typed row tuples `structure/grid.py` reads, so
this module is fully testable without a file on disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: How close the top-scoring row must be to the runner-up before
#: `detect_header` refuses to pick a winner and reports "not confident"
#: (D-03). Calibrated below the one real multi-banner-row margin this
#: project has (zephyr_bio_ZB-2025.xlsx: header scores 1.0, best data-row
#: runner-up scores 0.914 -- a 0.086 margin) so that reference case resolves
#: confidently, while a genuine tie/near-tie still routes to a
#: `StructureQuestion` instead of a silent guess. No canonical threshold
#: exists in prior art (01-RESEARCH.md Open Question 1) -- this is a
#: corpus-tuned starting point validated against one fixture, not a final
#: constant; revisit once more banner-row fixtures exist.
_CONFIDENCE_MARGIN = 0.05

#: Rows examined below a candidate when scoring its type-consistency signal.
_TYPE_CHECK_WINDOW = 5


@dataclass(frozen=True)
class HeaderDetection:
    """The outcome of scoring every candidate row for how header-like it is.

    `index` is always the best-guess row (even when `confident` is False) so
    a caller can pre-fill a `StructureQuestion`'s proposal with it (D-02) --
    "not confident" means "don't trust this automatically", not "no answer
    at all". `index` is only `None` when no row scored at all (an entirely
    blank grid).
    """

    index: int | None
    confident: bool
    scores: list[tuple[int, float]] = field(default_factory=list)


def header_row_scores(rows: list[tuple], max_scan: int = 15) -> list[tuple[int, float]]:
    """Score each candidate row 0..max_scan for how header-like it is.

    Signals (all computed from native cell types, not strings -- Pattern 6):
      - str_ratio: fraction of the candidate row's non-blank cells that are str
      - uniq_ratio: fraction of the candidate row's non-blank cells that are unique
      - fill_ratio: candidate row's non-blank cell count / the grid's max row width
        (the width-consistency signal from messytables' modal-count approach)
      - type_consistency: fraction of columns where the rows *below* the
        candidate share one Python type (the DuckDB type-mismatch signal,
        inverted: data rows below a real header are internally
        type-consistent per column)

    A fully-blank row is never scored -- it cannot be a header candidate.
    """
    width = max((len(row) for row in rows), default=0)
    scores: list[tuple[int, float]] = []
    for index in range(min(max_scan, max(len(rows) - 1, 0))):
        candidate = rows[index]
        non_blank = _non_blank_cells(candidate)
        if not non_blank:
            continue
        below = rows[index + 1 : index + 1 + _TYPE_CHECK_WINDOW]
        score = (
            0.3 * _str_ratio(non_blank)
            + 0.2 * _uniq_ratio(non_blank)
            + 0.2 * _fill_ratio(non_blank, width)
            + 0.3 * _type_consistency(candidate, below)
        )
        scores.append((index, score))
    return scores


def detect_header(rows: list[tuple], max_scan: int = 15) -> HeaderDetection:
    """Pick the most header-like row, or say "not confident" (D-03).

    Confident only when the top score's margin over the runner-up meets
    `_CONFIDENCE_MARGIN` -- a narrow margin means the deterministic layer
    cannot reliably separate the header from a data row, and silently
    picking the higher score risks exactly the shifted-header failure D-02
    exists to prevent (a clean-looking table with every field wrong).
    """
    scores = header_row_scores(rows, max_scan=max_scan)
    if not scores:
        return HeaderDetection(index=None, confident=False, scores=scores)

    ranked = sorted(scores, key=lambda item: item[1], reverse=True)
    top_index, top_score = ranked[0]
    if len(ranked) == 1:
        return HeaderDetection(index=top_index, confident=True, scores=scores)

    _, runner_up_score = ranked[1]
    confident = (top_score - runner_up_score) >= _CONFIDENCE_MARGIN
    return HeaderDetection(index=top_index, confident=confident, scores=scores)


def _non_blank_cells(row: tuple) -> list:
    return [cell for cell in row if cell is not None and str(cell).strip() != ""]


def _str_ratio(non_blank: list) -> float:
    return sum(1 for cell in non_blank if isinstance(cell, str)) / len(non_blank)


def _uniq_ratio(non_blank: list) -> float:
    return len(set(non_blank)) / len(non_blank)


def _fill_ratio(non_blank: list, width: int) -> float:
    return len(non_blank) / width if width else 0.0


def _type_consistency(candidate: tuple, below: list[tuple]) -> float:
    """Fraction of columns whose values in `below` share exactly one type."""
    checked = consistent = 0
    for column_index in range(len(candidate)):
        column_values = [
            row[column_index]
            for row in below
            if column_index < len(row) and row[column_index] is not None
        ]
        if len(column_values) < 2:
            continue
        checked += 1
        if len({type(value) for value in column_values}) == 1:
            consistent += 1
    return consistent / checked if checked else 0.0
