"""drop legacy drug.monthly_sort_order column

The per-drug monthly sort feature (open0.0.12) was removed in open0.0.14 and
replaced by ``storage_location``. Migration e7f8a9b0c1d2 still creates the
``monthly_sort_order`` column, leaving fresh databases with a column the ORM
model no longer declares. Drop it so the schema matches the model. Historical
databases that never held the column are tolerated (idempotent drop).

Revision ID: a3f2e1c0d4b5
Revises: d8b5f0a3c2e7
Create Date: 2026-07-31 10:00:00.000000

"""
from alembic import op

from backend.migrations.migration_helpers import (
    drop_existing_columns,
    refuse_unsafe_downgrade,
)


revision = "a3f2e1c0d4b5"
down_revision = "d8b5f0a3c2e7"
branch_labels = None
depends_on = None


def upgrade():
    drop_existing_columns("drug", ["monthly_sort_order"])


def downgrade():
    refuse_unsafe_downgrade(revision)
