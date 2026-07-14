"""Widen string columns required by historical SQLite data.

Revision ID: c7a4e9f2d1b6
Revises: b6e1d8f3a2c4
Create Date: 2026-07-14 11:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

from backend.migrations.migration_helpers import refuse_unsafe_downgrade


revision = "c7a4e9f2d1b6"
down_revision = "b6e1d8f3a2c4"
branch_labels = None
depends_on = None


def _widen_string_column(table_name, column_name, target_length):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    column = next(
        (
            item
            for item in inspector.get_columns(table_name)
            if item["name"] == column_name
        ),
        None,
    )
    if column is None:
        raise RuntimeError(f"Required column {table_name}.{column_name} is missing")

    current_type = column["type"]
    if not isinstance(current_type, sa.String):
        raise RuntimeError(
            f"Cannot widen {table_name}.{column_name} from {current_type!r}"
        )
    current_length = getattr(current_type, "length", None)
    if isinstance(current_length, int) and current_length >= target_length:
        return

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            batch_op.alter_column(
                column_name,
                existing_type=current_type,
                type_=sa.String(length=target_length),
                existing_nullable=bool(column["nullable"]),
            )
        return
    if bind.dialect.name not in {"mysql", "mariadb"}:
        raise RuntimeError(f"Unsupported migration dialect: {bind.dialect.name}")

    preparer = bind.dialect.identifier_preparer
    quoted_table = preparer.quote(table_name)
    quoted_column = preparer.quote(column_name)
    max_length = bind.execute(
        sa.text(
            f"SELECT MAX(CHAR_LENGTH({quoted_column})) FROM {quoted_table}"
        )
    ).scalar()
    if max_length is not None and int(max_length) > target_length:
        raise RuntimeError(
            f"Cannot resize {table_name}.{column_name} to VARCHAR({target_length}); "
            f"existing maximum length is {int(max_length)}"
        )

    op.alter_column(
        table_name,
        column_name,
        existing_type=current_type,
        type_=sa.String(length=target_length),
        existing_nullable=bool(column["nullable"]),
    )


def upgrade():
    _widen_string_column("diagnosis_dict", "pinyin", 255)
    _widen_string_column("drug", "storage_location", 50)


def downgrade():
    refuse_unsafe_downgrade(revision)
