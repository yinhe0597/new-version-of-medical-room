"""Add drug stock group and variant fields

Revision ID: 5c2d9f5a3e0a
Revises: 4f7a1c2b3d4e
Create Date: 2026-04-13 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "5c2d9f5a3e0a"
down_revision = "4f7a1c2b3d4e"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("drug", schema=None) as batch_op:
        batch_op.add_column(sa.Column("variant_type", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("stock_group_code", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("unit_amount", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("base_name", sa.String(length=128), nullable=True))
        batch_op.create_index("ix_drug_stock_group_code", ["stock_group_code"], unique=False)

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
    op.create_index("ix_drug_stock_group_batch_no", "drug_stock_group", ["batch_no"], unique=False)
    op.create_index("ix_drug_stock_group_base_name", "drug_stock_group", ["base_name"], unique=False)


def downgrade():
    op.drop_index("ix_drug_stock_group_base_name", table_name="drug_stock_group")
    op.drop_index("ix_drug_stock_group_batch_no", table_name="drug_stock_group")
    op.drop_table("drug_stock_group")

    with op.batch_alter_table("drug", schema=None) as batch_op:
        batch_op.drop_index("ix_drug_stock_group_code")
        batch_op.drop_column("base_name")
        batch_op.drop_column("unit_amount")
        batch_op.drop_column("stock_group_code")
        batch_op.drop_column("variant_type")

