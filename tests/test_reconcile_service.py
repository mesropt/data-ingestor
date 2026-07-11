"""Reconcile-on-upload CORE — conflict detection, exact-alias pre-fill, and the
`reconcile_or_map` / `apply_reconcile_resolution` orchestration (08-01, TDD RED).

These prove the reconcile layer at the service seam, independent of any route
(08-02 is pure transport wiring):

  * `detect_reconcile_conflicts` flags EXACTLY the alias-target disagreements
    between an uploaded map file and the master Schema — never novel, same-target,
    or different-vendor aliases (RECON-02 core, D-08-02/04);
  * exact `(vendor, source_column)` alias pre-fill maps a covered column at
    confidence 1.0 WITHOUT a Claude call, short-circuits Claude entirely when
    every field is covered (the known-vendor money shot), and works from column
    NAMES alone so headers_only is never regressed (RECON-01, P4);
  * `reconcile_or_map` refuses-and-asks on conflict (mutating nothing) else
    augments → pre-fills → Claude-fills-the-rest → validates into ONE
    MappingProposal; `apply_reconcile_resolution` honours per-conflict
    keep_master / take_map_file for THIS run without overwriting master aliases.

Written test-first per the plan's TDD gate. No live Claude call is ever made —
the mapper seam (`service.propose_mapping`) is always monkeypatched or spied.
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
    ReconcileConflict,
    ReconcileQuestion,
    Schema,
)
from assayingest.fields.models import Field, FieldSet
from assayingest.learning.sqlite_schema_store import SqliteSchemaStore
from assayingest.parsing.table import RawTable

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic"
NOVASCREEN_01 = DATA / "novascreen_batch01.csv"

_TS = "2026-01-01T00:00:00+00:00"


# --- builders ----------------------------------------------------------------


def _alias(vendor: str, source_column: str) -> Alias:
    return Alias(
        vendor=vendor,
        source_column=source_column,
        provenance_kind="from_map_file",
        provenance_actor="map-file-source",
        created_at=_TS,
    )


def _master_schema(field_aliases: dict[str, list[Alias]], *, name: str = "assay") -> Schema:
    """A master Schema built directly from `{field_name: [Alias, ...]}` — no
    store round-trip needed for the pure conflict-detection tests."""
    fields = tuple(
        CanonicalField(field=Field(name=fname), aliases=tuple(aliases))
        for fname, aliases in field_aliases.items()
    )
    return Schema(id="s1", name=name, fields=fields, created_by=None, created_at=_TS)


def _envelope(field_aliases: dict[str, list[Alias]], *, name: str = "assay") -> dict:
    """A Phase-07 master-map JSON envelope (the uploaded map file format)."""
    return {
        "schema_version": 1,
        "id": "e1",
        "name": name,
        "created_by": None,
        "created_at": _TS,
        "fields": [
            {"name": fname, "aliases": [a.to_dict() for a in aliases]}
            for fname, aliases in field_aliases.items()
        ],
    }


# --- Task 1: detect_reconcile_conflicts (RECON-02 core) ----------------------


def test_conflict_when_map_file_alias_targets_a_different_canonical_field():
    master = _master_schema({"value": [_alias("acme", "cmpd")]})
    envelope = _envelope({"compound_id": [_alias("acme", "cmpd")]})

    question = service.detect_reconcile_conflicts(envelope, master)

    assert isinstance(question, ReconcileQuestion)
    assert question.has_conflicts is True
    assert question.conflicts == (
        ReconcileConflict(
            vendor="acme",
            source_column="cmpd",
            master_field="value",
            map_file_field="compound_id",
        ),
    )


def test_no_conflict_when_map_file_alias_matches_the_master_target_exactly():
    master = _master_schema({"compound_id": [_alias("acme", "cmpd")]})
    envelope = _envelope({"compound_id": [_alias("acme", "cmpd")]})

    question = service.detect_reconcile_conflicts(envelope, master)

    assert question.has_conflicts is False
    assert question.conflicts == ()


def test_no_conflict_for_a_novel_pair_the_master_has_never_seen():
    master = _master_schema({"value": [_alias("acme", "potency")]})
    envelope = _envelope({"compound_id": [_alias("acme", "cmpd")]})

    question = service.detect_reconcile_conflicts(envelope, master)

    assert question.has_conflicts is False


def test_no_conflict_when_only_the_vendor_differs_on_the_same_source_column():
    master = _master_schema({"value": [_alias("acme", "cmpd")]})
    envelope = _envelope({"compound_id": [_alias("othervendor", "cmpd")]})

    question = service.detect_reconcile_conflicts(envelope, master)

    assert question.has_conflicts is False


def test_aliasless_envelope_yields_an_empty_reconcile_question():
    master = _master_schema({"value": [_alias("acme", "cmpd")]})
    envelope = _envelope({"compound_id": []})

    question = service.detect_reconcile_conflicts(envelope, master)

    assert question == ReconcileQuestion(())
    assert question.has_conflicts is False


def test_reconcile_conflict_and_question_serialize_to_dict():
    conflict = ReconcileConflict(
        vendor="acme", source_column="cmpd", master_field="value",
        map_file_field="compound_id",
    )
    assert conflict.to_dict() == {
        "vendor": "acme",
        "source_column": "cmpd",
        "master_field": "value",
        "map_file_field": "compound_id",
    }
    assert ReconcileQuestion((conflict,)).to_dict() == {
        "conflicts": [conflict.to_dict()]
    }


# --- Task 2: _reconcile_map exact-alias pre-fill (RECON-01 + money shot) ------


def _schema_with_aliases(field_aliases: dict[str, list[Alias]]) -> Schema:
    """A master Schema whose crosswalk already holds `field_aliases`."""
    return _master_schema(field_aliases)


def _fieldset(*names: str) -> FieldSet:
    return FieldSet(name="assay", fields=tuple(Field(name=n) for n in names))


def _table(headers: list[str], *, rows: list[list[str]] | None = None) -> RawTable:
    return RawTable(headers=headers, rows=rows or [], source_name="upload.csv")


def _mapper_returning(field_names: list[str], recorder: list[str] | None = None):
    """A fake propose_mapping_fn that records which field names it was asked to
    map and returns a clear FieldMapping for each remaining field."""

    def _fn(table, field_set, client=None, *, headers_only=False):
        asked = field_set.field_names
        if recorder is not None:
            recorder.extend(asked)
        return MappingProposal(
            source_columns=list(table.headers),
            field_mappings=[
                FieldMapping(
                    target_field=name,
                    source_column="potency" if name == "value" else None,
                    confidence=0.8,
                    reasoning="claude filled the remainder",
                    needs_confirmation=False,
                )
                for name in asked
            ],
        )

    return _fn


def test_prefill_maps_covered_field_at_confidence_one_and_asks_mapper_for_the_rest():
    schema = _schema_with_aliases({"compound_id": [_alias("acme", "cmpd")]})
    table = _table(["cmpd", "potency"], rows=[["NVS-1", "12.5"]])
    field_set = _fieldset("compound_id", "value")
    asked: list[str] = []

    proposal, provenance = service._reconcile_map(
        table, field_set, schema, "acme",
        headers_only=False, client=None,
        propose_mapping_fn=_mapper_returning(["value"], asked),
    )

    assert provenance == "reconciled-from-crosswalk"
    assert asked == ["value"]  # mapper NEVER asked for the pre-filled compound_id
    by_field = {m.target_field: m for m in proposal.field_mappings}
    assert by_field["compound_id"].source_column == "cmpd"
    assert by_field["compound_id"].confidence == 1.0
    assert by_field["compound_id"].needs_confirmation is False
    assert "acme" in by_field["compound_id"].reasoning
    assert by_field["value"].source_column == "potency"
    # Merged order follows the field set's declared order.
    assert [m.target_field for m in proposal.field_mappings] == ["compound_id", "value"]


def test_short_circuit_never_calls_the_mapper_when_every_field_is_covered():
    schema = _schema_with_aliases(
        {"compound_id": [_alias("acme", "cmpd")], "value": [_alias("acme", "potency")]}
    )
    table = _table(["cmpd", "potency"])
    field_set = _fieldset("compound_id", "value")

    def _explode(*args, **kwargs):
        raise AssertionError("propose_mapping must NOT be called: all fields covered")

    proposal, provenance = service._reconcile_map(
        table, field_set, schema, "acme",
        headers_only=False, client=None, propose_mapping_fn=_explode,
    )

    assert provenance == "reconciled-from-crosswalk"
    assert all(m.confidence == 1.0 and not m.needs_confirmation for m in proposal.field_mappings)
    assert {m.target_field: m.source_column for m in proposal.field_mappings} == {
        "compound_id": "cmpd", "value": "potency",
    }


def test_prefill_headers_only_produces_the_same_result_from_names_alone():
    schema = _schema_with_aliases({"compound_id": [_alias("acme", "cmpd")]})
    table = _table(["cmpd", "potency"], rows=[])  # headers only, no cell values
    field_set = _fieldset("compound_id", "value")

    proposal, _ = service._reconcile_map(
        table, field_set, schema, "acme",
        headers_only=True, client=None,
        propose_mapping_fn=_mapper_returning(["value"]),
    )

    covered = {m.target_field: m for m in proposal.field_mappings}["compound_id"]
    assert covered.source_column == "cmpd"
    assert covered.confidence == 1.0


def test_no_coverage_falls_every_field_through_to_the_mapper():
    schema = _schema_with_aliases({"compound_id": [_alias("othervendor", "cmpd")]})
    table = _table(["cmpd", "potency"])
    field_set = _fieldset("compound_id", "value")
    asked: list[str] = []

    proposal, _ = service._reconcile_map(
        table, field_set, schema, "acme",
        headers_only=False, client=None,
        propose_mapping_fn=_mapper_returning(["compound_id", "value"], asked),
    )

    assert sorted(asked) == ["compound_id", "value"]  # nothing pre-filled
    assert {m.target_field for m in proposal.field_mappings} == {"compound_id", "value"}


def test_prefill_normalisation_matches_case_and_whitespace_variants():
    schema = _schema_with_aliases({"compound_id": [_alias("acme", "cmpd")]})
    table = _table(["  CMPD ", "potency"])  # differs only by case + whitespace
    field_set = _fieldset("compound_id", "value")

    proposal, _ = service._reconcile_map(
        table, field_set, schema, "acme",
        headers_only=False, client=None,
        propose_mapping_fn=_mapper_returning(["value"]),
    )

    covered = {m.target_field: m for m in proposal.field_mappings}["compound_id"]
    assert covered.source_column == "  CMPD "  # original header preserved
    assert covered.confidence == 1.0


# --- Task 3: reconcile_or_map + apply_reconcile_resolution orchestration ------

_SCHEMA_NAME = "assay-potency"


def _seeded_master(tmp_path, *, fields=("compound_id", "value"),
                   master_aliases: dict[str, list[Alias]] | None = None):
    """A tmp-path SqliteSchemaStore promoted to a governed Schema, optionally
    pre-seeded with `master_aliases` (`{field_name: [Alias, ...]}`)."""
    store = SqliteSchemaStore(tmp_path / "profiles.db")
    field_set = FieldSet(name=_SCHEMA_NAME, fields=tuple(Field(name=n) for n in fields))
    service.promote(field_set, created_by="curator@example.com", store=store)
    schema = store.get_schema(_SCHEMA_NAME)
    for field_name, aliases in (master_aliases or {}).items():
        for a in aliases:
            store.add_alias(
                schema.id, field_name,
                Alias(vendor=a.vendor, source_column=a.source_column,
                      provenance_kind="manual", provenance_actor="curator@example.com",
                      created_at=_TS),
            )
    return store, store.get_schema(_SCHEMA_NAME).id


def _clear_value_mapper():
    """A monkeypatch for service.propose_mapping: returns a clear FieldMapping for
    each field the reduced field set asks about (novascreen -> potency/None)."""

    def _fn(table, field_set, client=None, *, headers_only=False):
        return MappingProposal(
            source_columns=list(table.headers),
            field_mappings=[
                FieldMapping(
                    target_field=name,
                    source_column="potency" if name == "value" else None,
                    confidence=0.9, reasoning="claude filled the remainder",
                    needs_confirmation=False,
                )
                for name in field_set.field_names
            ],
        )

    return _fn


def test_reconcile_or_map_returns_reconcile_question_and_mutates_nothing_on_conflict(
    tmp_path, monkeypatch,
):
    store, schema_id = _seeded_master(
        tmp_path=tmp_path, master_aliases={"value": [_alias("acme", "cmpd")]},
    )
    envelope = _envelope({"compound_id": [_alias("acme", "cmpd")]})
    before = store.list_aliases_for(schema_id)

    calls = {"n": 0}

    def _spy(*args, **kwargs):
        calls["n"] += 1
        raise AssertionError("propose_mapping must not run on a conflict")

    monkeypatch.setattr(service, "propose_mapping", _spy)

    result = service.reconcile_or_map(
        str(NOVASCREEN_01),
        FieldSet(name=_SCHEMA_NAME, fields=(Field(name="compound_id"), Field(name="value"))),
        schema_store=store, target_schema_name=_SCHEMA_NAME, vendor="acme",
        envelope=envelope,
    )

    assert isinstance(result, ReconcileQuestion)
    assert result.has_conflicts is True
    assert store.list_aliases_for(schema_id) == before  # nothing augmented
    assert calls["n"] == 0  # nothing mapped


def test_reconcile_or_map_no_conflict_augments_prefills_and_validates(tmp_path, monkeypatch):
    store, schema_id = _seeded_master(tmp_path=tmp_path)
    # Novel, non-conflicting: master has no alias for (acme, cmpd) yet.
    envelope = _envelope({"compound_id": [_alias("acme", "cmpd")]})
    monkeypatch.setattr(service, "propose_mapping", _clear_value_mapper())

    result = service.reconcile_or_map(
        str(NOVASCREEN_01),
        FieldSet(name=_SCHEMA_NAME, fields=(Field(name="compound_id"), Field(name="value"))),
        schema_store=store, target_schema_name=_SCHEMA_NAME, vendor="acme",
        envelope=envelope,
    )

    assert isinstance(result, service.MapResult)
    assert result.provenance == "reconciled-from-crosswalk"
    # The map file's novel alias is now augmented into the store (from_map_file).
    aliases = store.list_aliases_for(schema_id)
    assert ("acme", "cmpd") in {(a.vendor, a.source_column) for a in aliases}
    assert any(a.provenance_kind == "from_map_file" for a in aliases)
    # compound_id was pre-filled at 1.0 from the crosswalk, not from Claude.
    by_field = {m.target_field: m for m in result.proposal.field_mappings}
    assert by_field["compound_id"].source_column == "cmpd"
    assert by_field["compound_id"].confidence == 1.0
    assert by_field["compound_id"].needs_confirmation is False


def test_reconcile_or_map_raises_schema_not_found_for_an_unknown_target(tmp_path, monkeypatch):
    store, _ = _seeded_master(tmp_path=tmp_path)
    with pytest.raises(service.SchemaNotFoundError):
        service.reconcile_or_map(
            str(NOVASCREEN_01),
            FieldSet(name="x", fields=(Field(name="value"),)),
            schema_store=store, target_schema_name="no-such-schema", vendor="acme",
            envelope=_envelope({"value": []}),
        )


def test_reconcile_or_map_returns_structural_question_unchanged(tmp_path, monkeypatch):
    from assayingest.parsing.hint import StructureQuestion

    store, _ = _seeded_master(tmp_path=tmp_path)
    question = StructureQuestion(
        unsure_about="which row is the real header", reason="ambiguous", confidence=0.4,
    )
    monkeypatch.setattr(service, "parse", lambda path, *, sheet=None: question)

    result = service.reconcile_or_map(
        "whatever.csv",
        FieldSet(name=_SCHEMA_NAME, fields=(Field(name="value"),)),
        schema_store=store, target_schema_name=_SCHEMA_NAME, vendor="acme",
        envelope=_envelope({"value": []}),
    )

    assert result is question


def test_apply_reconcile_resolution_take_map_file_prefills_map_file_field(tmp_path, monkeypatch):
    store, schema_id = _seeded_master(
        tmp_path=tmp_path, master_aliases={"value": [_alias("acme", "cmpd")]},
    )
    envelope = _envelope({"compound_id": [_alias("acme", "cmpd")]})
    monkeypatch.setattr(service, "propose_mapping", _clear_value_mapper())

    result = service.apply_reconcile_resolution(
        str(NOVASCREEN_01),
        FieldSet(name=_SCHEMA_NAME, fields=(Field(name="compound_id"), Field(name="value"))),
        schema_store=store, target_schema_name=_SCHEMA_NAME, vendor="acme",
        envelope=envelope, choices=[("acme", "cmpd", "take_map_file")],
    )

    assert isinstance(result, service.MapResult)
    by_field = {m.target_field: m for m in result.proposal.field_mappings}
    # take_map_file -> "cmpd" pre-fills to the map file's canonical field.
    assert by_field["compound_id"].source_column == "cmpd"
    assert by_field["compound_id"].confidence == 1.0
    # The master's conflicting stored alias (value <- cmpd) is NOT overwritten.
    master_value_aliases = {
        (a.vendor, a.source_column)
        for cf in store.get_schema(_SCHEMA_NAME).fields if cf.field.name == "value"
        for a in cf.aliases
    }
    assert ("acme", "cmpd") in master_value_aliases


def test_apply_reconcile_resolution_keep_master_prefills_master_field(tmp_path, monkeypatch):
    store, schema_id = _seeded_master(
        tmp_path=tmp_path, master_aliases={"value": [_alias("acme", "cmpd")]},
    )
    envelope = _envelope({"compound_id": [_alias("acme", "cmpd")]})

    def _compound_mapper(table, field_set, client=None, *, headers_only=False):
        return MappingProposal(
            source_columns=list(table.headers),
            field_mappings=[
                FieldMapping(
                    target_field=name, source_column=None, confidence=0.9,
                    reasoning="remainder", needs_confirmation=False,
                )
                for name in field_set.field_names
            ],
        )

    monkeypatch.setattr(service, "propose_mapping", _compound_mapper)

    result = service.apply_reconcile_resolution(
        str(NOVASCREEN_01),
        FieldSet(name=_SCHEMA_NAME, fields=(Field(name="compound_id"), Field(name="value"))),
        schema_store=store, target_schema_name=_SCHEMA_NAME, vendor="acme",
        envelope=envelope, choices=[("acme", "cmpd", "keep_master")],
    )

    by_field = {m.target_field: m for m in result.proposal.field_mappings}
    # keep_master -> "cmpd" pre-fills to the master's existing canonical field (value).
    assert by_field["value"].source_column == "cmpd"
    assert by_field["value"].confidence == 1.0


def test_reconcile_or_map_runs_validate_flagging_a_constraint_violation(tmp_path, monkeypatch):
    tmp = tmp_path
    store = SqliteSchemaStore(tmp / "profiles.db")
    field_set = FieldSet(
        name=_SCHEMA_NAME,
        fields=(Field(name="assay_type", allowed_values=("EC50",)),),
    )
    service.promote(field_set, created_by="curator@example.com", store=store)
    schema = store.get_schema(_SCHEMA_NAME)
    store.add_alias(
        schema.id, "assay_type",
        Alias(vendor="acme", source_column="assay", provenance_kind="manual",
              provenance_actor="curator@example.com", created_at=_TS),
    )
    envelope = _envelope({"assay_type": [_alias("acme", "assay")]})  # same target -> no conflict

    def _explode(*args, **kwargs):
        raise AssertionError("all fields covered -> no mapper call")

    monkeypatch.setattr(service, "propose_mapping", _explode)

    result = service.reconcile_or_map(
        str(NOVASCREEN_01), field_set,
        schema_store=store, target_schema_name=_SCHEMA_NAME, vendor="acme",
        envelope=envelope,
    )

    assert isinstance(result, service.MapResult)
    # "assay" pre-filled to assay_type at 1.0, but novascreen's IC50 violates
    # allowed_values=("EC50",) -> validate() forces needs_confirmation True.
    assay = {m.target_field: m for m in result.proposal.field_mappings}["assay_type"]
    assert assay.source_column == "assay"
    assert assay.needs_confirmation is True
