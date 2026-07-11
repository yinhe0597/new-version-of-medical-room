"""Bridge the historical migration head to the current ORM schema.

Revision ID: b6e1d8f3a2c4
Revises: e7f8a9b0c1d2
Create Date: 2026-07-11 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "b6e1d8f3a2c4"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(table_name):
    return table_name in _inspector().get_table_names()


def _column_names(table_name):
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _add_missing_columns(table_name, columns):
    existing = _column_names(table_name)
    missing = [column for column in columns if column.name not in existing]
    if not missing:
        return
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        for column in missing:
            batch_op.add_column(column)


def _ensure_index(index_name, table_name, columns, unique=False):
    existing = {
        index["name"]
        for index in _inspector().get_indexes(table_name)
        if index.get("name")
    }
    if index_name not in existing:
        op.create_index(index_name, table_name, columns, unique=unique)


def _ensure_unique(constraint_name, table_name, columns):
    expected = set(columns)
    for constraint in _inspector().get_unique_constraints(table_name):
        if set(constraint.get("column_names") or ()) == expected:
            return
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.create_unique_constraint(constraint_name, columns)


def _ensure_foreign_key(
    constraint_name,
    table_name,
    local_columns,
    referred_table,
    remote_columns,
):
    for foreign_key in _inspector().get_foreign_keys(table_name):
        if (
            list(foreign_key.get("constrained_columns") or ()) == list(local_columns)
            and foreign_key.get("referred_table") == referred_table
            and list(foreign_key.get("referred_columns") or ()) == list(remote_columns)
        ):
            return
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.create_foreign_key(
            constraint_name,
            referred_table,
            local_columns,
            remote_columns,
        )


def _widen_password_hash():
    password_hash = next(
        column
        for column in _inspector().get_columns("user")
        if column["name"] == "password_hash"
    )
    current_length = getattr(password_hash["type"], "length", None)
    if not isinstance(current_length, int) or current_length >= 256:
        return
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.alter_column(
            "password_hash",
            existing_type=password_hash["type"],
            type_=sa.String(length=256),
            existing_nullable=password_hash.get("nullable", True),
        )


def _create_missing_tables():
    if not _table_exists("daily_stock_snapshot"):
        op.create_table(
            "daily_stock_snapshot",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("drug_id", sa.Integer(), nullable=True),
            sa.Column("date", sa.Date(), nullable=True),
            sa.Column("stock", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["drug_id"], ["drug.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "drug_id",
                "date",
                name="uq_daily_stock_snapshot_drug_date",
            ),
        )

    if not _table_exists("operation_log"):
        op.create_table(
            "operation_log",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("action_type", sa.String(length=50), nullable=True),
            sa.Column("target_type", sa.String(length=50), nullable=True),
            sa.Column("target_id", sa.Integer(), nullable=True),
            sa.Column("summary", sa.String(length=200), nullable=True),
            sa.Column("details", sa.Text(), nullable=True),
            sa.Column("timestamp", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _table_exists("text_template"):
        op.create_table(
            "text_template",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("doctor_id", sa.Integer(), nullable=False),
            sa.Column("category", sa.String(length=50), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["doctor_id"], ["user.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _table_exists("inventory_record"):
        op.create_table(
            "inventory_record",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("drug_id", sa.Integer(), nullable=True),
            sa.Column("nurse_id", sa.Integer(), nullable=True),
            sa.Column("visit_id", sa.Integer(), nullable=True),
            sa.Column("old_stock", sa.Integer(), nullable=True),
            sa.Column("new_stock", sa.Integer(), nullable=True),
            sa.Column("operation_type", sa.String(length=20), nullable=True),
            sa.Column("remark", sa.String(length=200), nullable=True),
            sa.Column("timestamp", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["drug_id"], ["drug.id"]),
            sa.ForeignKeyConstraint(["nurse_id"], ["user.id"]),
            sa.ForeignKeyConstraint(["visit_id"], ["visit.id"]),
            sa.PrimaryKeyConstraint("id"),
        )


def upgrade():
    _create_missing_tables()

    _add_missing_columns(
        "drug",
        [
            sa.Column("storage_location", sa.String(length=10), nullable=True),
            sa.Column("expiry_date", sa.Date(), nullable=True),
        ],
    )
    _add_missing_columns(
        "patient",
        [
            sa.Column("name_pinyin", sa.String(length=255), nullable=True),
            sa.Column("name_initials", sa.String(length=255), nullable=True),
            sa.Column("patient_type", sa.String(length=20), nullable=True),
            sa.Column("department", sa.String(length=100), nullable=True),
            sa.Column("shop_name", sa.String(length=100), nullable=True),
        ],
    )
    _add_missing_columns(
        "payment",
        [
            sa.Column("is_employee_discount", sa.Boolean(), nullable=True),
            sa.Column("original_amount", sa.Float(), nullable=True),
            sa.Column("receipt_snapshot", sa.Text(), nullable=True),
            sa.Column("actual_consultation_fee", sa.Float(), nullable=True),
            sa.Column("actual_drug_amount", sa.Float(), nullable=True),
        ],
    )
    _add_missing_columns(
        "prescription_item",
        [
            sa.Column("is_scattered", sa.Boolean(), nullable=True),
            sa.Column("purchase_cost", sa.Float(), nullable=True),
            sa.Column("is_intravenous", sa.Boolean(), nullable=True),
            sa.Column("infusion_group", sa.Integer(), nullable=True),
            sa.Column("infusion_dosage_value", sa.Float(), nullable=True),
            sa.Column("infusion_dosage_unit", sa.String(length=10), nullable=True),
            sa.Column("infusion_method", sa.String(length=50), nullable=True),
        ],
    )
    _add_missing_columns(
        "user",
        [
            sa.Column("token_version", sa.Integer(), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1"),
            ),
        ],
    )
    _add_missing_columns(
        "visit",
        [
            sa.Column("special_note", sa.Text(), nullable=True),
            sa.Column("revoked_by", sa.Integer(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("revoke_reason", sa.Text(), nullable=True),
        ],
    )

    _widen_password_hash()
    _ensure_foreign_key(
        "fk_visit_revoked_by_user",
        "visit",
        ["revoked_by"],
        "user",
        ["id"],
    )

    _ensure_index(
        "ix_daily_stock_snapshot_date",
        "daily_stock_snapshot",
        ["date"],
    )
    _ensure_index(
        "ix_daily_stock_snapshot_drug_id",
        "daily_stock_snapshot",
        ["drug_id"],
    )
    _ensure_unique(
        "uq_daily_stock_snapshot_drug_date",
        "daily_stock_snapshot",
        ["drug_id", "date"],
    )
    _ensure_index(
        "ix_operation_log_action_type",
        "operation_log",
        ["action_type"],
    )
    _ensure_index("ix_operation_log_user_id", "operation_log", ["user_id"])
    _ensure_index("ix_text_template_category", "text_template", ["category"])
    _ensure_index("ix_text_template_doctor_id", "text_template", ["doctor_id"])
    _ensure_index(
        "ix_inventory_record_operation_type",
        "inventory_record",
        ["operation_type"],
    )
    _ensure_index("ix_inventory_record_visit_id", "inventory_record", ["visit_id"])
    _ensure_index("ix_patient_id_card", "patient", ["id_card"])
    _ensure_index("ix_patient_name_initials", "patient", ["name_initials"])
    _ensure_index("ix_patient_name_pinyin", "patient", ["name_pinyin"])
    _ensure_index("ix_patient_patient_type", "patient", ["patient_type"])
    _ensure_index("ix_user_is_active", "user", ["is_active"])


def _drop_index_if_present(index_name, table_name):
    existing = {
        index["name"]
        for index in _inspector().get_indexes(table_name)
        if index.get("name")
    }
    if index_name in existing:
        op.drop_index(index_name, table_name=table_name)


def _drop_columns_if_present(table_name, column_names):
    existing = _column_names(table_name)
    present = [name for name in column_names if name in existing]
    if not present:
        return
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        for column_name in present:
            batch_op.drop_column(column_name)


def downgrade():
    _drop_index_if_present("ix_user_is_active", "user")
    _drop_index_if_present("ix_patient_patient_type", "patient")
    _drop_index_if_present("ix_patient_name_pinyin", "patient")
    _drop_index_if_present("ix_patient_name_initials", "patient")
    _drop_index_if_present("ix_patient_id_card", "patient")

    foreign_keys = _inspector().get_foreign_keys("visit")
    revoked_key = next(
        (
            foreign_key
            for foreign_key in foreign_keys
            if foreign_key.get("name") == "fk_visit_revoked_by_user"
        ),
        None,
    )
    if revoked_key is not None:
        with op.batch_alter_table("visit", schema=None) as batch_op:
            batch_op.drop_constraint("fk_visit_revoked_by_user", type_="foreignkey")

    _drop_columns_if_present(
        "visit",
        ["revoke_reason", "revoked_at", "revoked_by", "special_note"],
    )
    _drop_columns_if_present("user", ["is_active", "token_version"])
    _drop_columns_if_present(
        "prescription_item",
        [
            "infusion_method",
            "infusion_dosage_unit",
            "infusion_dosage_value",
            "infusion_group",
            "is_intravenous",
            "purchase_cost",
            "is_scattered",
        ],
    )
    _drop_columns_if_present(
        "payment",
        [
            "actual_drug_amount",
            "actual_consultation_fee",
            "receipt_snapshot",
            "original_amount",
            "is_employee_discount",
        ],
    )
    _drop_columns_if_present(
        "patient",
        ["shop_name", "department", "patient_type", "name_initials", "name_pinyin"],
    )
    _drop_columns_if_present("drug", ["expiry_date", "storage_location"])

    for table_name in (
        "inventory_record",
        "text_template",
        "operation_log",
        "daily_stock_snapshot",
    ):
        if _table_exists(table_name):
            op.drop_table(table_name)
