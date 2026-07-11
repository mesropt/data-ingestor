"""The governed-Schema repository seam (D-07-02) -- the canonical-model +
vendor-alias crosswalk store, behind an ABC exactly like `store.py`'s
`ProfileStore`. A Postgres-backed multi-tenant store (FUTURE) will implement
this identically; domain code, services, and the API depend only on this
interface, never on `sqlite3` directly (CLAUDE.md: map infrastructure to
domain at the boundary).

This store is the *human-curated master*, distinct from the profile store's
*learned-mapping cache* -- a NEW seam, not a widening of `ProfileStore`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.models import Alias, Schema
from ..fields.models import Field


class SchemaStore(ABC):
    """The seam a Postgres-backed governed store (FUTURE) implements identically.

    Two invariants every implementation must uphold structurally, not by
    convention: schemas are isolated (SCHEMA-04 -- no shared fields or
    aliases) and alias provenance is immutable once first seen (ALIAS-03 --
    who/when is never lost or overwritten). Every write is augment-only (P3).
    """

    @abstractmethod
    def create_schema(
        self, name: str, fields: tuple[Field, ...], created_by: str | None
    ) -> Schema:
        """Persist a new governed Schema whose canonical fields are `fields`
        (each with no aliases yet) and return it with a generated `id`.
        `name` is the domain identity -- unique per store."""

    @abstractmethod
    def get_schema(self, identifier: str) -> Schema | None:
        """The Schema matching this `id` OR `name`, fully populated with its
        canonical fields and their aliases -- or `None` on any miss."""

    @abstractmethod
    def list_schemas(self) -> list[Schema]:
        """Every governed Schema in the store (SCHEMA-04 -- they coexist)."""

    @abstractmethod
    def add_or_update_fields(self, schema_id: str, fields: tuple[Field, ...]) -> Schema:
        """Augment a Schema with any `fields` whose name is not already
        present; an existing field's definition is kept, never overwritten,
        and nothing is ever deleted (P3). Returns the updated Schema."""

    @abstractmethod
    def add_alias(self, schema_id: str, field_name: str, alias: Alias) -> None:
        """Record `alias` on the named canonical field, idempotent by
        (canonical field, vendor, source column): a re-observed alias keeps
        its first-seen provenance actor and timestamp (ALIAS-03), never
        overwriting who recorded it or when."""

    @abstractmethod
    def list_aliases_for(self, schema_id: str) -> list[Alias]:
        """Every alias recorded against this Schema, each with its vendor and
        full provenance (kind/actor/created_at) intact (ALIAS-01/02/03)."""
