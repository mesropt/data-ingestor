"""FastAPI dependency-injection seams (RESEARCH.md Pattern 1's DI note).

Every route depends on these functions, never constructs a store/client
directly -- a test overrides them via `app.dependency_overrides[get_x] =
lambda: fake`, with zero monkeypatching needed for the store/client seam
itself (the mapper function `service.propose_mapping` still uses the
existing monkeypatch idiom, since it is a plain module attribute, not a
FastAPI dependency).
"""

from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException

from ..auth.models import User
from ..auth.session import SESSION_COOKIE_NAME, read_session_token
from ..auth.sqlite_store import SqliteUserStore
from ..auth.store import UserStore
from ..learning.field_set_store import FieldSetTemplateStore
from ..learning.schema_store import SchemaStore
from ..learning.sqlite_field_set_store import SqliteFieldSetStore
from ..learning.sqlite_schema_store import SqliteSchemaStore
from ..learning.sqlite_store import SqliteProfileStore
from ..learning.store import ProfileStore


def get_profile_store() -> ProfileStore:
    """Default: the project's standard local SQLite path
    (`.assayingest/profiles.db`, relative to the working directory) --
    identical default `cli.py::_resolve_store` uses. Tests override this
    with a tmp-path store so no test ever touches the real demo database."""
    return SqliteProfileStore()


def get_field_set_store() -> FieldSetTemplateStore:
    """Default: `SqliteFieldSetStore`, the same local SQLite file
    `get_profile_store` writes to (D-03) -- field-set templates and learned
    profiles share one consistent local store. Tests override this with a
    tmp-path store so no test ever touches the real demo database."""
    return SqliteFieldSetStore()


def get_schema_store() -> SchemaStore:
    """Default: `SqliteSchemaStore`, the SAME local SQLite file
    `get_profile_store`/`get_field_set_store`/`get_user_store` write to
    (D-07-02) -- the governed crosswalk store shares one consistent local
    store. Tests override this with a tmp-path store so no test ever touches
    the real demo database (mirrors `get_profile_store`/`get_user_store`)."""
    return SqliteSchemaStore()


def get_anthropic_client():
    """`None` by default -- the SDK resolves credentials itself
    (`anthropic.Anthropic()` with no args) exactly as `mapping/mapper.py`'s
    own `client or anthropic.Anthropic()` fallback does. Overridable in
    tests to inject a fake client-shaped object (mirrors
    `tests/test_headers_only.py`'s `_FakeClient`/`_FakeMessages` idiom) so a
    real end-to-end mapper call can be tested without a real network call.
    """
    return None


def get_user_store() -> UserStore:
    """Default: `SqliteUserStore`, the SAME local SQLite file
    `get_profile_store`/`get_field_set_store` write to (D-06-02) -- users,
    profiles, and field-set templates share one local store. Tests override
    this with a tmp-path store so no test ever touches the real demo database
    (mirrors `get_profile_store`)."""
    return SqliteUserStore()


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
