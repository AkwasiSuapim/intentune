"""create listener profiles

Phase B1. The one table Prototype 1 needs before any library or session
data: the generated local listener identity (D01). The application creates
the default row at startup (application/local_listener.py), not this
migration; the partial unique index guarantees there is never more than one.

created_at holds a UTC value. The ORM column type, UtcDateTime, stores it as
a plain DATETIME; migrations use the plain type so they never import
application code.

Revision ID: 6ef3a3452ab7
Revises:
Create Date: 2026-10-19 17:03:15.420167

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6ef3a3452ab7'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'listener_profiles',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_listener_profiles')),
    )
    with op.batch_alter_table('listener_profiles', schema=None) as batch_op:
        batch_op.create_index(
            'uq_listener_profiles_is_default',
            ['is_default'],
            unique=True,
            sqlite_where=sa.text('is_default = 1'),
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('listener_profiles', schema=None) as batch_op:
        batch_op.drop_index('uq_listener_profiles_is_default', sqlite_where=sa.text('is_default = 1'))

    op.drop_table('listener_profiles')
