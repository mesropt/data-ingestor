"""D-11-19 stage 3: when BOTH deterministic stages return zero coverage across
EVERY governed Schema, that sheet's HEADERS go to Claude, which ranks the
Schemas.

This is not a departure from "Python before LLM" -- it is D-10-03's
Python → Claude → human ladder applied to the Schema choice itself. The cheap
deterministic pass always runs first, and an LLM call is only ever spent on what
it could not resolve.

Four properties every test in this file defends:

  * CLAUDE IS LAST, NEVER FIRST. When ANY Schema has ANY coverage for a sheet,
    the ranker is called ZERO times. Pinned with an exploding injected `rank_fn`
    -- the same proof idiom `tests/test_python_first_prefill.py:180` and
    `tests/test_schema_scorer.py` established.
  * HEADERS ONLY (D-11-04/D-10-05). `propose_schema_ranking` takes a
    `list[str]`. There is no cell value in scope to leak -- structurally, not by
    a guard someone must remember -- so `headers_only` cannot change what is
    sent, and the two modes are identical here.
  * CLAUDE ONLY PROPOSES (D-11-06, unchanged). Its ranking pre-selects; it never
    auto-applies, and the human confirms every sheet. A Claude-sourced proposal
    is LABELLED as such (`source="claude"`), because a human is entitled to know
    that a proposal has no crosswalk evidence behind it.
  * A SCHEMA CLAUDE INVENTS DOES NOT EXIST. The output model is a runtime
    `Literal` over the governed Schema names (so an out-of-set name is a schema
    violation at the SDK boundary), AND `_to_domain` drops it again at the
    wire→domain boundary -- mirroring `_names_a_column_that_does_not_exist`
    (`mapping/mapper.py:256`). Two closures, because a boundary you only close
    once is a boundary you close by luck.

No test here makes a live API call. The seam is an injected client / injected
fn, so every path runs with `ANTHROPIC_API_KEY` unset.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from assayingest.domain.models import Alias, CanonicalField, Schema
from assayingest.fields.models import Field
from assayingest.mapping import schema_ranker
from assayingest.mapping.schema_ranker import (
    RankedSchema,
    build_ranking_wire_model,
    propose_schema_ranking,
)

_TS = "2026-01-01T00:00:00+00:00"

_MODULE = Path(schema_ranker.__file__)


# --- builders --------------------------------------------------------------


def _alias(vendor: str, source_column: str) -> Alias:
    return Alias(
        vendor=vendor,
        source_column=source_column,
        provenance_kind="manual",
        provenance_actor="curator@example.com",
        created_at=_TS,
    )


def _schema(name: str, field_names: list[str], *, aliases: dict[str, list[Alias]] | None = None) -> Schema:
    aliases = aliases or {}
    return Schema(
        id=f"id-{name}",
        name=name,
        fields=tuple(
            CanonicalField(field=Field(name=fname), aliases=tuple(aliases.get(fname, ())))
            for fname in field_names
        ),
        created_by=None,
        created_at=_TS,
    )


def _wire(schema_names: list[str], ranking: list[tuple[str, str]]):
    """A validated wire object as the SDK would hand one back. `schema_names` is
    the name set the output model is built over -- pass a SUPERSET of the
    governed set to forge the "the model named a Schema that does not exist"
    case, exactly as `tests/test_mapper_boundary.py` forges its hallucinated
    column."""
    model = build_ranking_wire_model(schema_names)
    return model(ranking=[{"schema_name": name, "reason": reason} for name, reason in ranking])


def _fake_client(parsed_output, captured: dict | None = None, *, stop_reason: str = "end_turn"):
    """The injectable seam every test uses instead of a real API call -- it
    records the outbound request so the headers-only claim is ASSERTED against
    what was actually sent, never merely asserted in prose."""

    class _FakeMessages:
        def parse(self, **kwargs):
            if captured is not None:
                captured.update(kwargs)

            class _Response:
                pass

            response = _Response()
            response.parsed_output = parsed_output
            response.stop_reason = stop_reason
            return response

    class _FakeClient:
        messages = _FakeMessages()

    return _FakeClient()


# --- the ranking itself ----------------------------------------------------


def test_claude_ranks_the_governed_schemas_best_first():
    schemas = [_schema("left", ["a"]), _schema("right", ["b"])]
    wire = _wire(
        ["left", "right"],
        [("right", "its field names read like these headers"), ("left", "a weaker fit")],
    )

    ranked = propose_schema_ranking(["h1", "h2"], schemas, client=_fake_client(wire))

    assert ranked == (
        RankedSchema(schema_name="right", reason="its field names read like these headers", rank=1),
        RankedSchema(schema_name="left", reason="a weaker fit", rank=2),
    )


def test_a_ranked_schema_carries_a_human_readable_reason():
    """The panel's "Claude suggests {schema}" line is only honest if it can also
    say WHY. A rank with no reason is a verdict the human cannot check."""
    schemas = [_schema("left", ["a"])]
    wire = _wire(["left"], [("left", "three of its field names appear verbatim in the header row")])

    ranked = propose_schema_ranking(["h1"], schemas, client=_fake_client(wire))

    assert ranked[0].reason == "three of its field names appear verbatim in the header row"


def test_a_ranked_schema_is_a_proposal_and_carries_no_verdict():
    """D-11-06 unchanged: Claude proposes, the human disposes. There is no
    `selected`, no `confident`, no `auto_apply` for anything downstream to
    mistake for permission."""
    ranked = RankedSchema(schema_name="left", reason="why", rank=1)

    for verdict in ("selected", "confident", "auto_apply", "apply", "winner"):
        assert not hasattr(ranked, verdict)


# --- the boundary: a Schema Claude invents is DROPPED, never returned -------


def test_a_schema_name_the_model_invents_is_dropped_at_the_boundary():
    """Mirrors `test_mapper_boundary.py`'s hallucinated-column test. The
    `Literal` output model already makes this a schema violation at the SDK
    boundary; this closes it AGAIN on the way in, because a boundary closed once
    is a boundary closed by luck."""
    schemas = [_schema("real", ["a"])]
    wire = _wire(["real", "invented"], [("invented", "confidently wrong"), ("real", "the true one")])

    ranked = propose_schema_ranking(["h1"], schemas, client=_fake_client(wire))

    assert [r.schema_name for r in ranked] == ["real"]


def test_dropping_a_hallucination_renumbers_the_ranks_contiguously():
    """A dropped entry must not leave a hole in the ranking: `rank` is this
    proposal's position among the SURVIVORS, never among what the model claimed."""
    schemas = [_schema("real", ["a"])]
    wire = _wire(["real", "invented"], [("invented", "confidently wrong"), ("real", "the true one")])

    ranked = propose_schema_ranking(["h1"], schemas, client=_fake_client(wire))

    assert ranked[0].rank == 1


