"""create long-term adaptation

Phase B10. The listener's long-term profile and the history of how it came to
be (spec §23, D06, D20):

- long_term_profiles: the current profile, one row per listener, absent until
  the first adjustment. Preferred genres and moods are a JSON list.
- long_term_adjustments: append-only. Every change, with its dimension, what
  changed and why, the value before and after (JSON), the adaptation policy
  version, and a per-listener sequence.
- long_term_adjustment_evidence: the effective items behind each adjustment,
  each pointing at its session, its track, and the raw fact that decided it (a
  feedback event or a turn, exactly one), with its weight.

Nothing existing changes. The downgrade drops the three tables; the raw
history the profile was derived from is untouched, so the profile can be
derived again.

Timestamps hold UTC values as plain DATETIME; migrations never import
application code.

Revision ID: 5d8e2b7a9c41
Revises: 4b1e9c7d2a6f
Create Date: 2026-10-22 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d8e2b7a9c41'
down_revision: Union[str, Sequence[str], None] = '4b1e9c7d2a6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DIMENSIONS = "'GENRE', 'MOOD', 'ENERGY', 'DANCEABILITY', 'TEMPO', 'VALENCE', 'ACOUSTICNESS'"
_CHANGES = "'ADDED', 'REMOVED', 'SET', 'RAISED', 'LOWERED', 'CLEARED'"
_CAUSES = "'GATE_MET', 'BOUNDED_STEP', 'GATE_LOST', 'DISPLACED', 'RECOMPUTED'"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'long_term_profiles',
        sa.Column('listener_profile_id', sa.String(length=36), nullable=False),
        sa.Column('preferred_genres_json', sa.Text(), nullable=False),
        sa.Column('preferred_moods_json', sa.Text(), nullable=False),
        sa.Column('preferred_energy', sa.Float(), nullable=True),
        sa.Column('preferred_danceability', sa.Float(), nullable=True),
        sa.Column('preferred_tempo_bpm', sa.Float(), nullable=True),
        sa.Column('preferred_valence', sa.Float(), nullable=True),
        sa.Column('preferred_acousticness', sa.Float(), nullable=True),
        sa.Column('policy_version', sa.String(length=64), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('preferred_energy IS NULL OR preferred_energy BETWEEN 0 AND 1', name=op.f('ck_long_term_profiles_preferred_energy')),
        sa.CheckConstraint('preferred_danceability IS NULL OR preferred_danceability BETWEEN 0 AND 1', name=op.f('ck_long_term_profiles_preferred_danceability')),
        sa.CheckConstraint('preferred_valence IS NULL OR preferred_valence BETWEEN 0 AND 1', name=op.f('ck_long_term_profiles_preferred_valence')),
        sa.CheckConstraint('preferred_acousticness IS NULL OR preferred_acousticness BETWEEN 0 AND 1', name=op.f('ck_long_term_profiles_preferred_acousticness')),
        sa.CheckConstraint('preferred_tempo_bpm IS NULL OR preferred_tempo_bpm > 0', name=op.f('ck_long_term_profiles_preferred_tempo_bpm')),
        sa.ForeignKeyConstraint(['listener_profile_id'], ['listener_profiles.id'], name=op.f('fk_long_term_profiles_listener_profile_id_listener_profiles')),
        sa.PrimaryKeyConstraint('listener_profile_id', name=op.f('pk_long_term_profiles')),
    )
    op.create_table(
        'long_term_adjustments',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('listener_profile_id', sa.String(length=36), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('dimension', sa.String(length=16), nullable=False),
        sa.Column('change', sa.String(length=16), nullable=False),
        sa.Column('cause', sa.String(length=16), nullable=False),
        sa.Column('subject', sa.String(length=100), nullable=True),
        sa.Column('previous_json', sa.Text(), nullable=False),
        sa.Column('resulting_json', sa.Text(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('policy_version', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(f'dimension IN ({_DIMENSIONS})', name=op.f('ck_long_term_adjustments_dimension')),
        sa.CheckConstraint(f'change IN ({_CHANGES})', name=op.f('ck_long_term_adjustments_change')),
        sa.CheckConstraint(f'cause IN ({_CAUSES})', name=op.f('ck_long_term_adjustments_cause')),
        sa.CheckConstraint('sequence >= 1', name=op.f('ck_long_term_adjustments_sequence')),
        sa.CheckConstraint("(dimension IN ('GENRE', 'MOOD')) = (subject IS NOT NULL)", name=op.f('ck_long_term_adjustments_subject_when_categorical')),
        sa.CheckConstraint("(dimension IN ('GENRE', 'MOOD')) = (change IN ('ADDED', 'REMOVED'))", name=op.f('ck_long_term_adjustments_change_fits_dimension')),
        sa.ForeignKeyConstraint(['listener_profile_id'], ['listener_profiles.id'], name=op.f('fk_long_term_adjustments_listener_profile_id_listener_profiles')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_long_term_adjustments')),
        sa.UniqueConstraint('listener_profile_id', 'sequence', name='uq_long_term_adjustments_listener_sequence'),
    )
    op.create_table(
        'long_term_adjustment_evidence',
        sa.Column('adjustment_id', sa.String(length=36), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('track_id', sa.String(length=36), nullable=False),
        sa.Column('feedback_event_id', sa.String(length=36), nullable=True),
        sa.Column('session_turn_id', sa.String(length=36), nullable=True),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.CheckConstraint('position >= 0', name=op.f('ck_long_term_adjustment_evidence_position')),
        sa.CheckConstraint('weight BETWEEN -1 AND 1 AND weight <> 0', name=op.f('ck_long_term_adjustment_evidence_weight')),
        sa.CheckConstraint('(feedback_event_id IS NULL) <> (session_turn_id IS NULL)', name=op.f('ck_long_term_adjustment_evidence_one_raw_fact')),
        sa.ForeignKeyConstraint(['adjustment_id'], ['long_term_adjustments.id'], name=op.f('fk_long_term_adjustment_evidence_adjustment_id_long_term_adjustments')),
        sa.ForeignKeyConstraint(['session_id'], ['listening_sessions.id'], name=op.f('fk_long_term_adjustment_evidence_session_id_listening_sessions')),
        sa.ForeignKeyConstraint(['track_id'], ['tracks.id'], name=op.f('fk_long_term_adjustment_evidence_track_id_tracks')),
        sa.ForeignKeyConstraint(['feedback_event_id'], ['feedback_events.id'], name=op.f('fk_long_term_adjustment_evidence_feedback_event_id_feedback_events')),
        sa.ForeignKeyConstraint(['session_turn_id'], ['session_turns.id'], name=op.f('fk_long_term_adjustment_evidence_session_turn_id_session_turns')),
        sa.PrimaryKeyConstraint('adjustment_id', 'position', name=op.f('pk_long_term_adjustment_evidence')),
        sa.UniqueConstraint('adjustment_id', 'session_id', 'track_id', name='uq_long_term_adjustment_evidence_item'),
    )
    with op.batch_alter_table('long_term_adjustment_evidence', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_long_term_adjustment_evidence_feedback_event_id'), ['feedback_event_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_long_term_adjustment_evidence_session_turn_id'), ['session_turn_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('long_term_adjustment_evidence', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_long_term_adjustment_evidence_session_turn_id'))
        batch_op.drop_index(batch_op.f('ix_long_term_adjustment_evidence_feedback_event_id'))
    op.drop_table('long_term_adjustment_evidence')
    op.drop_table('long_term_adjustments')
    op.drop_table('long_term_profiles')
