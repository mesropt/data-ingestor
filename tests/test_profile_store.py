"""learning.profile / learning.store / learning.postgres_store -- the profile
domain model, its repository seam, and the PostgreSQL implementation
(LEARN-02/05/06, D-01/06/07/08). Written test-first (TDD RED)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text

from assayingest.learning.profile import LearnedProfile, StoredFieldMapping
from assayingest.parsing.hint import StructuralHint, TableShape


def _profile(
    field_set_signature: str = "fs-sig",
    column_signature: str = "col-sig",
    hint: StructuralHint | None = None,
    profile_id: str = "p-1",
) -> LearnedProfile:
    return LearnedProfile(
        profile_id=profile_id,
        field_set_signature=field_set_signature,
        column_signature=column_signature,
        field_mappings=(
            StoredFieldMapping(
                target_field="compound_id",
                source_column_normalised="compound id",
                source_column_occurrence=0,
            ),
            StoredFieldMapping(
                target_field="unit",
                source_column_normalised=None,
                source_column_occurrence=0,
                inferred_value="nM",
            ),
        ),
        structural_hint=hint,
        created_at=datetime.now(UTC).isoformat(),
    )


def test_round_trip_preserves_every_field(profile_store):
    profile = _profile()

    profile_store.save(profile)
    found = profile_store.find(profile.field_set_signature, profile.column_signature)

    assert found == profile


def test_structural_hint_round_trips(profile_store):
    hint = StructuralHint(header_row_index=2, table_shape=TableShape.ROW_PER_RECORD)
    profile = _profile(hint=hint)

    profile_store.save(profile)
    found = profile_store.find(profile.field_set_signature, profile.column_signature)

    assert found.structural_hint == hint


def test_structural_hint_none_round_trips_none(profile_store):
    profile = _profile(hint=None)

    profile_store.save(profile)
    found = profile_store.find(profile.field_set_signature, profile.column_signature)

    assert found.structural_hint is None


def test_one_field_set_may_hold_several_profiles(profile_store):
    # LEARN-05: one vendor's format can drift over time -- each new
    # signature gets its own row rather than overwriting the old one.
    first = _profile(field_set_signature="fs-1", column_signature="col-a", profile_id="p-a")
    second = _profile(field_set_signature="fs-1", column_signature="col-b", profile_id="p-b")
    profile_store.save(first)
    profile_store.save(second)

    profiles = profile_store.list_for_field_set("fs-1")

    assert {p.column_signature for p in profiles} == {"col-a", "col-b"}


def test_saving_the_same_signature_pair_again_overwrites_not_raises(profile_store):
    # A curator re-confirming a correction for the SAME file layout upserts,
    # never raises or duplicates a row.
    original = _profile(field_set_signature="fs-1", column_signature="col-a")
    profile_store.save(original)

    corrected = LearnedProfile(
        profile_id="p-2",
        field_set_signature="fs-1",
        column_signature="col-a",
        field_mappings=(
            StoredFieldMapping(
                target_field="compound_id",
                source_column_normalised="cmpd",
                source_column_occurrence=0,
            ),
        ),
        structural_hint=None,
        created_at=datetime.now(UTC).isoformat(),
    )
    profile_store.save(corrected)  # must not raise

    found = profile_store.find("fs-1", "col-a")
    assert found.profile_id == "p-2"
    assert len(profile_store.list_for_field_set("fs-1")) == 1


def test_find_returns_none_on_a_miss(profile_store):
    assert profile_store.find("no-such-field-set", "no-such-signature") is None


def test_to_dict_shape_matches_the_manifest_base():
    profile = _profile(hint=StructuralHint(header_row_index=1))
    data = profile.to_dict()

    assert set(data.keys()) == {
        "profile_id",
        "field_set_signature",
        "column_signature",
        "field_mappings",
        "structural_hint",
        "created_at",
    }
    assert data["structural_hint"]["header_row_index"] == 1
    assert data["field_mappings"][0]["target_field"] == "compound_id"


def test_store_never_string_formats_a_header_into_sql(profile_store, db_session):
    # A signature containing a SQL metacharacter must round-trip safely -- proof the
    # store binds parameters rather than formatting SQL (ASVS V5). If it ever
    # f-stringed the value in, the `DROP TABLE` would execute and the COUNT below
    # would raise `UndefinedTable` instead of returning 1.
    hostile_sig = "'; DROP TABLE profiles; --"
    profile = _profile(field_set_signature=hostile_sig, column_signature="col-x")

    profile_store.save(profile)
    found = profile_store.find(hostile_sig, "col-x")

    assert found is not None
    assert db_session.execute(text("SELECT COUNT(*) FROM profiles")).scalar() == 1
