"""Claude structural-assist — a PROPOSAL only, never applied (D-01 layer 2).

This is the second of the three structure-resolution layers (D-01): when the
deterministic heuristics in `parsing/structure/` are not confident, this
module asks Claude for its best reading of the raw-grid evidence and maps
the answer onto a `StructuralHint` meant to PRE-FILL a `StructureQuestion`.

Isolated from the deterministic layer so the deterministic tests never touch
the SDK (D-04) — this module is the only place a Claude call for *structure*
(as opposed to column *meaning*, which is `mapping/mapper.py`'s job) is
made: `propose_structure` answers one unresolved structural question, and
`judge_workbook_layout` answers a whole workbook's layout in one batched
call (D-12-14). No function here applies a hint or returns a resolved
`RawTable`: the human's confirmation is the only thing that ever resolves
structure (D-02).
"""

from __future__ import annotations

import datetime

import anthropic

from .hint import StructuralHint, TableShape
from .structure.layout import KeyValueBlock, LayoutKind, SheetLayout, TableBlock
from .structure_schema import WireStructureProposal, build_workbook_layout_wire_model

_MODEL = "claude-opus-4-8"
_MAX_TOKENS = 4096

#: The evidence-grid bounds (D-12-14, locked): the judge's cost is capped no
#: matter how large the file, and both driving sheets fit entirely.
#: How much of a sheet the judge is shown. It was 20 rows, and that was not a
#: cost decision so much as a blindfold: sequoia_cmp stacks four panels down one
#: worksheet with header rows at 10, 20, 30 and 40, so a 20-row window showed the
#: judge the first table and the first section heading and NOTHING else. It
#: answered "one table with a preamble", which was the only answer its evidence
#: supported — and four tables were then read as one, putting the word 'Unts'
#: under a field that allows H or L. A verdict about a sheet's structure cannot
#: be reached from a window that cannot contain the structure. 60 rows covers the
#: stacked-panel report this exists for; beyond that the header line still says
#: how many rows the sheet really has, so a truncated view is never mistaken for
#: the whole sheet.
_GRID_MAX_ROWS = 60
_GRID_MAX_COLS = 10

#: How many times the judge may be asked about one workbook before the sheets it
#: still has not named are left to ask the human.
#:
#: The batched call names each sheet by a string, and on an 8-sheet workbook the
#: model was observed answering for one sheet TWICE and for another NOT AT ALL
#: (`cascade_allergy`: two `Patient Info` verdicts, no `IgE Results` verdict).
#: The boundary handled that exactly as it should -- the duplicate was dropped
#: and the unnamed sheet became an honest UNKNOWN -- but the consequence landed
#: on the curator: a sheet with no verdict has no header row, therefore no
#: headers, therefore no Schema proposal, and the screen said nothing about the
#: real, readable table sitting in it.
#:
#: So a sheet the model never NAMED is asked about again, alone with the others
#: it forgot, where there is no list of names to lose track of. Round 2 is not a
#: retry of a FAILED call (an outage still raises, unretried, on the first round)
#: -- it is the same question asked about a shorter list. An honest `unknown`
#: verdict and a verdict rejected by the clamp are ANSWERS: they are never
#: re-asked, because re-asking a model that fairly said "I cannot tell" until it
#: says something else is how a guess gets manufactured.
_JUDGE_MAX_ROUNDS = 2

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


