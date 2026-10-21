"""create playlists

Phase B7. The listener's playlists (spec §9, D34):

- playlists: a named collection belonging to a listener. Names are unique
  per listener.
- playlist_items: one track at one position. The primary key (playlist_id,
  track_id) keeps a track to one entry per playlist (execution guide §10);
  positions are unique within a playlist.

feedback_events also accepts PLAYLIST_ADD, a recommendation added to a
playlist (Feedback Policy v1: +1.00). Changing its CHECK constraint needs a
table rebuild in SQLite, done in batch mode; its rows, index, and composite
foreign key are kept. The downgrade removes PLAYLIST_ADD events before
restoring the earlier constraint, since the playlists they came from are
dropped too.

Timestamps hold UTC values as plain DATETIME; migrations never import
application code.

Revision ID: ce0b59df2cd1
Revises: de244c476f3a
Create Date: 2026-10-21 08:05:23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce0b59df2cd1'
down_revision: Union[str, Sequence[str], None] = 'de244c476f3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_EVENT_TYPES_BEFORE = "'LIKE', 'SAVE', 'REPLAY', 'SKIP', 'COMPLETE', 'NOT_FOR_ME'"
_EVENT_TYPES = _EVENT_TYPES_BEFORE + ", 'PLAYLIST_ADD'"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'playlists',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('listener_profile_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('length(name) BETWEEN 1 AND 100', name=op.f('ck_playlists_name')),
        sa.ForeignKeyConstraint(['listener_profile_id'], ['listener_profiles.id'], name=op.f('fk_playlists_listener_profile_id_listener_profiles')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_playlists')),
        sa.UniqueConstraint('listener_profile_id', 'name', name='uq_playlists_listener_name'),
    )
    op.create_table(
        'playlist_items',
        sa.Column('playlist_id', sa.String(length=36), nullable=False),
        sa.Column('track_id', sa.String(length=36), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('added_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('position >= 0', name=op.f('ck_playlist_items_position')),
        sa.ForeignKeyConstraint(['playlist_id'], ['playlists.id'], name=op.f('fk_playlist_items_playlist_id_playlists')),
        sa.ForeignKeyConstraint(['track_id'], ['tracks.id'], name=op.f('fk_playlist_items_track_id_tracks')),
        sa.PrimaryKeyConstraint('playlist_id', 'track_id', name=op.f('pk_playlist_items')),
        sa.UniqueConstraint('playlist_id', 'position', name='uq_playlist_items_playlist_position'),
    )
    with op.batch_alter_table('playlist_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_playlist_items_track_id'), ['track_id'], unique=False)

    with op.batch_alter_table('feedback_events', schema=None, recreate='always') as batch_op:
        batch_op.drop_constraint(op.f('ck_feedback_events_event_type'), type_='check')
        batch_op.create_check_constraint(op.f('ck_feedback_events_event_type'), f'event_type IN ({_EVENT_TYPES})')


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM feedback_events WHERE event_type = 'PLAYLIST_ADD'")
    with op.batch_alter_table('feedback_events', schema=None, recreate='always') as batch_op:
        batch_op.drop_constraint(op.f('ck_feedback_events_event_type'), type_='check')
        batch_op.create_check_constraint(op.f('ck_feedback_events_event_type'), f'event_type IN ({_EVENT_TYPES_BEFORE})')

    with op.batch_alter_table('playlist_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_playlist_items_track_id'))
    op.drop_table('playlist_items')
    op.drop_table('playlists')
