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

import anthropic

from .hint import StructuralHint, TableShape
from .structure_schema import WireStructureProposal

_MODEL = "claude-opus-4-8"
_MAX_TOKENS = 4096

_SYSTEM_PROMPT = """\
You are the structural-assist engine of AssayIngest, a tool that ingests \
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
