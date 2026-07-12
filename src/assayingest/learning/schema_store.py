"""The governed-Schema repository seam (D-07-02) -- the canonical-model +
vendor-alias crosswalk store, behind an ABC exactly like `store.py`'s
`ProfileStore`. A Postgres-backed multi-tenant store (FUTURE) will implement
this identically; domain code, services, and the API depend only on this
interface, never on a database driver (CLAUDE.md: map infrastructure to
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

    Invariants every implementation must uphold structurally, not by
    convention: schemas are isolated (SCHEMA-04 -- no shared fields or
    aliases) and alias provenance is immutable once first seen (ALIAS-03 --
    who/when is never lost or overwritten).

    The store is no longer purely augment-only (D-10-12/D-10-15): a machine
    may only ADD (`add_or_update_fields`, `add_alias`, both still
    `ON CONFLICT DO NOTHING`); only a human, through the explicit edit path,
    may UPDATE or REMOVE, and every removal is recorded as a tombstone
    carrying who and when -- never a physical DELETE.
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
    def rename_schema(self, schema_id: str, new_name: str) -> Schema:
        """Change the Schema's name -- its `id`, canonical fields, aliases,
        and all provenance are untouched; only the domain-identity label
        moves. Uniqueness stays structural (the store's UNIQUE on `name`);
        the caller (`service.rename_schema`) owns the friendly collision
        check so a clash surfaces as a typed error, not a driver exception.
        Returns the renamed Schema."""

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
        """Every LIVE alias recorded against this Schema, each with its vendor
        and full provenance (kind/actor/created_at) intact (ALIAS-01/02/03).
        A tombstoned alias (D-10-15), or a live alias on a tombstoned field,
        is never returned."""

    @abstractmethod
    def update_field(self, schema_id: str, field_name: str, field: Field) -> Schema:
        """The ONLY method that overwrites a stored field definition --
        genuinely `DO UPDATE`, unlike the augment-only `add_or_update_fields`.
        Scoped by `schema_id` (SCHEMA-04): can never touch a field belonging
        to a different Schema. Raises `ValueError` naming the consequence
        when `field_name` is absent from this Schema, or already tombstoned
        (D-10-15) -- you cannot edit what was removed."""

    @abstractmethod
    def remove_field(
        self, schema_id: str, field_name: str, *, removed_by: str, removed_at: str
    ) -> Schema:
        """Tombstone the named canonical field -- never a physical DELETE
        (D-10-15). Cascades a tombstone to every LIVE alias hanging off it,
        in the SAME transaction, so the crosswalk can never match a vendor
        name onto a field that no longer exists. Scoped by `schema_id`
        (SCHEMA-04). Raises `ValueError` naming the consequence when
        `field_name` is absent or already tombstoned."""

    @abstractmethod
    def remove_alias(
        self,
        schema_id: str,
        field_name: str,
        vendor: str,
        source_column: str,
        *,
        removed_by: str,
        removed_at: str,
    ) -> None:
        """Tombstone one alias -- never a physical DELETE (D-10-15). Scoped
        by `schema_id` (SCHEMA-04). Raises `ValueError` naming the
        consequence when no LIVE alias matches `field_name`/`vendor`/
        `source_column` in this Schema."""