_JUDGE_SYSTEM_PROMPT = """\
You are the layout judge of a tool that ingests messy tabular files. Every
vendor formats its file differently: a worksheet can be an ordinary table, a
labels-down-the-side cover block, a wide matrix, several stacked tables, or
not a table at all. You are shown one bounded evidence grid per worksheet of
a single workbook, with visible row and column indices and each sheet's true
dimensions, and you return one layout verdict per worksheet.

A row_per_record sheet has one column per FIELD and one row per RECORD. A
key_value sheet has one column of FIELD NAMES and one (or more) column(s) of
their values — a patient cover sheet, a specimen header, a methodology
block. The tell is that column A reads as a list of field names (Patient
Name, MRN, Collected), not as a list of records.

A real lab sheet usually surrounds its data table with things that are NOT
data: a title banner, a key-value cover block naming the patient and the
specimen, section headings, a footer of notes or disclaimers. NONE of that
makes the sheet multiple_tables. If the sheet contains exactly ONE table of
records, report row_per_record, name its header row in header_row_index, and
fence its records with first_data_row / last_data_row so everything above and
below is skipped. That is what those fields are FOR — a sheet is not
unreadable merely because a table has a preamble.

Reserve multiple_tables for a sheet that genuinely holds TWO OR MORE tables OF
RECORDS, each with its own header row and its own rows beneath it. A cover
block plus one results table is ONE table with a preamble, not two tables.

THE TEST that separates the two cases is whether a later row introduces a
DIFFERENT SET OF COLUMN NAMES. A section heading ('Renal Function' alone in
column A) interrupts a table but does not restart it — the columns underneath
are still the same columns. A row that names columns AGAIN, differently ('Test |
Result | Flag | Units' up top, then 'Analyte | Value | Units | Ref Lo | Ref Hi'
further down), is a SECOND TABLE: its column 2 means something different from
the first table's column 2. Read as one table, the second header row arrives as
DATA and its words land under the first table's columns — the word 'Units' ends
up in a field that only allows H or L. Scan the WHOLE grid you are shown for
these repeat header rows before settling on row_per_record.

When the sheet is multiple_tables, fill `tables` with every table, in grid
order, each fenced by its own header_row_index / first_data_row / last_data_row.
Each of them will be offered to the human as a separate dataset, so fence them
exactly: a table's last_data_row is the row before the next table's section
heading or header row.

Give each table its title_row_index too: the row of the section heading it sits
under, the lone label above its header row that names the panel. That heading is
what the CURATOR calls this table, so a table that has one must never be
presented to them as a bare row range. Name the ROW; the tool reads the words.

A sheet with no content at all is not_a_table.

Three non-negotiable rules:
1. Propose, never decide. Each verdict only PRE-FILLS a question a human
will confirm or correct — it is never applied automatically.
2. Never guess silently. 'unknown' is a valid, honest answer and is far
better than a plausible layout you cannot justify from the grid. Say why,
naming the row and column indices that led you there.
3. You return indices, never cell contents. Every value is read from the
file by the tool itself; your verdict names positions only.

You are shown each worksheet's bounded evidence grid and nothing else.
Answer for every worksheet listed.
"""

_JUDGE_REDACTED_NOTICE = (
    "Cell contents have been replaced by their types. Judge the layout from "
    "the type pattern alone; do not ask for the values.\n"
)


def judge_workbook_layout(
    grids: dict[str, list[tuple]],
    client: anthropic.Anthropic | None = None,
    *,
    headers_only: bool,
) -> dict[str, SheetLayout]:
    """Ask Claude for every sheet's layout verdict in ONE batched call and
    return one `SheetLayout` per sheet — a proposal, never an application.

    One call per workbook, not one per sheet (D-12-14): the cost is latency,
    not dollars, and sequential calls would sit in front of the sheet
    screen. The boundary is closed twice — `sheet_name` is a runtime
    `Literal` over the REAL sheet names at the SDK boundary, and
    `_to_domain_verdicts` clamps every index against the real grid and fills
    every omission with UNKNOWN on the way in.

    `headers_only` is a REQUIRED keyword, forwarded to every rendered grid
    (D-12-06: there is no central privacy choke point, so this call site
    enforces the guarantee itself). A missing API key surfaces as
    `anthropic.AuthenticationError` from the SDK, and a missing verdict as
    `ValueError` — no retry and no logging here: availability degradation
    is the CALLER's boundary, and this function raises, it does not log.

    A sheet the model does not NAME at all is asked about again — alone with the
    other sheets it forgot (`_JUDGE_MAX_ROUNDS`) — because a forgotten sheet is
    not a judgement, and a curator paid for it in headers they never got. What
    the model DID answer is never re-asked, honest `unknown` included.
    """
    if not grids:
        return {}
    client = client or anthropic.Anthropic()
    answered: dict[str, SheetLayout] = {}
    pending = dict(grids)
    for _ in range(_JUDGE_MAX_ROUNDS):
        answered.update(_judged_round(pending, client, headers_only=headers_only))
        pending = {
            name: rows for name, rows in pending.items() if name not in answered
        }
        if not pending:
            break
    return {name: answered.get(name, _omitted_verdict()) for name in grids}


