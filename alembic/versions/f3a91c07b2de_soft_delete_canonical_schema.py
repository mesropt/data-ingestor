"""soft delete canonical schema

Extends the D-10-15 tombstone (`removed_at`/`removed_by`) to `canonical_schema`,
and replaces its full UNIQUE on `name` with a PARTIAL unique index predicated on
`removed_at IS NULL`.

Deleting a Schema must never issue a DELETE. It would take its canonical fields
with it, and with them every alias the crosswalk ever learned -- each carrying
who recorded it and when -- destroying the audit trail and leaving every
already-exported dataset's target unexplainable after the fact. The Schema is
marked removed instead, and every read filters it out.

The partial index is the load-bearing half, for the same reason it was for a
field (T-10-09): a tombstoned Schema must not permanently occupy its name, or a
curator who deleted a Schema by mistake could never re-create it under the name
it had.

Revision ID: f3a91c07b2de
Revises: c4f9a71b52d8
Create Date: 2026-07-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a91c07b2de'
down_revision: Union[str, Sequence[str], None] = 'c4f9a71b52d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('canonical_schema', sa.Column('removed_at', sa.String(), nullable=True))
    op.add_column('canonical_schema', sa.Column('removed_by', sa.String(), nullable=True))

    # The constraint's auto-generated name, read directly off the live database
    # (never guessed) -- the same discipline 8d7f8c21e1cd used.
    op.drop_constraint('canonical_schema_name_key', 'canonical_schema', type_='unique')

    op.create_index(
        'uq_canonical_schema_live',
        'canonical_schema',
        ['name'],
        unique=True,
        postgresql_where=sa.text('removed_at IS NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_canonical_schema_live', table_name='canonical_schema')
    op.create_unique_constraint('canonical_schema_name_key', 'canonical_schema', ['name'])
    op.drop_column('canonical_schema', 'removed_by')
    op.drop_column('canonical_schema', 'removed_at')
