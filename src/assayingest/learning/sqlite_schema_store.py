"""The local SQLite `SchemaStore` implementation (D-07-02) -- mirrors
`learning/sqlite_field_set_store.py` line-for-line, in the SAME local SQLite
file (`_DEFAULT_DB_PATH`) the profile + field-set + user stores already write
to: one consistent local governed store, gitignored, never a network DB in
v1 (P2).

Together with `learning/sqlite_store.py` and
`learning/sqlite_field_set_store.py`, this is one of the only modules in this
project allowed to `import sqlite3`.

Every query uses parameterised `?` placeholders -- never f-string SQL -- a
schema name, vendor label, or source-column name is untrusted text flowing
from an uploaded file or a browser request (T-07-01, ASVS V5), no different
in trust level from the header strings `sqlite_store.py`'s docstring already
calls out.

Two invariants are enforced structurally here, not in Python:
  * SCHEMA-04 isolation -- every read filters on the `schema_id` /
    `canonical_field_id` foreign key, so a schema can only ever see its own
    fields and aliases.
  * ALIAS-03 immutable provenance -- `add_alias` is `INSERT OR IGNORE`
    against `UNIQUE(canonical_field_id, vendor, source_column)`, so a
    re-observed alias keeps its first-seen `provenance_actor`/`created_at`;
    there is deliberately no `ON CONFLICT DO UPDATE` that could overwrite it.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from ..domain.models import Alias, CanonicalField, Schema
from ..fields.loader import from_dict as _field_from_dict
from ..fields.models import Field
from .schema_store import SchemaStore
from .sqlite_store import _DEFAULT_DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_by TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(name)
);
CREATE TABLE IF NOT EXISTS canonical_field (
    id TEXT PRIMARY KEY,
    schema_id TEXT NOT NULL REFERENCES schema(id),
    name TEXT NOT NULL,
    description TEXT,
    type TEXT,
    allowed_values_json TEXT,
    unit TEXT,
    required INTEGER NOT NULL DEFAULT 1,
    min REAL,
    max REAL,
    date_format TEXT,
    UNIQUE(schema_id, name)
);
CREATE TABLE IF NOT EXISTS alias (
    id TEXT PRIMARY KEY,
    canonical_field_id TEXT NOT NULL REFERENCES canonical_field(id),
    vendor TEXT NOT NULL,
    source_column TEXT NOT NULL,
    provenance_kind TEXT NOT NULL,
    provenance_actor TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(canonical_field_id, vendor, source_column)
);
CREATE INDEX IF NOT EXISTS idx_canonical_field_schema
    ON canonical_field(schema_id);
CREATE INDEX IF NOT EXISTS idx_alias_field
    ON alias(canonical_field_id);
"""


