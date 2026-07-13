"""SHEET-05: rank the governed Schemas for ONE sheet's headers, in pure
Python, and SAY WHY.

Today the human must pick a Schema from a dropdown BEFORE upload -- file
unparsed, no header yet seen. This scorer inverts the order: parse first,
propose per sheet second, human confirms third. It is a composition of
functions that already exist and are already tested (`_covered_fields`,
`_vendor_agnostic_alias_index`, `field_set_from_schema`, `ProfileStore.find`,
`column_signature`) -- so what these tests pin is the CONTRACT, not the
matching, which `tests/test_python_first_prefill.py` already owns.

Four properties every test here defends, and none of them are negotiable:

  * ZERO CLAUDE CALLS. This is stage 1-2 of D-11-19's ladder; Claude is
    stage 3 and belongs to plan 11-05. Every scenario runs with
    `service.propose_mapping` monkeypatched to an exploding stub -- the same
    proof idiom `tests/test_python_first_prefill.py:180` established.
  * HEADERS ONLY (D-11-04). The scorer's input is a `list[str]`. There is no
    `RawTable` parameter, so there is no cell value it could read even by
    accident, and `headers_only` cannot change its answer.
  * NO THRESHOLD (D-11-06). Zero coverage proposes SKIP -- never the least-bad
    Schema. A tie is returned AS a tie and the scorer breaks it for nobody.
    Deliberately unlike `rank_sheets`'s `_CONFIDENCE_MARGIN`: there is no
    number to tune here and therefore none to get wrong.
  * NO TOMBSTONE RESURRECTION (D-11-23). Schemas reach the scorer only as
    objects the caller got from `SchemaStore`, whose tombstone filter is
    structural -- so a removed field or alias cannot reappear in a proposal.
    Mirrors `tests/api/test_upload_schema_target.py:186/:209` against the
    scorer's own read path.

The four synthetic workbooks are the acceptance fixtures (11-CONTEXT.md): the
starter crosswalk seeded in plan 11-02 is what makes their headers score at
all, so a green run here is also the proof that 11-02 landed.
"""

from __future__ import annotations

import pytest

from assayingest import service
from assayingest.domain.models import Alias, CanonicalField, Schema
from assayingest.fields.models import Field, FieldSet
from assayingest.learning.profile import LearnedProfile
from assayingest.learning.reconstruct import stored_mapping_from
from assayingest.learning.seed import seed_schema_aliases, seed_schemas
from assayingest.learning.signature import column_signature
from assayingest.domain.models import FieldMapping

_TS = "2026-01-01T00:00:00+00:00"

# The headers of each acceptance fixture's sheets, as `describe_sheets` resolves
# them (pinned by `tests/test_structure_describe_sheets.py`). Repeated here as
# literals so THIS file tests the scorer alone -- a parser regression must not
# be able to make a scorer test pass.
ZEPHYR_WEEK_1 = ["Compound ID", "Assay", "Result", "Units", "Protein Target", "Replicates", "Run Date"]
DELTA_EGFR = ["Compound", "IC50 (nM)", "Reps", "Date"]
DELTA_JAK2 = ["Cmpd ID", "IC50 nM", "# runs", "Tested on"]
DELTA_BRAF = ["compound_id", "ic50_nm", "n", "date"]
MERIDIAN_DATA = ["CMP", "ASY", "VAL", "UOM", "TGT", "NREP", "DT"]
MERIDIAN_LEGEND = ["CMP", "compound identifier"]


# --- builders --------------------------------------------------------------


def _alias(vendor: str, source_column: str) -> Alias:
    return Alias(
        vendor=vendor, source_column=source_column, provenance_kind="manual",
        provenance_actor="curator@example.com", created_at=_TS,
    )


def _schema(field_aliases: dict[str, list[Alias]], *, name: str, schema_id: str | None = None) -> Schema:
    fields = tuple(
        CanonicalField(field=Field(name=fname), aliases=tuple(aliases))
        for fname, aliases in field_aliases.items()
    )
    return Schema(
        id=schema_id or f"id-{name}", name=name, fields=fields, created_by=None, created_at=_TS,
    )


@pytest.fixture(autouse=True)
def _no_claude(monkeypatch):
    """AUTOUSE, and the load-bearing guard of this whole file: the scorer is
    PURE PYTHON. Any Claude call from any test here fails the run."""

    def _explode(*_args, **_kwargs):
        raise AssertionError(
            "propose_mapping must NOT be called: the Schema scorer is pure Python "
            "(Claude is stage 3, D-11-19, and belongs to plan 11-05)"
        )

    monkeypatch.setattr(service, "propose_mapping", _explode)


