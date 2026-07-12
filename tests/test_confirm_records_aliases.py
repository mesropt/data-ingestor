"""service.confirm additively records crosswalk aliases (ALIAS-04, D-07-05/06),
TDD RED-first (07-03 Task 1).

Store-level tests against a tmp-path `SqliteSchemaStore` pre-seeded (via
`service.promote`) with a governed Schema. These pin the ADDITIVE contract:

  * with a target Schema + vendor, each resolved source column becomes a
    `manual`, user-attributed alias on the matching canonical field
    (ALIAS-01/02/03/04);
  * a field whose resolved `source_column` is `None` (an inferred-only field)
    records NO alias;
  * a confirm with no schema_store / no target_schema_name / no vendor writes
    nothing — the store is untouched and the returned `ConfirmResult` keeps its
    existing shape (existing behavior unchanged);
  * recording is idempotent (first-seen provenance kept) and gated behind
    confirm success — a `NotReadyError`/`FieldCoverageError` path writes nothing.
"""

from __future__ import annotations

import pytest

from assayingest import service
from assayingest.domain.models import FieldMapping
from assayingest.fields.models import Field, FieldSet
from assayingest.learning.sqlite_schema_store import SqliteSchemaStore
from assayingest.parsing.table import RawTable

_SCHEMA_NAME = "assay-potency"


def _table() -> RawTable:
    return RawTable(
        headers=["cmpd", "potency"],
        rows=[["NVS-1", "12.5"], ["NVS-2", "8.0"]],
        source_name="batch.csv",
    )


def _field_set() -> FieldSet:
    return FieldSet(
        name=_SCHEMA_NAME,
        fields=(Field(name="compound_id"), Field(name="value")),
    )


