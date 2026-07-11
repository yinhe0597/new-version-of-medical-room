"""Add visit verification fields and prescription item price audit fields

Revision ID: 4f7a1c2b3d4e
Revises: 03af525657e5
Create Date: 2026-04-10 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

from backend.migrations.migration_helpers import (
    add_missing_columns,
    ensure_foreign_key,
    refuse_unsafe_downgrade,
)


# revision identifiers, used by Alembic.
revision = "4f7a1c2b3d4e"
down_revision = "03af525657e5"
branch_labels = None
depends_on = None


def upgrade():
    add_missing_columns(
        "visit",
        [
            sa.Column("verified_by", sa.Integer(), nullable=True),
            sa.Column("verified_at", sa.DateTime(), nullable=True),
            sa.Column("rejected_by", sa.Integer(), nullable=True),
            sa.Column("rejected_at", sa.DateTime(), nullable=True),
            sa.Column("reject_reason", sa.Text(), nullable=True),
        ],
    )
    ensure_foreign_key(
        "fk_visit_verified_by_user",
        "visit",
        ["verified_by"],
        "user",
        ["id"],
    )
    ensure_foreign_key(
        "fk_visit_rejected_by_user",
        "visit",
        ["rejected_by"],
        "user",
        ["id"],
    )

    add_missing_columns(
        "prescription_item",
        [
            sa.Column("original_price", sa.Float(), nullable=True),
            sa.Column("original_amount", sa.Float(), nullable=True),
            sa.Column("new_price", sa.Float(), nullable=True),
            sa.Column("new_amount", sa.Float(), nullable=True),
            sa.Column("modified_by", sa.Integer(), nullable=True),
            sa.Column("modified_at", sa.DateTime(), nullable=True),
            sa.Column("modify_reason", sa.Text(), nullable=True),
        ],
    )
    ensure_foreign_key(
        "fk_prescription_item_modified_by_user",
        "prescription_item",
        ["modified_by"],
        "user",
        ["id"],
    )

    op.execute(
        """
        UPDATE prescription_item
        SET
            original_price = COALESCE(original_price, price_at_visit),
            original_amount = COALESCE(original_amount, amount),
            new_price = COALESCE(new_price, price_at_visit),
            new_amount = COALESCE(new_amount, amount)
        """
    )


def downgrade():
    refuse_unsafe_downgrade(revision)
