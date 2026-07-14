"""Use double precision for values that must survive logical backup.

Revision ID: d8b5f0a3c2e7
Revises: c7a4e9f2d1b6
Create Date: 2026-07-14 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

from backend.migrations.migration_helpers import refuse_unsafe_downgrade


revision = "d8b5f0a3c2e7"
down_revision = "c7a4e9f2d1b6"
branch_labels = None
depends_on = None


DOUBLE_COLUMNS = {
    "drug": ("price", "purchase_price", "scattered_price"),
    "parked_visit": ("consultation_fee",),
    "payment": (
        "amount",
        "original_amount",
        "actual_consultation_fee",
        "actual_drug_amount",
    ),
    "prescription_item": (
        "price_at_visit",
        "amount",
        "original_price",
        "original_amount",
        "new_price",
        "new_amount",
        "purchase_cost",
        "infusion_dosage_value",
    ),
    "visit": ("consultation_fee", "total_amount"),
}
OPTIONAL_DOUBLE_COLUMNS = {
    "drug": ("daily_loss_rate",),
    "prescription_item": ("herb_dosage",),
}


def _convert_column(table_name, column_name, *, required):
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite stores FLOAT and DOUBLE with the same REAL affinity.
        return
    if bind.dialect.name not in {"mysql", "mariadb"}:
        raise RuntimeError(f"Unsupported migration dialect: {bind.dialect.name}")

    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        if required:
            raise RuntimeError(f"Required table {table_name} is missing")
        return
    column = next(
        (
            item
            for item in inspector.get_columns(table_name)
            if item["name"] == column_name
        ),
        None,
    )
    if column is None:
        if required:
            raise RuntimeError(f"Required column {table_name}.{column_name} is missing")
        return

    current_type = column["type"]
    if getattr(current_type, "__visit_name__", "").lower() == "double":
        return
    if not isinstance(current_type, sa.Float):
        raise RuntimeError(
            f"Cannot convert {table_name}.{column_name} from {current_type!r}"
        )
    default = column.get("default")
    op.alter_column(
        table_name,
        column_name,
        existing_type=current_type,
        type_=sa.Double(),
        existing_nullable=bool(column["nullable"]),
        existing_server_default=(
            sa.text(str(default)) if default is not None else None
        ),
    )


def upgrade():
    for table_name, column_names in DOUBLE_COLUMNS.items():
        for column_name in column_names:
            _convert_column(table_name, column_name, required=True)
    for table_name, column_names in OPTIONAL_DOUBLE_COLUMNS.items():
        for column_name in column_names:
            _convert_column(table_name, column_name, required=False)


def downgrade():
    refuse_unsafe_downgrade(revision)
