"""The PostgreSQL rows behind `api.state.UploadRegistry`'s write-through.

Deliberately DUMB: this store moves opaque `(token, entry_json, timestamps)`
strings and knows nothing about `UploadEntry` -- the serialization boundary
lives in `api/state.py`, right next to the dataclass it serializes. That
split is what keeps the import graph acyclic (`state` -> `pending_store` ->
`persistence`, never back) and keeps this module a pure persistence adapter,
mirroring `learning/postgres_store.py`'s Session-in-the-constructor pattern.

The TTL/expiry POLICY (what "expired" means, when to sweep, purge on
confirm) is owned by the registry; this store only executes the deletes it
is asked for. `expires_at` comparisons are plain SQL string comparisons,
sound because `api.state` writes fixed-width UTC ISO-8601 exclusively --
lexicographic order IS chronological order for that format.

Every statement is SQLAlchemy Core with bound parameters -- `entry_json`
embeds untrusted uploaded file content and must only ever travel as data
(ASVS V5, same rule as the profile store).
"""

from __future__ import annotations

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from ..persistence.models import PendingUploadRow


class PostgresPendingUploadStore:
    """The `pending_uploads` table behind `UploadRegistry`'s persistence."""

    def __init__(self, session: Session) -> None:
        """Take a `Session` -- never an engine, never a sessionmaker.

        Load-bearing for the test suite's outer-transaction isolation, for
        exactly the reasons `PostgresProfileStore.__init__` documents.
        """
        self._session = session

    def save(self, token: str, entry_json: str, created_at: str, expires_at: str) -> None:
        """Persist one review-ready entry under its freshly-minted token.

        A plain INSERT, no upsert: `UploadRegistry.put` mints a new uuid4
        per call, so a token collision is a bug worth surfacing, never a
        conflict to paper over.
        """
        self._session.execute(
            insert(PendingUploadRow).values(
                token=token,
                entry_json=entry_json,
                created_at=created_at,
                expires_at=expires_at,
            )
        )
        self._session.commit()

    def load(self, token: str) -> tuple[str, str] | None:
        """The `(entry_json, expires_at)` pair for `token`, or `None`.

        Expiry is NOT judged here -- the registry owns the clock and the
        policy; this method only fetches what is stored.
        """
        row = self._session.scalars(
            select(PendingUploadRow).where(PendingUploadRow.token == token)
        ).first()
        return (row.entry_json, row.expires_at) if row is not None else None

    def delete(self, token: str) -> None:
        """Remove one row (confirm purge, or an expired row found on lookup).
        Deleting an already-absent token is a no-op, not an error."""
        self._session.execute(
            delete(PendingUploadRow).where(PendingUploadRow.token == token)
        )
        self._session.commit()

    def delete_expired(self, now_iso: str) -> None:
        """The lazy TTL sweep: drop every row whose `expires_at` has passed,
        so uploaded cell values never linger at rest waiting for someone to
        ask for their dead token."""
        self._session.execute(
            delete(PendingUploadRow).where(PendingUploadRow.expires_at <= now_iso)
        )
        self._session.commit()
