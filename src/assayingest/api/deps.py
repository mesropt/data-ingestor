"""FastAPI dependency-injection seams (RESEARCH.md Pattern 1's DI note).

Every route depends on these functions, never constructs a store/client
directly -- a test overrides them via `app.dependency_overrides[get_x] =
lambda: fake`, with zero monkeypatching needed for the store/client seam
itself (the mapper function `service.propose_mapping` still uses the
existing monkeypatch idiom, since it is a plain module attribute, not a
FastAPI dependency).

Each store factory takes its `Session` from `Depends(get_session)` -- the one
place a Session can come from (`persistence/engine.py`). The RETURN types are the
abstract interfaces, never the concrete stores: dependencies point toward the
domain, so a route can never accidentally reach for a Postgres-specific method.

Overriding `get_session` alone therefore rebinds EVERY store the app resolves, which
is what makes the test suite's isolation total rather than per-store (see
`tests/conftest.py`). Three other Session paths -- lifespan seeding, the startup
schema check, and the CLI -- live outside FastAPI's DI and reach the same seam
directly; `dependency_overrides` cannot help them.
"""

from __future__ import annotations

import anthropic
from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import service
from ..auth.models import User
from ..auth.postgres_store import PostgresUserStore
from ..auth.session import SESSION_COOKIE_NAME, read_session_token
from ..auth.store import UserStore
from ..learning.field_set_store import FieldSetTemplateStore
from ..learning.postgres_field_set_store import PostgresFieldSetStore
from ..learning.postgres_schema_store import PostgresSchemaStore
from ..learning.postgres_store import PostgresProfileStore
from ..learning.schema_store import SchemaStore
from ..learning.store import ProfileStore
from ..persistence.engine import get_session

__all__ = [
    "get_anthropic_client",
    "get_current_user",
    "get_field_set_store",
    "get_profile_store",
    "get_schema_store",
    "get_session",
    "get_user_store",
    "require_user",
    "require_verified_user",
]


def get_profile_store(session: Session = Depends(get_session)) -> ProfileStore:
    """The learned-profile store, on this request's Session."""
    return PostgresProfileStore(session)


def get_field_set_store(session: Session = Depends(get_session)) -> FieldSetTemplateStore:
    """The field-set template store, on this request's Session (D-03) -- the same
    database, and the same Session, every other store here uses."""
    return PostgresFieldSetStore(session)


def get_schema_store(session: Session = Depends(get_session)) -> SchemaStore:
    """The governed crosswalk store, on this request's Session (D-07-02)."""
    return PostgresSchemaStore(session)


def get_user_store(session: Session = Depends(get_session)) -> UserStore:
    """The user store, on this request's Session (D-06-02)."""
    return PostgresUserStore(session)


def get_anthropic_client():
    """A real client when this deployment HAS credentials, else `None`.

    It used to return `None` unconditionally, on the reasoning that the SDK
    resolves credentials itself (`mapping/mapper.py` does `client or
    anthropic.Anthropic()`). That is true of the mapper -- and it silently
    disabled the LAYOUT JUDGE, which does not ask the same question. Its seam
    (`service._judge_for`) reads `client is None` as "there is no judge" and
    fails closed to `layout_unknown` on every sheet, so a correctly-configured
    server showed "The layout judge couldn't run" on every workbook, and no
    sheet ever got a Schema proposed. `None` meant two different things to two
    callers, and the quieter one lost.

    So the ambiguity is removed at the source: `None` now means exactly what
    every seam already reads it as -- NO CREDENTIALS, therefore no model call.

    Tests keep their offline guarantee by OVERRIDING this dependency (with
    `lambda: None` for the no-model path, or a fake client at this same seam --
    `tests/test_headers_only.py`'s `_FakeClient` idiom), so the suite never
    depends on what the ambient environment happens to hold.
    """
    if not service.has_credentials():
        return None
    return anthropic.Anthropic()


def get_current_user(
    di_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    store: UserStore = Depends(get_user_store),
) -> User | None:
    """Resolve the signed-in user from the session cookie, or `None`.

    Never raises: a caller that only needs to KNOW who is signed in (a UI-only
    affordance, or the future `/api/auth/config`) can depend on this directly.
    A missing, expired, or tampered cookie -- attacker-controlled input crossing
    the trust boundary (T-06-01) -- resolves to `None`, never an error."""
    if di_session is None:
        return None
    user_id = read_session_token(di_session)
    if user_id is None:
        return None
    return store.get(user_id)


def require_user(user: User | None = Depends(get_current_user)) -> User:
    """The P1 server-side gate (AUTH-01): raise 401 for any signed-out request
    to a governed endpoint, regardless of what the client renders."""
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to perform this action.")
    return user


def require_verified_user(user: User = Depends(require_user)) -> User:
    """D-06-06: a signed-in but unverified user IS authenticated (so this is a
    403, not a 401 -- re-authenticating would not fix it) but is still forbidden
    from a governed action until they verify their email. `is_verified` is read
    from the freshly-loaded `User` row, never a client-sent claim."""
    if not user.is_verified:
        raise HTTPException(
            status_code=403,
            detail="Verify your email to perform this action.",
        )
    return user
