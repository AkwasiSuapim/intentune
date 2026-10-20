"""create listening sessions

Phase B4. The session domain (spec §10, D31, D35):

- listening_sessions: current state. Status (ACTIVE or ENDED, with an end
  reason), the listener, and the ListeningContext in force, stored as JSON.
  At most one ACTIVE session per listener (partial unique index).
- recommendation_occurrences: each recommendation surfaced in a session, with
  rank, score, and algorithm. The QUEUED rows, ordered by queue_position, are
  the upcoming queue; the one PLAYING row (partial unique index) is the
  current track.
- session_turns: each steering action, in sequence, with the context it left
  in force. No raw text is stored (D33).
- feedback_events: raw listening facts (played seconds, duration, fraction).
  Recording and interpreting them is B6.

Composite foreign keys (occurrence_id, session_id) keep a turn's or event's
occurrence inside the same session.

Timestamps hold UTC values as plain DATETIME; migrations never import
application code.

Revision ID: dd7360f46b8b
Revises: 7a42f0b9c8bf
Create Date: 2026-10-20 08:19:06.623857

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dd7360f46b8b'
down_revision: Union[str, Sequence[str], None] = '7a42f0b9c8bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'listening_sessions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('listener_profile_id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('end_reason', sa.String(length=32), nullable=True),
        sa.Column('context_json', sa.Text(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint("(status = 'ACTIVE' AND ended_at IS NULL AND end_reason IS NULL) OR (status = 'ENDED' AND ended_at IS NOT NULL AND end_reason IS NOT NULL)", name=op.f('ck_listening_sessions_end_matches_status')),
        sa.CheckConstraint("end_reason IS NULL OR end_reason IN ('ENDED_BY_LISTENER', 'REPLACED_BY_NEW_SESSION', 'APP_RESTARTED')", name=op.f('ck_listening_sessions_end_reason')),
        sa.CheckConstraint("status IN ('ACTIVE', 'ENDED')", name=op.f('ck_listening_sessions_status')),
        sa.ForeignKeyConstraint(['listener_profile_id'], ['listener_profiles.id'], name=op.f('fk_listening_sessions_listener_profile_id_listener_profiles')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_listening_sessions')),
    )
    with op.batch_alter_table('listening_sessions', schema=None) as batch_op:
        batch_op.create_index('ix_listening_sessions_listener_started', ['listener_profile_id', 'started_at'], unique=False)
        batch_op.create_index('uq_listening_sessions_one_active', ['listener_profile_id'], unique=True, sqlite_where=sa.text("status = 'ACTIVE'"))

    op.create_table(
        'recommendation_occurrences',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('track_id', sa.String(length=36), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('algorithm', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('queue_position', sa.Integer(), nullable=True),
        sa.Column('surfaced_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint("(status = 'QUEUED') = (queue_position IS NOT NULL)", name=op.f('ck_recommendation_occurrences_queue_position_while_queued')),
        sa.CheckConstraint("(status IN ('PLAYED', 'REPLACED', 'DISCARDED')) = (finished_at IS NOT NULL)", name=op.f('ck_recommendation_occurrences_finished_when_done')),
        sa.CheckConstraint("(status IN ('PLAYING', 'PLAYED')) = (started_at IS NOT NULL)", name=op.f('ck_recommendation_occurrences_started_when_played')),
        sa.CheckConstraint("status IN ('QUEUED', 'PLAYING', 'PLAYED', 'REPLACED', 'DISCARDED')", name=op.f('ck_recommendation_occurrences_status')),
        sa.CheckConstraint('queue_position IS NULL OR queue_position >= 0', name=op.f('ck_recommendation_occurrences_queue_position')),
        sa.CheckConstraint('rank >= 1', name=op.f('ck_recommendation_occurrences_rank')),
        sa.CheckConstraint('score IS NULL OR score BETWEEN 0 AND 1', name=op.f('ck_recommendation_occurrences_score')),
        sa.ForeignKeyConstraint(['session_id'], ['listening_sessions.id'], name=op.f('fk_recommendation_occurrences_session_id_listening_sessions')),
        sa.ForeignKeyConstraint(['track_id'], ['tracks.id'], name=op.f('fk_recommendation_occurrences_track_id_tracks')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_recommendation_occurrences')),
        sa.UniqueConstraint('id', 'session_id', name='uq_recommendation_occurrences_id_session'),
    )
    with op.batch_alter_table('recommendation_occurrences', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_recommendation_occurrences_track_id'), ['track_id'], unique=False)
        batch_op.create_index('uq_recommendation_occurrences_one_playing', ['session_id'], unique=True, sqlite_where=sa.text("status = 'PLAYING'"))
        batch_op.create_index('uq_recommendation_occurrences_queue_position', ['session_id', 'queue_position'], unique=True, sqlite_where=sa.text('queue_position IS NOT NULL'))

    op.create_table(
        'feedback_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('occurrence_id', sa.String(length=36), nullable=False),
        sa.Column('event_type', sa.String(length=16), nullable=False),
        sa.Column('played_seconds', sa.Float(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('played_fraction', sa.Float(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("event_type IN ('LIKE', 'SAVE', 'REPLAY', 'SKIP', 'COMPLETE', 'NOT_FOR_ME')", name=op.f('ck_feedback_events_event_type')),
        sa.CheckConstraint("event_type NOT IN ('SKIP', 'COMPLETE') OR played_seconds IS NOT NULL", name=op.f('ck_feedback_events_playback_facts_when_required')),
        sa.CheckConstraint('(played_fraction IS NULL) = (played_seconds IS NULL)', name=op.f('ck_feedback_events_fraction_with_facts')),
        sa.CheckConstraint('(played_seconds IS NULL) = (duration_seconds IS NULL)', name=op.f('ck_feedback_events_playback_facts_together')),
        sa.CheckConstraint('duration_seconds IS NULL OR duration_seconds > 0', name=op.f('ck_feedback_events_duration_seconds')),
        sa.CheckConstraint('played_fraction IS NULL OR played_fraction BETWEEN 0 AND 1', name=op.f('ck_feedback_events_played_fraction')),
        sa.CheckConstraint('played_seconds IS NULL OR played_seconds >= 0', name=op.f('ck_feedback_events_played_seconds')),
        sa.ForeignKeyConstraint(['occurrence_id', 'session_id'], ['recommendation_occurrences.id', 'recommendation_occurrences.session_id'], name='fk_feedback_events_occurrence_same_session'),
        sa.ForeignKeyConstraint(['session_id'], ['listening_sessions.id'], name=op.f('fk_feedback_events_session_id_listening_sessions')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_feedback_events')),
    )
    with op.batch_alter_table('feedback_events', schema=None) as batch_op:
        batch_op.create_index('ix_feedback_events_session_occurred', ['session_id', 'occurred_at'], unique=False)

    op.create_table(
        'session_turns',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('context_json', sa.Text(), nullable=False),
        sa.Column('occurrence_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("(kind = 'INITIAL_INTENT') = (sequence = 1)", name=op.f('ck_session_turns_initial_intent_first')),
        sa.CheckConstraint("kind IN ('INITIAL_INTENT', 'REFINE', 'NEXT', 'NOT_FOR_ME', 'MORE_LIKE_THIS', 'SURPRISE_ME', 'MORE_FAMILIAR', 'TRY_SOMETHING_DIFFERENT')", name=op.f('ck_session_turns_kind')),
        sa.CheckConstraint("kind NOT IN ('NOT_FOR_ME', 'MORE_LIKE_THIS') OR occurrence_id IS NOT NULL", name=op.f('ck_session_turns_target_when_required')),
        sa.CheckConstraint('sequence >= 1', name=op.f('ck_session_turns_sequence')),
        sa.ForeignKeyConstraint(['occurrence_id', 'session_id'], ['recommendation_occurrences.id', 'recommendation_occurrences.session_id'], name='fk_session_turns_occurrence_same_session'),
        sa.ForeignKeyConstraint(['session_id'], ['listening_sessions.id'], name=op.f('fk_session_turns_session_id_listening_sessions')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_session_turns')),
        sa.UniqueConstraint('session_id', 'sequence', name='uq_session_turns_session_sequence'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('session_turns')
    with op.batch_alter_table('feedback_events', schema=None) as batch_op:
        batch_op.drop_index('ix_feedback_events_session_occurred')

    op.drop_table('feedback_events')
    with op.batch_alter_table('recommendation_occurrences', schema=None) as batch_op:
        batch_op.drop_index('uq_recommendation_occurrences_queue_position', sqlite_where=sa.text('queue_position IS NOT NULL'))
        batch_op.drop_index('uq_recommendation_occurrences_one_playing', sqlite_where=sa.text("status = 'PLAYING'"))
        batch_op.drop_index(batch_op.f('ix_recommendation_occurrences_track_id'))

    op.drop_table('recommendation_occurrences')
    with op.batch_alter_table('listening_sessions', schema=None) as batch_op:
        batch_op.drop_index('uq_listening_sessions_one_active', sqlite_where=sa.text("status = 'ACTIVE'"))
        batch_op.drop_index('ix_listening_sessions_listener_started')

    op.drop_table('listening_sessions')
