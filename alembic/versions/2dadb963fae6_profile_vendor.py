"""profile vendor

Adds the 10-09/INGEST-02 nullable `vendor` column to `profiles`: the human's
vendor assertion at confirm time, persisted alongside the column signature
it was confirmed for, so a later upload of the same-signature file can be
pre-filled and labelled as remembered instead of re-asked.

Nullable is not laziness: every profile saved before this plan genuinely has
no recorded vendor, and NULL says so honestly. There is no backfill, because
there is nothing truthful to backfill with.

Revision ID: 2dadb963fae6
Revises: 8d7f8c21e1cd
Create Date: 2026-07-12 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2dadb963fae6'
down_revision: Union[str, Sequence[str], None] = '8d7f8c21e1cd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('profiles', sa.Column('vendor', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('profiles', 'vendor')
