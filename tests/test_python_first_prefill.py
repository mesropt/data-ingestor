"""INGEST-02 (D-10-02/03): the deterministic Python-first alias pre-fill that
runs BEFORE any Claude call, plus the Schema -> FieldSet adapter (D-10-02)
that makes a governed Schema's canonical fields the mapper's target fields.

Escalation order under test: profile auto-apply (existing, strictly
strongest) -> Python crosswalk pre-fill (new) -> Claude on whatever remains
-> the human (existing amber gate, unchanged). Every scenario here runs with
`service.propose_mapping` monkeypatched or spied -- no live Claude call, the
same idiom `tests/test_reconcile_service.py` established for the reconcile
pass this generalizes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from assayingest import service
from assayingest.domain.models import (
    Alias,
    CanonicalField,
    FieldMapping,
    MappingProposal,
    Schema,
)
from assayingest.fields.models import Field, FieldSet
from assayingest.learning.profile import LearnedProfile
from assayingest.learning.reconstruct import stored_mapping_from
from assayingest.learning.signature import column_signature
from assayingest.parsing.table import RawTable

_TS = "2026-01-01T00:00:00+00:00"


# --- builders ------------------------------------------------------------


def _alias(vendor: str, source_column: str) -> Alias:
    return Alias(
        vendor=vendor, source_column=source_column, provenance_kind="manual",
        provenance_actor="curator@example.com", created_at=_TS,
    )


def _schema(field_aliases: dict[str, list[Alias]], *, name: str = "assay") -> Schema:
    fields = tuple(
        CanonicalField(field=Field(name=fname), aliases=tuple(aliases))
        for fname, aliases in field_aliases.items()
    )
    return Schema(id="s1", name=name, fields=fields, created_by=None, created_at=_TS)


def _table(headers: list[str], rows: list[list[str]] | None = None) -> RawTable:
    return RawTable(headers=headers, rows=rows or [], source_name="upload.csv")


def _fieldset(*names: str) -> FieldSet:
    return FieldSet(name="assay", fields=tuple(Field(name=n) for n in names))


def _mapper_returning(recorder: list[str] | None = None):
    """A fake propose_mapping_fn recording which field names it was asked to
    map, returning a clear (unmapped) FieldMapping for each."""

    def _fn(table, field_set, client=None, *, headers_only=False):
        asked = field_set.field_names
        if recorder is not None:
            recorder.extend(asked)
        return MappingProposal(
            source_columns=list(table.headers),
            field_mappings=[
                FieldMapping(
                    target_field=name, source_column=None, confidence=0.8,
                    reasoning="claude filled the remainder", needs_confirmation=False,
                )
                for name in asked
            ],
        )

    return _fn


# --- field_set_from_schema (D-10-02) --------------------------------------


def test_field_set_from_schema_derives_fields_and_name():
    schema = _schema({"compound_id": [], "value": []}, name="assay-potency")

    field_set = service.field_set_from_schema(schema)

    assert field_set.name == "assay-potency"
    assert field_set.field_names == ["compound_id", "value"]


def test_field_set_from_schema_signature_matches_the_originally_promoted_field_set(schema_store):
    original = FieldSet(
        name="assay-potency",
        fields=(Field(name="compound_id"), Field(name="value", type="number")),
    )
    schema = service.promote(original, created_by="curator@example.com", store=schema_store)
    schema_store.add_alias(schema.id, "compound_id", _alias("acme", "cmpd"))
    schema = schema_store.get_schema(schema.id)

    derived = service.field_set_from_schema(schema)

    assert derived.signature == original.signature  # an existing learned profile still matches


def test_field_set_from_schema_excludes_a_tombstoned_field_and_the_signature_changes(schema_store):
    """Intended, not a bug: removing a canonical field genuinely changes the
    target field set, so a profile learned against the OLD set correctly
    stops matching -- documented explicitly, per the plan's own instruction."""
    original = FieldSet(
        name="assay-potency",
        fields=(Field(name="compound_id"), Field(name="value", type="number")),
    )
    schema = service.promote(original, created_by="curator@example.com", store=schema_store)
    schema_store.remove_field(schema.id, "value", removed_by="curator@example.com", removed_at=_TS)
    schema = schema_store.get_schema(schema.id)

    derived = service.field_set_from_schema(schema)

    assert derived.field_names == ["compound_id"]
    assert derived.signature != original.signature


