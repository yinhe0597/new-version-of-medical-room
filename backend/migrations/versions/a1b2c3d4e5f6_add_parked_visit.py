"""add parked_visit table

Revision ID: a1b2c3d4e5f6
Revises: 5c2d9f5a3e0a, f2c7a6b9d8e1
Create Date: 2026-05-18 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
# 合并已有的两个 head 分支
down_revision = ("5c2d9f5a3e0a", "f2c7a6b9d8e1")
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "parked_visit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("chief_complaint", sa.Text(), nullable=True),
        sa.Column("present_illness", sa.Text(), nullable=True),
        sa.Column("past_history", sa.Text(), nullable=True),
        sa.Column("physical_exam", sa.Text(), nullable=True),
        sa.Column("diagnosis", sa.Text(), nullable=True),
        sa.Column("doctor_advice", sa.Text(), nullable=True),
        sa.Column("special_note", sa.Text(), nullable=True),
        sa.Column("consultation_fee", sa.Float(), nullable=True),
        sa.Column("items_json", sa.Text(), nullable=True),
        sa.Column("quick_mode", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patient.id"]),
        sa.ForeignKeyConstraint(["doctor_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "patient_id", "doctor_id", name="uq_parked_visit_patient_doctor"
        ),
    )
    with op.batch_alter_table("parked_visit", schema=None) as batch_op:
        batch_op.create_index("ix_parked_visit_patient_id", ["patient_id"], unique=False)
        batch_op.create_index("ix_parked_visit_doctor_id", ["doctor_id"], unique=False)
        batch_op.create_index("ix_parked_visit_expires_at", ["expires_at"], unique=False)


def downgrade():
    with op.batch_alter_table("parked_visit", schema=None) as batch_op:
        batch_op.drop_index("ix_parked_visit_expires_at")
        batch_op.drop_index("ix_parked_visit_doctor_id")
        batch_op.drop_index("ix_parked_visit_patient_id")
    op.drop_table("parked_visit")
