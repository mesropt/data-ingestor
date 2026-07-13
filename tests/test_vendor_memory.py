"""The remembered-vendor lookup (INGEST-02, gap-closure 10-09 Task 3), TDD
RED-first.

The vendor is a human assertion, never derivable from the file itself --
but once a column signature has been confirmed once, asking for it again is
friction this task removes. `service.recall_vendor` resolves in a fixed
escalation order (mirroring D-10-03's own shape):

  1. exact, learned profile match -> unambiguous by the store's own
     UniqueConstraint(field_set_signature, column_signature)
  2. crosswalk fallback -- distinct vendors whose aliases match the file's
     headers: exactly one -> that vendor; two or more -> refuse to guess,
     name both; zero -> empty

Nothing may ever tie-break an ambiguous crosswalk match -- that is the one
load-bearing anti-guessing test in this file.
"""

from __future__ import annotations

from datetime import UTC, datetime

from assayingest import service
from assayingest.domain.models import Alias
from assayingest.fields.models import Field, FieldSet
from assayingest.learning.profile import LearnedProfile, StoredFieldMapping
from assayingest.learning.signature import column_signature
from assayingest.parsing.table import RawTable

_TS = datetime.now(UTC).isoformat()


def _table(headers: list[str]) -> RawTable:
    return RawTable(headers=headers, rows=[], source_name="x.csv")


def _field_set() -> FieldSet:
    return FieldSet(fields=(Field(name="compound_id"), Field(name="value")))


def _alias(vendor: str, source_column: str) -> Alias:
    return Alias(
        vendor=vendor, source_column=source_column, provenance_kind="manual",
        provenance_actor="curator@example.com", created_at=_TS,
    )


def _make_schema(schema_store, fields=("compound_id", "value")):
    field_set = FieldSet(name="assay-potency", fields=tuple(Field(name=n) for n in fields))
    return service.promote(field_set, created_by="curator@example.com", store=schema_store)


# --- LearnedProfile.vendor -----------------------------------------------------


def test_learned_profile_vendor_defaults_to_none_and_every_existing_site_still_constructs():
    profile = LearnedProfile(
        profile_id="p-1", field_set_signature="fs", column_signature="cs",
        field_mappings=(), structural_hint=None, created_at=_TS,
    )
    assert profile.vendor is None


def test_learned_profile_to_dict_emits_vendor():
    profile = LearnedProfile(
        profile_id="p-1", field_set_signature="fs", column_signature="cs",
        field_mappings=(), structural_hint=None, created_at=_TS, vendor="novascreen",
    )
    assert profile.to_dict()["vendor"] == "novascreen"


# --- postgres_store round-trip -------------------------------------------------


def test_profile_store_round_trips_vendor(profile_store):
    profile = LearnedProfile(
        profile_id="p-1", field_set_signature="fs-1", column_signature="cs-1",
        field_mappings=(
            StoredFieldMapping(
                target_field="compound_id", source_column_normalised="cmpd",
                source_column_occurrence=0,
            ),
        ),
        structural_hint=None, created_at=_TS, vendor="novascreen",
    )
    profile_store.save(profile)

    found = profile_store.find("fs-1", "cs-1")

    assert found.vendor == "novascreen"


def test_profile_store_find_with_no_vendor_recorded_is_none(profile_store):
    profile = LearnedProfile(
        profile_id="p-1", field_set_signature="fs-1", column_signature="cs-1",
        field_mappings=(), structural_hint=None, created_at=_TS,
    )
    profile_store.save(profile)

    found = profile_store.find("fs-1", "cs-1")

    assert found.vendor is None


def test_reconfirming_the_same_signature_upserts_and_learns_the_vendor(profile_store):
    """A profile saved WITHOUT a vendor, then re-confirmed WITH one, learns
    it -- the upsert path must thread vendor through, not just the insert."""
    original = LearnedProfile(
        profile_id="p-1", field_set_signature="fs-1", column_signature="cs-1",
        field_mappings=(), structural_hint=None, created_at=_TS,
    )
    profile_store.save(original)

    reconfirmed = LearnedProfile(
        profile_id="p-2", field_set_signature="fs-1", column_signature="cs-1",
        field_mappings=(), structural_hint=None, created_at=_TS, vendor="novascreen",
    )
    profile_store.save(reconfirmed)

    found = profile_store.find("fs-1", "cs-1")
    assert found.vendor == "novascreen"


# --- service.save_profile_if_ready / confirm thread the vendor ----------------


def test_save_profile_if_ready_accepts_and_persists_vendor(profile_store):
    field_set = _field_set()
    table = _table(["cmpd", "potency"])

    from assayingest.domain.models import FieldMapping, MappingProposal
    from assayingest.validation.validator import validate

    proposal = MappingProposal(
        source_columns=table.headers,
        field_mappings=[
            FieldMapping(
                target_field="compound_id", source_column="cmpd", confidence=1.0,
                reasoning="exact", needs_confirmation=False,
            ),
            FieldMapping(
                target_field="value", source_column="potency", confidence=1.0,
                reasoning="exact", needs_confirmation=False,
            ),
        ],
    )
    proposal = validate(table, proposal, field_set)

    service.save_profile_if_ready(profile_store, field_set, table, proposal, None, vendor="novascreen")

    found = profile_store.find(field_set.signature, column_signature(table.headers))
    assert found is not None
    assert found.vendor == "novascreen"


