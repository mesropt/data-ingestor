"""The four auth DI seams in `api/deps.py` (D-06-06 substrate).

These are exercised by calling the dependency functions directly with a
controlled `UserStore`, the way FastAPI would resolve them -- `get_current_user`
must never raise, `require_user` is the 401 gate, `require_verified_user` is the
403 gate for a signed-in-but-unverified user.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from assayingest.api import deps
from assayingest.auth import session
from assayingest.auth.models import User
from assayingest.auth.store import UserStore


class _FakeStore(UserStore):
    """A UserStore returning one preset user by id (the DI seam a test injects
    in place of SqliteUserStore)."""

    def __init__(self, user: User | None) -> None:
        self._user = user

    def save(self, user: User) -> None:  # pragma: no cover - unused here
        raise NotImplementedError

    def get(self, user_id: str) -> User | None:
        if self._user is not None and self._user.id == user_id:
            return self._user
        return None

    def get_by_email(self, email: str) -> User | None:  # pragma: no cover
        raise NotImplementedError

    def mark_verified(self, user_id: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def get_or_create_by_email(self, email: str) -> User:  # pragma: no cover
        raise NotImplementedError


def _user(*, is_verified: bool) -> User:
    return User(
        id="u-1",
        email="a@b.com",
        password_hash="h",
        is_verified=is_verified,
        auth_provider="password",
        created_at="2026-07-11T00:00:00Z",
    )


def test_get_current_user_none_when_no_cookie():
    store = _FakeStore(_user(is_verified=True))
    assert deps.get_current_user(di_session=None, store=store) is None


def test_get_current_user_none_on_garbage_cookie(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    store = _FakeStore(_user(is_verified=True))
    # Never raises -- an attacker-controlled cookie value just resolves to None.
    assert deps.get_current_user(di_session="garbage", store=store) is None


def test_get_current_user_resolves_valid_cookie(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    user = _user(is_verified=True)
    store = _FakeStore(user)
    token = session.create_session_token("u-1")
    assert deps.get_current_user(di_session=token, store=store) == user


def test_require_user_raises_401_when_signed_out():
    with pytest.raises(HTTPException) as exc:
        deps.require_user(user=None)
    assert exc.value.status_code == 401


def test_require_user_returns_user_when_signed_in():
    user = _user(is_verified=True)
    assert deps.require_user(user=user) is user


def test_require_verified_user_raises_403_when_unverified():
    with pytest.raises(HTTPException) as exc:
        deps.require_verified_user(user=_user(is_verified=False))
    assert exc.value.status_code == 403


def test_require_verified_user_returns_user_when_verified():
    user = _user(is_verified=True)
    assert deps.require_verified_user(user=user) is user
