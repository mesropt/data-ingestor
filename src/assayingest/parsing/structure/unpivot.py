"""The pure key-value/transposed un-pivot — grid in, (headers, rows) out
(SHAPE-02).

Pure module: no file I/O, no `pandas`, no `openpyxl`, no `anthropic` import —
the transform consumes the native-typed row tuples `structure/grid.py` reads
and a confirmed `SheetLayout`, so it is fully testable on hand-built tuples
(`tests/test_structure_layout.py`'s parametrized purity guard pins this).

Two 1-line cell contracts are deliberately re-implemented here rather than
imported: `_stringify` mirrors `table.py::_row_to_strings` and `_clean_label`
mirrors `table.py::_clean_header` (minus its pandas-only ``Unnamed:`` branch,
which cannot occur on a native openpyxl grid). Importing them from `table.py`
would drag pandas into this pure module — the duplication is two lines and
deliberate.
"""

from __future__ import annotations

from .layout import KeyValueBlock, SheetLayout


def unpivot_key_value(
    rows: list[tuple], layout: SheetLayout
) -> tuple[list[str], list[list[str]]]:
    """Turn a key-value (or transposed) grid into (headers, string_rows) —
    the two things a `RawTable` is made of.

    Labels become headers and values become data cells, block by block in
    declared order. With `one_record_per_value_column=False` every block
    contributes columns to ONE record; with `True`, each value column is its
    own record (the transposed melt, D-12-13) — a record from one block
    leaves any other block's columns empty.

    Only cells inside each block's declared `[first_row, last_row]` rows and
    declared columns are ever read. A row whose label AND every value cell
    are all blank is padding, not a field, and is skipped; a blank label
    over a real value is kept with an empty header (an unlabelled row is
    signal, not noise — the `_clean_header` rationale).
    """
    block_data = [_read_block(rows, block) for block in layout.key_value_blocks]
    if layout.one_record_per_value_column:
        labels = [label for block_labels, _ in block_data for label in block_labels]
        string_rows = _one_row_per_value_column(block_data, layout.key_value_blocks)
    else:
        labels, string_rows = _one_combined_record(block_data)
    return _disambiguate(labels), string_rows


def _read_block(
    rows: list[tuple], block: KeyValueBlock
) -> tuple[list[str], list[list[str]]]:
    """One block's kept (labels, value grid) — blank label+value rows skipped."""
    labels: list[str] = []
    value_grid: list[list[str]] = []
    for row_index in range(block.first_row, block.last_row + 1):
        row = rows[row_index] if 0 <= row_index < len(rows) else ()
        label_cell = _cell(row, block.label_column)
        value_cells = [_cell(row, column) for column in block.value_columns]
        if _is_blank(label_cell) and all(_is_blank(cell) for cell in value_cells):
            continue
        labels.append(_clean_label(label_cell))
        value_grid.append([_stringify(cell) for cell in value_cells])
    return labels, value_grid


def _one_combined_record(
    block_data: list[tuple[list[str], list[list[str]]]],
) -> tuple[list[str], list[list[str]]]:
    """All blocks' cells as the columns of ONE record, in block order.

    A block with several value columns contributes one column per (label,
    value column) pair — the label repeats and `_disambiguate` renames it.
    """
    labels: list[str] = []
    record: list[str] = []
    for block_labels, value_grid in block_data:
        for label, values in zip(block_labels, value_grid):
            for value in values:
                labels.append(label)
                record.append(value)
    return labels, [record]


def _one_row_per_value_column(
    block_data: list[tuple[list[str], list[list[str]]]],
    blocks: tuple[KeyValueBlock, ...],
) -> list[list[str]]:
    """The transposed melt: one record per value column, block by block.

    Headers span every block's labels; a record from block N fills its own
    block's segment and leaves the other blocks' cells empty.
    """
    total_width = sum(len(block_labels) for block_labels, _ in block_data)
    string_rows: list[list[str]] = []
    segment_start = 0
    for (block_labels, value_grid), block in zip(block_data, blocks):
        for value_index in range(len(block.value_columns)):
            record = [""] * total_width
            for label_index in range(len(block_labels)):
                record[segment_start + label_index] = value_grid[label_index][value_index]
            string_rows.append(record)
        segment_start += len(block_labels)
    return string_rows


def _disambiguate(labels: list[str]) -> list[str]:
    """Rename duplicate labels deterministically: `Collected`, `Collected (2)`.

    The consequence this prevents: `canonical._column_index` resolves a
    header by FIRST occurrence (`canonical.py:259-269`, via 12-RESEARCH
    Pitfall 6), so a duplicate header's second column is silently
    unreachable downstream — value loss with no error. Raising instead was
    rejected ("which of your two `Collected` rows is real?" has no good
    answer — the honest one is "both, under different names"), and
    inheriting first-wins was rejected as silent data loss (12-RESEARCH
    §Friction (c)). Blank labels stay blank: they are already the "column
    exists but is unlabelled" signal, and suffixing them would fabricate a
    header no cell carries.
    """
    occurrences: dict[str, int] = {}
    used: set[str] = set()
    result: list[str] = []
    for label in labels:
        if label == "":
            result.append(label)
            continue
        occurrence = occurrences.get(label, 0) + 1
        candidate = label if occurrence == 1 else f"{label} ({occurrence})"
        while candidate in used:  # a genuine "X (2)" label already in play
            occurrence += 1
            candidate = f"{label} ({occurrence})"
        occurrences[label] = occurrence
        used.add(candidate)
        result.append(candidate)
    return result


def _cell(row: tuple, index: int) -> object:
    """The cell at `index`, or None when the (ragged) row is too short."""
    return row[index] if 0 <= index < len(row) else None


def _is_blank(cell: object) -> bool:
    return cell is None or str(cell).strip() == ""


def _clean_label(cell: object) -> str:
    """Mirror of `table.py::_clean_header`'s contract (table.py:206-215):
    strip surrounding whitespace, keep blank labels as empty strings."""
    return "" if cell is None else str(cell).strip()


def _stringify(cell: object) -> str:
    """Mirror of `table.py::_row_to_strings`'s contract (table.py:524-526):
    `"" if cell is None else str(cell)` — a native float becomes `'0.19'`
    with no thousands separator, keeping the downstream locale gate honest."""
    return "" if cell is None else str(cell)
