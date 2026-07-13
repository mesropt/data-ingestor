"""PostgresUserStore behaviour (D-06-02) -- users live in PostgreSQL behind the
same repository seam pattern as the profile/field-set stores.

Every test runs inside the harness's rolled-back outer transaction, so no test ever
touches the real demo database.
"""

from __future__ import annotations

from assayingest.auth.models import User


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


def test_save_then_get_returns_equal_user(user_store):
    user = _user()
    user_store.save(user)
    assert user_store.get("u-1") == user


def test_get_unknown_id_returns_none(user_store):
    assert user_store.get("nope") is None


def test_get_by_email_returns_saved_user(user_store):
    user = _user()
    user_store.save(user)
    assert user_store.get_by_email("a@b.com") == user


def test_get_by_email_unknown_returns_none(user_store):
    assert user_store.get_by_email("missing@b.com") is None


def test_mark_verified_flips_flag(user_store):
    user_store.save(_user(is_verified=False))
    user_store.mark_verified("u-1")
    got = user_store.get("u-1")
    assert got is not None
    assert got.is_verified is True


def test_is_verified_round_trips_as_a_real_bool_never_an_int(user_store):
    # Postgres BOOLEAN, not SQLite's 0/1 INTEGER: the store passes the Python bool
    # straight through, with no int()/bool() cast on either side. `is False` / `is
    # True` (identity, not equality) is what makes this a real assertion -- `1 == True`
    # in Python, so `== True` would pass even against the old integer round-trip.
    user_store.save(_user(is_verified=False))
    assert user_store.get("u-1").is_verified is False

    user_store.mark_verified("u-1")
    assert user_store.get("u-1").is_verified is True


def test_save_is_upsert_on_email(user_store):
    user_store.save(_user(password_hash="hash-1"))
    # A second save with the SAME email updates the row, never duplicates.
    user_store.save(_user(id="u-2", password_hash="hash-2"))
    got = user_store.get_by_email("a@b.com")
    assert got is not None
    assert got.password_hash == "hash-2"


def test_save_upsert_keeps_the_original_id(user_store):
    # `id` is deliberately absent from the ON CONFLICT SET clause: an existing
    # user's stable id must survive a credential change, or every session cookie
    # ever issued to them would silently stop resolving.
    user_store.save(_user(id="u-1", password_hash="hash-1"))
    user_store.save(_user(id="u-2", password_hash="hash-2"))

    got = user_store.get_by_email("a@b.com")
    assert got.id == "u-1"
    assert got.password_hash == "hash-2"
    assert user_store.get("u-2") is None


def test_get_or_create_by_email_creates_verified_google_user(user_store):
    created = user_store.get_or_create_by_email("new@b.com")
    assert created.email == "new@b.com"
    assert created.is_verified is True
    assert created.auth_provider == "google"
    assert created.password_hash is None
    # It was persisted, not just returned.
    assert user_store.get_by_email("new@b.com") == created


def test_get_or_create_by_email_returns_existing_unchanged(user_store):
    existing = _user(email="dup@b.com", is_verified=True, password_hash="pw")
    user_store.save(existing)
    got = user_store.get_or_create_by_email("dup@b.com")
    assert got == existing
