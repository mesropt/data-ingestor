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