# --- _vendor_agnostic_alias_index -----------------------------------------


def test_vendor_agnostic_index_matches_a_normalised_header_regardless_of_vendor():
    schema = _schema({"compound_id": [_alias("acme", "cmpd")]})

    index = service._vendor_agnostic_alias_index(schema)

    assert index["cmpd"] == "compound_id"


def test_vendor_agnostic_index_collides_to_none_when_two_vendors_disagree():
    schema = _schema(
        {
            "compound_id": [_alias("acme", "cmpd")],
            "value": [_alias("othervendor", "cmpd")],
        }
    )

    index = service._vendor_agnostic_alias_index(schema)

    assert index["cmpd"] is None  # never guess which vendor is right


def test_vendor_agnostic_index_does_not_collide_when_two_vendors_agree_on_the_same_field():
    schema = _schema(
        {"compound_id": [_alias("acme", "cmpd"), _alias("othervendor", "cmpd")]}
    )

    index = service._vendor_agnostic_alias_index(schema)

    assert index["cmpd"] == "compound_id"


def test_vendor_agnostic_index_excludes_a_tombstoned_alias(schema_store):
    field_set = FieldSet(name="assay", fields=(Field(name="compound_id"),))
    schema = service.promote(field_set, created_by="curator@example.com", store=schema_store)
    schema_store.add_alias(schema.id, "compound_id", _alias("acme", "cmpd"))
    schema_store.remove_alias(
        schema.id, "compound_id", "acme", "cmpd",
        removed_by="curator@example.com", removed_at=_TS,
    )
    schema = schema_store.get_schema(schema.id)

    index = service._vendor_agnostic_alias_index(schema)

    assert "cmpd" not in index  # a tombstoned alias never resurrects


# --- the pre-fill itself: zero/partial/no Claude calls (the money shot) ---


def test_full_crosswalk_coverage_calls_the_mapper_zero_times():
    schema = _schema(
        {"compound_id": [_alias("acme", "cmpd")], "value": [_alias("acme", "potency")]}
    )
    table = _table(["cmpd", "potency"])
    field_set = _fieldset("compound_id", "value")

    def _explode(*args, **kwargs):
        raise AssertionError("propose_mapping must NOT be called: every field is crosswalked")

    proposal, escalation = service._python_first_prefill(
        table, field_set, schema, headers_only=False, client=None, propose_mapping_fn=_explode,
    )

    assert escalation.python_matched == 2
    assert escalation.claude_matched == 0
    assert escalation.total == 2
    assert {m.target_field: m.source_column for m in proposal.field_mappings} == {
        "compound_id": "cmpd", "value": "potency",
    }
    assert all(m.confidence == 1.0 and not m.needs_confirmation for m in proposal.field_mappings)


def test_partial_crosswalk_coverage_sends_claude_only_the_uncovered_fields():
    schema = _schema({"compound_id": [_alias("acme", "cmpd")]})
    table = _table(["cmpd", "potency"])
    field_set = _fieldset("compound_id", "value")
    asked: list[str] = []

    proposal, escalation = service._python_first_prefill(
        table, field_set, schema, headers_only=False, client=None,
        propose_mapping_fn=_mapper_returning(asked),
    )

    assert asked == ["value"]  # mapper never asked for the pre-filled compound_id
    assert escalation.python_matched == 1
    assert escalation.claude_matched == 1
    assert escalation.total == 2
    by_field = {m.target_field: m for m in proposal.field_mappings}
    assert by_field["compound_id"].source_column == "cmpd"
    assert by_field["compound_id"].confidence == 1.0


