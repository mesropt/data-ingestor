"""SqliteUserStore behaviour (D-06-02) -- users live in a local SQLite file
behind the same repository seam pattern as the profile/field-set stores.

Every test uses a tmp-path db so no test ever touches the real demo database.
"""

from __future__ import annotations

from assayingest.auth.models import User
from assayingest.auth.sqlite_store import SqliteUserStore


def _user(
    *,
    id: str = "u-1",
    email: str = "a@b.com",
    password_hash: str | None = "hash-1",
    is_verified: bool = False,
    auth_provider: str = "password",
    created_at: str = "2026-07-11T00:00:00Z",
) -> User:
    return User(
        id=id,
        email=email,
        password_hash=password_hash,
        is_verified=is_verified,
        auth_provider=auth_provider,
        created_at=created_at,
    )


def _store(tmp_path) -> SqliteUserStore:
    return SqliteUserStore(tmp_path / "users.db")


def test_save_then_get_returns_equal_user(tmp_path):
    store = _store(tmp_path)
    user = _user()
    store.save(user)
    assert store.get("u-1") == user


def test_get_unknown_id_returns_none(tmp_path):
    store = _store(tmp_path)
    assert store.get("nope") is None


def test_get_by_email_returns_saved_user(tmp_path):
    store = _store(tmp_path)
    user = _user()
    store.save(user)
    assert store.get_by_email("a@b.com") == user


def test_get_by_email_unknown_returns_none(tmp_path):
    store = _store(tmp_path)
    assert store.get_by_email("missing@b.com") is None


def test_mark_verified_flips_flag(tmp_path):
    store = _store(tmp_path)
    store.save(_user(is_verified=False))
    store.mark_verified("u-1")
    got = store.get("u-1")
    assert got is not None
    assert got.is_verified is True


def test_save_is_upsert_on_email(tmp_path):
    store = _store(tmp_path)
    store.save(_user(password_hash="hash-1"))
    # A second save with the SAME email updates the row, never duplicates.
    store.save(_user(id="u-2", password_hash="hash-2"))
    got = store.get_by_email("a@b.com")
    assert got is not None
    assert got.password_hash == "hash-2"


def test_tmp_store_creates_table_and_touches_no_other_file(tmp_path):
    store = _store(tmp_path)
    # The db file it was told to use exists...
    assert (tmp_path / "users.db").exists()
    # ...and a round-trip works, proving the users table was created in __init__.
    store.save(_user())
    assert store.get("u-1") is not None
    # No real demo DB was created under the tmp working dir.
    assert not (tmp_path / ".assayingest").exists()


def test_get_or_create_by_email_creates_verified_google_user(tmp_path):
    store = _store(tmp_path)
    created = store.get_or_create_by_email("new@b.com")
    assert created.email == "new@b.com"
    assert created.is_verified is True
    assert created.auth_provider == "google"
    assert created.password_hash is None
    # It was persisted, not just returned.
    assert store.get_by_email("new@b.com") == created


def test_get_or_create_by_email_returns_existing_unchanged(tmp_path):
    store = _store(tmp_path)
    existing = _user(email="dup@b.com", is_verified=True, password_hash="pw")
    store.save(existing)
    got = store.get_or_create_by_email("dup@b.com")
    assert got == existing
