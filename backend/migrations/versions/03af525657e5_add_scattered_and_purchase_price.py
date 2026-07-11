"""add_scattered_and_purchase_price

Revision ID: 03af525657e5
Revises: bbf28ffdb4c0
Create Date: 2026-03-26 14:13:39.419463

"""
from alembic import op
import sqlalchemy as sa

from backend.migrations.migration_helpers import (
    add_missing_columns,
    refuse_unsafe_downgrade,
)


# revision identifiers, used by Alembic.
revision = '03af525657e5'
down_revision = 'bbf28ffdb4c0'
branch_labels = None
depends_on = None


def upgrade():
    add_missing_columns(
        'drug',
        [
            sa.Column('batch_no', sa.String(length=50), nullable=True),
            sa.Column('inbound_at', sa.DateTime(), nullable=True),
            sa.Column('purchase_price', sa.Float(), nullable=True),
            sa.Column('has_scattered', sa.Boolean(), nullable=True),
            sa.Column('scattered_price', sa.Float(), nullable=True),
            sa.Column('conversion_rate', sa.Integer(), nullable=True),
        ],
    )


def downgrade():
    refuse_unsafe_downgrade(revision)