@pytest.fixture
def seeded_schemas(schema_store):
    """The four shipped Schemas WITH the starter crosswalk of plan 11-02,
    sourced the one legal way (D-11-23): `SchemaStore.list_schemas()`."""
    seed_schemas(schema_store)
    seed_schema_aliases(schema_store)
    return schema_store.list_schemas()


def _by_name(proposals) -> dict[str, service.SchemaProposal]:
    return {p.schema_name: p for p in proposals}


# --- the coverage is SHOWN, not just the verdict ---------------------------


def test_the_proposal_names_which_field_matched_which_header(seeded_schemas):
    """The builder's "6/7 canonical fields matched" made checkable: the human
    is being asked to check the tool's reasoning, and cannot check what is not
    shown."""
    proposals = service.propose_schemas_for_sheet(DELTA_EGFR, seeded_schemas, None)

    potency = _by_name(proposals)["assay-potency"]
    assert potency.matched == {
        "compound_id": "Compound",
        "value": "IC50 (nM)",
        "n_replicates": "Reps",
        "assay_date": "Date",
    }
    assert potency.uncovered == ("assay_type", "unit", "target")
    assert potency.total == 7
    assert potency.score == pytest.approx(4 / 7)
    assert potency.source == "crosswalk"


def test_the_uncovered_fields_and_the_matched_fields_partition_the_schema(seeded_schemas):
    for proposal in service.propose_schemas_for_sheet(DELTA_EGFR, seeded_schemas, None):
        assert len(proposal.matched) + len(proposal.uncovered) == proposal.total
        assert set(proposal.matched) & set(proposal.uncovered) == set()


def test_the_best_schema_ranks_first(seeded_schemas):
    proposals = service.propose_schemas_for_sheet(DELTA_EGFR, seeded_schemas, None)

    assert proposals[0].schema_name == "assay-potency"
    assert proposals[0].score > proposals[-1].score


def test_a_fully_covered_sheet_scores_1_0(seeded_schemas):
    """zephyr Week 1 -- every one of assay-potency's seven canonical fields is
    matched by a header the lab actually wrote. The money shot, in Python, with
    no Claude call at all."""
    potency = _by_name(service.propose_schemas_for_sheet(ZEPHYR_WEEK_1, seeded_schemas, None))["assay-potency"]

    assert potency.score == 1.0
    assert potency.uncovered == ()
    assert potency.matched["target"] == "Protein Target"


@pytest.mark.parametrize("headers", [DELTA_EGFR, DELTA_JAK2, DELTA_BRAF])
def test_delta_each_panels_own_spelling_resolves_to_the_same_canonical_fields(headers, seeded_schemas):
    """One sheet per target, a DIFFERENT header spelling on each -- the
    crosswalk resolves all three onto the same four canonical fields. This is
    the per-sheet-proposal case the phase exists for."""
    potency = _by_name(service.propose_schemas_for_sheet(headers, seeded_schemas, None))["assay-potency"]

    assert set(potency.matched) == {"compound_id", "value", "n_replicates", "assay_date"}


# --- stage 1 (learned profile) beats stage 2 (crosswalk) -- D-11-05 ---------


def test_a_learned_profile_hit_ranks_first_and_says_so(profile_store, seeded_schemas):
    """A confirmed profile for THIS exact column signature is the strongest
    evidence there is: it ranks above every crosswalk match, whatever their
    raw coverage."""
    potency = next(s for s in seeded_schemas if s.name == "pk-parameters")
    field_set = service.field_set_from_schema(potency)
    headers = ZEPHYR_WEEK_1  # scores 7/7 on assay-potency, ~1/8 on pk-parameters
    profile_store.save(
        LearnedProfile(
            profile_id="profile-1",
            field_set_signature=field_set.signature,
            column_signature=column_signature(headers),
            field_mappings=(
                stored_mapping_from(
                    FieldMapping(
                        target_field="compound_id", source_column="Compound ID",
                        confidence=1.0, reasoning="learned", needs_confirmation=False,
                    ),
                    headers,
                ),
            ),
            structural_hint=None,
            created_at=_TS,
        )
    )

    proposals = service.propose_schemas_for_sheet(headers, seeded_schemas, profile_store)

    assert proposals[0].schema_name == "pk-parameters"
    assert proposals[0].source == "profile"
    assert proposals[0].matched == {"compound_id": "Compound ID"}
    # ...ahead of a crosswalk match with STRICTLY HIGHER raw coverage:
    assert proposals[1].schema_name == "assay-potency"
    assert proposals[1].source == "crosswalk"
    assert proposals[1].score > proposals[0].score


