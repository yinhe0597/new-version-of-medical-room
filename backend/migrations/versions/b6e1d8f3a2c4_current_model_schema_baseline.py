"""Bridge the historical migration head to the current ORM schema.

Revision ID: b6e1d8f3a2c4
Revises: e7f8a9b0c1d2
Create Date: 2026-07-11 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

from backend.migrations.migration_helpers import (
    add_missing_columns as _add_missing_columns,
    ensure_foreign_key as _ensure_foreign_key,
    ensure_index as _ensure_index,
    ensure_unique as _ensure_unique,
    refuse_unsafe_downgrade as _refuse_unsafe_downgrade,
    require_table_shape as _require_table_shape,
)


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


def _normalize_string_length(
    table_name,
    column_name,
    target_length,
    *,
    allow_text=False,
):
    column = next(
        (
            item
            for item in _inspector().get_columns(table_name)
            if item["name"] == column_name
        ),
        None,
    )
    if column is None:
        raise RuntimeError(f"Required column {table_name}.{column_name} is missing")

    current_type = column["type"]
    current_length = getattr(current_type, "length", None)
    is_text = isinstance(current_type, sa.Text)
    if is_text and not allow_text:
        raise RuntimeError(
            f"Cannot safely convert {table_name}.{column_name} from "
            f"{current_type!r} to VARCHAR({target_length})"
        )
    if not isinstance(current_type, sa.String):
        raise RuntimeError(
            f"Cannot safely convert {table_name}.{column_name} from {current_type!r} "
            f"to VARCHAR({target_length})"
        )
    if not is_text and isinstance(current_length, int):
        if current_length >= target_length:
            return
    elif not is_text:
        raise RuntimeError(
            f"Cannot safely determine the length of "
            f"{table_name}.{column_name}: {current_type!r}"
        )
    if isinstance(current_type, sa.CHAR):
        raise RuntimeError(
            f"Cannot safely convert fixed-width {table_name}.{column_name} "
            f"from {current_type!r}"
        )
    if current_length == target_length:
        return

    bind = op.get_bind()
    preparer = bind.dialect.identifier_preparer
    quoted_table = preparer.quote(table_name)
    quoted_column = preparer.quote(column_name)
    length_function = (
        "CHAR_LENGTH" if bind.dialect.name in {"mysql", "mariadb"} else "LENGTH"
    )
    max_length = bind.execute(
        sa.text(
            f"SELECT MAX({length_function}({quoted_column})) FROM {quoted_table}"
        )
    ).scalar()
    if max_length is not None and max_length > target_length:
        raise RuntimeError(
            f"Cannot safely convert {table_name}.{column_name} to "
            f"VARCHAR({target_length}): existing data is {max_length} characters long"
        )

    if is_text:
        if bind.dialect.name in {"mysql", "mariadb"}:
            from sqlalchemy.dialects.mysql import VARCHAR

            target_type = VARCHAR(
                length=target_length,
                charset=getattr(current_type, "charset", None),
                collation=getattr(current_type, "collation", None),
                ascii=getattr(current_type, "ascii", False),
                unicode=getattr(current_type, "unicode", False),
                binary=getattr(current_type, "binary", False),
                national=getattr(current_type, "national", False),
            )
        else:
            target_type = sa.String(
                length=target_length,
                collation=getattr(current_type, "collation", None),
            )
    else:
        target_type = current_type.copy()
        target_type.length = target_length

    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.alter_column(
            column_name,
            existing_type=current_type,
            type_=target_type,
            existing_nullable=column.get("nullable", True),
            existing_server_default=column.get("default"),
            existing_comment=column.get("comment"),
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

    _add_missing_columns(
        "inventory_record",
        [
            sa.Column("visit_id", sa.Integer(), nullable=True),
            sa.Column("operation_type", sa.String(length=20), nullable=True),
        ],
    )

    _require_table_shape(
        "daily_stock_snapshot",
        {"id", "drug_id", "date", "stock", "created_at"},
    )
    _require_table_shape(
        "operation_log",
        {
            "id", "user_id", "action_type", "target_type", "target_id",
            "summary", "details", "timestamp",
        },
    )
    _require_table_shape(
        "text_template",
        {
            "id", "doctor_id", "category", "title", "content",
            "created_at", "updated_at",
        },
    )
    _require_table_shape(
        "inventory_record",
        {
            "id", "drug_id", "nurse_id", "visit_id", "old_stock",
            "new_stock", "operation_type", "remark", "timestamp",
        },
    )

    _ensure_unique(
        "uq_daily_stock_snapshot_drug_date",
        "daily_stock_snapshot",
        ["drug_id", "date"],
    )
    _ensure_foreign_key(
        "fk_daily_stock_snapshot_drug_id_drug",
        "daily_stock_snapshot",
        ["drug_id"],
        "drug",
        ["id"],
    )
    _ensure_foreign_key(
        "fk_operation_log_user_id_user",
        "operation_log",
        ["user_id"],
        "user",
        ["id"],
    )
    _ensure_foreign_key(
        "fk_text_template_doctor_id_user",
        "text_template",
        ["doctor_id"],
        "user",
        ["id"],
    )
    for column_name, referred_table in (
        ("drug_id", "drug"),
        ("nurse_id", "user"),
        ("visit_id", "visit"),
    ):
        _ensure_foreign_key(
            f"fk_inventory_record_{column_name}_{referred_table}",
            "inventory_record",
            [column_name],
            referred_table,
            ["id"],
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

    _normalize_string_length("user", "password_hash", 256)
    _normalize_string_length("patient", "name_pinyin", 255, allow_text=True)
    _normalize_string_length("patient", "name_initials", 255, allow_text=True)
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


def downgrade():
    _refuse_unsafe_downgrade(revision)
