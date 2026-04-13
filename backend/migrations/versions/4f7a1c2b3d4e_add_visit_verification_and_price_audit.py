"""Add visit verification fields and prescription item price audit fields

Revision ID: 4f7a1c2b3d4e
Revises: 03af525657e5
Create Date: 2026-04-10 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4f7a1c2b3d4e"
down_revision = "03af525657e5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("visit", schema=None) as batch_op:
        batch_op.add_column(sa.Column("verified_by", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("verified_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("rejected_by", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("rejected_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("reject_reason", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_visit_verified_by_user",
            "user",
            ["verified_by"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_visit_rejected_by_user",
            "user",
            ["rejected_by"],
            ["id"],
        )

    with op.batch_alter_table("prescription_item", schema=None) as batch_op:
        batch_op.add_column(sa.Column("original_price", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("original_amount", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("new_price", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("new_amount", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("modified_by", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("modified_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("modify_reason", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_prescription_item_modified_by_user",
            "user",
            ["modified_by"],
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
    with op.batch_alter_table("prescription_item", schema=None) as batch_op:
        batch_op.drop_constraint("fk_prescription_item_modified_by_user", type_="foreignkey")
        batch_op.drop_column("modify_reason")
        batch_op.drop_column("modified_at")
        batch_op.drop_column("modified_by")
        batch_op.drop_column("new_amount")
        batch_op.drop_column("new_price")
        batch_op.drop_column("original_amount")
        batch_op.drop_column("original_price")

    with op.batch_alter_table("visit", schema=None) as batch_op:
        batch_op.drop_constraint("fk_visit_rejected_by_user", type_="foreignkey")
        batch_op.drop_constraint("fk_visit_verified_by_user", type_="foreignkey")
        batch_op.drop_column("reject_reason")
        batch_op.drop_column("rejected_at")
        batch_op.drop_column("rejected_by")
        batch_op.drop_column("verified_at")
        batch_op.drop_column("verified_by")