def test_without_a_store_every_proposal_is_a_crosswalk_one(seeded_schemas):
    """`store=None` degrades gracefully to the stages that remain meaningful,
    never raising -- `recall_vendor`'s own posture."""
    proposals = service.propose_schemas_for_sheet(ZEPHYR_WEEK_1, seeded_schemas, None)

    assert {p.source for p in proposals} == {"crosswalk"}


def test_a_profile_for_a_different_column_signature_does_not_hit(profile_store, seeded_schemas):
    potency = next(s for s in seeded_schemas if s.name == "pk-parameters")
    field_set = service.field_set_from_schema(potency)
    profile_store.save(
        LearnedProfile(
            profile_id="profile-1",
            field_set_signature=field_set.signature,
            column_signature=column_signature(["a totally different column list"]),
            field_mappings=(),
            structural_hint=None,
            created_at=_TS,
        )
    )

    proposals = service.propose_schemas_for_sheet(ZEPHYR_WEEK_1, seeded_schemas, profile_store)

    assert proposals[0].schema_name == "assay-potency"
    assert {p.source for p in proposals} == {"crosswalk"}


# --- zero coverage proposes SKIP -- never the least-bad Schema (D-11-06) ----


def test_zero_coverage_everywhere_returns_no_proposal_at_all(seeded_schemas):
    """THE CONTRACT: an empty tuple means "no Schema fits this sheet, propose
    skip". Nothing is force-mapped onto the least-bad Schema, and no Schema is
    returned with a 0.0 score to be mistaken for a candidate."""
    proposals = service.propose_schemas_for_sheet(
        ["timepoint", "aliquot barcode", "freezer shelf ref"], seeded_schemas, None
    )

    assert proposals == ()


def test_a_sheet_with_no_headers_at_all_returns_no_proposal(seeded_schemas):
    """orion's `Notes` sheet: no header row could be resolved, so `headers` is
    `[]`. There is nothing to score, and the honest answer is no proposal --
    not a crash, and not a Schema."""
    assert service.propose_schemas_for_sheet([], seeded_schemas, None) == ()


def test_meridian_legend_is_never_confused_for_the_data_sheet(seeded_schemas):
    """LEGEND is a code table, not data. Its one incidental hit (`CMP` is a
    real starter spelling for `compound_id`) is honestly reported as 1/7 --
    NOT suppressed, because the tool does not get to decide the human cannot
    see it, and NOT auto-applied, because nothing here ever is."""
    legend = _by_name(service.propose_schemas_for_sheet(MERIDIAN_LEGEND, seeded_schemas, None))
    data = _by_name(service.propose_schemas_for_sheet(MERIDIAN_DATA, seeded_schemas, None))

    assert legend["assay-potency"].matched == {"compound_id": "CMP"}
    assert legend["assay-potency"].score == pytest.approx(1 / 7)
    assert data["assay-potency"].score == 1.0
    assert legend["assay-potency"].score < data["assay-potency"].score


# --- a tie is a tie: the scorer breaks it for nobody (D-11-06) --------------


def test_two_equally_covered_schemas_are_both_returned_with_equal_scores():
    left = _schema({"compound_id": [_alias("acme", "cmpd")]}, name="left")
    right = _schema({"compound_id": [_alias("acme", "cmpd")]}, name="right")

    proposals = service.propose_schemas_for_sheet(["cmpd"], [left, right], None)

    assert len(proposals) == 2
    assert proposals[0].score == proposals[1].score  # the tie is DETECTABLE
    assert {p.schema_name for p in proposals} == {"left", "right"}


def test_a_tie_is_ordered_by_name_so_the_ordering_is_stable_not_a_verdict():
    """Two Schemas the evidence cannot separate are ordered alphabetically --
    a deliberately meaningless, stable order. There is no `selected` field on a
    proposal for the scorer to set, so first-in-the-list is a position, never a
    choice (D-11-06: the tool does not break the tie)."""
    right = _schema({"compound_id": [_alias("acme", "cmpd")]}, name="right")
    left = _schema({"compound_id": [_alias("acme", "cmpd")]}, name="left")

    proposals = service.propose_schemas_for_sheet(["cmpd"], [right, left], None)

    assert [p.schema_name for p in proposals] == ["left", "right"]
    assert not any(hasattr(p, "selected") or hasattr(p, "winner") for p in proposals)