def test_confirm_threads_the_vendor_into_the_saved_profile(profile_store, schema_store):
    from assayingest.domain.models import FieldMapping

    field_set = _field_set()
    table = _table(["cmpd", "potency"])
    schema = _make_schema(schema_store)

    result = service.confirm(
        table,
        [
            FieldMapping(
                target_field="compound_id", source_column="cmpd", confidence=1.0,
                reasoning="exact", needs_confirmation=False,
            ),
            FieldMapping(
                target_field="value", source_column="potency", confidence=1.0,
                reasoning="exact", needs_confirmation=False,
            ),
        ],
        field_set,
        save_profile=True,
        store=profile_store,
        schema_store=schema_store,
        target_schema_name=schema.name,
        vendor="novascreen",
        confirmed_by="curator@example.com",
    )

    found = profile_store.find(field_set.signature, column_signature(table.headers))
    assert found is not None
    assert found.vendor == "novascreen"
    assert result.profile_id == found.profile_id


# --- service.recall_vendor ------------------------------------------------------


def test_recall_vendor_exact_profile_match_is_unambiguous_by_construction(profile_store, schema_store):
    field_set = _field_set()
    table = _table(["cmpd", "potency"])
    schema = _make_schema(schema_store)

    profile = LearnedProfile(
        profile_id="p-1", field_set_signature=field_set.signature,
        column_signature=column_signature(table.headers),
        field_mappings=(), structural_hint=None, created_at=_TS, vendor="novascreen",
    )
    profile_store.save(profile)

    memory = service.recall_vendor(table, field_set, schema, profile_store)

    assert memory.vendor == "novascreen"
    assert memory.source == "profile"
    assert memory.candidates == ()


def test_recall_vendor_crosswalk_fallback_single_vendor(profile_store, schema_store):
    field_set = _field_set()
    table = _table(["cmpd", "potency"])
    schema = _make_schema(schema_store)
    schema_store.add_alias(schema.id, "compound_id", _alias("novascreen", "cmpd"))
    schema_store.add_alias(schema.id, "value", _alias("novascreen", "potency"))
    schema = schema_store.get_schema(schema.name)

    memory = service.recall_vendor(table, field_set, schema, profile_store)

    assert memory.vendor == "novascreen"
    assert memory.source == "crosswalk"
    assert memory.candidates == ()


def test_recall_vendor_two_vendors_refuses_to_guess_and_names_both(profile_store, schema_store):
    """THE load-bearing anti-guessing test: two vendors' aliases both match
    this file's columns -- the tool must pick NEITHER, and must name both,
    sorted."""
    field_set = _field_set()
    table = _table(["cmpd", "potency"])
    schema = _make_schema(schema_store)
    schema_store.add_alias(schema.id, "compound_id", _alias("zephyr", "cmpd"))
    schema_store.add_alias(schema.id, "value", _alias("novascreen", "potency"))
    schema = schema_store.get_schema(schema.name)

    memory = service.recall_vendor(table, field_set, schema, profile_store)

    assert memory.vendor is None
    assert memory.source is None
    assert memory.candidates == ("novascreen", "zephyr")


def test_recall_vendor_no_match_returns_empty(profile_store, schema_store):
    field_set = _field_set()
    table = _table(["totally", "unmapped"])
    schema = _make_schema(schema_store)

    memory = service.recall_vendor(table, field_set, schema, profile_store)

    assert memory.vendor is None
    assert memory.source is None
    assert memory.candidates == ()


def test_recall_vendor_a_tombstoned_alias_contributes_no_candidate(profile_store, schema_store):
    field_set = _field_set()
    table = _table(["cmpd", "potency"])
    schema = _make_schema(schema_store)
    schema_store.add_alias(schema.id, "compound_id", _alias("novascreen", "cmpd"))
    schema_store.add_alias(schema.id, "value", _alias("zephyr", "potency"))
    schema_store.remove_alias(
        schema.id, "value", "zephyr", "potency",
        removed_by="curator@example.com", removed_at=_TS,
    )
    schema = schema_store.get_schema(schema.name)

    memory = service.recall_vendor(table, field_set, schema, profile_store)

    # Only novascreen's (live) alias remains -- unambiguous, from the crosswalk.
    assert memory.vendor == "novascreen"
    assert memory.source == "crosswalk"


def test_recall_vendor_with_no_schema_returns_empty(profile_store):
    """No Schema was targeted at all (legacy field_set path) -- there is no
    crosswalk to fall back to, so recall_vendor still resolves cleanly to
    empty rather than raising."""
    field_set = _field_set()
    table = _table(["cmpd", "potency"])

    memory = service.recall_vendor(table, field_set, None, profile_store)

    assert memory.vendor is None
    assert memory.candidates == ()
