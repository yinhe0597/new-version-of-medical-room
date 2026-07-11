"""add_scattered_and_purchase_price

Revision ID: 03af525657e5
Revises: bbf28ffdb4c0
Create Date: 2026-03-26 14:13:39.419463

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '03af525657e5'
down_revision = 'bbf28ffdb4c0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('drug', schema=None) as batch_op:
        batch_op.add_column(sa.Column('batch_no', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('inbound_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('purchase_price', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('has_scattered', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('scattered_price', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('conversion_rate', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('drug', schema=None) as batch_op:
        batch_op.drop_column('conversion_rate')
        batch_op.drop_column('scattered_price')
        batch_op.drop_column('has_scattered')
        batch_op.drop_column('purchase_price')
        batch_op.drop_column('inbound_at')
        batch_op.drop_column('batch_no')