class SqliteSchemaStore(SchemaStore):
    """A local SQLite file behind the `SchemaStore` seam -- the same file the
    profile and field-set stores write to (`_DEFAULT_DB_PATH`, D-07-02)."""

    def __init__(self, db_path: str | Path = _DEFAULT_DB_PATH) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        """A connection with foreign-key enforcement ON -- so an alias can
        never reference a canonical field outside its own schema, backing the
        SCHEMA-04 isolation the queries already filter for."""
        conn = sqlite3.connect(self._path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn

    def create_schema(
        self, name: str, fields: tuple[Field, ...], created_by: str | None
    ) -> Schema:
        schema_id = str(uuid.uuid4())
        # `with conn:` commits/rolls back the transaction (not the connection
        # close -- `closing()` still owns that, mirrors sqlite_store.py).
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO schema (id, name, created_by, created_at) "
                "VALUES (?, ?, ?, ?)",
                (schema_id, name, created_by, datetime.now(UTC).isoformat()),
            )
            self._insert_missing_fields(conn, schema_id, fields)
        return self.get_schema(schema_id)

    def get_schema(self, identifier: str) -> Schema | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM schema WHERE id = ? OR name = ? LIMIT 1",
                (identifier, identifier),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_schema(conn, row)

    def list_schemas(self) -> list[Schema]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM schema ORDER BY name").fetchall()
            return [self._row_to_schema(conn, row) for row in rows]

    def add_or_update_fields(self, schema_id: str, fields: tuple[Field, ...]) -> Schema:
        with closing(self._connect()) as conn, conn:
            self._insert_missing_fields(conn, schema_id, fields)
        return self.get_schema(schema_id)

    def add_alias(self, schema_id: str, field_name: str, alias: Alias) -> None:
        with closing(self._connect()) as conn, conn:
            field_id = self._canonical_field_id(conn, schema_id, field_name)
            if field_id is None:
                raise ValueError(
                    f"Cannot record alias: schema {schema_id!r} has no "
                    f"canonical field named {field_name!r}."
                )
            # INSERT OR IGNORE keeps the FIRST-seen row on a repeat
            # (canonical_field_id, vendor, source_column) -- provenance is
            # never overwritten (ALIAS-03). No ON CONFLICT DO UPDATE.
            conn.execute(
                "INSERT OR IGNORE INTO alias "
                "(id, canonical_field_id, vendor, source_column, "
                " provenance_kind, provenance_actor, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    field_id,
                    alias.vendor,
                    alias.source_column,
                    alias.provenance_kind,
                    alias.provenance_actor,
                    alias.created_at,
                ),
            )

    def list_aliases_for(self, schema_id: str) -> list[Alias]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT a.* FROM alias a "
                "JOIN canonical_field c ON a.canonical_field_id = c.id "
                "WHERE c.schema_id = ? ORDER BY a.rowid",
                (schema_id,),
            ).fetchall()
            return [_row_to_alias(row) for row in rows]

    # --- internals ---------------------------------------------------------

    def _insert_missing_fields(
        self, conn: sqlite3.Connection, schema_id: str, fields: tuple[Field, ...]
    ) -> None:
        """Augment-only: a field whose (schema_id, name) already exists is
        left untouched (INSERT OR IGNORE against the UNIQUE constraint), so a
        benign constraint difference never overwrites the stored definition
        and nothing is ever deleted (P3, D-07-03/04)."""
        for field in fields:
            allowed = (
                json.dumps(list(field.allowed_values))
                if field.allowed_values is not None
                else None
            )
            conn.execute(
                "INSERT OR IGNORE INTO canonical_field "
                "(id, schema_id, name, description, type, allowed_values_json, "
                " unit, required, min, max, date_format) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    schema_id,
                    field.name,
                    field.description,
                    field.type,
                    allowed,
                    field.unit,
                    int(field.required),
                    field.min,
                    field.max,
                    field.date_format,
                ),
            )

    @staticmethod
    def _canonical_field_id(
        conn: sqlite3.Connection, schema_id: str, field_name: str
    ) -> str | None:
        row = conn.execute(
            "SELECT id FROM canonical_field WHERE schema_id = ? AND name = ?",
            (schema_id, field_name),
        ).fetchone()
        return row["id"] if row is not None else None

    def _row_to_schema(self, conn: sqlite3.Connection, row: sqlite3.Row) -> Schema:
        """The wire (SQLite rows) -> domain (`Schema`) boundary translator --
        the analog of `sqlite_store.py::_row_to_profile`. Reads only rows
        joined by this schema's `id` (SCHEMA-04 isolation)."""
        field_rows = conn.execute(
            "SELECT * FROM canonical_field WHERE schema_id = ? ORDER BY rowid",
            (row["id"],),
        ).fetchall()
        fields = tuple(
            CanonicalField(
                field=_row_to_field(field_row),
                aliases=self._aliases_for_field(conn, field_row["id"]),
            )
            for field_row in field_rows
        )
        return Schema(
            id=row["id"],
            name=row["name"],
            fields=fields,
            created_by=row["created_by"],
            created_at=row["created_at"],
        )

    def _aliases_for_field(
        self, conn: sqlite3.Connection, field_id: str
    ) -> tuple[Alias, ...]:
        rows = conn.execute(
            "SELECT * FROM alias WHERE canonical_field_id = ? ORDER BY rowid",
            (field_id,),
        ).fetchall()
        return tuple(_row_to_alias(row) for row in rows)


def _row_to_field(row: sqlite3.Row) -> Field:
    """Rebuild a `Field` through `fields.loader.from_dict` (not a bare
    `Field(**...)`) so a round-tripped canonical field gets the exact same
    name/length/type guards a freshly-declared one did -- never a second,
    weaker reconstruction path (mirrors `sqlite_field_set_store._row_to_field_set`).
    One field at a time, so the 50-field loader cap never applies to a read."""
    allowed_json = row["allowed_values_json"]
    field_dict = {
        "name": row["name"],
        "description": row["description"],
        "type": row["type"],
        "allowed_values": json.loads(allowed_json) if allowed_json else None,
        "unit": row["unit"],
        "required": bool(row["required"]),
        "min": row["min"],
        "max": row["max"],
        "date_format": row["date_format"],
    }
    return _field_from_dict({"fields": [field_dict]}).fields[0]


def _row_to_alias(row: sqlite3.Row) -> Alias:
    """The `sqlite3.Row -> Alias` boundary translator -- provenance carried
    through verbatim (ALIAS-02/03)."""
    return Alias(
        vendor=row["vendor"],
        source_column=row["source_column"],
        provenance_kind=row["provenance_kind"],
        provenance_actor=row["provenance_actor"],
        created_at=row["created_at"],
    )
