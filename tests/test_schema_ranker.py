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


# ===========================================================================
# Stage 3, wired: Claude is the scorer's LAST resort, never its first
# ===========================================================================
#
# `service.propose_schemas_for_sheet` runs the two deterministic stages, and
# ONLY when both return zero coverage across EVERY Schema does it reach the
# ranker. Every test below either proves that ordering or proves that the
# ranker's absence or failure degrades to "propose skip" — never to a broken
# manifest, and never to a human blocked by an LLM outage.

from assayingest import service  # noqa: E402
from assayingest.learning.seed import seed_schema_aliases, seed_schemas  # noqa: E402

# The headers of the acceptance fixtures, as `describe_sheets` resolves them.
# Repeated as literals so a parser regression cannot make a wiring test pass.
ZEPHYR_WEEK_1 = ["Compound ID", "Assay", "Result", "Units", "Protein Target", "Replicates", "Run Date"]
MERIDIAN_LEGEND = ["CMP", "compound identifier"]

#: Headers no seeded Schema covers at all — the ONLY condition under which any
#: LLM call is spent on the Schema choice.
UNCOVERED_HEADERS = ["timepoint", "aliquot barcode", "freezer shelf ref"]


@pytest.fixture
def seeded_schemas(schema_store):
    """The shipped Schemas WITH the starter crosswalk of plan 11-02, sourced the
    one legal way (D-11-23): `SchemaStore.list_schemas()`."""
    seed_schemas(schema_store)
    seed_schema_aliases(schema_store)
    return schema_store.list_schemas()


def _explode_rank(*_args, **_kwargs):
    raise AssertionError(
        "the ranker must NOT be called: a Schema already has deterministic "
        "coverage for this sheet (D-11-19 — Claude is stage 3, not stage 1)"
    )


def _recording_ranker(result: tuple[RankedSchema, ...]):
    calls: list[dict] = []

    def _fn(headers, schemas, *, sheet_name=None):
        calls.append({"headers": headers, "schemas": schemas, "sheet_name": sheet_name})
        return result

    return _fn, calls


_SUGGESTS_POTENCY = (RankedSchema(schema_name="assay-potency", reason="the headers read like a run log", rank=1),)


# --- ANY coverage anywhere means ZERO Claude calls -------------------------


def test_a_sheet_any_schema_covers_costs_zero_claude_calls(seeded_schemas):
    """The load-bearing ordering of D-11-19, pinned with an exploding ranker:
    the deterministic pass resolves zephyr's headers, so no call is ever made."""
    proposals = service.propose_schemas_for_sheet(
        ZEPHYR_WEEK_1, seeded_schemas, None, rank_fn=_explode_rank
    )

    assert proposals[0].score == 1.0
    assert proposals[0].source == "crosswalk"


def test_a_single_incidental_hit_is_still_coverage_and_still_costs_nothing(seeded_schemas):
    """D-11-24, pinned: meridian's LEGEND scores 1/7 (`CMP` is a real starter
    spelling). The escalation rule is LITERAL — exactly zero coverage, nothing
    else — so a 1/7 sheet is resolved, not escalated. There is no threshold here
    and none is coming."""
    proposals = service.propose_schemas_for_sheet(
        MERIDIAN_LEGEND, seeded_schemas, None, rank_fn=_explode_rank
    )

    assert proposals[0].score == pytest.approx(1 / 7)
    assert proposals[0].source == "crosswalk"


# --- zero coverage EVERYWHERE escalates, exactly once ----------------------


def test_zero_coverage_everywhere_calls_the_ranker_exactly_once(seeded_schemas):
    rank_fn, calls = _recording_ranker(_SUGGESTS_POTENCY)

    service.propose_schemas_for_sheet(
        UNCOVERED_HEADERS, seeded_schemas, None, rank_fn=rank_fn, sheet_name="Logistics"
    )

    assert len(calls) == 1
    assert calls[0]["headers"] == UNCOVERED_HEADERS
    assert calls[0]["sheet_name"] == "Logistics"
    assert [s.name for s in calls[0]["schemas"]] == [s.name for s in seeded_schemas]


def test_the_escalated_proposal_is_labelled_claude_and_claims_no_evidence(seeded_schemas):
    """The human is entitled to know a proposal has NO crosswalk evidence behind
    it. `source="claude"` says so; `matched={}` refuses to invent evidence; every
    field is honestly uncovered."""
    rank_fn, _ = _recording_ranker(_SUGGESTS_POTENCY)

    proposals = service.propose_schemas_for_sheet(
        UNCOVERED_HEADERS, seeded_schemas, None, rank_fn=rank_fn
    )

    potency = next(s for s in seeded_schemas if s.name == "assay-potency")
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.schema_name == "assay-potency"
    assert proposal.source == "claude"
    assert proposal.matched == {}
    assert set(proposal.uncovered) == {cf.field.name for cf in potency.fields}
    assert proposal.total == len(potency.fields)
    assert proposal.score == 0.0


