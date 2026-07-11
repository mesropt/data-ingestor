"""FastAPI dependency-injection seams (RESEARCH.md Pattern 1's DI note).

Every route depends on these functions, never constructs a store/client
directly -- a test overrides them via `app.dependency_overrides[get_x] =
lambda: fake`, with zero monkeypatching needed for the store/client seam
itself (the mapper function `service.propose_mapping` still uses the
existing monkeypatch idiom, since it is a plain module attribute, not a
FastAPI dependency).
"""

from __future__ import annotations

from ..learning.field_set_store import FieldSetTemplateStore
from ..learning.sqlite_field_set_store import SqliteFieldSetStore
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


def get_anthropic_client():
    """`None` by default -- the SDK resolves credentials itself
    (`anthropic.Anthropic()` with no args) exactly as `mapping/mapper.py`'s
    own `client or anthropic.Anthropic()` fallback does. Overridable in
    tests to inject a fake client-shaped object (mirrors
    `tests/test_headers_only.py`'s `_FakeClient`/`_FakeMessages` idiom) so a
    real end-to-end mapper call can be tested without a real network call.
    """
    return None
