"""The local-SQLite `UserStore` implementation (D-06-02).

Users live in the SAME local SQLite file as learned profiles and field-set
templates -- `_DEFAULT_DB_PATH` is imported from `learning/sqlite_store.py` so
there is one local store per install (P2 local-first). Every query uses
parameterised `?` placeholders (an email is untrusted request input, ASVS V5),
mirroring `learning/sqlite_store.py`.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from ..learning.sqlite_store import _DEFAULT_DB_PATH  # same local file (D-06-02)
from .models import User
from .store import UserStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    password_hash TEXT,
    is_verified INTEGER NOT NULL DEFAULT 0,
    auth_provider TEXT NOT NULL DEFAULT 'password',
    created_at TEXT NOT NULL,
    UNIQUE(email)
);
"""


class SqliteUserStore(UserStore):
    """A local SQLite file behind the `UserStore` seam."""

    def __init__(self, db_path: str | Path = _DEFAULT_DB_PATH) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self._path)) as conn:
            conn.executescript(_SCHEMA)

    def save(self, user: User) -> None:
        # `with conn:` commits the transaction (not a close -- `closing()` owns
        # that). ON CONFLICT(email) upserts a re-registered email rather than
        # raising or duplicating; `id` is left untouched on update so an
        # existing user's stable id survives a credential change.
        with closing(sqlite3.connect(self._path)) as conn, conn:
            conn.execute(
                "INSERT INTO users "
                "(id, email, password_hash, is_verified, auth_provider, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(email) DO UPDATE SET "
                "password_hash=excluded.password_hash, "
                "is_verified=excluded.is_verified, "
                "auth_provider=excluded.auth_provider",
                (
                    user.id,
                    user.email,
                    user.password_hash,
                    int(user.is_verified),
                    user.auth_provider,
                    user.created_at,
                ),
            )

    def get(self, user_id: str) -> User | None:
        with closing(sqlite3.connect(self._path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(row) if row is not None else None

    def get_by_email(self, email: str) -> User | None:
        with closing(sqlite3.connect(self._path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return _row_to_user(row) if row is not None else None

    def mark_verified(self, user_id: str) -> None:
        with closing(sqlite3.connect(self._path)) as conn, conn:
            conn.execute("UPDATE users SET is_verified = 1 WHERE id = ?", (user_id,))

    def get_or_create_by_email(self, email: str) -> User:
        existing = self.get_by_email(email)
        if existing is not None:
            return existing
        # A Google-provisioned account: email already asserted-verified by the
        # IdP (D-06-05), no local password.
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            password_hash=None,
            is_verified=True,
            auth_provider="google",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.save(user)
        return user


def _row_to_user(row: sqlite3.Row) -> User:
    """The SQLite-row -> domain-`User` boundary translator (the analog of
    `learning/sqlite_store.py::_row_to_profile`)."""
    return User(
        id=row["id"],
        email=row["email"],
        password_hash=row["password_hash"],
        is_verified=bool(row["is_verified"]),
        auth_provider=row["auth_provider"],
        created_at=row["created_at"],
    )
