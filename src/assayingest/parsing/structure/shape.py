"""Table-shape classification: row/column type-homogeneity inversion, plus a
numeric-column-cluster fingerprint (01-RESEARCH.md Pattern 5, D-10).

Only `TableShape.ROW_PER_RECORD` may ever become a `RawTable`. Every other
shape -- `wide_matrix`, `transposed`, `multiple_tables`, `unknown` -- is a
structurally-detected reason to ask instead of guess (D-11): shifting a
wide-matrix or transposed layout into one-row-per-record without un-pivoting
produces a clean-looking table with every field wrong, exactly the failure
PARSE-05 exists to prevent. Un-pivoting stays out of scope for v1
(PARSE-V2-01) -- this module only detects and names the shape.

Pure module: no I/O, no `pandas`, no `openpyxl`, no `anthropic` import (D-04)
-- every signal is computed from the native-typed row tuples
`structure/grid.py` reads, so this module is fully testable without a file
on disk.
"""

from __future__ import annotations

from collections import Counter

from ..hint import TableShape

#: `row_type_homogeneity` must exceed `column_type_homogeneity` by at least
#: this much before the transposed signal is trusted -- corpus-tuned so
#: `bionexus_transposed.xlsx`'s verified inversion (row 0.9 > col 0.426,
#: 01-RESEARCH.md Pattern 5) fires confidently while neither
#: `zephyr_bio_ZB-2025.xlsx` nor `apex_labs_wide_matrix.xlsx` -- both of
#: which score *higher* on columns than rows -- ever comes close to
#: inverting. Like header.py's `_CONFIDENCE_MARGIN`, this is a named,
#: corpus-grounded starting point, not a claim of a canonical threshold.
_TRANSPOSED_MARGIN = 0.1

#: A numeric-column cluster smaller than this can't be the wide_matrix
#: fingerprint -- apex_labs_wide_matrix.xlsx's verified cluster is 5
#: overlapping-range columns (EGFR/JAK2/BRAF/ALK/KRAS); a normal table's
#: numeric columns never cluster past 1-2, because each one measures
#: something different (01-RESEARCH.md Pattern 5).
_WIDE_MATRIX_MIN_COLUMNS = 3

#: The cluster must also span a meaningful share of the table's width, not
#: just an absolute count -- a 3-column cluster inside a 20-column table
#: isn't "the whole table is one wide matrix" (01-RESEARCH.md Pattern 5's
#: "≥40-50% of all columns").
_WIDE_MATRIX_MIN_FRACTION = 0.4


def classify_shape(rows: list[tuple]) -> TableShape:
    """Classify a resolved data region's shape (PARSE-05, D-10).

    `rows` is the native-typed data region -- the header row already sliced
    off by the caller (Pattern 6: detect on native types, convert to strings
    only after resolution). A fully-blank separator block between two
    populated regions is checked first and wins outright (`multiple_tables`)
    since it is a structural fact no homogeneity ratio can override; the
    `multiple_tables` branch has only one real corpus fixture
    (`triton_screening_two_tables.xlsx`, added in plan 03) -- treat it as a
    grounded but still-narrow predicate, not an exhaustively-validated one
    (01-RESEARCH.md Assumptions A4). Everything else falls through to the
    row/column type-homogeneity inversion (`transposed`), then the
    numeric-column-cluster fingerprint (`wide_matrix`), and finally the
    default, `row_per_record`.
    """
    if not rows:
        return TableShape.UNKNOWN
    if _has_blank_separator_block(rows):
        return TableShape.MULTIPLE_TABLES

    column_homogeneity = _column_type_homogeneity(rows)
    row_homogeneity = _row_type_homogeneity(rows)
    inverted = row_homogeneity - column_homogeneity >= _TRANSPOSED_MARGIN
    if inverted and _first_column_all_unique_strings(rows):
        return TableShape.TRANSPOSED

    if _is_wide_matrix(rows):
        return TableShape.WIDE_MATRIX

    return TableShape.ROW_PER_RECORD


def _row_is_blank(row: tuple) -> bool:
    return all(cell is None or str(cell).strip() == "" for cell in row)


def _has_blank_separator_block(rows: list[tuple]) -> bool:
    """True when a fully-blank row sits between populated rows on both
    sides -- the `multiple_tables` fingerprint. A single leading or trailing
    blank run (no populated content on one side) is not a separator; it
    never divides the data into two independent blocks."""
    blank_indices = [index for index, row in enumerate(rows) if _row_is_blank(row)]
    if not blank_indices:
        return False
    has_populated_before = any(
        not _row_is_blank(row) for row in rows[: blank_indices[0]]
    )
    has_populated_after = any(
        not _row_is_blank(row) for row in rows[blank_indices[-1] + 1 :]
    )
    return has_populated_before and has_populated_after


