"""create managed library

Phase B2. The managed local library (D02, D03, D24):

- library_sources: registered source folders, ACTIVE or MISSING.
- tracks: one row per distinct content, keyed by SHA-256. The managed copy is
  <id>.<audio_format> in managed media; no file path is stored.
- source_files: what each scan recorded about each file in a source (size,
  modification time, hash, outcome), so the next scan can skip unchanged files.
- track_labels: genre and mood labels with provenance; at most one primary
  label per kind per track.

Enumerated columns carry CHECK constraints listing the values the domain
defines in B2. Phases that add values (for example B3's ANALYZING and READY
track states) change them with a batch migration.

Timestamps hold UTC values; the ORM's UtcDateTime stores them as plain
DATETIME, and migrations use the plain type so they never import
application code.

Revision ID: 2540be2956b8
Revises: 6ef3a3452ab7
Create Date: 2026-10-19 19:48:57.405882

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2540be2956b8'
down_revision: Union[str, Sequence[str], None] = '6ef3a3452ab7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'library_sources',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('path', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_scanned_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('ACTIVE', 'MISSING')", name=op.f('ck_library_sources_status')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_library_sources')),
        sa.UniqueConstraint('path', name=op.f('uq_library_sources_path')),
    )
    op.create_table(
        'tracks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('audio_format', sa.String(length=8), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('original_filename', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('artist', sa.Text(), nullable=True),
        sa.Column('album', sa.Text(), nullable=True),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('analysis_version', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "audio_format IN ('mp3', 'm4a', 'flac', 'ogg', 'opus', 'wav')", name=op.f('ck_tracks_audio_format')
        ),
        sa.CheckConstraint("status IN ('IMPORTED', 'MISSING_MANAGED_FILE')", name=op.f('ck_tracks_status')),
        sa.CheckConstraint(
            'duration_seconds IS NULL OR duration_seconds >= 0', name=op.f('ck_tracks_duration_seconds')
        ),
        sa.CheckConstraint('size_bytes >= 0', name=op.f('ck_tracks_size_bytes')),
        sa.CheckConstraint('year IS NULL OR year BETWEEN 1 AND 9999', name=op.f('ck_tracks_year')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_tracks')),
        sa.UniqueConstraint('sha256', name=op.f('uq_tracks_sha256')),
    )
    op.create_table(
        'source_files',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('source_id', sa.String(length=36), nullable=False),
        sa.Column('relative_path', sa.Text(), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('modified_ns', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('failure_reason', sa.String(length=32), nullable=True),
        sa.Column('track_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "failure_reason IS NULL OR failure_reason IN "
            "('FILE_TOO_LARGE', 'UNSUPPORTED_FORMAT', 'IO_ERROR', 'CHANGED_DURING_IMPORT')",
            name=op.f('ck_source_files_failure_reason'),
        ),
        sa.CheckConstraint(
            "status <> 'IMPORTED' OR (track_id IS NOT NULL AND sha256 IS NOT NULL AND failure_reason IS NULL)",
            name=op.f('ck_source_files_imported_has_track'),
        ),
        sa.CheckConstraint(
            "status IN ('IMPORTED', 'UNSUPPORTED', 'FAILED', 'MISSING')", name=op.f('ck_source_files_status')
        ),
        sa.CheckConstraint(
            "status NOT IN ('UNSUPPORTED', 'FAILED') OR failure_reason IS NOT NULL",
            name=op.f('ck_source_files_rejected_has_reason'),
        ),
        sa.CheckConstraint('size_bytes >= 0', name=op.f('ck_source_files_size_bytes')),
        sa.ForeignKeyConstraint(
            ['source_id'], ['library_sources.id'], name=op.f('fk_source_files_source_id_library_sources')
        ),
        sa.ForeignKeyConstraint(['track_id'], ['tracks.id'], name=op.f('fk_source_files_track_id_tracks')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_source_files')),
        sa.UniqueConstraint('source_id', 'relative_path', name='uq_source_files_source_id_relative_path'),
    )
    with op.batch_alter_table('source_files', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_source_files_track_id'), ['track_id'], unique=False)

    op.create_table(
        'track_labels',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('track_id', sa.String(length=36), nullable=False),
        sa.Column('kind', sa.String(length=8), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('source', sa.String(length=64), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('is_primary', sa.Boolean(), nullable=False),
        sa.CheckConstraint("kind IN ('genre', 'mood')", name=op.f('ck_track_labels_kind')),
        sa.CheckConstraint(
            'confidence IS NULL OR confidence BETWEEN 0 AND 1', name=op.f('ck_track_labels_confidence')
        ),
        sa.CheckConstraint('is_primary IN (0, 1)', name=op.f('ck_track_labels_is_primary')),
        sa.ForeignKeyConstraint(['track_id'], ['tracks.id'], name=op.f('fk_track_labels_track_id_tracks')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_track_labels')),
        sa.UniqueConstraint('track_id', 'kind', 'value', 'source', name='uq_track_labels_track_kind_value_source'),
    )
    with op.batch_alter_table('track_labels', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_track_labels_track_id'), ['track_id'], unique=False)
        batch_op.create_index(
            'uq_track_labels_primary', ['track_id', 'kind'], unique=True, sqlite_where=sa.text('is_primary = 1')
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('track_labels', schema=None) as batch_op:
        batch_op.drop_index('uq_track_labels_primary', sqlite_where=sa.text('is_primary = 1'))
        batch_op.drop_index(batch_op.f('ix_track_labels_track_id'))

    op.drop_table('track_labels')
    with op.batch_alter_table('source_files', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_source_files_track_id'))

    op.drop_table('source_files')
    op.drop_table('tracks')
    op.drop_table('library_sources')