def test_no_crosswalk_coverage_sends_claude_the_full_field_set():
    schema = _schema({"compound_id": [_alias("othervendor", "cmpd")]})
    table = _table(["cmpd", "potency"])
    field_set = _fieldset("compound_id", "value")
    asked: list[str] = []

    proposal, escalation = service._python_first_prefill(
        table, field_set, schema, headers_only=False, client=None,
        propose_mapping_fn=_mapper_returning(asked),
    )

    assert sorted(asked) == ["compound_id", "value"]
    assert escalation.python_matched == 0
    assert escalation.claude_matched == 2


def test_prefilled_mapping_carries_confidence_one_and_names_the_crosswalk():
    schema = _schema({"compound_id": [_alias("acme", "cmpd")]})
    table = _table(["cmpd", "potency"])
    field_set = _fieldset("compound_id", "value")

    proposal, _ = service._python_first_prefill(
        table, field_set, schema, headers_only=False, client=None,
        propose_mapping_fn=_mapper_returning(),
    )

    compound = {m.target_field: m for m in proposal.field_mappings}["compound_id"]
    assert compound.confidence == 1.0
    assert compound.needs_confirmation is False
    assert "crosswalk" in compound.reasoning


def test_a_collided_header_falls_through_to_claude_unresolved():
    schema = _schema(
        {
            "compound_id": [_alias("acme", "cmpd")],
            "value": [_alias("othervendor", "cmpd")],
        }
    )
    table = _table(["cmpd"])
    field_set = _fieldset("compound_id", "value")
    asked: list[str] = []

    proposal, escalation = service._python_first_prefill(
        table, field_set, schema, headers_only=False, client=None,
        propose_mapping_fn=_mapper_returning(asked),
    )

    assert sorted(asked) == ["compound_id", "value"]  # collision -- never guessed
    assert escalation.python_matched == 0


def test_headers_only_is_irrelevant_to_the_prefill_matching_is_by_name_alone():
    schema = _schema({"compound_id": [_alias("acme", "cmpd")]})
    table = _table(["cmpd", "potency"], rows=[])  # headers only, no cell values
    field_set = _fieldset("compound_id", "value")

    proposal, _ = service._python_first_prefill(
        table, field_set, schema, headers_only=True, client=None,
        propose_mapping_fn=_mapper_returning(),
    )

    covered = {m.target_field: m for m in proposal.field_mappings}["compound_id"]
    assert covered.source_column == "cmpd"
    assert covered.confidence == 1.0


# --- resolve_table_mapping(schema=...) wiring -----------------------------


def test_resolve_table_mapping_with_schema_short_circuits_the_mapper_when_fully_covered(monkeypatch):
    schema = _schema(
        {"compound_id": [_alias("acme", "cmpd")], "value": [_alias("acme", "potency")]}
    )
    table = _table(["cmpd", "potency"])
    field_set = _fieldset("compound_id", "value")

    calls = {"n": 0}

    def _explode(*args, **kwargs):
        calls["n"] += 1
        raise AssertionError("propose_mapping must not be called")

    monkeypatch.setattr(service, "propose_mapping", _explode)

    proposal, provenance, profile_id = service.resolve_table_mapping(
        table, field_set, None, schema=schema,
    )

    assert calls["n"] == 0
    assert provenance == service._PROVENANCE_PYTHON_FIRST
    assert profile_id is None
    assert {m.target_field: m.source_column for m in proposal.field_mappings} == {
        "compound_id": "cmpd", "value": "potency",
    }


def test_resolve_table_mapping_with_schema_partial_coverage_provenance_is_fresh_claude(monkeypatch):
    schema = _schema({"compound_id": [_alias("acme", "cmpd")]})
    table = _table(["cmpd", "potency"])
    field_set = _fieldset("compound_id", "value")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(service, "propose_mapping", _mapper_returning())

    proposal, provenance, profile_id = service.resolve_table_mapping(
        table, field_set, None, schema=schema,
    )

    assert provenance == service._PROVENANCE_FRESH_CLAUDE


