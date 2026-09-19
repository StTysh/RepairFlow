"""property build_year, read-only messages table

Revision ID: dd3584cdf57b
Revises: 496bf82ee3e9
Create Date: 2026-09-19 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dd3584cdf57b'
down_revision: Union[str, Sequence[str], None] = '496bf82ee3e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    build_year is nullable with no backfill: there is no source of truth
    for a real construction year for any seeded property, so every row --
    old and new -- stays NULL until a real value is actually known
    (CLAUDE.md: never fabricate data).

    messages is a brand new, display-only tenant/contractor/operator
    message-thread table (see MessageModel's docstring): never read by the
    coordinator, not part of CaseSnapshot.
    """
    with op.batch_alter_table('properties', schema=None) as batch_op:
        batch_op.add_column(sa.Column('build_year', sa.Integer(), nullable=True))

    op.create_table(
        'messages',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('case_id', sa.String(length=36), nullable=False),
        sa.Column('sender_type', sa.String(length=40), nullable=False),
        sa.Column('sender_name', sa.String(length=128), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('photo_url', sa.String(length=512), nullable=True),
        sa.Column('created_at', sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['repair_cases.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.create_index('ix_message_case_created', ['case_id', 'created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_index('ix_message_case_created')
    op.drop_table('messages')

    with op.batch_alter_table('properties', schema=None) as batch_op:
        batch_op.drop_column('build_year')
