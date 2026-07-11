"""Add drug stock group and variant fields

Revision ID: 5c2d9f5a3e0a
Revises: 4f7a1c2b3d4e
Create Date: 2026-04-13 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

from backend.migrations.migration_helpers import (
    add_missing_columns,
    ensure_foreign_key,
    ensure_index,
    ensure_unique,
    refuse_unsafe_downgrade,
    require_table_shape,
    table_exists,
)


revision = "5c2d9f5a3e0a"
down_revision = "4f7a1c2b3d4e"
branch_labels = None
depends_on = None


def upgrade():
    add_missing_columns(
        "drug",
        [
            sa.Column("variant_type", sa.String(length=20), nullable=True),
            sa.Column("stock_group_code", sa.String(length=36), nullable=True),
            sa.Column("unit_amount", sa.Integer(), nullable=True),
            sa.Column("base_name", sa.String(length=128), nullable=True),
        ],
    )
    ensure_index("ix_drug_stock_group_code", "drug", ["stock_group_code"])

    if not table_exists("drug_stock_group"):
        op.create_table(
            "drug_stock_group",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("group_code", sa.String(length=36), nullable=False),
            sa.Column("batch_no", sa.String(length=50), nullable=False),
            sa.Column("base_name", sa.String(length=128), nullable=False),
            sa.Column("unit_name", sa.String(length=20), nullable=False),
            sa.Column("total_units", sa.Integer(), nullable=False),
            sa.Column("pack_amount", sa.Integer(), nullable=False),
            sa.Column("retail_amount", sa.Integer(), nullable=True),
            sa.Column("pack_drug_id", sa.Integer(), nullable=False),
            sa.Column("retail_drug_id", sa.Integer(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["pack_drug_id"], ["drug.id"], name="fk_drug_stock_group_pack_drug"),
            sa.ForeignKeyConstraint(["retail_drug_id"], ["drug.id"], name="fk_drug_stock_group_retail_drug"),
            sa.ForeignKeyConstraint(["created_by"], ["user.id"], name="fk_drug_stock_group_created_by"),
            sa.UniqueConstraint("group_code", name="uq_drug_stock_group_group_code"),
        )
    require_table_shape(
        "drug_stock_group",
        {
            "id", "group_code", "batch_no", "base_name", "unit_name",
            "total_units", "pack_amount", "retail_amount", "pack_drug_id",
            "retail_drug_id", "created_by", "created_at",
        },
    )
    ensure_unique(
        "uq_drug_stock_group_group_code",
        "drug_stock_group",
        ["group_code"],
    )
    ensure_foreign_key(
        "fk_drug_stock_group_pack_drug",
        "drug_stock_group",
        ["pack_drug_id"],
        "drug",
        ["id"],
    )
    ensure_foreign_key(
        "fk_drug_stock_group_retail_drug",
        "drug_stock_group",
        ["retail_drug_id"],
        "drug",
        ["id"],
    )
    ensure_foreign_key(
        "fk_drug_stock_group_created_by",
        "drug_stock_group",
        ["created_by"],
        "user",
        ["id"],
    )
    ensure_index("ix_drug_stock_group_batch_no", "drug_stock_group", ["batch_no"])
    ensure_index("ix_drug_stock_group_base_name", "drug_stock_group", ["base_name"])


def downgrade():
    refuse_unsafe_downgrade(revision)

