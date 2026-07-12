"""soft delete canonical field and alias

Adds the D-10-15 tombstone columns (`removed_at`/`removed_by`) to
`canonical_field` and `alias`, and replaces their full UNIQUE constraints with
PARTIAL unique indexes predicated on `removed_at IS NULL`.

This is the load-bearing change of Phase 10 Plan 02: without the partial
index, a tombstoned row would permanently occupy its unique key and
`ON CONFLICT DO NOTHING` would silently swallow a re-add of a previously
removed field/alias -- invisible forever, with no error (T-10-09).

Revision ID: 8d7f8c21e1cd
Revises: 1403186caa00
Create Date: 2026-07-12 15:10:55.567763

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d7f8c21e1cd'
down_revision: Union[str, Sequence[str], None] = '1403186caa00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('canonical_field', sa.Column('removed_at', sa.String(), nullable=True))
    op.add_column('canonical_field', sa.Column('removed_by', sa.String(), nullable=True))
    op.add_column('alias', sa.Column('removed_at', sa.String(), nullable=True))
    op.add_column('alias', sa.Column('removed_by', sa.String(), nullable=True))

    # Drop the old FULL unique constraints -- their auto-generated names, read
    # directly off the live database (never guessed).
    op.drop_constraint(
        'canonical_field_schema_id_name_key', 'canonical_field', type_='unique'
    )
    op.drop_constraint(
        'alias_canonical_field_id_vendor_source_column_key', 'alias', type_='unique'
    )

    # Replace them with PARTIAL unique indexes: a tombstoned row no longer
    # occupies its key, so a re-added field/alias becomes a fresh, live row.
    op.create_index(
        'uq_canonical_field_live',
        'canonical_field',
        ['schema_id', 'name'],
        unique=True,
        postgresql_where=sa.text('removed_at IS NULL'),
    )
    op.create_index(
        'uq_alias_live',
        'alias',
        ['canonical_field_id', 'vendor', 'source_column'],
        unique=True,
        postgresql_where=sa.text('removed_at IS NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_alias_live', table_name='alias')
    op.drop_index('uq_canonical_field_live', table_name='canonical_field')

    op.create_unique_constraint(
        'alias_canonical_field_id_vendor_source_column_key',
        'alias',
        ['canonical_field_id', 'vendor', 'source_column'],
    )
    op.create_unique_constraint(
        'canonical_field_schema_id_name_key',
        'canonical_field',
        ['schema_id', 'name'],
    )

    op.drop_column('alias', 'removed_by')
    op.drop_column('alias', 'removed_at')
    op.drop_column('canonical_field', 'removed_by')
    op.drop_column('canonical_field', 'removed_at')