def _type_class(value: object) -> type:
    """Normalize int/float into one numeric class before comparing types --
    the same storage-artifact fix `header.py::_type_class` applies (a
    whole-number cell reads back as `int` next to `float` neighbors in a
    genuinely-numeric column; that's an openpyxl quirk, not a structural
    signal)."""
    if isinstance(value, bool):  # bool is an int subclass -- keep it distinct
        return bool
    if isinstance(value, (int, float)):
        return float
    return type(value)


def _majority_type_fraction(values: list) -> float:
    """The fraction of non-blank values sharing the single most common type
    class -- 1.0 when a column/row is internally type-consistent, lower as
    it mixes types. Continuous, not binary all-or-nothing, so one stray
    value doesn't collapse an otherwise-consistent column/row's score."""
    present = [value for value in values if value is not None]
    if not present:
        return 1.0
    counts = Counter(_type_class(value) for value in present)
    return max(counts.values()) / len(present)


def _column_type_homogeneity(rows: list[tuple]) -> float:
    """Average, across every column, of how internally type-consistent that
    column is -- a normal `row_per_record` table scores high here (each
    column is one measurement, one type throughout every row)."""
    width = max(len(row) for row in rows)
    scores = [
        _majority_type_fraction([row[column] for row in rows if column < len(row)])
        for column in range(width)
    ]
    return sum(scores) / len(scores) if scores else 0.0


def _row_type_homogeneity(rows: list[tuple]) -> float:
    """Average, across every row (excluding column 0, per Pattern 5), of how
    internally type-consistent that row is -- a `transposed` table scores
    high here because each row is one field, repeated as the same type
    across every compound."""
    scores = [_majority_type_fraction(list(row[1:])) for row in rows]
    return sum(scores) / len(scores) if scores else 0.0


def _first_column_all_unique_strings(rows: list[tuple]) -> bool:
    """The `transposed` shape's second confirming signal (Pattern 5) --
    `bionexus_transposed.xlsx`'s first column is field-label strings, never
    a repeated value. Required alongside the inversion (not sufficient
    alone): a normal table's ID column is also all-unique strings, so this
    check only ever narrows a positive inversion, never substitutes for
    one."""
    values = [row[0] for row in rows if row and row[0] is not None]
    return (
        bool(values)
        and all(isinstance(value, str) for value in values)
        and len(set(values)) == len(values)
    )


def _numeric_columns(rows: list[tuple], width: int) -> dict[int, tuple[float, float]]:
    """Columns whose every non-blank value is numeric, mapped to their
    (min, max) value range. A column with even one non-numeric value (e.g.
    a unit string) is excluded outright -- the wide_matrix fingerprint is
    about *purely* numeric measurement columns, per Pattern 5."""
    ranges: dict[int, tuple[float, float]] = {}
    for column in range(width):
        values = [row[column] for row in rows if column < len(row) and row[column] is not None]
        if len(values) < 2:
            continue
        if all(_type_class(value) is float for value in values):
            ranges[column] = (min(values), max(values))
    return ranges


def _ranges_overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def _largest_overlapping_cluster(ranges: dict[int, tuple[float, float]]) -> int:
    """Size of the largest set of numeric columns whose value ranges
    mutually pairwise-overlap -- `apex_labs_wide_matrix.xlsx`'s 5 measurement
    columns (EGFR/JAK2/BRAF/ALK/KRAS, all ~0-950 nM) overlap pairwise; its
    `n` replicate column (2-4) overlaps none of them and is correctly
    excluded from the cluster rather than diluting the count."""
    columns = list(ranges)
    if not columns:
        return 0
    adjacency = {
        column: {
            other
            for other in columns
            if other != column and _ranges_overlap(ranges[column], ranges[other])
        }
        for column in columns
    }
    return max(len(_connected_component(column, adjacency)) for column in columns)


def _connected_component(start: int, adjacency: dict[int, set[int]]) -> set[int]:
    seen = {start}
    frontier = [start]
    while frontier:
        node = frontier.pop()
        for neighbour in adjacency[node] - seen:
            seen.add(neighbour)
            frontier.append(neighbour)
    return seen


def _is_wide_matrix(rows: list[tuple]) -> bool:
    """`>= _WIDE_MATRIX_MIN_COLUMNS` columns (and `>= _WIDE_MATRIX_MIN_FRACTION`
    of the table's width) sharing a numeric dtype with pairwise-overlapping
    value ranges -- the fingerprint Pattern 5 verified separates
    `apex_labs_wide_matrix.xlsx` from a normal table. A table with a real
    category/unit column (like zephyr's `Units`) never produces more than
    one free-floating numeric measurement column, so its overlapping
    cluster never reaches the minimum -- the cluster-size gate is what
    stands in for "no distinguishing category/unit column" here, rather
    than a separate, more fragile column-label heuristic.
    """
    width = max(len(row) for row in rows)
    ranges = _numeric_columns(rows, width)
    cluster_size = _largest_overlapping_cluster(ranges)
    return (
        cluster_size >= _WIDE_MATRIX_MIN_COLUMNS
        and cluster_size / width >= _WIDE_MATRIX_MIN_FRACTION
    )
