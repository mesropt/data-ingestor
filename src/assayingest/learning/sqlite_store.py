"""The local SQLite `ProfileStore` implementation (D-01) -- the ONLY module
in this project allowed to `import sqlite3`. A local file is itself a
confidentiality control (P2): the profile store never travels over a
network, unlike a DB server, and this module is the sole seam a future
Postgres-backed store (Phase 4+) would replace.

Every query uses parameterised `?` placeholders -- never f-string SQL, even
though the database is local -- because a header string is untrusted file
content flowing straight from an uploaded file (ASVS V5, RESEARCH.md
Don't-Hand-Roll table).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from ..parsing.hint import StructuralHint
from .profile import LearnedProfile, StoredFieldMapping
from .store import ProfileStore

#: Default location, relative to the working directory (D-01) -- visible,
#: overridable with `--profiles-db PATH`, and gitignored (`/.assayingest/`).
_DEFAULT_DB_PATH = ".assayingest/profiles.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,
    field_set_signature TEXT NOT NULL,
    column_signature TEXT NOT NULL,
    mapping_json TEXT NOT NULL,
    structural_hint_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(field_set_signature, column_signature)
);
CREATE INDEX IF NOT EXISTS idx_profiles_lookup
    ON profiles(field_set_signature, column_signature);
"""


class SqliteProfileStore(ProfileStore):
    """A local SQLite file behind the `ProfileStore` seam."""

    def __init__(self, db_path: str | Path = _DEFAULT_DB_PATH) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self._path)) as conn:
            conn.executescript(_SCHEMA)

    def save(self, profile: LearnedProfile) -> None:
        # `with conn:` here commits/rolls back the transaction (not a
        # connection close -- `closing()` still owns that, RESEARCH.md
        # Anti-Pattern). ON CONFLICT upserts a re-confirmed correction for
        # the same signature pair rather than raising or duplicating a row.
        with closing(sqlite3.connect(self._path)) as conn, conn:
            conn.execute(
                "INSERT INTO profiles "
                "(id, field_set_signature, column_signature, mapping_json, "
                " structural_hint_json, created_at) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(field_set_signature, column_signature) DO UPDATE SET "
                "id=excluded.id, mapping_json=excluded.mapping_json, "
                "structural_hint_json=excluded.structural_hint_json, "
                "created_at=excluded.created_at",
                (
                    profile.profile_id,
                    profile.field_set_signature,
                    profile.column_signature,
                    json.dumps([m.to_dict() for m in profile.field_mappings]),
                    json.dumps(profile.structural_hint.to_dict())
                    if profile.structural_hint is not None
                    else None,
                    profile.created_at,
                ),
            )

    def find(self, field_set_signature: str, column_signature: str) -> LearnedProfile | None:
        with closing(sqlite3.connect(self._path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM profiles WHERE field_set_signature = ? "
                "AND column_signature = ?",
                (field_set_signature, column_signature),
            ).fetchone()
        return _row_to_profile(row) if row is not None else None

    def list_for_field_set(self, field_set_signature: str) -> list[LearnedProfile]:
        with closing(sqlite3.connect(self._path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM profiles WHERE field_set_signature = ?",
                (field_set_signature,),
            ).fetchall()
        return [_row_to_profile(r) for r in rows]


def _row_to_profile(row: sqlite3.Row) -> LearnedProfile:
    """The wire (SQLite row) -> domain (`LearnedProfile`) boundary
    translator -- the `sqlite3.Row -> LearnedProfile` analog of
    `mapping/mapper.py::_to_domain`."""
    mappings = [StoredFieldMapping(**m) for m in json.loads(row["mapping_json"])]
    hint_json = row["structural_hint_json"]
    hint = StructuralHint(**json.loads(hint_json)) if hint_json else None
    return LearnedProfile(
        profile_id=row["id"],
        field_set_signature=row["field_set_signature"],
        column_signature=row["column_signature"],
        field_mappings=tuple(mappings),
        structural_hint=hint,
        created_at=row["created_at"],
    )
