"""The PostgreSQL `ProfileStore` implementation (D-01).

Every statement is built through SQLAlchemy Core with bound parameters -- never
f-string SQL -- because a header string is untrusted file content flowing straight
from an uploaded file (ASVS V5). `tests/test_profile_store.py` pins this with a
hostile `'; DROP TABLE profiles; --` signature that must round-trip as plain data.

This store UPSERTS on a repeat `(field_set_signature, column_signature)`, and that
is deliberate: a curator re-confirming a correction for the same file layout should
replace the old mapping. It is one of the THREE stores that upsert. The schema
store's `add_alias`/`_insert_missing_fields` deliberately do NOT -- see
`postgres_schema_store.py`. The asymmetry is load-bearing; do not "tidy" it.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..parsing.hint import StructuralHint
from ..persistence.models import ProfileRow
from .profile import LearnedProfile, StoredFieldMapping
from .store import ProfileStore


class PostgresProfileStore(ProfileStore):
    """A PostgreSQL table behind the `ProfileStore` seam."""

    def __init__(self, session: Session) -> None:
        """Take a `Session` -- never an engine, never a sessionmaker.

        Load-bearing. A store that opened its own connection per method would check
        out a DIFFERENT pooled connection, land outside the test suite's outer
        transaction, and the rollback would then roll back nothing: rows would leak
        between tests and the failures would look random.
        """
        self._session = session

    def save(self, profile: LearnedProfile) -> None:
        stmt = insert(ProfileRow).values(
            id=profile.profile_id,
            field_set_signature=profile.field_set_signature,
            column_signature=profile.column_signature,
            mapping_json=json.dumps([m.to_dict() for m in profile.field_mappings]),
            structural_hint_json=(
                json.dumps(profile.structural_hint.to_dict())
                if profile.structural_hint is not None
                else None
            ),
            created_at=profile.created_at,
        )
        # Upserts a re-confirmed correction for the same signature pair rather than
        # raising or duplicating a row. Updating the primary key `id` in the SET
        # clause is legal in Postgres and preserves today's semantics exactly.
        stmt = stmt.on_conflict_do_update(
            index_elements=["field_set_signature", "column_signature"],
            set_={
                "id": stmt.excluded.id,
                "mapping_json": stmt.excluded.mapping_json,
                "structural_hint_json": stmt.excluded.structural_hint_json,
                "created_at": stmt.excluded.created_at,
            },
        )
        self._session.execute(stmt)
        self._session.commit()

    def find(self, field_set_signature: str, column_signature: str) -> LearnedProfile | None:
        row = self._session.scalars(
            select(ProfileRow).where(
                ProfileRow.field_set_signature == field_set_signature,
                ProfileRow.column_signature == column_signature,
            )
        ).first()
        return _entity_to_profile(row) if row is not None else None

    def list_for_field_set(self, field_set_signature: str) -> list[LearnedProfile]:
        rows = self._session.scalars(
            select(ProfileRow).where(ProfileRow.field_set_signature == field_set_signature)
        ).all()
        return [_entity_to_profile(row) for row in rows]


def _entity_to_profile(row: ProfileRow) -> LearnedProfile:
    """The wire (ORM row) -> domain (`LearnedProfile`) boundary translator -- the
    `ProfileRow -> LearnedProfile` analog of `mapping/mapper.py::_to_domain`.

    The `*_json` columns are TEXT, so this still owns the `json.loads` (psycopg would
    have pre-parsed a JSONB column, and `json.loads(list)` raises)."""
    mappings = [StoredFieldMapping(**m) for m in json.loads(row.mapping_json)]
    hint = StructuralHint(**json.loads(row.structural_hint_json)) if row.structural_hint_json else None
    return LearnedProfile(
        profile_id=row.id,
        field_set_signature=row.field_set_signature,
        column_signature=row.column_signature,
        field_mappings=tuple(mappings),
        structural_hint=hint,
        created_at=row.created_at,
    )
