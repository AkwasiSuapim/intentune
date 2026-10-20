"""create background analysis

Phase B3. Persisted background analysis (D26, D28):

- analysis_jobs: one job per track, kind, and analyzer version (name@version),
  with status, attempt count, and the reason for the last failure or skip.
- track_features: measured features with provenance (analyzer name, version,
  computation time, and confidence for estimates). One current value per
  feature per track.
- tracks.status may now also be ANALYZING and READY. SQLite cannot alter a
  CHECK constraint in place, so the tracks table is rebuilt in batch mode
  (foreign keys are off during migrations, and env.py checks them before
  commit).

Downgrading returns ANALYZING and READY tracks to IMPORTED and clears their
analysis_version, because their features are dropped with track_features.

Timestamps hold UTC values as plain DATETIME; migrations never import
application code.

Revision ID: 7a42f0b9c8bf
Revises: 2540be2956b8
Create Date: 2026-10-20 00:12:41.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a42f0b9c8bf'
down_revision: Union[str, Sequence[str], None] = '2540be2956b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_B2_TRACK_STATUSES = "status IN ('IMPORTED', 'MISSING_MANAGED_FILE')"
_B3_TRACK_STATUSES = "status IN ('IMPORTED', 'ANALYZING', 'READY', 'MISSING_MANAGED_FILE')"


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('tracks', schema=None, recreate='always') as batch_op:
        batch_op.drop_constraint(op.f('ck_tracks_status'), type_='check')
        batch_op.create_check_constraint(op.f('ck_tracks_status'), _B3_TRACK_STATUSES)

    op.create_table(
        'analysis_jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('track_id', sa.String(length=36), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('analyzer', sa.String(length=128), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('failure_reason', sa.String(length=32), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "failure_reason IS NULL OR failure_reason IN ('FORMAT_NOT_SUPPORTED', 'SUPERSEDED', 'DECODE_ERROR', "
            "'IO_ERROR', 'MISSING_MANAGED_FILE', 'INTERRUPTED', 'ANALYZER_ERROR')",
            name=op.f('ck_analysis_jobs_failure_reason'),
        ),
        sa.CheckConstraint("kind IN ('ANALYZE_AUDIO')", name=op.f('ck_analysis_jobs_kind')),
        sa.CheckConstraint(
            "status <> 'SUCCEEDED' OR failure_reason IS NULL", name=op.f('ck_analysis_jobs_succeeded_has_no_reason')
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'SKIPPED')", name=op.f('ck_analysis_jobs_status')
        ),
        sa.CheckConstraint(
            "status NOT IN ('FAILED', 'SKIPPED') OR failure_reason IS NOT NULL",
            name=op.f('ck_analysis_jobs_finished_has_reason'),
        ),
        sa.CheckConstraint('attempts >= 0', name=op.f('ck_analysis_jobs_attempts')),
        sa.ForeignKeyConstraint(['track_id'], ['tracks.id'], name=op.f('fk_analysis_jobs_track_id_tracks')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_analysis_jobs')),
        sa.UniqueConstraint('track_id', 'kind', 'analyzer', name='uq_analysis_jobs_track_kind_analyzer'),
    )
    with op.batch_alter_table('analysis_jobs', schema=None) as batch_op:
        batch_op.create_index('ix_analysis_jobs_status_created_at', ['status', 'created_at'], unique=False)

    op.create_table(
        'track_features',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('track_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('analyzer_name', sa.String(length=64), nullable=False),
        sa.Column('analyzer_version', sa.String(length=64), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('computed_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "name IN ('decoded_duration_seconds', 'sample_peak', 'rms_level')", name=op.f('ck_track_features_name')
        ),
        sa.CheckConstraint(
            'confidence IS NULL OR confidence BETWEEN 0 AND 1', name=op.f('ck_track_features_confidence')
        ),
        sa.ForeignKeyConstraint(['track_id'], ['tracks.id'], name=op.f('fk_track_features_track_id_tracks')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_track_features')),
        sa.UniqueConstraint('track_id', 'name', name='uq_track_features_track_id_name'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('track_features')
    with op.batch_alter_table('analysis_jobs', schema=None) as batch_op:
        batch_op.drop_index('ix_analysis_jobs_status_created_at')

    op.drop_table('analysis_jobs')

    op.execute("UPDATE tracks SET status = 'IMPORTED' WHERE status IN ('ANALYZING', 'READY')")
    op.execute("UPDATE tracks SET analysis_version = NULL")
    with op.batch_alter_table('tracks', schema=None, recreate='always') as batch_op:
        batch_op.drop_constraint(op.f('ck_tracks_status'), type_='check')
        batch_op.create_check_constraint(op.f('ck_tracks_status'), _B2_TRACK_STATUSES)
