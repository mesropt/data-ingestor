"""The PostgreSQL `FieldSetTemplateStore` implementation (D-03) -- mirrors
`learning/postgres_store.py::PostgresProfileStore` line-for-line, in the same
database every other store reaches through the same `Session`.

Every statement binds its parameters -- never f-string SQL -- because a template's
`name` is raw text a curator typed into the browser (T-04-09), no different in
trust level from the header strings `postgres_store.py`'s docstring calls out
(ASVS V5).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..fields.loader import from_dict
from ..fields.models import FieldSet
from ..persistence.models import FieldSetTemplateRow
from .field_set_store import FieldSetTemplateStore


class PostgresFieldSetStore(FieldSetTemplateStore):
    """A PostgreSQL table behind the `FieldSetTemplateStore` seam."""

    def __init__(self, session: Session) -> None:
        """Take a `Session` -- never an engine (see `learning/postgres_store.py`)."""
        self._session = session

    def save(self, name: str, field_set: FieldSet) -> str:
        template_id = str(uuid.uuid4())
        stmt = insert(FieldSetTemplateRow).values(
            id=template_id,
            name=name,
            field_set_json=json.dumps(field_set.to_dict()),
            signature=field_set.signature,
            created_at=datetime.now(UTC).isoformat(),
        )
        # Upserts a re-saved template under the same name rather than raising or
        # duplicating. Note this MINTS a fresh id per call and updates `id` on
        # conflict -- which is exactly why `learning/seed.py` reads `store.list()`
        # first and skips names already present, instead of seeding unconditionally
        # (that would silently re-mint every preset's id on every restart).
        stmt = stmt.on_conflict_do_update(
            index_elements=["name"],
            set_={
                "id": stmt.excluded.id,
                "field_set_json": stmt.excluded.field_set_json,
                "signature": stmt.excluded.signature,
                "created_at": stmt.excluded.created_at,
            },
        )
        self._session.execute(stmt)
        self._session.commit()
        return template_id

    def get(self, template_id: str) -> FieldSet | None:
        row = self._session.scalars(
            select(FieldSetTemplateRow).where(FieldSetTemplateRow.id == template_id)
        ).first()
        return _entity_to_field_set(row) if row is not None else None

    def list(self) -> list[tuple[str, str]]:
        rows = self._session.execute(
            select(FieldSetTemplateRow.id, FieldSetTemplateRow.name).order_by(
                FieldSetTemplateRow.name
            )
        ).all()
        return [(row.id, row.name) for row in rows]


def _entity_to_field_set(row: FieldSetTemplateRow) -> FieldSet:
    """The wire (ORM row) -> domain (`FieldSet`) boundary translator.

    Rebuilds through `fields.loader.from_dict` (not a bare `FieldSet(**...)`) so a
    round-tripped template gets the exact same name/length/type guards a freshly-saved
    one did -- never a second, weaker reconstruction path."""
    return from_dict(json.loads(row.field_set_json))