def test_there_is_no_threshold_or_confidence_margin_in_the_scorer():
    """D-11-06, pinned as code: `rank_sheets` has a `_CONFIDENCE_MARGIN` to
    tune and therefore to get wrong. This path has none, and a future edit that
    introduces one fails here."""
    source = (service.__file__).replace(".pyc", ".py")
    with open(source, encoding="utf-8") as fh:
        text = fh.read()

    assert "MARGIN" not in text
    assert "THRESHOLD" not in text


# --- tombstones can never resurrect through this new read path (D-11-23) ----


def test_a_tombstoned_field_is_absent_from_total_and_from_uncovered(schema_store):
    """Mirrors `tests/api/test_upload_schema_target.py:186` against the scorer:
    a removed canonical field is not "uncovered", it is GONE -- it must not
    inflate the denominator, and it must never be shown to the human as a field
    the sheet failed to cover."""
    schema = service.promote(
        FieldSet(name="assay-potency", fields=(Field(name="compound_id"), Field(name="target"))),
        created_by="curator@example.com", store=schema_store,
    )
    schema_store.add_alias(schema.id, "compound_id", _alias("acme", "cmpd"))
    schema_store.remove_field(schema.id, "target", removed_by="curator@example.com", removed_at=_TS)

    proposals = service.propose_schemas_for_sheet(["cmpd", "target"], schema_store.list_schemas(), None)

    assert proposals[0].total == 1
    assert proposals[0].uncovered == ()
    assert proposals[0].matched == {"compound_id": "cmpd"}
    assert proposals[0].score == 1.0  # 1/1, not 1/2 -- the removed field is gone, not missing


def test_a_tombstoned_alias_contributes_zero_coverage(schema_store):
    """Mirrors `tests/api/test_upload_schema_target.py:209`: a curator-deleted
    spelling stops matching, and the field it used to cover becomes honestly
    uncovered."""
    schema = service.promote(
        FieldSet(name="assay-potency", fields=(Field(name="compound_id"), Field(name="target"))),
        created_by="curator@example.com", store=schema_store,
    )
    schema_store.add_alias(schema.id, "compound_id", _alias("acme", "cmpd"))
    schema_store.add_alias(schema.id, "target", _alias("acme", "target_gene"))
    schema_store.remove_alias(
        schema.id, "target", "acme", "target_gene",
        removed_by="curator@example.com", removed_at=_TS,
    )

    proposals = service.propose_schemas_for_sheet(["cmpd", "target_gene"], schema_store.list_schemas(), None)

    assert proposals[0].matched == {"compound_id": "cmpd"}
    assert proposals[0].uncovered == ("target",)


def test_the_scorer_cannot_reach_a_schema_except_through_the_store(schema_store):
    """D-11-23's ONE rule, pinned structurally: the scorer takes `Schema`
    OBJECTS. It holds no `SchemaStore`, opens no session, and issues no query
    of its own -- so there is no second read path for a tombstone to slip
    through, by construction rather than by a filter someone must remember."""
    import inspect

    parameters = inspect.signature(service.propose_schemas_for_sheet).parameters

    assert "schemas" in parameters
    assert not any("schema_store" in name for name in parameters)


# --- headers only, and no Claude (the autouse `_no_claude` guard) -----------


def test_the_scorer_takes_headers_and_never_a_table(seeded_schemas):
    """D-11-04, structurally: the input is a `list[str]`. A cell value cannot
    leak into a proposal because no cell value is ever passed in."""
    import inspect

    parameters = inspect.signature(service.propose_schemas_for_sheet).parameters

    assert "headers" in parameters
    assert "table" not in parameters


def test_scoring_every_fixture_sheet_calls_claude_zero_times(seeded_schemas):
    """The autouse `_no_claude` stub raises on any call; scoring every
    acceptance sheet without tripping it IS the proof."""
    for headers in [ZEPHYR_WEEK_1, DELTA_EGFR, DELTA_JAK2, DELTA_BRAF, MERIDIAN_DATA, MERIDIAN_LEGEND, []]:
        service.propose_schemas_for_sheet(headers, seeded_schemas, None)
