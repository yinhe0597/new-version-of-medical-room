"""add monthly_sort_order to drug

Revision ID: e7f8a9b0c1d2
Revises: a1b2c3d4e5f6
Create Date: 2026-05-28 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "e7f8a9b0c1d2"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("drug", schema=None) as batch_op:
        batch_op.add_column(sa.Column("monthly_sort_order", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("drug", schema=None) as batch_op:
        batch_op.drop_column("monthly_sort_order")
