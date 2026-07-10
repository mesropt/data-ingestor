"""Claude structural-assist — the wire→domain boundary, exercised entirely
with a fake client (D-04: no real SDK call, no API key needed for these
tests). D-02's "never auto-applies" invariant is asserted directly: the
enrichment seam only ever pre-fills `StructureQuestion.proposal`."""

from __future__ import annotations

import dataclasses

import anthropic
import httpx
import pytest

from assayingest.parsing.hint import StructuralHint, StructureQuestion, TableShape
from assayingest.parsing.structure_assist import _to_domain, propose_structure
from assayingest.parsing.structure_schema import (
    WireStructureCandidate,
    WireStructureProposal,
)


class _FakeParsedResponse:
    def __init__(self, parsed_output, stop_reason="end_turn"):
        self.parsed_output = parsed_output
        self.stop_reason = stop_reason


class _FakeMessages:
    def __init__(self, parsed_output):
        self._parsed_output = parsed_output

    def parse(self, **kwargs):
        return _FakeParsedResponse(self._parsed_output)


class _FakeClient:
    """Stands in for `anthropic.Anthropic()` — never touches the network."""

    def __init__(self, parsed_output):
        self.messages = _FakeMessages(parsed_output)


def test_propose_structure_maps_wire_proposal_to_structural_hint_via_fake_client(
    monkeypatch,
):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    wire = WireStructureProposal(
        header_row_index=4,
        sheet_name=None,
        table_shape="row_per_record",
        confidence=0.8,
        reasoning="Row 4 is the only row that is all-string and unique.",
    )
    fake = _FakeClient(wire)

    hint = propose_structure(evidence="raw grid evidence here", client=fake)

    assert isinstance(hint, StructuralHint)
    assert hint.header_row_index == 4
    assert hint.table_shape is TableShape.ROW_PER_RECORD


def test_propose_structure_raises_value_error_when_parsed_output_is_none():
    fake = _FakeClient(None)

    with pytest.raises(ValueError, match="no structured proposal"):
        propose_structure(evidence="ambiguous evidence", client=fake)


def test_propose_structure_never_constructs_a_real_anthropic_client(monkeypatch):
    """D-04 seam: passing a fake client means `anthropic.Anthropic()` is never
    instantiated, so this test needs no credentials at all."""

    def _boom(*args, **kwargs):
        raise AssertionError("propose_structure must not construct a real client")

    monkeypatch.setattr(anthropic, "Anthropic", _boom)
    fake = _FakeClient(
        WireStructureProposal(
            header_row_index=None,
            sheet_name="Summary",
            table_shape="row_per_record",
            confidence=0.9,
            reasoning="Summary is the only tidy, wide sheet.",
        )
    )

    hint = propose_structure(evidence="evidence", client=fake)

    assert hint.sheet_name == "Summary"


def test_to_domain_maps_every_structural_hint_field():
    wire = WireStructureProposal(
        header_row_index=2,
        sheet_name="DATA",
        table_shape="transposed",
        decimal_separator=",",
        data_region="A3:G10",
        confidence=0.6,
        reasoning="Row homogeneity exceeds column homogeneity.",
        alternatives=[
            WireStructureCandidate(header_row_index=1, confidence=0.3),
        ],
    )

    hint = _to_domain(wire)

    assert hint == StructuralHint(
        sheet_name="DATA",
        header_row_index=2,
        decimal_separator=",",
        data_region="A3:G10",
        table_shape=TableShape.TRANSPOSED,
    )


def test_structure_assist_module_exposes_no_apply_or_raw_table_function():
    """D-02: this module may only ever build a pre-fill hint — it must never
    expose a function that applies a hint or resolves a table itself."""
    import assayingest.parsing.structure_assist as structure_assist

    public_names = [n for n in dir(structure_assist) if not n.startswith("_")]
    forbidden_substrings = ("apply", "resolve", "raw_table")
    for name in public_names:
        lowered = name.lower()
        assert not any(bad in lowered for bad in forbidden_substrings), (
            f"structure_assist.{name} looks like it applies/resolves structure, "
            "which D-02 forbids in this module"
        )


def test_enriching_a_not_confident_question_never_auto_resolves_it(monkeypatch):
    """D-02: even a confident Claude answer only pre-fills the question —
    resolving structure still requires an explicit human-confirmed hint."""
    from assayingest.cli import _enrich_question

    question = StructureQuestion(
        unsure_about="which row is the real header",
        reason="No candidate row scored clearly ahead of the others.",
        confidence=0.5,
        proposal=StructuralHint(header_row_index=0),
        evidence_rows=[["banner"], ["ZB-100", "Ki", "32.051"]],
    )
    fake = _FakeClient(
        WireStructureProposal(
            header_row_index=4,
            sheet_name=None,
            table_shape="row_per_record",
            confidence=0.95,
            reasoning="Row 4 is confidently the header.",
        )
    )

    enriched = _enrich_question(question, client=fake)

    assert isinstance(enriched, StructureQuestion)
    assert enriched.proposal.header_row_index == 4
    # Still just a pre-filled question — nothing resolves structure by itself.
    assert not hasattr(enriched, "resolved_table")


def test_enrich_question_degrades_gracefully_with_no_client_and_no_credentials(
    monkeypatch,
):
    """D-04: no client and no configured credentials must never crash, and
    must never attempt a real SDK call — the deterministic question is
    returned unchanged."""
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    def _boom(*args, **kwargs):
        raise AssertionError("no client/credentials must mean no SDK call at all")

    monkeypatch.setattr(anthropic, "Anthropic", _boom)
    from assayingest.cli import _enrich_question

    question = StructureQuestion(
        unsure_about="which sheet holds the data",
        reason="Summary and Raw timepoints both look equally data-like.",
        confidence=0.5,
        proposal=StructuralHint(sheet_name="Summary"),
    )

    enriched = _enrich_question(question, client=None)

    assert enriched == question


def test_enrich_question_degrades_gracefully_on_authentication_error():
    """D-04/T-01-10: an SDK auth failure must degrade, not crash the CLI."""
    from assayingest.cli import _enrich_question

    class _RejectingMessages:
        def parse(self, **kwargs):
            response = httpx.Response(
                401,
                request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
            )
            raise anthropic.AuthenticationError("bad key", response=response, body=None)

    class _RejectingClient:
        def __init__(self):
            self.messages = _RejectingMessages()

    question = StructureQuestion(
        unsure_about="which row is the real header",
        reason="No candidate row scored clearly ahead of the others.",
        confidence=0.5,
    )

    enriched = _enrich_question(question, client=_RejectingClient())

    assert enriched == question
