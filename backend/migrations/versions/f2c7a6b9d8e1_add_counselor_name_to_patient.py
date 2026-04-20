"""add counselor_name to patient

Revision ID: f2c7a6b9d8e1
Revises: d1a7f6c2ab10
Create Date: 2026-04-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "f2c7a6b9d8e1"
down_revision = "d1a7f6c2ab10"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("patient", schema=None) as batch_op:
        batch_op.add_column(sa.Column("counselor_name", sa.String(length=64), nullable=True))


def downgrade():
    with op.batch_alter_table("patient", schema=None) as batch_op:
        batch_op.drop_column("counselor_name")

