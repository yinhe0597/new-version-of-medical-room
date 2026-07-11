"""Small compatibility helpers for adopting pre-Alembic databases."""

from alembic import op
import sqlalchemy as sa


def inspector():
    return sa.inspect(op.get_bind())


def table_exists(table_name):
    return table_name in inspector().get_table_names()


def column_names(table_name):
    return {column["name"] for column in inspector().get_columns(table_name)}


def require_table_shape(table_name, required_columns, *, primary_key=("id",)):
    if not table_exists(table_name):
        raise RuntimeError(f"Required table {table_name!r} does not exist")

    missing = set(required_columns) - column_names(table_name)
    if missing:
        names = ", ".join(sorted(missing))
        raise RuntimeError(
            f"Existing table {table_name!r} is missing required columns: {names}"
        )

    actual_primary_key = tuple(
        inspector().get_pk_constraint(table_name).get("constrained_columns") or ()
    )
    if actual_primary_key != tuple(primary_key):
        raise RuntimeError(
            f"Existing table {table_name!r} has primary key {actual_primary_key!r}; "
            f"expected {tuple(primary_key)!r}"
        )


def add_missing_columns(table_name, columns):
    existing = column_names(table_name)
    missing = [column for column in columns if column.name not in existing]
    if not missing:
        return

    with op.batch_alter_table(table_name, schema=None) as batch_op:
        for column in missing:
            batch_op.add_column(column)


def refuse_unsafe_downgrade(revision):
    raise RuntimeError(
        f"Downgrade from revision {revision} is intentionally unsupported: "
        "this migration chain may adopt pre-existing schema objects. Restore "
        "the verified pre-migration backup instead."
    )


def _index_shape(index):
    dialect_options = index.get("dialect_options") or {}
    has_dialect_options = any(
        value is not None
        and not (
            isinstance(value, (str, tuple, list, set, dict))
            and len(value) == 0
        )
        for value in dialect_options.values()
    )
    has_extra_semantics = bool(
        has_dialect_options
        or index.get("column_sorting")
        or index.get("include_columns")
    )
    return (
        tuple(index.get("column_names") or ()),
        bool(index.get("unique")),
        has_extra_semantics,
    )


def ensure_index(index_name, table_name, columns, *, unique=False):
    expected = (tuple(columns), bool(unique), False)
    indexes = inspector().get_indexes(table_name)
    for index in indexes:
        actual = _index_shape(index)
        if index.get("name") == index_name and actual != expected:
            raise RuntimeError(
                f"Index {index_name!r} on {table_name!r} has shape {actual!r}; "
                f"expected {expected!r}"
            )
    for index in indexes:
        actual = _index_shape(index)
        if actual == expected:
            return

    op.create_index(index_name, table_name, columns, unique=unique)


