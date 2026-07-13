"""Claude structural-assist — a PROPOSAL only, never applied (D-01 layer 2).

This is the second of the three structure-resolution layers (D-01): when the
deterministic heuristics in `parsing/structure/` are not confident, this
module asks Claude for its best reading of the raw-grid evidence and maps
the answer onto a `StructuralHint` meant to PRE-FILL a `StructureQuestion`.

Isolated from the deterministic layer so the deterministic tests never touch
the SDK (D-04) — this module is the only place a Claude call for *structure*
(as opposed to column *meaning*, which is `mapping/mapper.py`'s job) is
made. No function here applies a hint or returns a resolved `RawTable`: the
human's confirmation is the only thing that ever resolves structure (D-02).
"""

from __future__ import annotations

import datetime

import anthropic

from .hint import StructuralHint, TableShape
from .structure.layout import KeyValueBlock, LayoutKind, SheetLayout
from .structure_schema import WireStructureProposal

_MODEL = "claude-opus-4-8"
_MAX_TOKENS = 4096

#: The evidence-grid bounds (D-12-14, locked): the judge's cost is capped no
#: matter how large the file, and both driving sheets fit entirely.
_GRID_MAX_ROWS = 20
_GRID_MAX_COLS = 10

#: The string-length buckets of the redacted grid (D-12-17): a raw length is
#: a side channel, and the bucket keeps the discriminative power — labels
#: cluster short, free text clusters long.
_STR_SHORT_MAX = 8
_STR_MED_MAX = 24

_SYSTEM_PROMPT = """\
You are the structural-assist engine of Data Ingestor, a tool that ingests \
messy data files. Every vendor formats its file differently: banner rows \
above the real header, multiple sheets where only one holds the data, or a \
table shaped as a wide matrix or transposed layout instead of one row per \
record. You are given raw evidence rows from a file whose structure a \
deterministic heuristic could not resolve confidently, and your job is to \
propose the single most likely reading.

Two non-negotiable rules:
1. Propose, never decide. Your answer only PRE-FILLS a question a human \
will confirm or correct — it is never applied automatically.
2. Never guess silently. If you are unsure between two readings, offer \
ranked alternatives with their own confidence instead of a bare guess, and \
set your overall confidence honestly low rather than inflating it.
"""


def propose_structure(
    evidence: str, client: anthropic.Anthropic | None = None
) -> StructuralHint:
    """Ask Claude for a structural reading of `evidence` and return it as a
    hint meant to pre-fill a `StructureQuestion.proposal` (D-01 layer 2).

    This function only ever builds a `StructuralHint` for pre-filling a
    question — no code path here applies it or returns a resolved table
    (D-02). A missing API key surfaces as `anthropic.AuthenticationError`
    from the SDK; the caller decides how to report it (mirrors
    `mapping/mapper.py::propose_mapping`'s existing contract).
    """
    client = client or anthropic.Anthropic()
    response = client.messages.parse(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": evidence}],
        output_format=WireStructureProposal,
    )
    wire = response.parsed_output
    if wire is None:
        raise ValueError(
            "Structure proposal failed: the model returned no structured "
            f"proposal (stop reason: {response.stop_reason})."
        )
    return _to_domain(wire)


def render_evidence_grid(
    sheet_name: str,
    rows: list[tuple],
    *,
    max_rows: int = _GRID_MAX_ROWS,
    max_cols: int = _GRID_MAX_COLS,
    headers_only: bool,
) -> str:
    """Render one sheet's bounded evidence grid for the layout judge.

    This is the phase's FOURTH `headers_only` enforcement site (after the
    mapper's render branch, the CLI's skip, and the wire model's emptied
    example values). There is no central privacy choke point in this
    codebase (D-12-06), so the signature is made to be one: `headers_only`
    is a REQUIRED keyword with no default — a future call site that forgets
    to answer the privacy question is a `TypeError`, never a silent leak.

    `headers_only=False` renders the REAL cell values, because the label
    words are the strongest key-value signal (D-12-09). `headers_only=True`
    renders each cell as its TYPE only — `blank` / `num` / `date` /
    `str:short` / `str:med` / `str:long` (D-12-04, bucketed per D-12-17 so
    not even a string's exact length leaves the server).

    Row and column indices are rendered visibly (`R0:`, `C0`) because the
    verdict returns indices — the model must SEE the indices it names. The
    true-dimensions line always renders, so a truncated view is never
    mistaken for the whole sheet.
    """
    n_rows = len(rows)
    n_cols = max((len(row) for row in rows), default=0)
    shown_rows = min(n_rows, max_rows)
    shown_cols = min(n_cols, max_cols)
    lines = [
        f"Sheet {_one_line(sheet_name)!r}: this sheet is {n_rows} rows x "
        f"{n_cols} cols; showing the first {shown_rows} x {shown_cols}",
        "Columns: " + " | ".join(f"C{i}" for i in range(shown_cols)),
    ]
    for index, row in enumerate(rows[:max_rows]):
        cells = [
            _render_cell(cell, headers_only=headers_only) for cell in row[:max_cols]
        ]
        lines.append(f"R{index}: " + " | ".join(cells))
    return "\n".join(lines)


def _render_cell(cell, *, headers_only: bool) -> str:
    """One grid cell, newline-collapsed so it cannot escape its bullet and
    read as a top-level instruction (the `mapper._one_line` hazard), and —
    under `headers_only` — reduced to its type bucket, never its value."""
    text = "" if cell is None else _one_line(cell)
    if not text:
        return "blank"
    if not headers_only:
        return text
    if isinstance(cell, (int, float)) and not isinstance(cell, bool):
        return "num"
    if isinstance(cell, bool):
        return "num"
    if isinstance(cell, (datetime.date, datetime.datetime)):
        return "date"
    return _bucket_string_length(len(text))


