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
