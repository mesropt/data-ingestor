"""Confirms `_MAX_TOKENS = 16000` holds for a real 50-field response.

Closes 02-RESEARCH.md's Open Question 1: the response *payload* size was
estimated analytically (~6,700 tokens worst case) but adaptive-thinking
token spend at `effort: "high"` was never measured against a real call, per
the research protocol's "no live billed API call" constraint. This is the
ONLY test in the phase permitted to issue a billed API call, and it issues
exactly one.

Skips cleanly without `ANTHROPIC_API_KEY`, exactly like the existing live
test idiom (`test_cli_run.py`) -- the offline suite must never depend on
credentials.
"""

import os

import anthropic
import pytest

from assayingest.fields.models import Field, FieldSet
from assayingest.mapping.mapper import _MAX_TOKENS, _MODEL, _render_request, _render_system_prompt, _to_domain
from assayingest.mapping.schema import build_wire_models
from assayingest.parsing.table import RawTable

#: The CONTEXT.md-mandated cap (D-04) -- if 50 fields ever truncates, that
#: is exactly the scenario D-04's error-before-any-schema exists to prevent
#: from happening silently, so this must be known to hold, not assumed.
_FIFTY_FIELD_SET = FieldSet(
    fields=tuple(
        Field(name=f"field_{i:02d}", description=f"Synthetic field number {i}.")
        for i in range(1, 51)
    )
)

_TABLE = RawTable(
    headers=["Compound", "Value", "Unit", "Date"],
    rows=[
        ["A-1", "12.5", "nM", "01/01/2025"],
        ["A-2", "8.75", "nM", "02/01/2025"],
    ],
    source_name="synthetic_50_field_probe.csv",
)


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="live 50-field token-budget probe requires ANTHROPIC_API_KEY",
)
def test_fifty_field_response_does_not_truncate_at_max_tokens():
    assert len(_FIFTY_FIELD_SET.fields) == 50

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_render_system_prompt(_FIFTY_FIELD_SET),
        messages=[
            {"role": "user", "content": _render_request(_TABLE, _FIFTY_FIELD_SET)}
        ],
        output_format=build_wire_models(_FIFTY_FIELD_SET.field_names),
    )

    assert response.stop_reason != "max_tokens", (
        f"_MAX_TOKENS={_MAX_TOKENS} truncated a real 50-field response "
        f"(stop_reason={response.stop_reason!r}) -- raise the constant."
    )
    assert response.parsed_output is not None

    # Same boundary mapping propose_mapping() uses internally -- proves the
    # public contract, not just the raw SDK call, holds at 50 fields.
    proposal = _to_domain(response.parsed_output, _TABLE.headers, list(_FIFTY_FIELD_SET.field_names))
    assert len(proposal.field_mappings) == 50
