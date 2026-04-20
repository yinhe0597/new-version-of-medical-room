"""add temporary patient fields

Revision ID: d1a7f6c2ab10
Revises: bbf28ffdb4c0
Create Date: 2026-04-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "d1a7f6c2ab10"
down_revision = "bbf28ffdb4c0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("patient", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_temporary", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("age", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("id_card", sa.String(length=20), nullable=True))
        batch_op.create_index(batch_op.f("ix_patient_is_temporary"), ["is_temporary"], unique=False)

    op.execute("UPDATE patient SET is_temporary = 0 WHERE is_temporary IS NULL")


def downgrade():
    with op.batch_alter_table("patient", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_patient_is_temporary"))
        batch_op.drop_column("id_card")
        batch_op.drop_column("age")
        batch_op.drop_column("is_temporary")

