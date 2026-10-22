"""accept unlike feedback

Phase B9. feedback_events also accepts UNLIKE: the listener took back a Like.
It is stored as a raw fact of its own; the LIKE it cancels is kept, so the
history can be read again (B10, B11). Feedback Policy v1 reads an UNLIKE as
cancelling the Likes before it, never as negative evidence.

Changing the CHECK constraint needs a table rebuild in SQLite, done in batch
mode, as B7 did; rows, the index, and the composite foreign key are kept. The
downgrade removes UNLIKE events before restoring the earlier constraint.

Revision ID: 4b1e9c7d2a6f
Revises: ce0b59df2cd1
Create Date: 2026-10-21 17:30:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '4b1e9c7d2a6f'
down_revision: Union[str, Sequence[str], None] = 'ce0b59df2cd1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_EVENT_TYPES_BEFORE = "'LIKE', 'SAVE', 'REPLAY', 'SKIP', 'COMPLETE', 'NOT_FOR_ME', 'PLAYLIST_ADD'"
_EVENT_TYPES = _EVENT_TYPES_BEFORE + ", 'UNLIKE'"


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('feedback_events', schema=None, recreate='always') as batch_op:
        batch_op.drop_constraint(op.f('ck_feedback_events_event_type'), type_='check')
        batch_op.create_check_constraint(op.f('ck_feedback_events_event_type'), f'event_type IN ({_EVENT_TYPES})')


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM feedback_events WHERE event_type = 'UNLIKE'")
    with op.batch_alter_table('feedback_events', schema=None, recreate='always') as batch_op:
        batch_op.drop_constraint(op.f('ck_feedback_events_event_type'), type_='check')
        batch_op.create_check_constraint(op.f('ck_feedback_events_event_type'), f'event_type IN ({_EVENT_TYPES_BEFORE})')
