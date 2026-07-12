"""pending uploads

Adds the `pending_uploads` table: one review-ready pending upload per
`upload_token`, so a curator's open Review screen survives a server restart,
a `--reload` cycle, or landing on a different worker (the confirm-after-
deploy defect -- the registry was a single process's OrderedDict).

`entry_json` holds the uploaded file's cell values at rest -- deliberately
transient: `expires_at` is a TTL the registry enforces (expired rows are
deleted on lookup and swept on every persist), and a successful confirm
purges the row immediately. Timestamps are String ISO-8601 like every other
table here, fixed-width UTC so the sweep is a plain string comparison; the
index on `expires_at` is what keeps that sweep off a table scan.

Revision ID: c4f9a71b52d8
Revises: 2dadb963fae6
Create Date: 2026-07-12 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f9a71b52d8'
down_revision: Union[str, Sequence[str], None] = '2dadb963fae6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('pending_uploads',
    sa.Column('token', sa.String(), nullable=False),
    sa.Column('entry_json', sa.Text(), nullable=False),
    sa.Column('created_at', sa.String(), nullable=False),
    sa.Column('expires_at', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('token')
    )
    op.create_index(op.f('ix_pending_uploads_expires_at'), 'pending_uploads', ['expires_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_pending_uploads_expires_at'), table_name='pending_uploads')
    op.drop_table('pending_uploads')