def _bucket_string_length(length: int) -> str:
    """The D-12-17 buckets: `str:short` <=8 / `str:med` 9-24 / `str:long` 25+.
    Length is measured AFTER whitespace collapse, so padding cannot shift a
    cell's bucket."""
    if length <= _STR_SHORT_MAX:
        return "str:short"
    if length <= _STR_MED_MAX:
        return "str:med"
    return "str:long"


def _one_line(text) -> str:
    """Collapse any run of whitespace — newlines included — into one space."""
    return " ".join(str(text).split())


def _to_domain_verdicts(
    wire, sheet_names: list[str], grid_dims: dict[str, tuple[int, int]]
) -> dict[str, SheetLayout]:
    """Map the judge's wire verdicts onto `SheetLayout`s at the boundary —
    the SECOND closure, after the runtime `Literal` (a boundary closed once
    is a boundary closed by luck).

    Two invented rules, both fail-closed (D-12-14), and their consequence:
    an out-of-grid verdict becomes an honest question, not a crash and not
    a guess.

      * CLAMP: every integer index is checked against the sheet's REAL grid
        (`grid_dims` maps sheet name -> (n_rows, n_cols)). An out-of-grid
        index turns that one sheet's verdict into UNKNOWN — never an
        `IndexError`, and never a clamped-but-kept verdict, because a
        "repaired" wrong index is still a wrong verdict.
      * FILL: a sheet the model omitted (or answered for under an invented
        name, which is dropped) is filled with UNKNOWN — a forgotten sheet
        must ask, never default to an ordinary row-per-record reading.

    The returned dict has exactly one `SheetLayout` per input sheet name,
    always, in `sheet_names` order. Duplicate verdicts for one sheet keep
    the first and drop the rest; confidence is clamped into [0, 1].
    """
    real = set(sheet_names)
    kept: dict[str, SheetLayout] = {}
    for verdict in wire.sheets:
        name = verdict.sheet_name
        if name not in real or name in kept:
            continue
        kept[name] = _one_verdict_to_domain(verdict, grid_dims.get(name, (0, 0)))
    omitted = SheetLayout(
        kind=LayoutKind.UNKNOWN,
        confidence=0.0,
        reasoning=(
            "The model returned no verdict for this sheet — it asks instead "
            "of defaulting to an ordinary reading."
        ),
    )
    return {name: kept.get(name, omitted) for name in sheet_names}


def _one_verdict_to_domain(verdict, dims: tuple[int, int]) -> SheetLayout:
    """One wire verdict -> one `SheetLayout`, or UNKNOWN when any index does
    not fit the sheet's real grid."""
    rejected = _rejected_index(verdict, dims)
    if rejected is not None:
        n_rows, n_cols = dims
        return SheetLayout(
            kind=LayoutKind.UNKNOWN,
            confidence=0.0,
            reasoning=(
                f"The proposed layout named {rejected}, which does not fit "
                f"this sheet's real {n_rows} x {n_cols} grid — the verdict "
                "was discarded, so this sheet asks instead of guessing."
            ),
        )
    return SheetLayout(
        kind=LayoutKind(verdict.kind),
        confidence=min(1.0, max(0.0, verdict.confidence)),
        reasoning=verdict.reasoning,
        header_row_index=verdict.header_row_index,
        first_data_row=verdict.first_data_row,
        last_data_row=verdict.last_data_row,
        key_value_blocks=tuple(
            KeyValueBlock(
                label_column=block.label_column,
                value_columns=tuple(block.value_columns),
                first_row=block.first_row,
                last_row=block.last_row,
            )
            for block in verdict.key_value_blocks
        ),
        one_record_per_value_column=verdict.one_record_per_value_column,
    )


def _rejected_index(verdict, dims: tuple[int, int]) -> str | None:
    """Name the first index that does not fit the real grid, or `None` when
    every index fits. Negative, past-the-edge, and inverted ranges are all
    rejections — each is a verdict about a grid that does not exist."""
    n_rows, n_cols = dims

    def row_ok(index: int) -> bool:
        return 0 <= index < n_rows

    def col_ok(index: int) -> bool:
        return 0 <= index < n_cols

    for field in ("header_row_index", "first_data_row", "last_data_row"):
        value = getattr(verdict, field)
        if value is not None and not row_ok(value):
            return f"{field} {value}"
    if (
        verdict.first_data_row is not None
        and verdict.last_data_row is not None
        and verdict.first_data_row > verdict.last_data_row
    ):
        return (
            f"an inverted data-row range (first_data_row "
            f"{verdict.first_data_row} after last_data_row "
            f"{verdict.last_data_row})"
        )
    for block in verdict.key_value_blocks:
        if not col_ok(block.label_column):
            return f"label_column {block.label_column}"
        for column in block.value_columns:
            if not col_ok(column):
                return f"value_columns entry {column}"
        if not row_ok(block.first_row):
            return f"first_row {block.first_row}"
        if not row_ok(block.last_row):
            return f"last_row {block.last_row}"
        if block.first_row > block.last_row:
            return (
                f"an inverted block row range (first_row {block.first_row} "
                f"after last_row {block.last_row})"
            )
    return None


def _to_domain(wire: WireStructureProposal) -> StructuralHint:
    """Map the validated wire model onto a `StructuralHint` at the boundary.

    This is the sole conversion `propose_structure` calls — it only ever
    returns a hint meant to pre-fill a question (D-02); nothing here
    resolves or applies structure.
    """
    return StructuralHint(
        sheet_name=wire.sheet_name,
        header_row_index=wire.header_row_index,
        decimal_separator=wire.decimal_separator,
        data_region=wire.data_region,
        table_shape=TableShape(wire.table_shape),
    )
