"""record surfaced position and exploration

Phase B5. Two columns on recommendation_occurrences:

- surfaced_position: where in its queue the occurrence was surfaced, from 0.
  It never changes, unlike queue_position, which is cleared when the
  occurrence leaves the queue. With it, a surfaced order such as rank 2
  ahead of rank 1 can be reconstructed after the queue has moved on.
- is_exploration: whether Recommendation Policy v1 surfaced the occurrence
  as its exploration pick, so later evidence about it can move the
  exploration rate (spec §18, §20).

Existing occurrences were not exploration picks and read as 0. Their
surfaced positions are recovered from insertion order: B4 inserted each
queue's occurrences one at a time, in queue order, all with the same
surfaced_at, so within one session and one surfaced_at, rowid order is the
surfaced order. That is read before the table is rebuilt, while the rowids
are still the original ones.

Adding CHECK constraints needs a table rebuild in SQLite, done in batch mode.
Foreign keys are off during migrations, and env.py checks them before commit;
turns and feedback events reference this table.

Revision ID: de244c476f3a
Revises: dd7360f46b8b
Create Date: 2026-10-20 09:58:27.763197

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'de244c476f3a'
down_revision: Union[str, Sequence[str], None] = 'dd7360f46b8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # A plain ADD COLUMN keeps the rows, and so their rowids, where they are.
    op.add_column('recommendation_occurrences', sa.Column('surfaced_position', sa.Integer(), nullable=True))
    op.execute(
        "UPDATE recommendation_occurrences SET surfaced_position = ("
        "SELECT count(*) FROM recommendation_occurrences AS earlier "
        "WHERE earlier.session_id = recommendation_occurrences.session_id "
        "AND earlier.surfaced_at = recommendation_occurrences.surfaced_at "
        "AND earlier.rowid < recommendation_occurrences.rowid)"
    )
    with op.batch_alter_table('recommendation_occurrences', schema=None, recreate='always') as batch_op:
        batch_op.alter_column('surfaced_position', existing_type=sa.Integer(), nullable=False)
        batch_op.add_column(sa.Column('is_exploration', sa.Boolean(), server_default=sa.text('0'), nullable=False))
        batch_op.create_check_constraint(op.f('ck_recommendation_occurrences_surfaced_position'), 'surfaced_position >= 0')
        batch_op.create_check_constraint(op.f('ck_recommendation_occurrences_is_exploration'), 'is_exploration IN (0, 1)')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('recommendation_occurrences', schema=None, recreate='always') as batch_op:
        batch_op.drop_constraint(op.f('ck_recommendation_occurrences_is_exploration'), type_='check')
        batch_op.drop_constraint(op.f('ck_recommendation_occurrences_surfaced_position'), type_='check')
        batch_op.drop_column('is_exploration')
        batch_op.drop_column('surfaced_position')