def ensure_unique(constraint_name, table_name, columns):
    expected = tuple(columns)
    expected_index = (expected, True, False)
    schema_inspector = inspector()
    constraints = schema_inspector.get_unique_constraints(table_name)
    indexes = schema_inspector.get_indexes(table_name)
    indexes_by_name = {
        index.get("name"): index for index in indexes if index.get("name")
    }

    def constraint_shape(constraint):
        duplicate_index = constraint.get("duplicates_index")
        if duplicate_index:
            index = indexes_by_name.get(duplicate_index)
            if index is None:
                return (
                    tuple(constraint.get("column_names") or ()),
                    True,
                    True,
                )
            return _index_shape(index)
        return (
            tuple(constraint.get("column_names") or ()),
            True,
            False,
        )

    for constraint in constraints:
        actual = constraint_shape(constraint)
        if constraint.get("name") == constraint_name and actual != expected_index:
            raise RuntimeError(
                f"Unique constraint {constraint_name!r} on {table_name!r} has "
                f"shape {actual!r}; expected {expected_index!r}"
            )
    for constraint in constraints:
        if constraint_shape(constraint) == expected_index:
            return

    for index in indexes:
        actual = _index_shape(index)
        if index.get("name") == constraint_name and actual != expected_index:
            raise RuntimeError(
                f"Constraint name {constraint_name!r} on {table_name!r} is "
                "already used by a different index"
            )
    for index in indexes:
        actual = _index_shape(index)
        if actual == expected_index:
            return

    bind = op.get_bind()
    preparer = bind.dialect.identifier_preparer
    quoted_table = preparer.quote(table_name)
    quoted_columns = [preparer.quote(column) for column in columns]
    group_by = ", ".join(quoted_columns)
    non_null = " AND ".join(f"{column} IS NOT NULL" for column in quoted_columns)
    duplicate_groups = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM ("
            f"SELECT 1 FROM {quoted_table} WHERE {non_null} "
            f"GROUP BY {group_by} HAVING COUNT(*) > 1"
            ") AS duplicate_groups"
        )
    ).scalar()
    if duplicate_groups:
        raise RuntimeError(
            f"Cannot create unique constraint {constraint_name!r} on "
            f"{table_name!r}: found {duplicate_groups} duplicate key group(s)"
        )

    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.create_unique_constraint(constraint_name, list(columns))


def ensure_foreign_key(
    constraint_name,
    table_name,
    local_columns,
    referred_table,
    remote_columns,
):
    expected_relationship = (
        tuple(local_columns),
        None,
        referred_table,
        tuple(remote_columns),
    )
    fk_inspector = inspector()
    foreign_keys = fk_inspector.get_foreign_keys(table_name)
    default_schema = fk_inspector.default_schema_name

    def relationship(foreign_key):
        referred_schema = foreign_key.get("referred_schema")
        if referred_schema == default_schema:
            referred_schema = None
        return (
            tuple(foreign_key.get("constrained_columns") or ()),
            referred_schema,
            foreign_key.get("referred_table"),
            tuple(foreign_key.get("referred_columns") or ()),
        )

    def non_default_options(foreign_key):
        return {
            key: value
            for key, value in (foreign_key.get("options") or {}).items()
            if value is not None
        }

    for foreign_key in foreign_keys:
        if foreign_key.get("name") == constraint_name and (
            relationship(foreign_key) != expected_relationship
            or non_default_options(foreign_key)
        ):
            raise RuntimeError(
                f"Foreign key name {constraint_name!r} on {table_name!r} is "
                "already used by a different relationship"
            )
    for foreign_key in foreign_keys:
        if relationship(foreign_key) == expected_relationship:
            options = non_default_options(foreign_key)
            if options:
                raise RuntimeError(
                    f"Foreign key on {table_name!r} for {tuple(local_columns)!r} "
                    f"has incompatible options: {options!r}"
                )
            return

    bind = op.get_bind()
    preparer = bind.dialect.identifier_preparer
    local_table = preparer.quote(table_name)
    remote_table = preparer.quote(referred_table)
    local = [preparer.quote(column) for column in local_columns]
    remote = [preparer.quote(column) for column in remote_columns]
    join_clause = " AND ".join(
        f"source.{left} = target.{right}" for left, right in zip(local, remote)
    )
    non_null = " AND ".join(f"source.{column} IS NOT NULL" for column in local)
    missing_target = " AND ".join(f"target.{column} IS NULL" for column in remote)
    orphan_count = bind.execute(
        sa.text(
            f"SELECT COUNT(*) FROM {local_table} AS source "
            f"LEFT JOIN {remote_table} AS target ON {join_clause} "
            f"WHERE {non_null} AND {missing_target}"
        )
    ).scalar()
    if orphan_count:
        raise RuntimeError(
            f"Cannot create foreign key {constraint_name!r} on {table_name!r}: "
            f"found {orphan_count} orphan row(s)"
        )

    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.create_foreign_key(
            constraint_name,
            referred_table,
            local_columns,
            remote_columns,
        )