def _judged_round(
    grids: dict[str, list[tuple]], client: anthropic.Anthropic, *, headers_only: bool
) -> dict[str, SheetLayout]:
    """One batched call, and a layout for exactly the sheets the model NAMED —
    no UNKNOWN fill, so the caller can tell "the model said it cannot tell" (an
    answer) from "the model never mentioned this sheet" (a lost question)."""
    sheet_names = list(grids)
    rendered = "\n\n".join(
        render_evidence_grid(name, rows, headers_only=headers_only)
        for name, rows in grids.items()
    )
    response = client.messages.parse(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_render_judge_system_prompt(headers_only=headers_only),
        messages=[
            {
                "role": "user",
                "content": f"Workbook: {len(sheet_names)} worksheets.\n\n{rendered}\n",
            }
        ],
        output_format=build_workbook_layout_wire_model(sheet_names),
    )
    wire = response.parsed_output
    if wire is None:
        raise ValueError(
            "No layout verdict was produced for the workbook: the model "
            "returned no structured proposal "
            f"(stop reason: {response.stop_reason})."
        )
    grid_dims = {
        name: (len(rows), max((len(row) for row in rows), default=0))
        for name, rows in grids.items()
    }
    return _named_verdicts(wire, sheet_names, grid_dims)


def _render_judge_system_prompt(*, headers_only: bool) -> str:
    """The judge's system prompt: three non-negotiable rules plus the
    definitional row_per_record vs key_value line Python could not draw —
    and, only under `headers_only`, the notice that contents were replaced
    by types (D-12-04)."""
    if headers_only:
        return _JUDGE_SYSTEM_PROMPT + "\n" + _JUDGE_REDACTED_NOTICE
    return _JUDGE_SYSTEM_PROMPT


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

    FILL is the last word, and `judge_workbook_layout` gets to ask again before
    it is spoken: the two halves are `_named_verdicts` (CLAMP, the answers) and
    `_omitted_verdict` (FILL, the silence), so a caller can tell them apart.
    """
    named = _named_verdicts(wire, sheet_names, grid_dims)
    return {name: named.get(name, _omitted_verdict()) for name in sheet_names}


def _named_verdicts(
    wire, sheet_names: list[str], grid_dims: dict[str, tuple[int, int]]
) -> dict[str, SheetLayout]:
    """The CLAMP half: one `SheetLayout` per sheet the model actually NAMED (a
    duplicate name keeps the first verdict; an invented one is dropped), each
    already checked against its sheet's real grid.

    A sheet missing from the result is a sheet the model never spoke about —
    which is not the same claim as `unknown`, and is why this half exists apart
    from the fill."""
    real = set(sheet_names)
    kept: dict[str, SheetLayout] = {}
    for verdict in wire.sheets:
        name = verdict.sheet_name
        if name not in real or name in kept:
            continue
        kept[name] = _one_verdict_to_domain(verdict, grid_dims.get(name, (0, 0)))
    return kept


def _omitted_verdict() -> SheetLayout:
    """The FILL half: what a sheet the model never named is worth — a question,
    never an ordinary row-per-record reading."""
    return SheetLayout(
        kind=LayoutKind.UNKNOWN,
        confidence=0.0,
        reasoning=(
            "The model returned no verdict for this sheet — it asks instead "
            "of defaulting to an ordinary reading."
        ),
    )


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
        tables=tuple(
            TableBlock(
                header_row_index=table.header_row_index,
                first_data_row=table.first_data_row,
                last_data_row=table.last_data_row,
                title_row_index=table.title_row_index,
            )
            for table in getattr(verdict, "tables", ())
        ),
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
    for index, table in enumerate(getattr(verdict, "tables", ())):
        for field in ("header_row_index", "first_data_row", "last_data_row"):
            value = getattr(table, field)
            if not row_ok(value):
                return f"table {index}'s {field} {value}"
        title = table.title_row_index
        if title is not None and not row_ok(title):
            return f"table {index}'s title_row_index {title}"
        if table.first_data_row > table.last_data_row:
            return (
                f"table {index}'s inverted data-row range (first_data_row "
                f"{table.first_data_row} after last_data_row "
                f"{table.last_data_row})"
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