def test_resolve_table_mapping_without_schema_is_unchanged(monkeypatch):
    """BACKWARD COMPATIBILITY: omitting `schema` entirely (the CLI's own call
    site, and every existing test) reaches the plain fresh-Claude branch on
    the FULL field set, exactly as before."""
    table = _table(["cmpd", "potency"])
    field_set = _fieldset("compound_id", "value")
    asked: list[str] = []

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(service, "propose_mapping", _mapper_returning(asked))

    proposal, provenance, profile_id = service.resolve_table_mapping(table, field_set, None)

    assert sorted(asked) == ["compound_id", "value"]
    assert provenance == service._PROVENANCE_FRESH_CLAUDE


# --- composition with the profile store (Assumption A3) -------------------


def test_profile_auto_apply_still_wins_over_the_python_pass_and_claude(monkeypatch, profile_store):
    field_set = _fieldset("compound_id", "value")
    schema = _schema(
        {"compound_id": [_alias("acme", "cmpd")], "value": [_alias("acme", "potency")]}
    )
    table = _table(["cmpd", "potency"])

    ready = MappingProposal(
        source_columns=table.headers,
        field_mappings=[
            FieldMapping(
                target_field="compound_id", source_column="cmpd", confidence=1.0,
                reasoning="learned profile", needs_confirmation=False,
            ),
            FieldMapping(
                target_field="value", source_column="potency", confidence=1.0,
                reasoning="learned profile", needs_confirmation=False,
            ),
        ],
    )
    profile = LearnedProfile(
        profile_id="profile-1",
        field_set_signature=field_set.signature,
        column_signature=column_signature(table.headers),
        field_mappings=tuple(
            stored_mapping_from(m, table.headers) for m in ready.field_mappings
        ),
        structural_hint=None,
        created_at=_TS,
    )
    profile_store.save(profile)

    calls = {"n": 0}

    def _explode(*args, **kwargs):
        calls["n"] += 1
        raise AssertionError("propose_mapping must NOT be called: the profile wins")

    monkeypatch.setattr(service, "propose_mapping", _explode)

    proposal, provenance, profile_id = service.resolve_table_mapping(
        table, field_set, profile_store, schema=schema,
    )

    assert calls["n"] == 0
    assert provenance == "auto-applied-from-profile"
    assert profile_id == "profile-1"


# --- tests/test_reconcile_service.py's own reconcile path stays untouched -


def test_reconcile_map_function_itself_is_never_touched_by_this_plan():
    """Sanity pin: `_reconcile_map`/`_alias_index` are untouched by this
    plan (D-07-04 augment-only invariant) -- the new Python-first pass lives
    BESIDE them, never through them."""
    assert hasattr(service, "_reconcile_map")
    assert hasattr(service, "_alias_index")
    assert hasattr(service, "_python_first_prefill")
    assert service._python_first_prefill is not service._reconcile_map


# --- resolve_or_map: escalation counts end-to-end --------------------------


def test_resolve_or_map_reports_python_and_claude_escalation_counts(tmp_path, monkeypatch):
    csv_path = tmp_path / "upload.csv"
    csv_path.write_text("cmpd,potency,extra1,extra2\nNVS-1,12.5,a,b\n", encoding="utf-8")

    schema = _schema({"compound_id": [_alias("acme", "cmpd")]})
    field_set = FieldSet(
        name="assay",
        fields=(
            Field(name="compound_id"), Field(name="value"),
            Field(name="e1"), Field(name="e2"),
        ),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(service, "propose_mapping", _mapper_returning())

    result = service.resolve_or_map(str(csv_path), field_set, store=None, schema=schema)

    assert result.escalation is not None
    assert result.escalation.python_matched == 1
    assert result.escalation.claude_matched == 3
    assert result.escalation.total == 4


def test_resolve_or_map_escalation_is_none_without_a_schema(tmp_path, monkeypatch):
    """BACKWARD COMPATIBILITY: no `schema` -> no escalation to report."""
    csv_path = tmp_path / "upload.csv"
    csv_path.write_text("cmpd,potency\nNVS-1,12.5\n", encoding="utf-8")
    field_set = FieldSet(name="assay", fields=(Field(name="compound_id"), Field(name="value")))

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(service, "propose_mapping", _mapper_returning())

    result = service.resolve_or_map(str(csv_path), field_set, store=None)

    assert result.escalation is None
