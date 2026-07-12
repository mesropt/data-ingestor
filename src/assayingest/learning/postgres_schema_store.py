"""The PostgreSQL `SchemaStore` implementation (D-07-02) -- the canonical-model +
vendor-alias crosswalk store, in the same database every other store reaches
through the same `Session`.

Every statement binds its parameters -- never f-string SQL -- because a schema name,
vendor label, or source-column name is untrusted text flowing from an uploaded file
or a browser request (T-07-01, ASVS V5).

THREE invariants are enforced STRUCTURALLY here, not in Python:

  * SCHEMA-04 isolation -- every read filters on the `schema_id` /
    `canonical_field_id` foreign key, so a schema can only ever see its own fields
    and aliases. Postgres enforces foreign keys unconditionally, so the old
    `PRAGMA foreign_keys = ON` line is gone and this invariant got STRONGER.

  * ALIAS-03 immutable provenance -- `add_alias` is `ON CONFLICT DO NOTHING` against
    `UNIQUE(canonical_field_id, vendor, source_column)`, so a re-observed alias keeps
    its first-seen `provenance_actor`/`created_at`. There is deliberately NO
    `DO UPDATE` that could overwrite it. Do not "tidy" this into an upsert to match
    the other three stores -- the asymmetry IS the invariant.

  * P3 augment-only -- `_insert_missing_fields` is likewise `DO NOTHING`, so a field
    whose `(schema_id, name)` already exists is left untouched: a benign constraint
    difference never overwrites a stored definition, and nothing is ever deleted
    (D-07-03/04).

`DO NOTHING` is stricter than the old `INSERT OR IGNORE`, which also swallowed NOT
NULL and CHECK violations; `DO NOTHING` swallows only unique/exclusion conflicts.
Every NOT NULL column here is always supplied, so that is a tightening at no cost.

Ordering is by the `seq` Identity column, never `rowid` (which does not exist in
Postgres). Without it, `Schema.fields` and the alias list would come back in
whatever physical order Postgres felt like -- silently non-deterministic.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..domain.models import Alias, CanonicalField, Schema
from ..fields.loader import from_dict as _field_from_dict
from ..fields.models import Field
from ..persistence.models import AliasRow, CanonicalFieldRow, SchemaRow
from .schema_store import SchemaStore


class PostgresSchemaStore(SchemaStore):
    """A PostgreSQL crosswalk store behind the `SchemaStore` seam."""

    def __init__(self, session: Session) -> None:
        """Take a `Session` -- never an engine (see `learning/postgres_store.py`)."""
        self._session = session

    def create_schema(
        self, name: str, fields: tuple[Field, ...], created_by: str | None
    ) -> Schema:
        schema_id = str(uuid.uuid4())
        self._session.execute(
            insert(SchemaRow).values(
                id=schema_id,
                name=name,
                created_by=created_by,
                created_at=datetime.now(UTC).isoformat(),
            )
        )
        self._insert_missing_fields(schema_id, fields)
        self._session.commit()
        return self.get_schema(schema_id)

    def get_schema(self, identifier: str) -> Schema | None:
        row = self._session.scalars(
            select(SchemaRow)
            .where((SchemaRow.id == identifier) | (SchemaRow.name == identifier))
            .limit(1)
        ).first()
        if row is None:
            return None
        return self._entity_to_schema(row)

    def list_schemas(self) -> list[Schema]:
        rows = self._session.scalars(select(SchemaRow).order_by(SchemaRow.name)).all()
        return [self._entity_to_schema(row) for row in rows]

    def rename_schema(self, schema_id: str, new_name: str) -> Schema:
        # Only the label moves: fields and aliases hang off `schema_id`
        # foreign keys, so no other row is touched and a learned profile --
        # keyed on the fields-only `FieldSet.signature`, never the name --
        # keeps matching (SCHEMA-04 isolation is id-based, not name-based).
        self._session.execute(
            update(SchemaRow).where(SchemaRow.id == schema_id).values(name=new_name)
        )
        self._session.commit()
        return self.get_schema(schema_id)

    def add_or_update_fields(self, schema_id: str, fields: tuple[Field, ...]) -> Schema:
        self._insert_missing_fields(schema_id, fields)
        self._session.commit()
        return self.get_schema(schema_id)

    def add_alias(self, schema_id: str, field_name: str, alias: Alias) -> None:
        field_id = self._canonical_field_id(schema_id, field_name)
        if field_id is None:
            raise ValueError(
                f"Cannot record alias: schema {schema_id!r} has no "
                f"canonical field named {field_name!r}."
            )
        # DO NOTHING keeps the FIRST-seen row on a repeat (canonical_field_id, vendor,
        # source_column) -- provenance is never overwritten (ALIAS-03). NEVER DO UPDATE.
        self._session.execute(
            insert(AliasRow)
            .values(
                id=str(uuid.uuid4()),
                canonical_field_id=field_id,
                vendor=alias.vendor,
                source_column=alias.source_column,
                provenance_kind=alias.provenance_kind,
                provenance_actor=alias.provenance_actor,
                # Carried through verbatim from the domain object, never now():
                # re-stamping a curator's recorded time is the overwrite ALIAS-03 forbids.
                created_at=alias.created_at,
            )
            .on_conflict_do_nothing(
                index_elements=["canonical_field_id", "vendor", "source_column"],
                # The unique index is PARTIAL (`WHERE removed_at IS NULL`, D-10-15) --
                # ON CONFLICT must name the same predicate or Postgres cannot match it
                # to the index at all. Omitting this is exactly what would make a
                # tombstoned alias permanently block a re-add (T-10-09).
                index_where=AliasRow.removed_at.is_(None),
            )
        )
        self._session.commit()

    def list_aliases_for(self, schema_id: str) -> list[Alias]:
        rows = self._session.scalars(
            select(AliasRow)
            .join(CanonicalFieldRow, AliasRow.canonical_field_id == CanonicalFieldRow.id)
            .where(
                CanonicalFieldRow.schema_id == schema_id,
                # D-10-15: a tombstoned alias, or a live alias hanging off a
                # tombstoned field (belt and braces alongside the cascade),
                # must never surface here.
                AliasRow.removed_at.is_(None),
                CanonicalFieldRow.removed_at.is_(None),
            )
            .order_by(AliasRow.seq)  # replaces `ORDER BY a.rowid`
        ).all()
        return [_entity_to_alias(row) for row in rows]

    def update_field(self, schema_id: str, field_name: str, field: Field) -> Schema:
        field_id = self._canonical_field_id(schema_id, field_name)
        if field_id is None:
            raise ValueError(
                f"Cannot update field: schema {schema_id!r} has no live canonical "
                f"field named {field_name!r}."
            )
        allowed = (
            json.dumps(list(field.allowed_values))
            if field.allowed_values is not None
            else None
        )
        # A genuine overwrite -- unlike `_insert_missing_fields`, this is the
        # store's first real UPDATE. Scoped by BOTH id and schema_id so it can
        # never reach across the SCHEMA-04 boundary even if a caller ever
        # passed a field_id from a different schema.
        self._session.execute(
            update(CanonicalFieldRow)
            .where(
                CanonicalFieldRow.id == field_id, CanonicalFieldRow.schema_id == schema_id
            )
            .values(
                name=field.name,
                description=field.description,
                type=field.type,
                allowed_values_json=allowed,
                unit=field.unit,
                required=field.required,
                min=field.min,
                max=field.max,
                date_format=field.date_format,
            )
        )
        self._session.commit()
        return self.get_schema(schema_id)

    def remove_field(
        self, schema_id: str, field_name: str, *, removed_by: str, removed_at: str
    ) -> Schema:
        field_id = self._canonical_field_id(schema_id, field_name)
        if field_id is None:
            raise ValueError(
                f"Cannot remove field: schema {schema_id!r} has no live canonical "
                f"field named {field_name!r}."
            )
        # Cascade FIRST, in the SAME transaction as the field's own tombstone
        # (one commit below): a partial cascade would leave aliases pointing
        # at a dead field, and the crosswalk would keep matching a vendor
        # name onto a field that no longer exists (D-10-15).
        self._session.execute(
            update(AliasRow)
            .where(AliasRow.canonical_field_id == field_id, AliasRow.removed_at.is_(None))
            .values(removed_at=removed_at, removed_by=removed_by)
        )
        self._session.execute(
            update(CanonicalFieldRow)
            .where(
                CanonicalFieldRow.id == field_id, CanonicalFieldRow.schema_id == schema_id
            )
            .values(removed_at=removed_at, removed_by=removed_by)
        )
        self._session.commit()
        return self.get_schema(schema_id)

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
        field_id = self._canonical_field_id(schema_id, field_name)
        if field_id is None:
            raise ValueError(
                f"Cannot remove alias: schema {schema_id!r} has no live canonical "
                f"field named {field_name!r}."
            )
        result = self._session.execute(
            update(AliasRow)
            .where(
                AliasRow.canonical_field_id == field_id,
                AliasRow.vendor == vendor,
                AliasRow.source_column == source_column,
                AliasRow.removed_at.is_(None),
            )
            .values(removed_at=removed_at, removed_by=removed_by)
        )
        if result.rowcount == 0:
            raise ValueError(
                f"Cannot remove alias: schema {schema_id!r} field {field_name!r} has "
                f"no live alias for vendor {vendor!r}, column {source_column!r}."
            )
        self._session.commit()

    # --- internals ---------------------------------------------------------

    def _insert_missing_fields(self, schema_id: str, fields: tuple[Field, ...]) -> None:
        """Augment-only: a field whose (schema_id, name) already exists is left
        untouched (ON CONFLICT DO NOTHING against the UNIQUE constraint), so a benign
        constraint difference never overwrites the stored definition and nothing is
        ever deleted (P3, D-07-03/04)."""
        for field in fields:
            allowed = (
                json.dumps(list(field.allowed_values))
                if field.allowed_values is not None
                else None
            )
            self._session.execute(
                insert(CanonicalFieldRow)
                .values(
                    id=str(uuid.uuid4()),
                    schema_id=schema_id,
                    name=field.name,
                    description=field.description,
                    type=field.type,
                    allowed_values_json=allowed,
                    unit=field.unit,
                    # No int() cast: `required` is a real Postgres BOOLEAN.
                    required=field.required,
                    min=field.min,
                    max=field.max,
                    date_format=field.date_format,
                )
                .on_conflict_do_nothing(
                    index_elements=["schema_id", "name"],
                    # Same partial-index reasoning as `add_alias` above.
                    index_where=CanonicalFieldRow.removed_at.is_(None),
                )
            )

    def _canonical_field_id(self, schema_id: str, field_name: str) -> str | None:
        # D-10-15: excludes tombstoned fields, so `add_alias` can never attach
        # an alias to a removed field (it raises its existing ValueError
        # instead), and a double-`remove_field`/`update_field` on an already
        # tombstoned name correctly raises too.
        return self._session.scalars(
            select(CanonicalFieldRow.id).where(
                CanonicalFieldRow.schema_id == schema_id,
                CanonicalFieldRow.name == field_name,
                CanonicalFieldRow.removed_at.is_(None),
            )
        ).first()

    def _entity_to_schema(self, row: SchemaRow) -> Schema:
        """The wire (ORM rows) -> domain (`Schema`) boundary translator -- the analog
        of `learning/postgres_store.py::_entity_to_profile`. Reads only rows joined by
        this schema's `id` (SCHEMA-04 isolation)."""
        field_rows = self._session.scalars(
            select(CanonicalFieldRow)
            .where(
                CanonicalFieldRow.schema_id == row.id,
                # D-10-15: a tombstoned field is invisible to every caller of
                # this method -- no per-caller filter needed anywhere else.
                CanonicalFieldRow.removed_at.is_(None),
            )
            .order_by(CanonicalFieldRow.seq)  # replaces `ORDER BY rowid`
        ).all()
        fields = tuple(
            CanonicalField(
                field=_entity_to_field(field_row),
                aliases=self._aliases_for_field(field_row.id),
            )
            for field_row in field_rows
        )
        return Schema(
            id=row.id,
            name=row.name,
            fields=fields,
            created_by=row.created_by,
            created_at=row.created_at,
        )

    def _aliases_for_field(self, field_id: str) -> tuple[Alias, ...]:
        rows = self._session.scalars(
            select(AliasRow)
            .where(
                AliasRow.canonical_field_id == field_id,
                # D-10-15: a tombstoned alias is invisible to every caller.
                AliasRow.removed_at.is_(None),
            )
            .order_by(AliasRow.seq)  # replaces `ORDER BY rowid`
        ).all()
        return tuple(_entity_to_alias(row) for row in rows)


def _entity_to_field(row: CanonicalFieldRow) -> Field:
    """Rebuild a `Field` through `fields.loader.from_dict` (not a bare `Field(**...)`)
    so a round-tripped canonical field gets the exact same name/length/type guards a
    freshly-declared one did -- never a second, weaker reconstruction path. One field
    at a time, so the 50-field loader cap never applies to a read.

    No bool() cast on `required`: it already arrives as a Python bool."""
    field_dict = {
        "name": row.name,
        "description": row.description,
        "type": row.type,
        "allowed_values": json.loads(row.allowed_values_json)
        if row.allowed_values_json
        else None,
        "unit": row.unit,
        "required": row.required,
        "min": row.min,
        "max": row.max,
        "date_format": row.date_format,
    }
    return _field_from_dict({"fields": [field_dict]}).fields[0]


def _entity_to_alias(row: AliasRow) -> Alias:
    """The `AliasRow -> Alias` boundary translator -- provenance carried through
    verbatim (ALIAS-02/03)."""
    return Alias(
        vendor=row.vendor,
        source_column=row.source_column,
        provenance_kind=row.provenance_kind,
        provenance_actor=row.provenance_actor,
        created_at=row.created_at,
    )
