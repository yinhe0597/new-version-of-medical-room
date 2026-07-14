"""Safely copy the project SQLite database into a prepared MySQL database.

The command is a dry-run by default. A destructive copy requires ``--execute``,
``--yes``, and the source SHA-256 printed by a preceding dry-run after the
application has been stopped. The target schema must already exist and be
upgraded with Alembic; this tool only copies data.
"""

import argparse
from contextlib import closing, contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile

from alembic.script import ScriptDirectory
from sqlalchemy import MetaData, String, and_, create_engine, func, inspect, select, text
from sqlalchemy.engine import URL, make_url


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app import create_app, db
from backend.config import (
    Config,
    _database_requires_tls,
    _engine_configuration,
    _validated_mysql_query,
)


LEGACY_MYSQL_KEYS = (
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_HOST",
    "MYSQL_PORT",
    "MYSQL_DB",
)
DEFAULT_SQLITE_PATH = ROOT_DIR / "data" / "app.db"
DEFAULT_BATCH_SIZE = 1000
MIGRATIONS_DIR = ROOT_DIR / "backend" / "migrations"
STRICT_SQL_MODES = {"STRICT_TRANS_TABLES", "STRICT_ALL_TABLES"}


class MigrationConfig(Config):
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SCHEDULER_ENABLED = False
    STARTUP_DATA_REPAIRS_ENABLED = False


@dataclass(frozen=True)
class TableStats:
    row_count: int
    primary_key_digest: str


@dataclass(frozen=True)
class SourceSnapshot:
    path: Path
    sha256: str


@dataclass(frozen=True)
class MigrationPlan:
    table_names: tuple
    source_stats: dict
    target_stats: dict
    expected_alembic_head: str


@dataclass(frozen=True)
class ReflectedForeignKey:
    child_table: object
    parent_table: object
    local_names: tuple
    remote_names: tuple

    @property
    def label(self):
        child = _table_label(self.child_table)
        parent = _table_label(self.parent_table)
        return (
            f"{child}.{'/'.join(self.local_names)} -> "
            f"{parent}.{'/'.join(self.remote_names)}"
        )


def _migration_config(database_url):
    url = _normalize_mysql_url(database_url, "DATABASE_URL")
    raw_uri = url.render_as_string(hide_password=False)
    uri, engine_options = _engine_configuration(raw_uri)
    requires_tls = _database_requires_tls(uri)
    return type(
        "ResolvedMigrationConfig",
        (MigrationConfig,),
        {
            "SQLALCHEMY_DATABASE_URI": uri,
            "SQLALCHEMY_ENGINE_OPTIONS": engine_options,
            "DATABASE_REQUIRE_TLS": requires_tls,
        },
    )


def _normalize_mysql_url(value, label):
    try:
        url = make_url(value)
    except Exception as exc:
        raise RuntimeError(f"{label} is not a valid SQLAlchemy URL") from exc

    if url.drivername == "mysql":
        url = url.set(drivername="mysql+pymysql")
    if url.drivername != "mysql+pymysql":
        raise RuntimeError(
            f"{label} must use mysql+pymysql (received {url.drivername!r})"
        )
    if not url.database:
        raise RuntimeError(f"{label} must include a database name")

    serialized = (
        value
        if isinstance(value, str)
        else url.render_as_string(hide_password=False)
    )
    query = _validated_mysql_query(serialized, url)
    query.setdefault("charset", "utf8mb4")
    return url.set(query=query)