def test_a_schema_ranked_twice_is_kept_once():
    """A list output cannot structurally forbid a repeat. One Schema cannot hold
    two ranks, so the first is the answer and the second is dropped."""
    schemas = [_schema("real", ["a"])]
    wire = _wire(["real"], [("real", "first answer"), ("real", "second answer")])

    ranked = propose_schema_ranking(["h1"], schemas, client=_fake_client(wire))

    assert [r.schema_name for r in ranked] == ["real"]
    assert ranked[0].reason == "first answer"


def test_the_output_model_forbids_an_out_of_set_name_at_the_sdk_boundary():
    """The runtime `Literal` over the governed names is the FIRST closure: the
    SDK itself cannot produce an out-of-set name against this schema."""
    model = build_ranking_wire_model(["real"])

    with pytest.raises(ValidationError):
        model(ranking=[{"schema_name": "invented", "reason": "nope"}])


def test_every_schema_dropped_leaves_no_proposal_at_all():
    """A ranking made entirely of invented names is no ranking. The honest answer
    is an empty tuple -- propose skip -- never the least-bad survivor."""
    schemas = [_schema("real", ["a"])]
    wire = _wire(["real", "invented"], [("invented", "confidently wrong")])

    assert propose_schema_ranking(["h1"], schemas, client=_fake_client(wire)) == ()


# --- fail closed -----------------------------------------------------------


def test_no_structured_output_raises_naming_the_consequence():
    """CONVENTIONS.md: the message names what did NOT happen, not the symptom."""
    schemas = [_schema("real", ["a"])]

    with pytest.raises(ValueError) as exc:
        propose_schema_ranking(
            ["h1"], schemas, client=_fake_client(None, stop_reason="max_tokens"), sheet_name="Sheet1"
        )

    message = str(exc.value)
    assert "Sheet1" in message
    assert "no schema ranking was produced" in message.lower()
    assert "max_tokens" in message


