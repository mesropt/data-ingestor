"""Shared authenticated-`TestClient` builders (10-09, D-10-13).

`POST /api/upload`, `/api/structural-hint/resolve`, and `/api/date-format/
resolve` are now gated by `require_user` (Task 2). Every test that drives
one of those routes through `TestClient` must inject a signed-in `User` via
`app.dependency_overrides[get_current_user]` -- overriding `get_current_user`
(not `require_user`) is deliberate: it is the single root dependency that
satisfies BOTH `require_user` and `require_verified_user`, so a file that
already overrides `require_verified_user` for `/api/confirm`'s gate keeps
working unchanged once this override is added alongside it.

Lifted verbatim from `tests/api/test_reconcile.py::_verified_user`/
`_unverified_user` (the exact shape it already established) so every other
affected test file shares ONE definition instead of re-deriving it.
"""

from __future__ import annotations

from assayingest.auth.models import User

_TS = "2026-01-01T00:00:00+00:00"


def verified_user() -> User:
    return User(
        id="u", email="curator@example.com", password_hash=None,
        is_verified=True, auth_provider="password", created_at=_TS,
    )


def unverified_user() -> User:
    return User(
        id="u2", email="new@example.com", password_hash=None,
        is_verified=False, auth_provider="password", created_at=_TS,
    )