def _ready_mappings() -> list[FieldMapping]:
    return [
        FieldMapping(
            target_field="compound_id", source_column="cmpd", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
        FieldMapping(
            target_field="value", source_column="potency", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
    ]


def _seeded_store(tmp_path, field_set: FieldSet | None = None) -> SqliteSchemaStore:
    store = SqliteSchemaStore(tmp_path / "profiles.db")
    service.promote(field_set or _field_set(), created_by="curator@example.com", store=store)
    return store


def _aliases_by_field(store: SqliteSchemaStore) -> dict[str, list]:
    schema = store.get_schema(_SCHEMA_NAME)
    return {cf.field.name: list(cf.aliases) for cf in schema.fields}


# --- ALIAS-04: confirm with a Schema + vendor records manual aliases ----------


def test_confirm_records_manual_actor_aliases_for_each_resolved_column(tmp_path):
    store = _seeded_store(tmp_path)

    result = service.confirm(
        _table(), _ready_mappings(), _field_set(),
        schema_store=store, target_schema_name=_SCHEMA_NAME,
        vendor="NovaScreen", confirmed_by="a@b.com",
    )

    assert isinstance(result, service.ConfirmResult)
    by_field = _aliases_by_field(store)
    assert [a.source_column for a in by_field["compound_id"]] == ["cmpd"]
    assert [a.source_column for a in by_field["value"]] == ["potency"]
    for name in ("compound_id", "value"):
        alias = by_field[name][0]
        assert alias.vendor == "NovaScreen"
        assert alias.provenance_kind == "manual"
        assert alias.provenance_actor == "a@b.com"
        assert alias.created_at  # a real timestamp was stamped


def test_confirm_records_no_alias_for_an_inferred_only_field(tmp_path):
    """A field whose resolved source_column is None (inferred, but still clear)
    contributes NO alias — there is no vendor column to crosswalk."""
    field_set = FieldSet(
        name=_SCHEMA_NAME,
        fields=(Field(name="compound_id"), Field(name="value"), Field(name="assay_type")),
    )
    store = _seeded_store(tmp_path, field_set)
    mappings = _ready_mappings() + [
        FieldMapping(
            target_field="assay_type", source_column=None, confidence=1.0,
            reasoning="inferred IC50 from context", needs_confirmation=False,
            inferred_value="IC50",
        ),
    ]

    service.confirm(
        _table(), mappings, field_set,
        schema_store=store, target_schema_name=_SCHEMA_NAME,
        vendor="NovaScreen", confirmed_by="a@b.com",
    )

    by_field = _aliases_by_field(store)
    assert by_field["assay_type"] == []  # inferred-only -> no alias
    assert len(by_field["compound_id"]) == 1
    assert len(by_field["value"]) == 1


# --- purely additive: no schema/vendor -> nothing written ---------------------


def test_confirm_without_schema_or_vendor_records_nothing(tmp_path):
    store = _seeded_store(tmp_path)
    schema_id = store.get_schema(_SCHEMA_NAME).id
    assert store.list_aliases_for(schema_id) == []

    result = service.confirm(_table(), _ready_mappings(), _field_set())

    # Existing ConfirmResult shape is unchanged, and the store is untouched.
    assert isinstance(result, service.ConfirmResult)
    assert result.proposal.is_ready is True
    assert result.tidy.field_names == ["compound_id", "value"]
    assert result.manifest["provenance"] == "fresh-claude"
    assert store.list_aliases_for(schema_id) == []


def test_confirm_with_schema_but_no_vendor_records_nothing(tmp_path):
    """All three of schema_store/target_schema_name/vendor must be present;
    a missing vendor alone means nothing is written (matches the client
    default where vendor is absent)."""
    store = _seeded_store(tmp_path)
    schema_id = store.get_schema(_SCHEMA_NAME).id

    service.confirm(
        _table(), _ready_mappings(), _field_set(),
        schema_store=store, target_schema_name=_SCHEMA_NAME, vendor=None,
        confirmed_by="a@b.com",
    )

    assert store.list_aliases_for(schema_id) == []


# --- ALIAS-03: idempotent, first-seen provenance kept -------------------------


def test_confirm_records_aliases_idempotently_keeping_first_provenance(tmp_path):
    store = _seeded_store(tmp_path)

    service.confirm(
        _table(), _ready_mappings(), _field_set(),
        schema_store=store, target_schema_name=_SCHEMA_NAME,
        vendor="NovaScreen", confirmed_by="first@b.com",
    )
    service.confirm(
        _table(), _ready_mappings(), _field_set(),
        schema_store=store, target_schema_name=_SCHEMA_NAME,
        vendor="NovaScreen", confirmed_by="second@b.com",
    )

    schema_id = store.get_schema(_SCHEMA_NAME).id
    aliases = store.list_aliases_for(schema_id)
    assert len(aliases) == 2  # one per (field, vendor, source_column), not four
    assert all(a.provenance_actor == "first@b.com" for a in aliases)


# --- T-07-11: recording is gated behind confirm success -----------------------


def test_confirm_records_no_alias_when_the_gate_rejects_a_yellow_field(tmp_path):
    field_set = FieldSet(name=_SCHEMA_NAME, fields=(Field(name="value", min=100),))
    store = _seeded_store(tmp_path, field_set)
    blocked = [
        FieldMapping(
            target_field="value", source_column="potency", confidence=1.0,
            reasoning="curator says so", needs_confirmation=False,  # tampered
        ),
    ]

    with pytest.raises(service.NotReadyError):
        service.confirm(
            _table(), blocked, field_set,
            schema_store=store, target_schema_name=_SCHEMA_NAME,
            vendor="NovaScreen", confirmed_by="a@b.com",
        )

    schema_id = store.get_schema(_SCHEMA_NAME).id
    assert store.list_aliases_for(schema_id) == []


def test_confirm_records_no_alias_when_field_coverage_is_incomplete(tmp_path):
    store = _seeded_store(tmp_path)
    partial = [
        FieldMapping(
            target_field="compound_id", source_column="cmpd", confidence=1.0,
            reasoning="exact match", needs_confirmation=False,
        ),
        # "value" omitted entirely -> FieldCoverageError before the gate.
    ]

    with pytest.raises(service.FieldCoverageError):
        service.confirm(
            _table(), partial, _field_set(),
            schema_store=store, target_schema_name=_SCHEMA_NAME,
            vendor="NovaScreen", confirmed_by="a@b.com",
        )

    schema_id = store.get_schema(_SCHEMA_NAME).id
    assert store.list_aliases_for(schema_id) == []
