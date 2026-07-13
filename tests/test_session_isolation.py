"""Proof that the test harness actually isolates -- do not assume it, pin it.

`tests/conftest.py` closes TWO doors so that all four Session paths (FastAPI DI,
lifespan seeding, the startup schema check, the CLI) reach the test's connection
rather than the developer's real database. These tests prove the doors are shut.

The composition-root door is the subtle one, and it is the one that regressed
twice during planning. It is also the door an "obvious simplification" reopens:
capture the session factory at import time (`from .engine import SessionFactory`)
and a test's rebind silently does not take -- the suite stays green while writing
to dev. `test_composition_root_sessions_reach_the_test_connection` is what fails
in that world.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text

from assayingest.learning.postgres_store import PostgresProfileStore
from assayingest.learning.profile import LearnedProfile, StoredFieldMapping
from assayingest.persistence import engine as engine_module


def _profile(profile_id: str = "seam-1") -> LearnedProfile:
    return LearnedProfile(
        profile_id=profile_id,
        field_set_signature="fs-seam",
        column_signature="col-seam",
        field_mappings=(
            StoredFieldMapping(
                target_field="compound_id",
                source_column_normalised="compound id",
                source_column_occurrence=0,
            ),
        ),
        structural_hint=None,
        created_at=datetime.now(UTC).isoformat(),
    )


def test_composition_root_sessions_reach_the_test_connection(db_session):
    """A store built the way `_lifespan` and the CLI build one -- straight from the
    composition-root seam, with no FastAPI anywhere -- must write to the TEST
    connection, so `db_session` can see the row.

    This fails if the seam is captured at import time instead of dereferenced at
    call time (the patch would not take, the write would land in the DEV database,
    and `db_session` would see nothing).
    """
    with engine_module.new_session() as session:
        PostgresProfileStore(session).save(_profile())

    found = db_session.execute(
        text("SELECT id FROM profiles WHERE field_set_signature = 'fs-seam'")
    ).scalar()

    assert found == "seam-1"


def test_the_seam_is_rebindable_and_never_builds_the_dev_engine(db_session):
    """The autouse fixture rebound the seam BEFORE anything touched it, so the
    module-level dev engine was never constructed. If this fails, some import-time
    code path built an engine against DATABASE_URL -- i.e. against the developer's
    real database."""
    assert engine_module._engine is None


def test_a_rolled_back_test_leaves_no_row_behind(profile_store, db_session):
    """Isolation is a property of every test, including this one: the row written
    here is invisible to the next test because the outer transaction is rolled back.
    Paired with the identical write in the test above -- if the rollback did not
    happen, one of the two would hit the UNIQUE constraint on (fs, col)."""
    profile_store.save(_profile(profile_id="seam-2"))

    count = db_session.execute(
        text("SELECT COUNT(*) FROM profiles WHERE field_set_signature = 'fs-seam'")
    ).scalar()

    assert count == 1