def _legacy_mysql_url(environ):
    configured = {key: environ.get(key) for key in LEGACY_MYSQL_KEYS}
    if not any(value not in (None, "") for value in configured.values()):
        return None
    if not configured["MYSQL_PASSWORD"]:
        raise RuntimeError(
            "Legacy MYSQL_* configuration is present but MYSQL_PASSWORD is missing"
        )
    try:
        port = int(configured["MYSQL_PORT"] or 3306)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("MYSQL_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("MYSQL_PORT must be between 1 and 65535")

    return URL.create(
        "mysql+pymysql",
        username=configured["MYSQL_USER"] or "root",
        password=configured["MYSQL_PASSWORD"],
        host=configured["MYSQL_HOST"] or "127.0.0.1",
        port=port,
        database=configured["MYSQL_DB"] or "medical_db",
        query={"charset": "utf8mb4"},
    )


def _target_identity(url):
    return (
        url.drivername,
        url.username or "",
        url.password or "",
        (url.host or "").lower(),
        url.port or 3306,
        url.database or "",
    )


def resolve_target_url(environ=None):
    """Resolve DATABASE_URL, allowing matching legacy MYSQL_* as a fallback."""
    environ = os.environ if environ is None else environ
    primary_value = environ.get("DATABASE_URL")
    primary = (
        _normalize_mysql_url(primary_value, "DATABASE_URL")
        if primary_value
        else None
    )
    legacy = _legacy_mysql_url(environ)

    if primary is None and legacy is None:
        raise RuntimeError(
            "DATABASE_URL is required (legacy MYSQL_* variables are accepted temporarily)"
        )
    if primary is not None and legacy is not None:
        if _target_identity(primary) != _target_identity(legacy):
            raise RuntimeError(
                "DATABASE_URL conflicts with legacy MYSQL_* target configuration"
            )
    return primary or legacy


def safe_target_summary(database_url):
    # Query parameters may contain TLS material or provider-specific tokens;
    # omit them entirely instead of relying only on password masking.
    return make_url(database_url).set(query={}).render_as_string(hide_password=True)


def discover_expected_alembic_head(migrations_dir=MIGRATIONS_DIR):
    migrations_dir = Path(migrations_dir).resolve()
    if not migrations_dir.is_dir():
        raise RuntimeError(f"Alembic migrations directory is missing: {migrations_dir}")
    heads = ScriptDirectory(str(migrations_dir)).get_heads()
    if len(heads) != 1:
        raise RuntimeError(
            "SQLite-to-MySQL migration requires exactly one Alembic head; "
            f"found {len(heads)}"
        )
    return heads[0]


def _assert_target_alembic_head(connection, expected_head):
    schema = inspect(connection)
    if not schema.has_table("alembic_version"):
        raise RuntimeError(
            "MySQL target is unversioned: alembic_version table is missing"
        )
    current_heads = list(
        connection.execute(text("SELECT version_num FROM alembic_version")).scalars()
    )
    if current_heads != [expected_head]:
        current_label = ", ".join(sorted(current_heads)) or "<empty>"
        raise RuntimeError(
            "MySQL target is not at the required Alembic head "
            f"(current={current_label}, expected={expected_head})"
        )


def _is_disabled_mysql_flag(value):
    if isinstance(value, bool):
        return not value
    return str(value).strip().lower() in {"0", "off", "false"}


def _validate_mysql_copy_preconditions(
    *,
    sql_mode,
    autocommit,
    transaction_read_only,
    global_read_only,
    global_super_read_only,
    table_engines,
    required_table_names,
    isolation_level=None,
):
    required_table_names = tuple(required_table_names)
    enabled_modes = {
        item.strip().upper() for item in str(sql_mode or "").split(",") if item.strip()
    }
    if not (enabled_modes & STRICT_SQL_MODES):
        raise RuntimeError(
            "MySQL target session must enable STRICT_TRANS_TABLES or "
            "STRICT_ALL_TABLES before importing data"
        )

    if not _is_disabled_mysql_flag(autocommit):
        raise RuntimeError(
            "MySQL target session autocommit must be disabled so the import can roll back"
        )
    if str(isolation_level or "").strip().upper() == "AUTOCOMMIT":
        raise RuntimeError(
            "MySQL target SQLAlchemy connection may not use AUTOCOMMIT isolation"
        )

    read_only_flags = {
        "session transaction_read_only": transaction_read_only,
        "global read_only": global_read_only,
        "global super_read_only": global_super_read_only,
    }
    enabled_read_only = [
        name
        for name, value in read_only_flags.items()
        if not _is_disabled_mysql_flag(value)
    ]
    if enabled_read_only:
        raise RuntimeError(
            "MySQL target is read-only and cannot run a transactional import: "
            + ", ".join(enabled_read_only)
        )

    normalized_engines = {
        str(name).casefold(): str(engine or "").upper()
        for name, engine in table_engines.items()
    }
    missing = [
        name
        for name in required_table_names
        if name.casefold() not in normalized_engines
    ]
    if missing:
        raise RuntimeError(
            "MySQL target engine metadata is missing modeled tables: "
            + ", ".join(sorted(missing))
        )

    non_transactional = [
        f"{name}={normalized_engines[name.casefold()] or '<unknown>'}"
        for name in required_table_names
        if normalized_engines[name.casefold()] != "INNODB"
    ]
    if non_transactional:
        raise RuntimeError(
            "MySQL import requires every modeled target table to use InnoDB; found "
            + ", ".join(sorted(non_transactional))
        )


def _assert_mysql_copy_preconditions(connection, table_names):
    if connection.dialect.name != "mysql":
        return

    settings = connection.execute(
        text(
            """
            SELECT
                @@SESSION.sql_mode AS sql_mode,
                @@SESSION.autocommit AS autocommit,
                @@SESSION.transaction_read_only AS transaction_read_only,
                @@GLOBAL.read_only AS global_read_only,
                @@GLOBAL.super_read_only AS global_super_read_only
            """
        )
    ).mappings().one()
    engine_rows = connection.execute(
        text(
            """
            SELECT
                TABLE_NAME AS table_name,
                ENGINE AS engine
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_type = 'BASE TABLE'
            """
        )
    ).mappings()
    table_engines = {
        row["table_name"]: row["engine"]
        for row in engine_rows
    }
    _validate_mysql_copy_preconditions(
        sql_mode=settings["sql_mode"],
        autocommit=settings["autocommit"],
        transaction_read_only=settings["transaction_read_only"],
        global_read_only=settings["global_read_only"],
        global_super_read_only=settings["global_super_read_only"],
        table_engines=table_engines,
        required_table_names=tuple(table_names),
        isolation_level=connection.get_execution_options().get("isolation_level"),
    )


def _modeled_table_names(model_metadata):
    return {table.name for table in model_metadata.sorted_tables}


def _modeled_destination_tables(model_metadata, destination_metadata):
    """Return destination tables that are owned by the current ORM metadata."""
    modeled_names = _modeled_table_names(model_metadata)
    destination_by_name = {
        table.name: table for table in destination_metadata.sorted_tables
    }
    return [
        destination_by_name[model_table.name]
        for model_table in model_metadata.sorted_tables
        if model_table.name in destination_by_name and model_table.name in modeled_names
    ]


def _table_label(table):
    return f"{table.schema}.{table.name}" if table.schema else table.name


def _reflected_foreign_keys(reflected_metadata):
    relationships = []
    tables = sorted(reflected_metadata.tables.values(), key=_table_label)
    for child in tables:
        constraints = sorted(
            child.foreign_key_constraints,
            key=lambda item: (
                item.name or "",
                tuple(element.parent.name for element in item.elements),
            ),
        )
        for constraint in constraints:
            elements = list(constraint.elements)
            if not elements:
                continue
            try:
                parent = elements[0].column.table
                if any(element.column.table is not parent for element in elements[1:]):
                    raise RuntimeError("composite foreign key references multiple tables")
            except Exception as exc:
                raise RuntimeError(
                    f"Unable to resolve reflected foreign key on {_table_label(child)}"
                ) from exc
            relationships.append(
                ReflectedForeignKey(
                    child_table=child,
                    parent_table=parent,
                    local_names=tuple(element.parent.name for element in elements),
                    remote_names=tuple(element.column.name for element in elements),
                )
            )
    return tuple(sorted(relationships, key=lambda item: item.label))


def _cross_boundary_foreign_keys(model_metadata, reflected_metadata):
    modeled_keys = {
        (table.schema, table.name) for table in model_metadata.sorted_tables
    }
    findings = []
    for relationship in _reflected_foreign_keys(reflected_metadata):
        child_key = (
            relationship.child_table.schema,
            relationship.child_table.name,
        )
        parent_key = (
            relationship.parent_table.schema,
            relationship.parent_table.name,
        )
        if (child_key in modeled_keys) != (parent_key in modeled_keys):
            findings.append(relationship.label)
    return tuple(findings)


def _assert_no_cross_boundary_foreign_keys(model_metadata, reflected_metadata):
    findings = _cross_boundary_foreign_keys(model_metadata, reflected_metadata)
    if findings:
        raise RuntimeError(
            "MySQL target has foreign keys crossing the ORM-managed import boundary; "
            "extension tables cannot be safely preserved during full replacement: "
            + "; ".join(findings)
        )


def _sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def source_snapshot(source_path):
    """Create a consistent SQLite online-backup snapshot in a temporary folder."""
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise RuntimeError(f"SQLite source database not found: {source}")

    with tempfile.TemporaryDirectory(prefix="medical-room-mysql-migration-") as temp_dir:
        snapshot_path = Path(temp_dir) / "source-snapshot.db"
        source_uri = source.as_uri() + "?mode=ro"
        try:
            with closing(sqlite3.connect(source_uri, uri=True)) as source_conn:
                with closing(sqlite3.connect(snapshot_path)) as snapshot_conn:
                    source_conn.backup(snapshot_conn)
        except sqlite3.Error as exc:
            raise RuntimeError(f"Unable to create SQLite source snapshot: {exc}") from exc

        with closing(sqlite3.connect(snapshot_path)) as snapshot_conn:
            check_rows = [row[0] for row in snapshot_conn.execute("PRAGMA quick_check")]
        if check_rows != ["ok"]:
            raise RuntimeError(
                "SQLite source snapshot failed PRAGMA quick_check: "
                + ", ".join(str(value) for value in check_rows)
            )

        yield SourceSnapshot(snapshot_path, _sha256_file(snapshot_path))


def _reflect_required_tables(connection, model_metadata, label):
    reflected = MetaData()
    reflected.reflect(bind=connection)
    required_names = _modeled_table_names(model_metadata)
    missing = sorted(required_names - set(reflected.tables))
    if missing:
        raise RuntimeError(
            f"{label} is missing required modeled tables: {', '.join(missing)}"
        )
    return reflected


def _validate_copy_columns(model_metadata, source_metadata, target_metadata):
    for model_table in model_metadata.sorted_tables:
        name = model_table.name
        model_columns = set(model_table.c.keys())
        source_columns = set(source_metadata.tables[name].c.keys())
        target_columns = set(target_metadata.tables[name].c.keys())

        missing_source = sorted(model_columns - source_columns)
        if missing_source:
            raise RuntimeError(
                f"Source table {name!r} is missing current model columns: "
                + ", ".join(missing_source)
            )
        missing_target = sorted(model_columns - target_columns)
        if missing_target:
            raise RuntimeError(
                f"Target table {name!r} is missing current model columns: "
                + ", ".join(missing_target)
            )

        source_only = sorted(source_columns - target_columns)
        if source_only:
            raise RuntimeError(
                f"Target table {name!r} cannot preserve source columns: "
                + ", ".join(source_only)
            )
        target_only = sorted(target_columns - source_columns)
        if target_only:
            raise RuntimeError(
                f"Source table {name!r} cannot populate target columns without data loss: "
                + ", ".join(target_only)
            )


def _assert_source_string_lengths_fit(
    connection, source_metadata, target_metadata, table_names
):
    exceeded = []
    for table_name in table_names:
        source_table = source_metadata.tables[table_name]
        target_table = target_metadata.tables[table_name]
        for target_column in target_table.columns:
            limit = getattr(target_column.type, "length", None)
            if not isinstance(target_column.type, String) or not limit:
                continue
            source_column = source_table.c[target_column.name]
            max_length = connection.execute(
                select(func.max(func.length(source_column)))
            ).scalar_one()
            if max_length is not None and int(max_length) > int(limit):
                exceeded.append(
                    f"{table_name}.{target_column.name}: "
                    f"max {int(max_length)}, target {int(limit)}"
                )
    if exceeded:
        raise RuntimeError(
            "SQLite source string values exceed MySQL target column lengths: "
            + "; ".join(sorted(exceeded))
        )


def _primary_key_digest(connection, table):
    primary_key_columns = list(table.primary_key.columns)
    if not primary_key_columns:
        raise RuntimeError(f"Table {table.name!r} has no primary key for reconciliation")

    digest = hashlib.sha256()
    statement = select(*primary_key_columns).order_by(*primary_key_columns)
    for row in connection.execute(statement):
        serialized = json.dumps(
            list(row),
            ensure_ascii=True,
            separators=(",", ":"),
            default=str,
        )
        digest.update(serialized.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _table_stats(connection, metadata, table_names):
    stats = {}
    for name in table_names:
        table = metadata.tables[name]
        row_count = connection.execute(
            select(func.count()).select_from(table)
        ).scalar_one()
        stats[name] = TableStats(
            row_count=int(row_count),
            primary_key_digest=_primary_key_digest(connection, table),
        )
    return stats


def _record_batches(connection, source_table, target_columns, batch_size):
    primary_key_columns = list(source_table.primary_key.columns)
    statement = source_table.select()
    if primary_key_columns:
        statement = statement.order_by(*primary_key_columns)
    rows = connection.execution_options(stream_results=True).execute(
        statement
    ).mappings()
    while True:
        batch = rows.fetchmany(batch_size)
        if not batch:
            return
        yield [
            {
                key: value
                for key, value in dict(row).items()
                if key in target_columns
            }
            for row in batch
        ]


def _foreign_key_orphans(connection, model_metadata, reflected_metadata):
    findings = {}
    for model_table in model_metadata.sorted_tables:
        child = reflected_metadata.tables[model_table.name]
        constraints = sorted(
            model_table.foreign_key_constraints,
            key=lambda item: item.name or "",
        )
        for constraint in constraints:
            elements = list(constraint.elements)
            parent_name = elements[0].column.table.name
            parent = reflected_metadata.tables[parent_name]
            local_names = [element.parent.name for element in elements]
            remote_names = [element.column.name for element in elements]
            join_condition = and_(
                *(
                    child.c[local] == parent.c[remote]
                    for local, remote in zip(local_names, remote_names)
                )
            )
            all_local_values_present = and_(
                *(child.c[local].is_not(None) for local in local_names)
            )
            orphan_count = connection.execute(
                select(func.count())
                .select_from(child.outerjoin(parent, join_condition))
                .where(all_local_values_present, parent.c[remote_names[0]].is_(None))
            ).scalar_one()
            if orphan_count:
                key = (
                    f"{model_table.name}.{'/'.join(local_names)} -> "
                    f"{parent_name}.{'/'.join(remote_names)}"
                )
                findings[key] = int(orphan_count)
    return findings


def _actual_foreign_key_orphans(connection, reflected_metadata):
    findings = {}
    for relationship in _reflected_foreign_keys(reflected_metadata):
        child = relationship.child_table
        parent = relationship.parent_table
        join_condition = and_(
            *(
                child.c[local] == parent.c[remote]
                for local, remote in zip(
                    relationship.local_names,
                    relationship.remote_names,
                )
            )
        )
        all_local_values_present = and_(
            *(child.c[local].is_not(None) for local in relationship.local_names)
        )
        orphan_count = connection.execute(
            select(func.count())
            .select_from(child.outerjoin(parent, join_condition))
            .where(
                all_local_values_present,
                parent.c[relationship.remote_names[0]].is_(None),
            )
        ).scalar_one()
        if orphan_count:
            findings[relationship.label] = int(orphan_count)
    return findings


def _assert_no_foreign_key_orphans(connection, model_metadata, reflected_metadata, label):
    findings = _foreign_key_orphans(connection, model_metadata, reflected_metadata)
    if findings:
        details = "; ".join(
            f"{relationship}: {count}" for relationship, count in sorted(findings.items())
        )
        raise RuntimeError(f"{label} foreign-key orphan preflight failed: {details}")


def _assert_no_actual_foreign_key_orphans(connection, reflected_metadata, label):
    findings = _actual_foreign_key_orphans(connection, reflected_metadata)
    if findings:
        details = "; ".join(
            f"{relationship}: {count}" for relationship, count in sorted(findings.items())
        )
        raise RuntimeError(
            f"{label} actual foreign-key orphan preflight failed: {details}"
        )


def _assert_reconciled(expected_stats, actual_stats):
    differences = []
    for name in sorted(expected_stats):
        expected = expected_stats[name]
        actual = actual_stats.get(name)
        if actual is None:
            differences.append(f"{name}: missing from destination")
            continue
        if expected.row_count != actual.row_count:
            differences.append(
                f"{name}: row count {actual.row_count}, expected {expected.row_count}"
            )
        if expected.primary_key_digest != actual.primary_key_digest:
            differences.append(f"{name}: primary-key digest mismatch")
    if differences:
        raise RuntimeError("Post-copy reconciliation failed: " + "; ".join(differences))


def _snapshot_engine(snapshot_path):
    return create_engine(URL.create("sqlite+pysqlite", database=str(snapshot_path)))


def build_plan(
    snapshot_path,
    target_engine,
    model_metadata,
    *,
    expected_alembic_head=None,
):
    expected_alembic_head = (
        expected_alembic_head or discover_expected_alembic_head()
    )
    source_engine = _snapshot_engine(snapshot_path)
    try:
        with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
            source_metadata = _reflect_required_tables(
                source_conn, model_metadata, "SQLite source snapshot"
            )
            _assert_target_alembic_head(target_conn, expected_alembic_head)
            target_metadata = _reflect_required_tables(
                target_conn, model_metadata, "MySQL target"
            )
            _assert_no_cross_boundary_foreign_keys(
                model_metadata, target_metadata
            )
            _assert_mysql_copy_preconditions(
                target_conn,
                (table.name for table in model_metadata.sorted_tables),
            )
            _validate_copy_columns(model_metadata, source_metadata, target_metadata)
            _assert_source_string_lengths_fit(
                source_conn,
                source_metadata,
                target_metadata,
                (table.name for table in model_metadata.sorted_tables),
            )
            _assert_no_actual_foreign_key_orphans(
                target_conn, target_metadata, "MySQL target"
            )
            _assert_no_foreign_key_orphans(
                source_conn,
                model_metadata,
                source_metadata,
                "SQLite source snapshot",
            )
            table_names = tuple(table.name for table in model_metadata.sorted_tables)
            return MigrationPlan(
                table_names=table_names,
                source_stats=_table_stats(source_conn, source_metadata, table_names),
                target_stats=_table_stats(target_conn, target_metadata, table_names),
                expected_alembic_head=expected_alembic_head,
            )
    finally:
        source_engine.dispose()


def _copy_snapshot(
    snapshot_path,
    target_engine,
    model_metadata,
    plan,
    *,
    batch_size=DEFAULT_BATCH_SIZE,
):
    source_engine = _snapshot_engine(snapshot_path)
    try:
        with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
            source_metadata = _reflect_required_tables(
                source_conn, model_metadata, "SQLite source snapshot"
            )
            _assert_target_alembic_head(
                target_conn, plan.expected_alembic_head
            )
            target_metadata = _reflect_required_tables(
                target_conn, model_metadata, "MySQL target"
            )
            _assert_no_cross_boundary_foreign_keys(
                model_metadata, target_metadata
            )
            _assert_mysql_copy_preconditions(
                target_conn,
                (table.name for table in model_metadata.sorted_tables),
            )
            _validate_copy_columns(model_metadata, source_metadata, target_metadata)
            _assert_no_actual_foreign_key_orphans(
                target_conn, target_metadata, "MySQL target"
            )
            current_target_stats = _table_stats(
                target_conn, target_metadata, plan.table_names
            )
            _assert_reconciled(plan.target_stats, current_target_stats)
            # Reflection and pre-clear checks start SQLAlchemy's implicit read
            # transaction. End it before opening the destructive transaction.
            target_conn.commit()

            transaction = target_conn.begin()
            try:
                target_conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
                target_tables = _modeled_destination_tables(
                    model_metadata, target_metadata
                )
                for table in reversed(target_tables):
                    target_conn.execute(table.delete())

                for model_table in model_metadata.sorted_tables:
                    name = model_table.name
                    source_table = source_metadata.tables[name]
                    target_table = target_metadata.tables[name]
                    target_columns = set(target_table.c.keys())
                    for records in _record_batches(
                        source_conn,
                        source_table,
                        target_columns,
                        batch_size,
                    ):
                        target_conn.execute(target_table.insert(), records)

                actual_stats = _table_stats(
                    target_conn, target_metadata, plan.table_names
                )
                _assert_reconciled(plan.source_stats, actual_stats)
                _assert_no_foreign_key_orphans(
                    target_conn, model_metadata, target_metadata, "MySQL target"
                )
                _assert_no_actual_foreign_key_orphans(
                    target_conn, target_metadata, "MySQL target"
                )
                target_conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")
                transaction.commit()
            except Exception:
                if transaction.is_active:
                    transaction.rollback()
                try:
                    target_conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")
                    target_conn.commit()
                except Exception:
                    target_conn.invalidate()
                raise
    finally:
        source_engine.dispose()


def _validate_execution_flags(execute, yes, expected_source_sha256=None):
    if yes and not execute:
        raise RuntimeError("--yes is only valid together with --execute")
    if execute and not yes:
        raise RuntimeError("Destructive migration requires both --execute and --yes")
    if execute and not expected_source_sha256:
        raise RuntimeError(
            "--execute requires --expected-source-sha256 from a completed dry-run"
        )
    if not execute and expected_source_sha256:
        raise RuntimeError(
            "--expected-source-sha256 is only valid together with --execute"
        )
    if expected_source_sha256 and not re.fullmatch(
        r"[0-9a-fA-F]{64}", expected_source_sha256
    ):
        raise RuntimeError("--expected-source-sha256 must contain 64 hex characters")


def _assert_expected_source_sha256(actual_sha256, expected_sha256):
    if actual_sha256.lower() != expected_sha256.lower():
        raise RuntimeError(
            "SQLite source snapshot changed after dry-run "
            f"(actual={actual_sha256}, expected={expected_sha256.lower()})"
        )


def _print_plan(plan):
    print(f"Target Alembic head: {plan.expected_alembic_head}")
    print("\nTable preflight (source rows -> target rows):")
    for name in plan.table_names:
        print(
            f"  {name}: {plan.source_stats[name].row_count}"
            f" -> {plan.target_stats[name].row_count}"
        )


def run_migration(
    source_path,
    target_url,
    *,
    execute=False,
    yes=False,
    batch_size=DEFAULT_BATCH_SIZE,
    expected_source_sha256=None,
):
    _validate_execution_flags(execute, yes, expected_source_sha256)
    if not 1 <= batch_size <= 100000:
        raise RuntimeError("batch_size must be between 1 and 100000")
    target_url = _normalize_mysql_url(target_url, "DATABASE_URL")
    print(f"Target: {safe_target_summary(target_url)}")
    app = create_app(_migration_config(target_url), initialize_database=False)

    with source_snapshot(source_path) as snapshot:
        print(f"Source: {Path(source_path).expanduser().resolve()}")
        print(f"Source snapshot SHA-256: {snapshot.sha256}")
        if execute:
            _assert_expected_source_sha256(
                snapshot.sha256, expected_source_sha256
            )
        with app.app_context():
            plan = build_plan(snapshot.path, db.engine, db.metadata)
            _print_plan(plan)
            if not execute:
                print(
                    "\nDry-run preflight passed. No target data or schema was changed."
                )
                print(
                    "Stop all application writers, then rerun with --execute --yes "
                    f"--expected-source-sha256={snapshot.sha256}"
                )
                return plan

            print(
                "\nConfirmed destructive copy: all ORM-managed target tables will be replaced."
            )
            _copy_snapshot(
                snapshot.path,
                db.engine,
                db.metadata,
                plan,
                batch_size=batch_size,
            )
            print("Migration completed; row counts and primary keys reconcile.")
            return plan


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=os.environ.get("SQLITE_DB_PATH") or str(DEFAULT_SQLITE_PATH),
        help="SQLite source path (default: SQLITE_DB_PATH or data/app.db)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="perform the destructive target replacement after preflight",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm that ORM-managed target tables may be cleared",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"rows per insert batch (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--expected-source-sha256",
        help="exact Source snapshot SHA-256 printed by the preceding dry-run",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        _validate_execution_flags(
            args.execute, args.yes, args.expected_source_sha256
        )
        target_url = resolve_target_url()
        run_migration(
            args.source,
            target_url,
            execute=args.execute,
            yes=args.yes,
            batch_size=args.batch_size,
            expected_source_sha256=args.expected_source_sha256,
        )
    except RuntimeError as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
