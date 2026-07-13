"""The PostgreSQL `UserStore` implementation (D-06-02).

Users live in the SAME database as learned profiles, field-set templates, and the
governed schema store -- one store per deployment, reached through one `Session`.

Every statement binds its parameters -- never f-string SQL -- because an email is
untrusted request input (ASVS V5), mirroring `learning/postgres_store.py`.

The password hashing scheme is NOT this module's business: a `password_hash` is an
opaque pwdlib/Argon2 string, written and read verbatim.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..persistence.models import UserRow
from .models import User
from .store import UserStore


class PostgresUserStore(UserStore):
    """A PostgreSQL table behind the `UserStore` seam."""

    def __init__(self, session: Session) -> None:
        """Take a `Session` -- never an engine (see `learning/postgres_store.py`)."""
        self._session = session

    def save(self, user: User) -> None:
        stmt = insert(UserRow).values(
            id=user.id,
            email=user.email,
            password_hash=user.password_hash,
            # No int() cast: `is_verified` is a real Postgres BOOLEAN, which rejects
            # the integer 1 outright. The Python bool goes straight through.
            is_verified=user.is_verified,
            auth_provider=user.auth_provider,
            created_at=user.created_at,
        )
        # Upserts a re-registered email rather than raising or duplicating. `id` is
        # deliberately absent from the SET clause: an existing user's stable id must
        # survive a credential change.
        stmt = stmt.on_conflict_do_update(
            index_elements=["email"],
            set_={
                "password_hash": stmt.excluded.password_hash,
                "is_verified": stmt.excluded.is_verified,
                "auth_provider": stmt.excluded.auth_provider,
            },
        )
        self._session.execute(stmt)
        self._session.commit()

    def get(self, user_id: str) -> User | None:
        row = self._session.scalars(select(UserRow).where(UserRow.id == user_id)).first()
        return _entity_to_user(row) if row is not None else None

    def get_by_email(self, email: str) -> User | None:
        row = self._session.scalars(select(UserRow).where(UserRow.email == email)).first()
        return _entity_to_user(row) if row is not None else None

    def mark_verified(self, user_id: str) -> None:
        # The boolean True, not the integer 1 the previous store wrote.
        self._session.execute(
            update(UserRow).where(UserRow.id == user_id).values(is_verified=True)
        )
        self._session.commit()

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


def _entity_to_user(row: UserRow) -> User:
    """The wire (ORM row) -> domain (`User`) boundary translator -- the analog of
    `learning/postgres_store.py::_entity_to_profile`.

    No bool() cast: `is_verified` already arrives as a Python bool from a Postgres
    BOOLEAN column."""
    return User(
        id=row.id,
        email=row.email,
        password_hash=row.password_hash,
        is_verified=row.is_verified,
        auth_provider=row.auth_provider,
        created_at=row.created_at,
    )
