"""Validate the Alembic chain against isolated MySQL databases.

The administrator credential is read only through a local mysql_config_editor
login path. A random disposable application user is created through mysql's
stdin, so no password is placed in a command line, environment variable, or
repository file. The final cleanup removes only resources whose account
ownership attributes still match this run.

Example (after configuring the login path):

    python scripts/validate_mysql_alembic.py --login-path=codex-medroom --probe
    python scripts/validate_mysql_alembic.py --login-path=codex-medroom \
        --expected-server-uuid=<uuid-from-probe>
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from flask_migrate import upgrade
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text
from sqlalchemy import event, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import UniqueConstraint

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "backend" / "migrations"
CURRENT_HEAD = "b6e1d8f3a2c4"
HISTORICAL_SPLIT_REVISION = "bbf28ffdb4c0"
IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
LOGIN_PATH_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
SERVER_UUID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
LOCAL_MYSQL_HOST = "127.0.0.1"
HISTORY_EXTRA_COLUMNS = {
    "drug": (
        "monthly_sort_order",
        "is_herb",
        "herb_code",
        "herb_category",
        "herb_variety",
        "herb_spec",
        "alias_name",
        "pinyin_code",
        "processing_type",
        "safety_stock",
        "max_stock",
        "daily_loss_rate",
        "shelf_life_days",
        "storage_condition",
    ),
    "visit": ("tcm_enabled", "tcm_syndrome", "tcm_diagnosis_desc"),
    "prescription_item": (
        "prescription_type",
        "herb_dosage",
        "special_preparation",
        "herb_sort_order",
        "template_id",
    ),
}
EXTRA_COLUMN_SPECS = {
    ("drug", "monthly_sort_order"): (Integer(), True, None),
    ("drug", "is_herb"): (Boolean(), True, "0"),
    ("drug", "herb_code"): (String(12), True, None),
    ("drug", "herb_category"): (String(3), True, None),
    ("drug", "herb_variety"): (String(4), True, None),
    ("drug", "herb_spec"): (String(2), True, None),
    ("drug", "alias_name"): (String(128), True, None),
    ("drug", "pinyin_code"): (String(50), True, None),
    ("drug", "processing_type"): (String(20), True, None),
    ("drug", "safety_stock"): (Integer(), True, "0"),
    ("drug", "max_stock"): (Integer(), True, "0"),
    ("drug", "daily_loss_rate"): (Float(), True, "0.0"),
    ("drug", "shelf_life_days"): (Integer(), True, None),
    ("drug", "storage_condition"): (String(50), True, None),
    ("visit", "tcm_enabled"): (Boolean(), True, "0"),
    ("visit", "tcm_syndrome"): (String(100), True, None),
    ("visit", "tcm_diagnosis_desc"): (Text(), True, None),
    ("prescription_item", "prescription_type"): (
        String(10),
        True,
        "western",
    ),
    ("prescription_item", "herb_dosage"): (Float(), True, None),
    ("prescription_item", "special_preparation"): (
        String(50),
        True,
        None,
    ),
    ("prescription_item", "herb_sort_order"): (Integer(), True, None),
    ("prescription_item", "template_id"): (Integer(), True, None),
}
HISTORY_MODEL_DEFAULTS = {
    ("drug", "type"): "1",
    ("drug", "purchase_price"): "0.0",
    ("drug", "has_scattered"): "0",
    ("patient", "is_temporary"): "0",
    ("patient", "patient_type"): "student",
    ("payment", "is_employee_discount"): "0",
    ("prescription_item", "is_scattered"): "0",
    ("prescription_item", "purchase_cost"): "0.0",
    ("prescription_item", "is_intravenous"): "0",
}
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import _sync_model_schema, create_migration_app, db  # noqa: E402


def identifier(value: str) -> str:
    if not IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Unsafe generated identifier: {value!r}")
    return value


def mysql_identifier(value: str) -> str:
    return f"`{identifier(value)}`"


class MysqlAdmin:
    def __init__(self, login_path: str, host: str, port: int, mysql_bin: str):
        if not LOGIN_PATH_RE.fullmatch(login_path):
            raise ValueError(f"Unsafe login-path name: {login_path!r}")
        self.login_path = login_path
        self.host = host
        self.port = int(port)
        self.mysql_bin = mysql_bin

    def run(self, sql: str, label: str) -> str:
        args = [
            self.mysql_bin,
            "--no-defaults",
            f"--login-path={self.login_path}",
            "--protocol=TCP",
            f"--host={self.host}",
            f"--port={self.port}",
            "--connect-timeout=5",
            "--disable-reconnect",
            "--skip-force",
            "--default-character-set=utf8mb4",
            "--batch",
            "--skip-column-names",
            "--raw",
        ]
        child_env = os.environ.copy()
        for key in tuple(child_env):
            if key.upper().startswith("MYSQL_") or key.upper() == "TEST_LOGIN_FILE":
                child_env.pop(key, None)
        result = subprocess.run(
            args,
            input=sql,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            check=False,
            env=child_env,
        )
        if result.returncode:
            # Do not echo stderr: a SQL syntax error can include generated
            # literals, and the administrator credential must never leak.
            raise RuntimeError(
                f"mysql admin command {label!r} failed with exit "
                f"{result.returncode}"
            )
        return result.stdout

    def run_guarded(
        self, sql: str, label: str, *, expected_server_uuid: str
    ) -> str:
        if not SERVER_UUID_RE.fullmatch(expected_server_uuid):
            raise ValueError("Unsafe expected MySQL server UUID")
        guard = (
            "SET @medmig_guard_sql = IF("
            f"@@server_uuid = '{expected_server_uuid}', "
            "'SELECT NULL WHERE FALSE', "
            "'SELECT * FROM information_schema.medmig_wrong_server_guard');\n"
            "PREPARE medmig_guard_stmt FROM @medmig_guard_sql;\n"
            "EXECUTE medmig_guard_stmt;\n"
            "DEALLOCATE PREPARE medmig_guard_stmt;\n"
        )
        return self.run(guard + sql, label)

    def preflight(self, *, cleanup=False) -> dict[str, str]:
        output = self.run(
            "SELECT @@server_uuid, @@hostname, @@port, VERSION(), @@version_comment, "
            "@@default_storage_engine, @@character_set_server, "
            "@@collation_server, @@sql_mode, @@read_only, "
            "@@super_read_only, @@log_bin, @@general_log;",
            "preflight",
        ).strip()
        if not output:
            raise RuntimeError("MySQL preflight returned no server information")
        fields = output.split("\t")
        if len(fields) != 13:
            raise RuntimeError("MySQL preflight returned an unexpected result")
        names = (
            "server_uuid",
            "hostname",
            "port",
            "version",
            "version_comment",
            "engine",
            "charset",
            "collation",
            "sql_mode",
            "read_only",
            "super_read_only",
            "log_bin",
            "general_log",
        )
        details = dict(zip(names, fields))
        engine = details["engine"].lower()
        charset = details["charset"].lower()
        collation = details["collation"].lower()
        version = details["version"]
        version_comment = details["version_comment"]
        version_match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
        if (
            "mariadb" in (version + " " + version_comment).lower()
            or version_match is None
            or int(version_match.group(1)) != 8
            or tuple(map(int, version_match.groups())) < (8, 0, 21)
        ):
            raise RuntimeError(
                "This validator requires a MySQL 8.x server at 8.0.21 or newer; "
                f"got {version} ({version_comment})"
            )
        if not cleanup and engine != "innodb":
            raise RuntimeError(f"MySQL default storage engine is {engine!r}, not InnoDB")
        if not cleanup and charset != "utf8mb4":
            raise RuntimeError(
                "MySQL server default character set must be utf8mb4; "
                f"got {charset}/{collation}"
            )
        if details["read_only"] != "0" or details["super_read_only"] != "0":
            raise RuntimeError("MySQL server is read-only")
        if not cleanup and details["general_log"] != "0":
            raise RuntimeError(
                "MySQL general_log must be disabled before creating a temporary user"
            )
        if not cleanup and not {
            "STRICT_TRANS_TABLES",
            "STRICT_ALL_TABLES",
        } & set(details["sql_mode"].upper().split(",")):
            raise RuntimeError("MySQL strict SQL mode is required")
        return details

    def assert_target(
        self,
        label: str,
        *,
        expected_server_uuid: str,
        allow_binlog: bool,
        cleanup: bool = False,
    ) -> dict[str, str]:
        details = self.preflight(cleanup=cleanup)
        if details["server_uuid"] != expected_server_uuid:
            raise RuntimeError(
                f"Refusing {label}: MySQL server UUID changed after the probe"
            )
        if not cleanup and details["log_bin"] != "0" and not allow_binlog:
            raise RuntimeError(
                f"Refusing {label}: MySQL binary logging became enabled"
            )
        return details

    def run_mutation(
        self,
        sql: str,
        label: str,
        *,
        expected_server_uuid: str,
        allow_binlog: bool,
        cleanup: bool = False,
    ) -> str:
        self.assert_target(
            label,
            expected_server_uuid=expected_server_uuid,
            allow_binlog=allow_binlog,
            cleanup=cleanup,
        )
        return self.run_guarded(
            sql, label, expected_server_uuid=expected_server_uuid
        )


class TemporaryResources:
    def __init__(
        self,
        admin: MysqlAdmin,
        *,
        expected_server_uuid: str,
        allow_binlog: bool,
        scenarios: tuple[str, ...],
    ):
        suffix = secrets.token_hex(16)
        self.run_id = suffix
        self.admin = admin
        self.expected_server_uuid = expected_server_uuid
        self.allow_binlog = allow_binlog
        self.owner_token = secrets.token_hex(32)
        self.user = identifier(f"medmig_{suffix[:24]}")
        self.password = "Aa1!" + secrets.token_urlsafe(32)
        self.scenario_databases = {
            scenario: identifier(f"medroom_mig_{suffix}_{scenario}")
            for scenario in scenarios
        }
        self.databases = list(self.scenario_databases.values())
        self.attempted_databases: list[str] = []
        self.created_databases: list[str] = []
        self.account_hosts = ("localhost", "127.0.0.1")
        self.attempted_accounts: list[str] = []
        self.created_accounts: list[str] = []

    def _mutate(self, sql: str, label: str, *, cleanup=False) -> str:
        return self.admin.run_mutation(
            sql,
            label,
            expected_server_uuid=self.expected_server_uuid,
            allow_binlog=self.allow_binlog,
            cleanup=cleanup,
        )

    def _read(self, sql: str, label: str, *, cleanup=False) -> str:
        self.admin.assert_target(
            label,
            expected_server_uuid=self.expected_server_uuid,
            allow_binlog=self.allow_binlog,
            cleanup=cleanup,
        )
        return self.admin.run_guarded(
            sql,
            label,
            expected_server_uuid=self.expected_server_uuid,
        )

    def _account_ownership_predicate(self) -> str:
        database_path = "JSON_EXTRACT(ATTRIBUTE, '$.medmig_databases')"
        checks = [
            "JSON_TYPE(JSON_EXTRACT(ATTRIBUTE, '$.medmig_owner_token')) = 'STRING'",
            "JSON_TYPE(JSON_EXTRACT(ATTRIBUTE, '$.medmig_run_id')) = 'STRING'",
            "JSON_TYPE(JSON_EXTRACT(ATTRIBUTE, '$.medmig_server_uuid')) = 'STRING'",
            f"JSON_TYPE({database_path}) = 'ARRAY'",
            "JSON_UNQUOTE(JSON_EXTRACT(ATTRIBUTE, '$.medmig_owner_token')) = "
            f"'{self.owner_token}'",
            "JSON_UNQUOTE(JSON_EXTRACT(ATTRIBUTE, '$.medmig_run_id')) = "
            f"'{self.run_id}'",
            "JSON_UNQUOTE(JSON_EXTRACT(ATTRIBUTE, '$.medmig_server_uuid')) = "
            f"'{self.expected_server_uuid}'",
            f"JSON_LENGTH({database_path}) = {len(self.databases)}",
        ]
        checks.extend(
            f"JSON_CONTAINS({database_path}, JSON_QUOTE('{database}'))"
            for database in self.databases
        )
        return " AND ".join(checks)

    def create(self) -> None:
        user_literals = {
            host: f"'{self.user}'@'{host}'" for host in self.account_hosts
        }
        account_attribute = json.dumps(
            {
                "medmig_owner_token": self.owner_token,
                "medmig_run_id": self.run_id,
                "medmig_server_uuid": self.expected_server_uuid,
                "medmig_databases": self.databases,
            },
            separators=(",", ":"),
        )
        for host, user_literal in user_literals.items():
            self.attempted_accounts.append(host)
            self._mutate(
                f"CREATE USER {user_literal} IDENTIFIED BY '{self.password}' "
                f"ATTRIBUTE '{account_attribute}';",
                f"create temporary account {host}",
            )
            self.created_accounts.append(host)

        for database in self.databases:
            if self._database_exists(database):
                raise RuntimeError(
                    f"Refusing to replace pre-existing database {database}"
                )
            self.attempted_databases.append(database)
            self._mutate(
                "CREATE DATABASE "
                f"{mysql_identifier(database)} CHARACTER SET utf8mb4 "
                "COLLATE utf8mb4_unicode_ci;",
                f"create database {database}",
            )
            if not self._database_exists(database):
                raise RuntimeError(
                    f"Database {database} was not visible after CREATE DATABASE"
                )
            self.created_databases.append(database)
        statements = []
        for database in self.databases:
            for host in self.created_accounts:
                statements.append(
                    f"GRANT ALL PRIVILEGES ON {mysql_identifier(database)}.* "
                    f"TO {user_literals[host]};"
                )
        self._mutate("\n".join(statements), "grant temporary user")

    def _database_exists(self, database: str, *, cleanup=False) -> bool:
        output = self._read(
            "SELECT COUNT(*) FROM information_schema.schemata "
            f"WHERE schema_name = '{database}';",
            f"check database {database}",
            cleanup=cleanup,
        ).strip()
        return output == "1"

    def _database_is_owned(self, database: str) -> bool:
        if database not in self.databases:
            return False
        hosts = ", ".join(f"'{host}'" for host in self.account_hosts)
        output = self._read(
            "SELECT COUNT(*) FROM information_schema.user_attributes "
            f"WHERE USER = '{self.user}' AND HOST IN ({hosts}) AND "
            + self._account_ownership_predicate()
            + ";",
            f"verify database ownership {database}",
            cleanup=True,
        ).strip()
        try:
            return int(output) >= 1
        except ValueError as exc:
            raise RuntimeError(
                f"Could not verify database ownership for {database}"
            ) from exc

    def _account_state(self, host: str) -> tuple[bool, bool]:
        output = self._read(
            "SELECT COUNT(*), COALESCE(SUM("
            + self._account_ownership_predicate()
            + "), 0) "
            "FROM information_schema.user_attributes "
            f"WHERE USER = '{self.user}' AND HOST = '{host}';",
            f"verify temporary account {host}",
            cleanup=True,
        ).strip()
        fields = output.split("\t")
        if len(fields) != 2:
            raise RuntimeError(f"Could not verify temporary account {host}")
        return fields[0] == "1", fields[1] == "1"

    def cleanup(self) -> None:
        errors = []
        database_cleanup_failed = False
        for database in reversed(self.attempted_databases):
            try:
                if not self._database_exists(database, cleanup=True):
                    continue
                if not self._database_is_owned(database):
                    raise RuntimeError(
                        f"Refusing to drop unowned database {database}"
                    )
                self._mutate(
                    f"DROP DATABASE {mysql_identifier(database)};",
                    f"drop database {database}",
                    cleanup=True,
                )
                if self._database_exists(database, cleanup=True):
                    raise RuntimeError(
                        f"Database {database} still exists after DROP DATABASE"
                    )
            except BaseException as exc:
                try:
                    if not self._database_exists(database, cleanup=True):
                        continue
                except BaseException as verification_exc:
                    errors.append(
                        f"{type(verification_exc).__name__}: "
                        f"could not recheck {database}: {verification_exc}"
                    )
                database_cleanup_failed = True
                errors.append(f"{type(exc).__name__}: {exc}")
        if database_cleanup_failed:
            for host in reversed(self.attempted_accounts):
                try:
                    exists, owned = self._account_state(host)
                    if exists and owned:
                        self._mutate(
                            f"ALTER USER '{self.user}'@'{host}' ACCOUNT LOCK;",
                            f"lock temporary account {host}",
                            cleanup=True,
                        )
                except BaseException as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
            errors.append(
                "Temporary ownership accounts were retained because at least "
                "one database could not be removed"
            )
            raise RuntimeError("; ".join(errors))
        for host in reversed(self.attempted_accounts):
            try:
                exists, owned = self._account_state(host)
                if not exists:
                    continue
                if not owned:
                    if host in self.created_accounts:
                        raise RuntimeError(
                            f"Refusing to drop replaced temporary account {host}"
                        )
                    continue
                self._mutate(
                    f"DROP USER '{self.user}'@'{host}';",
                    f"drop temporary account {host}",
                    cleanup=True,
                )
            except BaseException as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
        if errors:
            raise RuntimeError("; ".join(errors))

    def url(self, database: str) -> URL:
        return URL.create(
            "mysql+pymysql",
            username=self.user,
            password=self.password,
            host=self.admin.host,
            port=self.admin.port,
            database=database,
            query={"charset": "utf8mb4"},
        )


def migration_config(database_url: URL):
    return type(
        "MysqlMigrationValidationConfig",
        (),
        {
            "TESTING": True,
            "SECRET_KEY": "mysql-migration-validation",
            "JWT_SECRET_KEY": "mysql-migration-validation-jwt",
            "SQLALCHEMY_DATABASE_URI": database_url,
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "CORS_ORIGINS": [],
            "SCHEDULER_ENABLED": False,
            "STARTUP_DATA_REPAIRS_ENABLED": False,
        },
    )


@contextmanager
def migration_app(resources: TemporaryResources, database: str):
    app = create_migration_app(migration_config(resources.url(database)))
    try:
        with app.app_context():
            yield app
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


def run_upgrade(resources: TemporaryResources, database: str, revision="head"):
    with migration_app(resources, database):
        upgrade(directory=str(MIGRATIONS_DIR), revision=revision)


def run_sql(resources: TemporaryResources, database: str, callback):
    with migration_app(resources, database):
        with db.engine.begin() as connection:
            return callback(connection)


def current_version(connection):
    return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def model_index_semantics(table):
    indexes = {
        (tuple(column.name for column in index.columns), bool(index.unique))
        for index in table.indexes
    }
    indexes.update(
        {
            (tuple(column.name for column in constraint.columns), True)
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
    )
    return indexes


def actual_index_semantics(connection, table_name):
    rows = connection.execute(
        text(
            "SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME, "
            "SUB_PART, INDEX_TYPE, IS_VISIBLE, COLLATION, EXPRESSION "
            "FROM information_schema.statistics WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = :table_name AND INDEX_NAME <> 'PRIMARY' "
            "ORDER BY INDEX_NAME, SEQ_IN_INDEX"
        ),
        {"table_name": table_name},
    ).all()
    grouped = {}
    for row in rows:
        grouped.setdefault(row[0], []).append(row)
    semantics = set()
    special_indexes = []
    for index_name, index_rows in grouped.items():
        if any(
            row[4] is not None
            or str(row[5]).upper() != "BTREE"
            or str(row[6]).upper() != "YES"
            or str(row[7]).upper() not in {"A", "NONE"}
            or row[8] is not None
            or row[3] is None
            for row in index_rows
        ):
            special_indexes.append(index_name)
            continue
        semantics.add(
            (
                tuple(row[3] for row in index_rows),
                not bool(index_rows[0][1]),
            )
        )
    return semantics, special_indexes


def actual_fk_semantics(schema_inspector, table_name):
    default_schema = schema_inspector.default_schema_name
    result = set()
    for foreign_key in schema_inspector.get_foreign_keys(table_name):
        schema = foreign_key.get("referred_schema")
        if schema == default_schema:
            schema = None
        options = foreign_key.get("options") or {}
        for key, value in options.items():
            if not isinstance(value, str):
                continue
            normalized = value.upper()
            if key in {"ondelete", "onupdate"} and normalized in {"RESTRICT", "NO ACTION"}:
                continue
            raise AssertionError(
                f"{table_name} has non-default foreign-key action: {key}={value!r}"
            )
        result.add(
            (
                tuple(foreign_key.get("constrained_columns") or ()),
                schema,
                foreign_key.get("referred_table"),
                tuple(foreign_key.get("referred_columns") or ()),
            )
        )
    return result


def model_fk_semantics(table):
    return {
        (
            tuple(column.name for column in constraint.columns),
            None,
            constraint.referred_table.name,
            tuple(element.column.name for element in constraint.elements),
        )
        for constraint in table.foreign_key_constraints
    }


def type_matches(actual, expected, *, allow_wider_string=False):
    actual_name = getattr(actual, "__visit_name__", "").lower()
    if isinstance(expected, Boolean):
        display_width = getattr(actual, "display_width", None)
        return actual_name in {"boolean", "tinyint"} and display_width in (None, 1)
    if isinstance(expected, Text):
        return actual_name in {"text", "mediumtext", "longtext"}
    if isinstance(expected, String):
        actual_length = getattr(actual, "length", None)
        if actual_name != "varchar" or actual_length is None:
            return False
        if allow_wider_string:
            return actual_length >= expected.length
        return actual_length == expected.length
    if isinstance(expected, Integer):
        return actual_name in {"integer", "int"} and not getattr(actual, "unsigned", False)
    if isinstance(expected, Float):
        return actual_name == "float"
    if isinstance(expected, DateTime):
        return actual_name == "datetime"
    if isinstance(expected, Date):
        return actual_name == "date"
    return actual_name == getattr(expected, "__visit_name__", "").lower()


def normalized_default(value):
    if value is None:
        return None
    normalized = str(value).strip()
    while normalized.startswith("(") and normalized.endswith(")"):
        normalized = normalized[1:-1].strip()
    return normalized.strip("'\"")


def defaults_equal(actual, expected):
    actual = normalized_default(actual)
    expected = normalized_default(expected)
    if actual == expected:
        return True
    if actual is None or expected is None:
        return False
    try:
        return Decimal(actual) == Decimal(expected)
    except InvalidOperation:
        return False


def validate_extra_column(table_name, column_name, column):
    spec = EXTRA_COLUMN_SPECS.get((table_name, column_name))
    if spec is None:
        raise AssertionError(
            f"No validation shape is defined for {table_name}.{column_name}"
        )
    expected_type, expected_nullable, expected_default = spec
    if not type_matches(column["type"], expected_type):
        raise AssertionError(
            f"{table_name}.{column_name} has unexpected type {column['type']!r}"
        )
    if column["nullable"] != expected_nullable or not defaults_equal(
        column.get("default"), expected_default
    ):
        raise AssertionError(
            f"{table_name}.{column_name} nullable/default mismatch: "
            f"{column['nullable']}/{column.get('default')!r}"
        )


def schema_fingerprint(connection):
    tables = connection.execute(
        text(
            "SELECT TABLE_NAME, ENGINE, TABLE_COLLATION "
            "FROM information_schema.tables WHERE TABLE_SCHEMA = DATABASE() "
            "ORDER BY TABLE_NAME"
        )
    ).all()
    rows = connection.execute(
        text(
            "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, "
            "COLUMN_DEFAULT, COLUMN_KEY, EXTRA, CHARACTER_SET_NAME, "
            "COLLATION_NAME, COLUMN_COMMENT "
            "FROM information_schema.columns WHERE TABLE_SCHEMA = DATABASE() "
            "ORDER BY TABLE_NAME, ORDINAL_POSITION"
        )
    ).all()
    indexes = connection.execute(
        text(
            "SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, "
            "COLUMN_NAME, SUB_PART, INDEX_TYPE, IS_VISIBLE, COLLATION, EXPRESSION "
            "FROM information_schema.statistics WHERE TABLE_SCHEMA = DATABASE() "
            "ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX"
        )
    ).all()
    foreign_keys = connection.execute(
        text(
            "SELECT k.TABLE_NAME, k.CONSTRAINT_NAME, k.COLUMN_NAME, "
            "k.REFERENCED_TABLE_SCHEMA, k.REFERENCED_TABLE_NAME, "
            "k.REFERENCED_COLUMN_NAME, k.ORDINAL_POSITION, "
            "r.UPDATE_RULE, r.DELETE_RULE "
            "FROM information_schema.key_column_usage AS k "
            "JOIN information_schema.referential_constraints AS r "
            "ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA "
            "AND r.TABLE_NAME = k.TABLE_NAME "
            "AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME "
            "WHERE k.TABLE_SCHEMA = DATABASE() AND k.REFERENCED_TABLE_NAME IS NOT NULL "
            "ORDER BY k.TABLE_NAME, k.CONSTRAINT_NAME, k.ORDINAL_POSITION"
        )
    ).all()
    return hashlib.sha256(
        repr((tables, rows, indexes, foreign_keys)).encode("utf-8")
    ).hexdigest()


def validate_schema(
    resources: TemporaryResources,
    database: str,
    *,
    extra_tables=(),
    extra_columns=None,
    wider_string_columns=(),
    allowed_model_defaults=None,
):
    extra_columns = extra_columns or {}
    wider_string_columns = set(wider_string_columns)
    allowed_model_defaults = allowed_model_defaults or {}

    def validate(connection):
        schema_inspector = inspect(connection)
        model_tables = set(db.metadata.tables)
        unknown_extra_tables = set(extra_columns) - model_tables
        if unknown_extra_tables:
            raise AssertionError(
                f"Extra columns reference unknown model tables: "
                f"{sorted(unknown_extra_tables)}"
            )
        for table_name, column_names in extra_columns.items():
            overlap = set(column_names) & set(
                db.metadata.tables[table_name].columns.keys()
            )
            if overlap:
                raise AssertionError(
                    f"Extra columns duplicate model columns on {table_name}: "
                    f"{sorted(overlap)}"
                )
        invalid_default_columns = {
            (table_name, column_name)
            for table_name, column_name in allowed_model_defaults
            if table_name not in db.metadata.tables
            or column_name not in db.metadata.tables[table_name].columns
        }
        if invalid_default_columns:
            raise AssertionError(
                "Allowed defaults reference unknown model columns: "
                f"{sorted(invalid_default_columns)}"
            )
        actual_tables = set(schema_inspector.get_table_names())
        expected_tables = model_tables | {"alembic_version"} | set(extra_tables)
        if actual_tables != expected_tables:
            raise AssertionError(
                f"Unexpected MySQL tables: {sorted(actual_tables ^ expected_tables)}"
            )
        if current_version(connection) != CURRENT_HEAD:
            raise AssertionError("alembic_version is not at the current head")

        table_metadata = connection.execute(
            text(
                "SELECT TABLE_NAME, ENGINE, TABLE_COLLATION "
                "FROM information_schema.tables WHERE TABLE_SCHEMA = DATABASE()"
            )
        ).all()
        for table_name, engine, collation in table_metadata:
            if engine.upper() != "INNODB" or collation.lower() != "utf8mb4_unicode_ci":
                raise AssertionError(
                    f"{table_name} has {engine}/{collation}, expected InnoDB/utf8mb4_unicode_ci"
                )

        session_settings = connection.execute(
            text(
                "SELECT @@character_set_connection, @@foreign_key_checks, "
                "@@character_set_database, @@collation_database"
            )
        ).one()
        if session_settings[0].lower() != "utf8mb4" or session_settings[1] != 1:
            raise AssertionError(f"Unexpected MySQL session settings: {session_settings!r}")
        if session_settings[2].lower() != "utf8mb4" or session_settings[3].lower() != "utf8mb4_unicode_ci":
            raise AssertionError(f"Unexpected MySQL database settings: {session_settings!r}")

        for table_name, model_table in db.metadata.tables.items():
            actual_columns = {
                column["name"]: column
                for column in schema_inspector.get_columns(table_name)
            }
            model_column_names = set(model_table.columns.keys())
            required_extra_columns = set(extra_columns.get(table_name, ()))
            expected_column_names = model_column_names | required_extra_columns
            if set(actual_columns) != expected_column_names:
                raise AssertionError(
                    f"{table_name} column mismatch: "
                    f"{sorted(set(actual_columns) ^ expected_column_names)}"
                )
            for model_column in model_table.columns:
                actual = actual_columns[model_column.name]
                if not type_matches(
                    actual["type"],
                    model_column.type,
                    allow_wider_string=(
                        table_name,
                        model_column.name,
                    ) in wider_string_columns,
                ):
                    raise AssertionError(
                        f"{table_name}.{model_column.name} has type {actual['type']!r}, "
                        f"expected {model_column.type!r}"
                    )
                if actual["nullable"] != model_column.nullable:
                    raise AssertionError(
                        f"{table_name}.{model_column.name} nullable mismatch"
                    )
                expected_default = allowed_model_defaults.get(
                    (table_name, model_column.name),
                    (
                        model_column.server_default.arg
                        if model_column.server_default is not None
                        else None
                    ),
                )
                if not defaults_equal(actual.get("default"), expected_default):
                    raise AssertionError(
                        f"{table_name}.{model_column.name} default "
                        f"{actual.get('default')!r} != "
                        f"{normalized_default(expected_default)!r}"
                    )

            for column_name in required_extra_columns:
                validate_extra_column(
                    table_name, column_name, actual_columns[column_name]
                )

            primary_key = schema_inspector.get_pk_constraint(table_name).get(
                "constrained_columns"
            )
            if primary_key != ["id"]:
                raise AssertionError(f"{table_name} has unexpected primary key {primary_key!r}")
            id_row = connection.execute(
                text(
                    "SELECT COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY, EXTRA "
                    "FROM information_schema.columns WHERE TABLE_SCHEMA = DATABASE() "
                    "AND TABLE_NAME = :table_name AND COLUMN_NAME = 'id'"
                ),
                {"table_name": table_name},
            ).one()
            if id_row[1] != "NO" or id_row[2] != "PRI" or "auto_increment" not in id_row[3].lower():
                raise AssertionError(f"{table_name}.id is not a signed auto-increment PK: {id_row!r}")
            if "unsigned" in id_row[0].lower():
                raise AssertionError(f"{table_name}.id must be signed: {id_row[0]}")

            expected_indexes = model_index_semantics(model_table)
            actual_indexes, special_indexes = actual_index_semantics(
                connection, table_name
            )
            if special_indexes:
                raise AssertionError(
                    f"{table_name} has prefix, functional, descending, invisible, "
                    f"or non-BTREE indexes: {sorted(special_indexes)}"
                )
            if not expected_indexes <= actual_indexes:
                raise AssertionError(
                    f"{table_name} is missing index semantics: "
                    f"{sorted(expected_indexes - actual_indexes)}"
                )
            expected_unique = {
                columns for columns, unique in expected_indexes if unique
            }
            actual_unique = {
                columns for columns, unique in actual_indexes if unique
            }
            if actual_unique != expected_unique:
                raise AssertionError(
                    f"{table_name} has unexpected unique semantics: "
                    f"{sorted(actual_unique ^ expected_unique)}"
                )
            expected_fks = model_fk_semantics(model_table)
            actual_fks = actual_fk_semantics(schema_inspector, table_name)
            if expected_fks != actual_fks:
                raise AssertionError(
                    f"{table_name} has unexpected FK semantics: "
                    f"{sorted(expected_fks ^ actual_fks)}"
                )
            allowed_indexes = expected_indexes | {
                (local_columns, False)
                for local_columns, _schema, _table, _columns in expected_fks
            }
            if not actual_indexes <= allowed_indexes:
                raise AssertionError(
                    f"{table_name} has unexpected index semantics: "
                    f"{sorted(actual_indexes - allowed_indexes)}"
                )
            for local_columns, _schema, referred_table, remote_columns in expected_fks:
                local_non_null = " AND ".join(
                    f"child.`{column}` IS NOT NULL" for column in local_columns
                )
                join = " AND ".join(
                    f"child.`{local}` = parent.`{remote}`"
                    for local, remote in zip(local_columns, remote_columns)
                )
                orphan_count = connection.execute(
                    text(
                        f"SELECT COUNT(*) FROM `{table_name}` AS child "
                        f"LEFT JOIN `{referred_table}` AS parent ON {join} "
                        f"WHERE {local_non_null} AND parent.`id` IS NULL"
                    )
                ).scalar_one()
                if orphan_count:
                    raise AssertionError(
                        f"{table_name}.{local_columns} has {orphan_count} orphan rows"
                    )

            character_columns = connection.execute(
                text(
                    "SELECT COLUMN_NAME, CHARACTER_SET_NAME, COLLATION_NAME "
                    "FROM information_schema.columns WHERE TABLE_SCHEMA = DATABASE() "
                    "AND TABLE_NAME = :table_name AND CHARACTER_SET_NAME IS NOT NULL"
                ),
                {"table_name": table_name},
            ).all()
            for column_name, character_set, collation in character_columns:
                if character_set.lower() != "utf8mb4" or collation.lower() != "utf8mb4_unicode_ci":
                    raise AssertionError(
                        f"{table_name}.{column_name} has {character_set}/{collation}, "
                        "expected utf8mb4/utf8mb4_unicode_ci"
                    )

        version_columns = {
            column["name"]: column
            for column in schema_inspector.get_columns("alembic_version")
        }
        version_column = version_columns.get("version_num")
        if (
            version_column is None
            or getattr(version_column["type"], "__visit_name__", "").lower()
            != "varchar"
            or getattr(version_column["type"], "length", None) != 32
        ):
            raise AssertionError("alembic_version.version_num must be VARCHAR(32)")
        if version_column["nullable"]:
            raise AssertionError("alembic_version.version_num must be NOT NULL")
        if version_column.get("default") is not None:
            raise AssertionError("alembic_version.version_num must not have a default")
        if schema_inspector.get_pk_constraint("alembic_version").get(
            "constrained_columns"
        ) != ["version_num"]:
            raise AssertionError("alembic_version.version_num must be the primary key")
        if connection.execute(text("SELECT COUNT(*) FROM alembic_version")).scalar_one() != 1:
            raise AssertionError("alembic_version must contain exactly one head row")
        version_charset = connection.execute(
            text(
                "SELECT CHARACTER_SET_NAME, COLLATION_NAME FROM "
                "information_schema.columns WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'alembic_version' AND COLUMN_NAME = 'version_num'"
            )
        ).one()
        if tuple(value.lower() for value in version_charset) != (
            "utf8mb4",
            "utf8mb4_unicode_ci",
        ):
            raise AssertionError(
                "alembic_version.version_num must use utf8mb4_unicode_ci"
            )

        return schema_fingerprint(connection)

    return run_sql(resources, database, validate)


def insert_unicode_fixture(resources: TemporaryResources, database: str) -> None:
    mark = "u" + chr(0x20BB7) + chr(0x1F642)
    now = datetime.utcnow()

    def insert(connection):
        connection.execute(
            text(
                "INSERT INTO `user` (id, username, password_hash, real_name, role) "
                "VALUES (1, :username, 'hash', :real_name, 'admin')"
            ),
            {"username": mark, "real_name": mark},
        )
        connection.execute(
            text(
                "INSERT INTO patient (id, student_id, name, gender, class_name, created_at) "
                "VALUES (1, 'u-1', :name, 'X', 'C', :created_at)"
            ),
            {"name": mark, "created_at": now},
        )
        connection.execute(
            text(
                "INSERT INTO drug (id, name, specification, unit, price, stock, status) "
                "VALUES (1, :name, '10mg', 'box', 1.5, 5, 1)"
            ),
            {"name": mark},
        )
        connection.execute(
            text(
                "INSERT INTO visit (id, patient_id, doctor_id, timestamp, diagnosis, status) "
                "VALUES (1, 1, 1, :timestamp, :diagnosis, 'pending')"
            ),
            {"timestamp": now, "diagnosis": mark},
        )
        connection.execute(
            text(
                "INSERT INTO prescription_item "
                "(id, visit_id, drug_id, usage, quantity, price_at_visit, amount) "
                "VALUES (1, 1, 1, :usage, 1, 1.5, 1.5)"
            ),
            {"usage": mark},
        )
        connection.execute(
            text(
                "INSERT INTO payment (id, visit_id, nurse_id, amount, payment_method) "
                "VALUES (1, 1, 1, 1.5, 'cash')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO diagnosis_dict (id, code, name, pinyin) "
                "VALUES (1, 'U1', :name, 'u')"
            ),
            {"name": mark},
        )
        connection.execute(
            text(
                "INSERT INTO inventory_record "
                "(id, drug_id, nurse_id, visit_id, old_stock, new_stock, operation_type) "
                "VALUES (1, 1, 1, 1, 5, 4, 'dispense')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO daily_stock_snapshot (id, drug_id, date, stock) "
                "VALUES (1, 1, '2026-07-11', 4)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO drug_stock_group "
                "(id, group_code, batch_no, base_name, unit_name, total_units, "
                "pack_amount, pack_drug_id) VALUES (1, 'g-1', 'b-1', :name, 'box', 1, 1, 1)"
            ),
            {"name": mark},
        )
        connection.execute(
            text(
                "INSERT INTO parked_visit "
                "(id, patient_id, doctor_id, diagnosis, expires_at) "
                "VALUES (1, 1, 1, :diagnosis, :expires_at)"
            ),
            {"diagnosis": mark, "expires_at": now + timedelta(days=1)},
        )
        connection.execute(
            text(
                "INSERT INTO text_template "
                "(id, doctor_id, category, title, content) "
                "VALUES (1, 1, 'general', :title, :content)"
            ),
            {"title": mark, "content": mark},
        )
        connection.execute(
            text(
                "INSERT INTO operation_log "
                "(id, user_id, action_type, target_type, summary) "
                "VALUES (1, 1, 'test', 'fixture', :summary)"
            ),
            {"summary": mark},
        )
        row = connection.execute(
            text(
                "SELECT name, CHAR_LENGTH(name), LENGTH(name) FROM patient WHERE id = 1"
            )
        ).one()
        if row[0] != mark or row[1] != 3 or row[2] != 9:
            raise AssertionError(f"utf8mb4 round-trip failed: {row!r}")
        if connection.execute(text("SELECT is_active FROM `user` WHERE id = 1")).scalar_one() != 1:
            raise AssertionError("user.is_active did not default to 1")

    run_sql(resources, database, insert)

    checks = [
        (
            "duplicate username",
            "INSERT INTO `user` (id, username, password_hash, real_name, role) "
            "VALUES (2, :username, 'hash', 'x', 'admin')",
            {"username": mark},
        ),
        (
            "foreign-key orphan",
            "INSERT INTO visit (id, patient_id, doctor_id, status) "
            "VALUES (2, 999999, 1, 'pending')",
            {},
        ),
        (
            "not-null group code",
            "INSERT INTO drug_stock_group "
            "(id, group_code, batch_no, base_name, unit_name, total_units, pack_amount, pack_drug_id) "
            "VALUES (2, NULL, 'b', 'x', 'box', 1, 1, 1)",
            {},
        ),
    ]
    for label, statement, parameters in checks:
        try:
            with migration_app(resources, database):
                with db.engine.begin() as connection:
                    connection.execute(text(statement), parameters)
        except IntegrityError:
            continue
        raise AssertionError(f"MySQL accepted invalid {label}")


def setup_history(resources: TemporaryResources, database: str) -> None:
    run_upgrade(resources, database, revision=HISTORICAL_SPLIT_REVISION)
    with migration_app(resources, database) as app:
        _sync_model_schema(app)

    def setup(connection):
        now = datetime.utcnow()
        connection.execute(text("DROP TABLE inventory_record"))
        connection.execute(text("DROP INDEX ix_user_is_active ON `user`"))
        connection.execute(
            text(
                "ALTER TABLE `user` DROP COLUMN token_version, "
                "DROP COLUMN is_active"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE `user` MODIFY password_hash VARCHAR(128) "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL "
                "COMMENT 'legacy-hash-comment'"
            )
        )
        connection.execute(text("DROP INDEX ix_patient_name_pinyin ON patient"))
        connection.execute(text("DROP INDEX ix_patient_name_initials ON patient"))
        connection.execute(
            text(
                "ALTER TABLE patient MODIFY name_pinyin TEXT "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL "
                "COMMENT 'legacy-pinyin-comment'"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE patient MODIFY name_initials TEXT "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL "
                "COMMENT 'legacy-initials-comment'"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE drug "
                "MODIFY type INT NULL DEFAULT 1, "
                "MODIFY purchase_price FLOAT NULL DEFAULT 0.0, "
                "MODIFY has_scattered BOOLEAN NULL DEFAULT 0"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE patient "
                "MODIFY is_temporary BOOLEAN NULL DEFAULT 0, "
                "MODIFY patient_type VARCHAR(20) NULL DEFAULT 'student'"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE payment "
                "MODIFY is_employee_discount BOOLEAN NULL DEFAULT 0"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE prescription_item "
                "MODIFY is_scattered BOOLEAN NULL DEFAULT 0, "
                "MODIFY purchase_cost FLOAT NULL DEFAULT 0.0, "
                "MODIFY is_intravenous BOOLEAN NULL DEFAULT 0"
            )
        )
        connection.execute(
            text(
                "INSERT INTO `user` (id, username, password_hash, real_name, role) "
                "VALUES (1, 'legacy-admin', 'legacy-hash', 'Legacy', 'admin')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO patient "
                "(id, student_id, name, gender, class_name, created_at) "
                "VALUES (1, 'legacy-1', 'Legacy', 'X', 'C', :created_at)"
            ),
            {"created_at": now},
        )
        connection.execute(
            text(
                "INSERT INTO drug (id, name, specification, unit, price, stock, status, type) "
                "VALUES (1, 'Legacy Drug', '10mg', 'box', 1.5, 5, 1, 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO visit (id, patient_id, doctor_id, diagnosis, status) "
                "VALUES (1, 1, 1, 'Legacy diagnosis', 'pending')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO prescription_item "
                "(id, visit_id, drug_id, quantity, price_at_visit, amount) "
                "VALUES (1, 1, 1, 1, 1.5, 1.5)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO payment (id, visit_id, nurse_id, amount, payment_method) "
                "VALUES (1, 1, 1, 1.5, 'cash')"
            )
        )
        connection.execute(text("UPDATE patient SET name_pinyin = 'legacy', name_initials = 'l' WHERE id = 1"))
        connection.execute(
            text(
                "ALTER TABLE drug "
                "ADD COLUMN monthly_sort_order INT NULL, "
                "ADD COLUMN is_herb BOOLEAN NULL DEFAULT 0, "
                "ADD COLUMN herb_code VARCHAR(12) NULL, "
                "ADD COLUMN herb_category VARCHAR(3) NULL, "
                "ADD COLUMN herb_variety VARCHAR(4) NULL, "
                "ADD COLUMN herb_spec VARCHAR(2) NULL, "
                "ADD COLUMN alias_name VARCHAR(128) NULL, "
                "ADD COLUMN pinyin_code VARCHAR(50) NULL, "
                "ADD COLUMN processing_type VARCHAR(20) NULL, "
                "ADD COLUMN safety_stock INT NULL DEFAULT 0, "
                "ADD COLUMN max_stock INT NULL DEFAULT 0, "
                "ADD COLUMN daily_loss_rate FLOAT NULL DEFAULT 0.0, "
                "ADD COLUMN shelf_life_days INT NULL, "
                "ADD COLUMN storage_condition VARCHAR(50) NULL"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE visit "
                "ADD COLUMN tcm_enabled BOOLEAN NULL DEFAULT 0, "
                "ADD COLUMN tcm_syndrome VARCHAR(100) NULL, "
                "ADD COLUMN tcm_diagnosis_desc TEXT NULL"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE prescription_item "
                "ADD COLUMN prescription_type VARCHAR(10) NULL DEFAULT 'western', "
                "ADD COLUMN herb_dosage FLOAT NULL, "
                "ADD COLUMN special_preparation VARCHAR(50) NULL, "
                "ADD COLUMN herb_sort_order INT NULL, "
                "ADD COLUMN template_id INT NULL"
            )
        )
        connection.execute(
            text(
                "UPDATE drug SET is_herb = 1, herb_code = 'H001', "
                "herb_category = '001', herb_variety = '0001', "
                "herb_spec = '01', alias_name = 'Legacy alias', "
                "pinyin_code = 'legacy-pinyin', processing_type = 'slice', "
                "safety_stock = 2, max_stock = 20, daily_loss_rate = 0.25, "
                "shelf_life_days = 365, storage_condition = 'dry' WHERE id = 1"
            )
        )
        connection.execute(
            text(
                "UPDATE visit SET tcm_enabled = 1, tcm_syndrome = 'Legacy syndrome', "
                "tcm_diagnosis_desc = 'Legacy TCM diagnosis' WHERE id = 1"
            )
        )
        connection.execute(
            text(
                "UPDATE prescription_item SET prescription_type = 'herb', "
                "herb_dosage = 3.5, special_preparation = 'decoct first', "
                "herb_sort_order = 7, template_id = 42 WHERE id = 1"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE inventory_record ("
                "id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, drug_id INT NULL, "
                "nurse_id INT NULL, old_stock INT NULL, new_stock INT NULL, "
                "remark VARCHAR(200) NULL, timestamp DATETIME NULL, "
                "FOREIGN KEY (drug_id) REFERENCES drug(id), "
                "FOREIGN KEY (nurse_id) REFERENCES `user`(id)) "
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
            )
        )
        connection.execute(
            text(
                "INSERT INTO diagnosis_dict (id, code, name, pinyin) "
                "VALUES (1, 'LEGACY', 'Legacy diagnosis dict', 'legacy')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO drug_stock_group "
                "(id, group_code, batch_no, base_name, unit_name, total_units, "
                "pack_amount, pack_drug_id, created_by, created_at) VALUES "
                "(1, 'legacy-group', 'legacy-batch', 'Legacy Drug', 'box', "
                "5, 5, 1, 1, :created_at)"
            ),
            {"created_at": now},
        )
        connection.execute(
            text(
                "INSERT INTO daily_stock_snapshot "
                "(id, drug_id, date, stock, created_at) "
                "VALUES (1, 1, '2026-07-10', 5, :created_at)"
            ),
            {"created_at": now},
        )
        connection.execute(
            text(
                "INSERT INTO parked_visit "
                "(id, patient_id, doctor_id, diagnosis, items_json, expires_at) "
                "VALUES (1, 1, 1, 'Legacy parked', '[{\"drug_id\":1}]', :expires_at)"
            ),
            {"expires_at": now + timedelta(days=1)},
        )
        connection.execute(
            text(
                "INSERT INTO text_template "
                "(id, doctor_id, category, title, content, created_at, updated_at) "
                "VALUES (1, 1, 'legacy', 'Legacy template', 'Legacy content', "
                ":created_at, :updated_at)"
            ),
            {"created_at": now, "updated_at": now},
        )
        connection.execute(
            text(
                "INSERT INTO operation_log "
                "(id, user_id, action_type, target_type, target_id, summary, details, timestamp) "
                "VALUES (1, 1, 'legacy', 'fixture', 1, 'Legacy operation', "
                "'Legacy details', :timestamp)"
            ),
            {"timestamp": now},
        )
        connection.execute(
            text(
                "INSERT INTO inventory_record "
                "(drug_id, nurse_id, old_stock, new_stock, remark) "
                "VALUES (1, 1, 5, 4, 'legacy')"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE audit_extension (id INT NOT NULL PRIMARY KEY, note VARCHAR(64)) "
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
            )
        )
        connection.execute(text("INSERT INTO audit_extension (id, note) VALUES (1, 'keep')"))

    run_sql(resources, database, setup)


HISTORY_TABLES = (
    "user",
    "patient",
    "drug",
    "visit",
    "payment",
    "prescription_item",
    "diagnosis_dict",
    "inventory_record",
    "drug_stock_group",
    "daily_stock_snapshot",
    "parked_visit",
    "text_template",
    "operation_log",
    "audit_extension",
)


def history_primary_keys(connection):
    return {
        table: tuple(
            connection.execute(
                text(f"SELECT id FROM `{table}` ORDER BY id")
            ).scalars()
        )
        for table in HISTORY_TABLES
    }


def history_values(connection):
    values = {
        "user": tuple(
            connection.execute(
                text(
                    "SELECT username, password_hash, real_name, role, "
                    "token_version, is_active FROM `user` WHERE id = 1"
                )
            ).one()
        ),
        "patient": tuple(
            connection.execute(
                text(
                    "SELECT student_id, name, name_pinyin, name_initials, "
                    "is_temporary, patient_type FROM patient WHERE id = 1"
                )
            ).one()
        ),
        "drug": tuple(
            connection.execute(
                text(
                    "SELECT name, stock, type, purchase_price, has_scattered, "
                    "monthly_sort_order, is_herb, herb_code, "
                    "herb_category, herb_variety, herb_spec, alias_name, "
                    "pinyin_code, processing_type, safety_stock, max_stock, "
                    "daily_loss_rate, shelf_life_days, storage_condition "
                    "FROM drug WHERE id = 1"
                )
            ).one()
        ),
        "visit": tuple(
            connection.execute(
                text(
                    "SELECT patient_id, doctor_id, diagnosis, status, tcm_enabled, "
                    "tcm_syndrome, tcm_diagnosis_desc "
                    "FROM visit WHERE id = 1"
                )
            ).one()
        ),
        "prescription_item": tuple(
            connection.execute(
                text(
                    "SELECT visit_id, drug_id, quantity, price_at_visit, amount, "
                    "is_scattered, purchase_cost, is_intravenous, "
                    "prescription_type, herb_dosage, special_preparation, "
                    "herb_sort_order, template_id, original_price, new_amount "
                    "FROM prescription_item WHERE id = 1"
                )
            ).one()
        ),
        "payment": tuple(
            connection.execute(
                text(
                    "SELECT visit_id, nurse_id, amount, payment_method, "
                    "is_employee_discount "
                    "FROM payment WHERE id = 1"
                )
            ).one()
        ),
        "inventory_record": tuple(
            connection.execute(
                text(
                    "SELECT drug_id, nurse_id, old_stock, new_stock, remark, "
                    "visit_id, operation_type FROM inventory_record WHERE id = 1"
                )
            ).one()
        ),
        "diagnosis_dict": tuple(
            connection.execute(
                text(
                    "SELECT code, name, pinyin FROM diagnosis_dict WHERE id = 1"
                )
            ).one()
        ),
        "drug_stock_group": tuple(
            connection.execute(
                text(
                    "SELECT group_code, batch_no, total_units, pack_amount, "
                    "pack_drug_id, created_by FROM drug_stock_group WHERE id = 1"
                )
            ).one()
        ),
        "daily_stock_snapshot": tuple(
            connection.execute(
                text(
                    "SELECT drug_id, DATE_FORMAT(date, '%Y-%m-%d'), stock "
                    "FROM daily_stock_snapshot WHERE id = 1"
                )
            ).one()
        ),
        "parked_visit": tuple(
            connection.execute(
                text(
                    "SELECT patient_id, doctor_id, diagnosis, items_json "
                    "FROM parked_visit WHERE id = 1"
                )
            ).one()
        ),
        "text_template": tuple(
            connection.execute(
                text(
                    "SELECT doctor_id, category, title, content "
                    "FROM text_template WHERE id = 1"
                )
            ).one()
        ),
        "operation_log": tuple(
            connection.execute(
                text(
                    "SELECT user_id, action_type, summary, details "
                    "FROM operation_log WHERE id = 1"
                )
            ).one()
        ),
        "audit_extension": connection.execute(
            text("SELECT note FROM audit_extension WHERE id = 1")
        ).scalar_one(),
    }
    values["comments"] = tuple(
        tuple(row)
        for row in connection.execute(
            text(
                "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_COMMENT FROM "
                "information_schema.columns WHERE TABLE_SCHEMA = DATABASE() "
                "AND ((TABLE_NAME = 'user' AND COLUMN_NAME = 'password_hash') "
                "OR (TABLE_NAME = 'patient' AND COLUMN_NAME IN "
                "('name_pinyin', 'name_initials'))) "
                "ORDER BY TABLE_NAME, COLUMN_NAME"
            )
        ).all()
    )
    return values


def run_history(resources: TemporaryResources, database: str) -> None:
    setup_history(resources, database)
    before_primary_keys = run_sql(resources, database, history_primary_keys)
    run_upgrade(resources, database)
    first_fingerprint = validate_schema(
        resources,
        database,
        extra_tables=("audit_extension",),
        extra_columns=HISTORY_EXTRA_COLUMNS,
        allowed_model_defaults=HISTORY_MODEL_DEFAULTS,
    )
    after_primary_keys = run_sql(resources, database, history_primary_keys)
    if before_primary_keys != after_primary_keys:
        raise AssertionError(
            "Historical primary keys changed: "
            f"{before_primary_keys!r} -> {after_primary_keys!r}"
        )
    preserved = run_sql(resources, database, history_values)
    expected = {
        "user": ("legacy-admin", "legacy-hash", "Legacy", "admin", None, 1),
        "patient": ("legacy-1", "Legacy", "legacy", "l", 0, "student"),
        "drug": (
            "Legacy Drug",
            5,
            1,
            0.0,
            0,
            None,
            1,
            "H001",
            "001",
            "0001",
            "01",
            "Legacy alias",
            "legacy-pinyin",
            "slice",
            2,
            20,
            0.25,
            365,
            "dry",
        ),
        "visit": (
            1,
            1,
            "Legacy diagnosis",
            "pending",
            1,
            "Legacy syndrome",
            "Legacy TCM diagnosis",
        ),
        "prescription_item": (
            1,
            1,
            1,
            1.5,
            1.5,
            0,
            0.0,
            0,
            "herb",
            3.5,
            "decoct first",
            7,
            42,
            1.5,
            1.5,
        ),
        "payment": (1, 1, 1.5, "cash", 0),
        "inventory_record": (1, 1, 5, 4, "legacy", None, None),
        "diagnosis_dict": ("LEGACY", "Legacy diagnosis dict", "legacy"),
        "drug_stock_group": ("legacy-group", "legacy-batch", 5, 5, 1, 1),
        "daily_stock_snapshot": (1, "2026-07-10", 5),
        "parked_visit": (1, 1, "Legacy parked", '[{"drug_id":1}]'),
        "text_template": (1, "legacy", "Legacy template", "Legacy content"),
        "operation_log": (1, "legacy", "Legacy operation", "Legacy details"),
        "audit_extension": "keep",
        "comments": (
            ("patient", "name_initials", "legacy-initials-comment"),
            ("patient", "name_pinyin", "legacy-pinyin-comment"),
            ("user", "password_hash", "legacy-hash-comment"),
        ),
    }
    if preserved != expected:
        raise AssertionError(
            f"Historical values changed unexpectedly: {preserved!r}"
        )
    run_upgrade(resources, database)
    second_fingerprint = validate_schema(
        resources,
        database,
        extra_tables=("audit_extension",),
        extra_columns=HISTORY_EXTRA_COLUMNS,
        allowed_model_defaults=HISTORY_MODEL_DEFAULTS,
    )
    if first_fingerprint != second_fingerprint:
        raise AssertionError("Second historical MySQL upgrade changed the schema")
    second_values = run_sql(resources, database, history_values)
    if second_values != preserved:
        raise AssertionError("Second historical MySQL upgrade changed business data")


def run_fresh(resources: TemporaryResources, database: str) -> None:
    run_upgrade(resources, database)
    first_fingerprint = validate_schema(
        resources, database, extra_columns={"drug": ("monthly_sort_order",)}
    )
    insert_unicode_fixture(resources, database)
    run_upgrade(resources, database)
    second_fingerprint = validate_schema(
        resources, database, extra_columns={"drug": ("monthly_sort_order",)}
    )
    if first_fingerprint != second_fingerprint:
        raise AssertionError("Second MySQL upgrade changed the schema fingerprint")


def validate_partial_retry_state(resources: TemporaryResources, database: str) -> None:
    expected_columns = {
        "drug": {
            "id",
            "name",
            "specification",
            "unit",
            "price",
            "stock",
            "status",
        },
        "patient": {
            "id",
            "student_id",
            "name",
            "gender",
            "class_name",
            "phone",
            "created_at",
        },
        "user": {"id", "username", "password_hash", "real_name", "role"},
    }

    def validate(connection):
        schema_inspector = inspect(connection)
        actual_tables = set(schema_inspector.get_table_names())
        expected_tables = {"alembic_version", *expected_columns}
        if actual_tables != expected_tables:
            raise AssertionError(
                "Injected failure did not leave the expected partial tables: "
                f"{sorted(actual_tables)}"
            )
        if connection.execute(
            text("SELECT COUNT(*) FROM alembic_version")
        ).scalar_one() != 0:
            raise AssertionError(
                "The failed initial revision must not stamp alembic_version"
            )
        for table_name, columns in expected_columns.items():
            actual_columns = {
                column["name"]
                for column in schema_inspector.get_columns(table_name)
            }
            if actual_columns != columns:
                raise AssertionError(
                    f"Partial {table_name} shape mismatch: {sorted(actual_columns)}"
                )
            if connection.execute(
                text(f"SELECT COUNT(*) FROM `{table_name}`")
            ).scalar_one() != 0:
                raise AssertionError(f"Partial {table_name} must be empty")
        user_indexes, special_indexes = actual_index_semantics(connection, "user")
        if user_indexes or special_indexes:
            raise AssertionError(
                "The injected failure must occur before the username index is created"
            )

    run_sql(resources, database, validate)


def run_retry(resources: TemporaryResources, database: str) -> None:
    trigger = {"fired": False}

    with migration_app(resources, database):
        engine = db.engine

        def inject_after_user_table(_connection, _cursor, statement, _parameters, _context, _executemany):
            if trigger["fired"]:
                return
            normalized = re.sub(r"[`\"]", "", statement.lower())
            if re.search(r"create\s+table\s+(?:if\s+not\s+exists\s+)?user\s*\(", normalized):
                trigger["fired"] = True
                raise RuntimeError("intentional MySQL DDL failure for retry validation")

        event.listen(engine, "after_cursor_execute", inject_after_user_table)
        try:
            migration_error = None
            try:
                upgrade(directory=str(MIGRATIONS_DIR))
            except BaseException as exc:
                if isinstance(exc, KeyboardInterrupt):
                    raise
                migration_error = exc
            if migration_error is None:
                raise AssertionError("DDL failure injection did not abort the migration")
        finally:
            event.remove(engine, "after_cursor_execute", inject_after_user_table)
            db.session.remove()
            engine.dispose()

    if not trigger["fired"]:
        raise AssertionError("DDL failure injection did not match CREATE TABLE user")
    validate_partial_retry_state(resources, database)
    run_upgrade(resources, database)
    first_fingerprint = validate_schema(
        resources, database, extra_columns={"drug": ("monthly_sort_order",)}
    )
    run_upgrade(resources, database)
    second_fingerprint = validate_schema(
        resources, database, extra_columns={"drug": ("monthly_sort_order",)}
    )
    if first_fingerprint != second_fingerprint:
        raise AssertionError("Second retry upgrade changed the MySQL schema")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--login-path", default="codex-medroom")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--expected-server-uuid")
    parser.add_argument("--allow-binlog", action="store_true")
    parser.add_argument(
        "--mysql-bin",
        default=shutil.which("mysql")
        or r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe",
    )
    parser.add_argument(
        "--scenario",
        choices=("all", "fresh", "history", "retry"),
        default="all",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not Path(args.mysql_bin).exists():
        raise RuntimeError(f"mysql client not found: {args.mysql_bin}")
    admin = MysqlAdmin(args.login_path, args.host, args.port, args.mysql_bin)
    resources = None
    primary_error = None
    cleanup_error = None
    exit_code = 1
    try:
        if args.host != LOCAL_MYSQL_HOST:
            raise RuntimeError(
                "MySQL validation is restricted to 127.0.0.1; use a local "
                "SSH tunnel for an explicitly authorized remote test instance"
            )
        details = admin.preflight()
        print(
            "MySQL preflight: "
            f"uuid={details['server_uuid']} host={details['hostname']} "
            f"port={details['port']} version={details['version']} "
            f"server-default={details['charset']}/{details['collation']} "
            f"binlog={details['log_bin']}"
        )
        if args.probe:
            exit_code = 0
        else:
            if args.expected_server_uuid != details["server_uuid"]:
                raise RuntimeError(
                    "Refusing to create temporary resources: pass the exact "
                    "--expected-server-uuid reported by --probe"
                )
            if details["log_bin"] != "0" and not args.allow_binlog:
                raise RuntimeError(
                    "Binary logging is enabled; pass --allow-binlog only after "
                    "accepting that temporary DDL and account metadata will be logged"
                )
            scenarios = {
                "fresh": run_fresh,
                "history": run_history,
                "retry": run_retry,
            }
            selected = (
                tuple(scenarios)
                if args.scenario == "all"
                else (args.scenario,)
            )
            resources = TemporaryResources(
                admin,
                expected_server_uuid=details["server_uuid"],
                allow_binlog=args.allow_binlog,
                scenarios=selected,
            )
            print(
                f"Temporary run_id={resources.run_id} user={resources.user} "
                f"databases={','.join(resources.databases)}"
            )
            resources.create()
            for scenario in selected:
                print(f"Running MySQL Alembic scenario: {scenario}")
                scenarios[scenario](
                    resources, resources.scenario_databases[scenario]
                )
                print(f"  PASS {scenario}")
            print("MySQL Alembic validation passed")
            exit_code = 0
    except BaseException as exc:
        primary_error = exc
        if not isinstance(exc, KeyboardInterrupt):
            print(f"MySQL Alembic validation failed: {exc}", file=sys.stderr)
    finally:
        if resources is not None:
            try:
                resources.cleanup()
            except BaseException as exc:
                cleanup_error = exc
    if cleanup_error is not None:
        if primary_error is None:
            print(
                f"MySQL cleanup failed: {cleanup_error}",
                file=sys.stderr,
            )
        else:
            print(
                f"MySQL cleanup failed after the primary error: {cleanup_error}",
                file=sys.stderr,
            )
        exit_code = 1
    if isinstance(primary_error, KeyboardInterrupt):
        raise primary_error
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
