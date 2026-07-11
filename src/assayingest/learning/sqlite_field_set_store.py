"""The local SQLite `FieldSetTemplateStore` implementation (D-03) -- mirrors
`learning/sqlite_store.py::SqliteProfileStore` line-for-line, in the SAME
local SQLite file (`_DEFAULT_DB_PATH`) the profile store already writes to:
one consistent local store, gitignored, never a network DB in v1 (P2).

Together with `learning/sqlite_store.py`, this is one of the only two
modules in this project allowed to `import sqlite3`.

Every query uses parameterised `?` placeholders -- never f-string SQL -- a
field-set template's `name` is raw text a curator typed into the browser
(T-04-09), no different in trust level from the header strings
`sqlite_store.py`'s own docstring already calls out (ASVS V5).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from ..fields.loader import from_dict
from ..fields.models import FieldSet
from .field_set_store import FieldSetTemplateStore
from .sqlite_store import _DEFAULT_DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS field_set_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    field_set_json TEXT NOT NULL,
    signature TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(name)
);
CREATE INDEX IF NOT EXISTS idx_field_set_templates_signature
    ON field_set_templates(signature);
"""


class SqliteFieldSetStore(FieldSetTemplateStore):
    """A local SQLite file behind the `FieldSetTemplateStore` seam -- the
    same file `SqliteProfileStore` writes to (`_DEFAULT_DB_PATH`, D-03)."""

    def __init__(self, db_path: str | Path = _DEFAULT_DB_PATH) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self._path)) as conn:
            conn.executescript(_SCHEMA)

    def save(self, name: str, field_set: FieldSet) -> str:
        # `with conn:` commits/rolls back the transaction (not a connection
        # close -- `closing()` still owns that, mirrors sqlite_store.py's own
        # anti-pattern note). ON CONFLICT upserts a re-saved template under
        # the same name rather than raising or duplicating a row.
        template_id = str(uuid.uuid4())
        with closing(sqlite3.connect(self._path)) as conn, conn:
            conn.execute(
                "INSERT INTO field_set_templates "
                "(id, name, field_set_json, signature, created_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET "
                "id=excluded.id, field_set_json=excluded.field_set_json, "
                "signature=excluded.signature, created_at=excluded.created_at",
                (
                    template_id,
                    name,
                    json.dumps(field_set.to_dict()),
                    field_set.signature,
                    datetime.now(UTC).isoformat(),
                ),
            )
        return template_id

    def get(self, template_id: str) -> FieldSet | None:
        with closing(sqlite3.connect(self._path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM field_set_templates WHERE id = ?", (template_id,)
            ).fetchone()
        return _row_to_field_set(row) if row is not None else None

    def list(self) -> list[tuple[str, str]]:
        with closing(sqlite3.connect(self._path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, name FROM field_set_templates ORDER BY name"
            ).fetchall()
        return [(row["id"], row["name"]) for row in rows]


def _row_to_field_set(row: sqlite3.Row) -> FieldSet:
    """The wire (SQLite row) -> domain (`FieldSet`) boundary translator --
    the `sqlite3.Row -> FieldSet` analog of `sqlite_store.py::_row_to_profile`.
    Rebuilds through `fields.loader.from_dict` (not a bare `FieldSet(**...)`)
    so a round-tripped template gets the exact same name/length/type guards
    a freshly-saved one did -- never a second, weaker reconstruction path."""
    return from_dict(json.loads(row["field_set_json"]))
