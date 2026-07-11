"""The user repository seam (D-06-02) -- the interface a Postgres-backed store
(a future multi-tenant phase) would implement identically. The API layer and
its DI functions depend only on this abstract interface, never on `sqlite3`
directly, mirroring `learning/store.py::ProfileStore`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import User


class UserStore(ABC):
    """The seam a Postgres-backed store (a future phase) implements identically.

    A local SQLite file is v2's only implementation (`sqlite_store.py`), but
    nothing in the API layer may depend on that fact -- only on the methods
    declared here (mirrors `ProfileStore`'s docstring, P2 local-first).
    """

    @abstractmethod
    def save(self, user: User) -> None:
        """Persist `user`, upserting on an identical `email` (never on `id`,
        since `id` is minted fresh on first save)."""

    @abstractmethod
    def get(self, user_id: str) -> User | None:
        """The one user with this id, or `None` on any miss -- `get_current_user`
        depends on this never raising."""

    @abstractmethod
    def get_by_email(self, email: str) -> User | None:
        """The one user with this email, or `None` on any miss (the sign-in
        credential lookup)."""

    @abstractmethod
    def mark_verified(self, user_id: str) -> None:
        """Flip `is_verified` to True for this user (the email-verify action,
        idempotent -- D-06-04)."""

    @abstractmethod
    def get_or_create_by_email(self, email: str) -> User:
        """Return the existing user for `email` unchanged, or provision a new
        verified, password-less `auth_provider="google"` user for a new email
        (the Google OAuth callback path, D-06-05)."""
