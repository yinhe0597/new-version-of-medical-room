"""add monthly_sort_order to drug

Revision ID: e7f8a9b0c1d2
Revises: a1b2c3d4e5f6
Create Date: 2026-05-28 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from backend.migrations.migration_helpers import (
    add_missing_columns,
    refuse_unsafe_downgrade,
)


revision = "e7f8a9b0c1d2"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    add_missing_columns(
        "drug",
        [sa.Column("monthly_sort_order", sa.Integer(), nullable=True)],
    )


def downgrade():
    refuse_unsafe_downgrade(revision)