def test_the_escalated_proposal_carries_claudes_reason_for_the_panel(seeded_schemas):
    """The UI-SPEC's line — "No crosswalk match — Claude suggests {schema}. Check
    it before ingesting." — needs the WHY, or it asks the human to check
    something they cannot see."""
    rank_fn, _ = _recording_ranker(_SUGGESTS_POTENCY)

    proposals = service.propose_schemas_for_sheet(
        UNCOVERED_HEADERS, seeded_schemas, None, rank_fn=rank_fn
    )

    assert proposals[0].reason == "the headers read like a run log"


def test_only_the_top_ranked_schema_becomes_the_proposal(seeded_schemas):
    """A ranking with no evidence behind it is a suggestion, not a shortlist.
    One suggestion is checkable; four ranked guesses are a menu of guesses."""
    rank_fn, _ = _recording_ranker(
        (
            RankedSchema(schema_name="pk-parameters", reason="best fit", rank=1),
            RankedSchema(schema_name="assay-potency", reason="second", rank=2),
        )
    )

    proposals = service.propose_schemas_for_sheet(
        UNCOVERED_HEADERS, seeded_schemas, None, rank_fn=rank_fn
    )

    assert [p.schema_name for p in proposals] == ["pk-parameters"]


def test_a_claude_sourced_proposal_still_auto_applies_nothing(seeded_schemas):
    """D-11-06 is UNCHANGED by this plan. There is no `selected`, no `confident`,
    no `auto_apply` on the proposal — the human confirms every sheet, and a
    Claude-sourced proposal is the LAST one that should ever be trusted blind."""
    rank_fn, _ = _recording_ranker(_SUGGESTS_POTENCY)

    proposal = service.propose_schemas_for_sheet(
        UNCOVERED_HEADERS, seeded_schemas, None, rank_fn=rank_fn
    )[0]

    for verdict in ("selected", "confident", "auto_apply", "apply", "winner"):
        assert not hasattr(proposal, verdict)


def test_a_ranker_naming_a_schema_that_is_not_governed_yields_no_proposal(seeded_schemas):
    """The ranker module closes this at its own boundary, and the service closes
    it again: a Schema the service cannot resolve in the governed set has no
    fields to count and no proposal to make. It is dropped, never repaired."""
    rank_fn, _ = _recording_ranker(
        (RankedSchema(schema_name="a-schema-that-does-not-exist", reason="invented", rank=1),)
    )

    assert service.propose_schemas_for_sheet(UNCOVERED_HEADERS, seeded_schemas, None, rank_fn=rank_fn) == ()


# --- absence and failure both degrade to "propose skip" (T-11-16) ----------


def test_with_no_client_and_no_ranker_a_zero_coverage_sheet_proposes_skip(seeded_schemas):
    """A missing API key must never break the sheet question. No ranker is
    available, so the honest answer is the one the deterministic stages already
    gave: no proposal — propose skip."""
    assert service.propose_schemas_for_sheet(UNCOVERED_HEADERS, seeded_schemas, None) == ()


def test_a_raising_ranker_degrades_to_propose_skip_and_never_raises(seeded_schemas):
    """An LLM outage costs the human a SUGGESTION, never their ability to choose.
    The sheet question still stands; the manifest still builds."""

    def _api_error(*_args, **_kwargs):
        raise RuntimeError("the API is down")

    assert service.propose_schemas_for_sheet(UNCOVERED_HEADERS, seeded_schemas, None, rank_fn=_api_error) == ()


def test_a_client_alone_reaches_the_real_ranker_with_that_client(monkeypatch, seeded_schemas):
    """`rank_fn` is the TEST seam; a `client` is the production route. Supplying
    a client and no `rank_fn` must reach `schema_ranker.propose_schema_ranking`
    with that very client."""
    seen: dict = {}
    sentinel = object()

    def _spy(headers, schemas, *, client=None, sheet_name=None):
        seen["client"] = client
        seen["headers"] = headers
        seen["sheet_name"] = sheet_name
        return _SUGGESTS_POTENCY

    monkeypatch.setattr(service, "propose_schema_ranking", _spy)

    proposals = service.propose_schemas_for_sheet(
        UNCOVERED_HEADERS, seeded_schemas, None, client=sentinel, sheet_name="Logistics"
    )

    assert seen["client"] is sentinel
    assert seen["headers"] == UNCOVERED_HEADERS
    assert seen["sheet_name"] == "Logistics"
    assert proposals[0].source == "claude"


def test_a_sheet_with_no_headers_never_escalates(seeded_schemas):
    """orion's `Notes`: no header row could be resolved. There is nothing for
    Claude to rank FROM, so no call is spent asking it to guess from nothing."""
    assert service.propose_schemas_for_sheet([], seeded_schemas, None, rank_fn=_explode_rank) == ()


def test_no_governed_schema_never_escalates():
    """Nothing to rank. The escalation is about which Schema fits — with none
    defined, the question does not exist."""
    assert service.propose_schemas_for_sheet(UNCOVERED_HEADERS, [], None, rank_fn=_explode_rank) == ()