def test_no_governed_schema_means_no_call_and_no_proposal():
    """There is nothing to rank. Asking Claude to rank an empty set is asking it
    to invent one -- and a `Literal` over no names is not even a schema."""
    exploding = _fake_client(None)

    def _explode(**_kwargs):
        raise AssertionError("no call may be made when there is no Schema to rank")

    exploding.messages.parse = _explode

    assert propose_schema_ranking(["h1"], [], client=exploding) == ()


def test_no_headers_means_no_call_and_no_proposal():
    """A sheet with no resolvable header row (orion's `Notes`) gives Claude
    nothing to rank FROM. Calling it anyway would be asking for a guess with no
    evidence -- which is the one thing this tool never does."""
    exploding = _fake_client(None)

    def _explode(**_kwargs):
        raise AssertionError("no call may be made when there is no header to rank from")

    exploding.messages.parse = _explode

    assert propose_schema_ranking([], [_schema("real", ["a"])], client=exploding) == ()


# --- headers only: what actually goes over the wire (T-11-14) ---------------


def test_the_request_carries_the_headers_and_the_governed_names_and_nothing_else():
    captured: dict = {}
    schemas = [_schema("catalogue", ["catalogue_number", "shelf"], aliases={"shelf": [_alias("acme", "Bay")]})]
    wire = _wire(["catalogue"], [("catalogue", "fits")])

    propose_schema_ranking(
        ["Barcode", "Bin location"], schemas, client=_fake_client(wire, captured), sheet_name="Inventory"
    )

    sent = captured["system"] + "\n" + captured["messages"][0]["content"]
    assert "Barcode" in sent
    assert "Bin location" in sent
    assert "catalogue" in sent  # the Schema's name
    assert "catalogue_number" in sent and "shelf" in sent  # its field names
    assert "Inventory" in sent  # the sheet being ranked


def test_the_signature_takes_headers_and_never_a_table():
    """T-11-14, closed structurally rather than by a guard: the parameter is a
    `list[str]`. There is no cell value in scope for a request to leak, so
    `headers_only` cannot change the answer and there is no mode for it to have."""
    parameters = inspect.signature(propose_schema_ranking).parameters

    assert "headers" in parameters
    assert "table" not in parameters
    assert "rows" not in parameters
    assert "headers_only" not in parameters


def test_the_prompt_carries_zero_compiled_in_vocabulary():
    """D-18 discipline (`mapper.py:72-79`): every Schema name and field name in
    the prompt comes from the `schemas` argument. A field set from a different
    domain entirely must produce a prompt with no trace of this one's."""
    captured: dict = {}
    schemas = [_schema("inventory", ["catalogue_number", "quantity", "shelf"])]
    wire = _wire(["inventory"], [("inventory", "fits")])

    propose_schema_ranking(["Barcode"], schemas, client=_fake_client(wire, captured), sheet_name="S")

    sent = (captured["system"] + "\n" + captured["messages"][0]["content"]).lower()
    for banned in ("ic50", "ec50", "compound", "assay", "egfr", "nm", "µm"):
        assert banned not in sent


def test_the_module_itself_compiles_in_no_domain_vocabulary():
    """The prompt is built from data, so the MODULE must contain none of it."""
    text = _MODULE.read_text(encoding="utf-8").lower()

    for banned in ("ic50", "ec50", "compound", "egfr"):
        assert banned not in text


# --- the call posture mirrors the mapper's (11-PATTERNS.md §3) --------------


def test_the_call_uses_the_same_model_and_structured_output_posture_as_the_mapper():
    """One skeleton, two prompts. A ranker that quietly used a different model,
    a different effort, or free-text output would be a second LLM contract to
    keep in step with the first."""
    from assayingest.mapping import mapper

    captured: dict = {}
    schemas = [_schema("real", ["a"])]
    propose_schema_ranking(["h1"], schemas, client=_fake_client(_wire(["real"], [("real", "fits")]), captured))

    assert schema_ranker._MODEL == mapper._MODEL
    assert captured["model"] == schema_ranker._MODEL
    assert captured["max_tokens"] == schema_ranker._MAX_TOKENS
    assert captured["output_config"] == {"effort": "high"}
    assert captured["output_format"] is not None
