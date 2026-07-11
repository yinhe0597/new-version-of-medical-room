"""add counselor_name to patient

Revision ID: f2c7a6b9d8e1
Revises: d1a7f6c2ab10
Create Date: 2026-04-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from backend.migrations.migration_helpers import (
    add_missing_columns,
    refuse_unsafe_downgrade,
)


revision = "f2c7a6b9d8e1"
down_revision = "d1a7f6c2ab10"
branch_labels = None
depends_on = None


def upgrade():
    add_missing_columns(
        "patient",
        [sa.Column("counselor_name", sa.String(length=64), nullable=True)],
    )


def downgrade():
    refuse_unsafe_downgrade(revision)

