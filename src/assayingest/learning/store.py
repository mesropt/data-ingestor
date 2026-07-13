"""The profile repository seam (D-01) -- the interface a Postgres-backed
store (Phase 4+, multi-user API) will implement identically. Domain code and
the CLI depend only on this abstract interface, never on a database driver
(CLAUDE.md: "Map infrastructure models to domain models at the layer
boundary -- don't mix layers in one dataclass").
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .profile import LearnedProfile


class ProfileStore(ABC):
    """The seam a Postgres-backed store (Phase 4+) implements identically.

    `PostgresProfileStore` (`postgres_store.py`) is the implementation, but
    nothing in the domain or the CLI's auto-apply path may depend on that fact --
    only on the three methods declared here. This interface contains zero SQL, and
    that is exactly why swapping the database out cost the domain nothing.
    """

    @abstractmethod
    def save(self, profile: LearnedProfile) -> None:
        """Persist `profile`, upserting on an identical
        `(field_set_signature, column_signature)` key."""

    @abstractmethod
    def find(self, field_set_signature: str, column_signature: str) -> LearnedProfile | None:
        """The one profile matching this exact key, or `None` on any miss
        (LEARN-04's Claude fallback depends on this never raising)."""

    @abstractmethod
    def list_for_field_set(self, field_set_signature: str) -> list[LearnedProfile]:
        """Every profile saved for this field set -- one vendor may hold
        several across format drift (LEARN-05)."""
