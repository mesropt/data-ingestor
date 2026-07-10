"""learning.profile / learning.store / learning.sqlite_store -- the profile
domain model, its repository seam, and the local SQLite implementation
(LEARN-02/05/06, D-01/06/07/08). Written test-first (TDD RED)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from assayingest.learning.profile import LearnedProfile, StoredFieldMapping
from assayingest.learning.sqlite_store import SqliteProfileStore
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


def test_round_trip_preserves_every_field(tmp_path):
    store = SqliteProfileStore(tmp_path / "profiles.db")
    profile = _profile()

    store.save(profile)
    found = store.find(profile.field_set_signature, profile.column_signature)

    assert found == profile


def test_structural_hint_round_trips(tmp_path):
    store = SqliteProfileStore(tmp_path / "profiles.db")
    hint = StructuralHint(header_row_index=2, table_shape=TableShape.ROW_PER_RECORD)
    profile = _profile(hint=hint)

    store.save(profile)
    found = store.find(profile.field_set_signature, profile.column_signature)

    assert found.structural_hint == hint


def test_structural_hint_none_round_trips_none(tmp_path):
    store = SqliteProfileStore(tmp_path / "profiles.db")
    profile = _profile(hint=None)

    store.save(profile)
    found = store.find(profile.field_set_signature, profile.column_signature)

    assert found.structural_hint is None


def test_one_field_set_may_hold_several_profiles(tmp_path):
    # LEARN-05: one vendor's format can drift over time -- each new
    # signature gets its own row rather than overwriting the old one.
    store = SqliteProfileStore(tmp_path / "profiles.db")
    first = _profile(field_set_signature="fs-1", column_signature="col-a", profile_id="p-a")
    second = _profile(field_set_signature="fs-1", column_signature="col-b", profile_id="p-b")
    store.save(first)
    store.save(second)

    profiles = store.list_for_field_set("fs-1")

    assert {p.column_signature for p in profiles} == {"col-a", "col-b"}


def test_saving_the_same_signature_pair_again_overwrites_not_raises(tmp_path):
    # A curator re-confirming a correction for the SAME file layout upserts,
    # never raises or duplicates a row.
    store = SqliteProfileStore(tmp_path / "profiles.db")
    original = _profile(field_set_signature="fs-1", column_signature="col-a")
    store.save(original)

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
    store.save(corrected)  # must not raise

    found = store.find("fs-1", "col-a")
    assert found.profile_id == "p-2"
    assert len(store.list_for_field_set("fs-1")) == 1


def test_find_returns_none_on_a_miss():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        store = SqliteProfileStore(Path(tmp) / "profiles.db")
        assert store.find("no-such-field-set", "no-such-signature") is None


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


def test_sqlite_store_creates_the_db_file_and_parent_dir_on_construction(tmp_path):
    db_path = tmp_path / "nested" / "profiles.db"
    SqliteProfileStore(db_path)
    assert db_path.exists()


def test_sqlite_store_never_string_formats_a_header_into_sql(tmp_path):
    # A header containing a SQL metacharacter must round-trip safely --
    # proof the store uses parameterised queries, not f-string SQL (ASVS V5).
    db_path = tmp_path / "profiles.db"
    store = SqliteProfileStore(db_path)
    hostile_sig = "'; DROP TABLE profiles; --"
    profile = _profile(field_set_signature=hostile_sig, column_signature="col-x")

    store.save(profile)
    found = store.find(hostile_sig, "col-x")

    assert found is not None
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] == 1
