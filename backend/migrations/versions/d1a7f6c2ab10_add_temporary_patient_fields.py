"""add temporary patient fields

Revision ID: d1a7f6c2ab10
Revises: bbf28ffdb4c0
Create Date: 2026-04-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from backend.migrations.migration_helpers import (
    add_missing_columns,
    ensure_index,
    refuse_unsafe_downgrade,
)


revision = "d1a7f6c2ab10"
down_revision = "bbf28ffdb4c0"
branch_labels = None
depends_on = None


def upgrade():
    add_missing_columns(
        "patient",
        [
            sa.Column("is_temporary", sa.Boolean(), nullable=True),
            sa.Column("age", sa.Integer(), nullable=True),
            sa.Column("id_card", sa.String(length=20), nullable=True),
        ],
    )
    ensure_index(
        "ix_patient_is_temporary",
        "patient",
        ["is_temporary"],
    )

    op.execute("UPDATE patient SET is_temporary = 0 WHERE is_temporary IS NULL")


def downgrade():
    refuse_unsafe_downgrade(revision)

