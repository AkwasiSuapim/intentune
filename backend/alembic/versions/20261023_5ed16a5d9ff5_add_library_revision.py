"""add library revision

Phase B11. One row whose revision the track repository advances, in the
same transaction, with every write to tracks or track_labels. A full read of
the library is reused while the revision it was read under is unchanged
(TD-022), so a request no longer rebuilds an unchanged library.

The repository advances it, not a trigger: a later batch rebuild of tracks
or track_labels would silently drop a trigger, and with it every
invalidation.

Nothing existing changes. The downgrade drops the table.

Revision ID: 5ed16a5d9ff5
Revises: 5d8e2b7a9c41
Create Date: 2026-10-23 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ed16a5d9ff5'
down_revision: Union[str, Sequence[str], None] = '5d8e2b7a9c41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'library_revision',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.CheckConstraint('id = 1', name=op.f('ck_library_revision_single_row')),
        sa.CheckConstraint('revision >= 1', name=op.f('ck_library_revision_revision')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_library_revision')),
    )
    op.execute("INSERT INTO library_revision (id, revision) VALUES (1, 1)")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('library_revision')
