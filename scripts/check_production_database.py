"""Read-only production database preflight for SQLite and MySQL.

The importable ``inspect_database`` function never initializes the Flask app,
runs migrations, or emits DDL/DML. SQLite is opened with ``mode=ro`` and every
explicit MySQL statement is limited to SELECT/SHOW.
"""

from __future__ import annotations

import argparse
import ast
import ipaddress
import json
import os
import re
import sqlite3
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, quote, urlsplit

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    inspect as sa_inspect,
    text,
)
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import UniqueConstraint


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REPORT_VERSION = 1
SUPPORTED_MYSQL_DRIVERS = {"", "pymysql"}
SUPPORTED_SQLITE_DRIVERS = {"", "pysqlite"}
READ_ONLY_SQL_PREFIXES = {"SELECT", "SHOW", "PRAGMA", "WITH", "EXPLAIN"}
SENSITIVE_QUERY_FRAGMENT = re.compile(r"pass|password|passwd|secret|token|key", re.I)
SENSITIVE_QUERY_NAMES = {
    "init_command",
    "ssl",
    "ssl_ca",
    "ssl_cert",
    "ssl_key",
    "ssl_key_password",
    "unix_socket",
}
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")
MYSQL_ALLOWED_QUERY_OPTIONS = {
    "charset",
    "unix_socket",
    "ssl_ca",
    "ssl_cert",
    "ssl_check_hostname",
    "ssl_disabled",
    "ssl_key",
    "ssl_key_password",
    "ssl_verify_cert",
    "ssl_verify_identity",
}
MYSQL_ALLOWED_DIRECT_CONNECT_ARGS = {
    "charset",
    "connect_timeout",
    "read_timeout",
    "ssl_ca",
    "ssl_cert",
    "ssl_key",
    "ssl_key_password",
    "ssl_verify_cert",
    "ssl_verify_identity",
    "unix_socket",
    "write_timeout",
}
INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")


def _validated_mysql_query(uri: str, url: URL) -> dict[str, str]:
    """Parse the original query so SQLAlchemy cannot hide blanks or duplicates."""

    try:
        raw_query = urlsplit(uri).query
    except ValueError as error:
        raise ValueError("MySQL connection URL could not be parsed") from error
    if not raw_query:
        if "?" in uri.split("#", 1)[0]:
            raise ValueError("MySQL URL query must not be empty")
        return {}
    if INVALID_PERCENT_ESCAPE.search(raw_query):
        raise ValueError("MySQL URL query contains an invalid percent escape")
    try:
        pairs = parse_qsl(
            raw_query,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
            max_num_fields=32,
        )
    except (UnicodeError, ValueError) as error:
        raise ValueError("MySQL URL query could not be parsed safely") from error

    query: dict[str, str] = {}
    for raw_name, raw_value in pairs:
        name = str(raw_name).lower()
        if name in query:
            raise ValueError(f"MySQL URL contains duplicate {name} options")
        if name not in MYSQL_ALLOWED_QUERY_OPTIONS:
            raise ValueError(f"MySQL URL contains unsupported query option {raw_name}")
        value = str(raw_value)
        if (
            not value
            or value != value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise ValueError(f"MySQL URL option {raw_name} must be non-empty")
        query[name] = value

    charset = query.get("charset")
    if charset is not None:
        if charset.lower() != "utf8mb4":
            raise ValueError("MySQL URL charset must be utf8mb4")
        query["charset"] = "utf8mb4"

    unix_socket = query.get("unix_socket")
    if unix_socket and (url.host is not None or url.port is not None):
        raise ValueError(
            "MySQL unix_socket URL must not also configure an authority host or port"
        )
    return query


def _default_migrations_directory() -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", ROOT))
    candidates = (
        bundle_root / "backend" / "migrations" / "versions",
        ROOT / "backend" / "migrations" / "versions",
    )
    return next((path for path in candidates if path.is_dir()), candidates[0])


def _literal_assignment(module: ast.Module, name: str):
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
            and node.value is not None
        ):
            return ast.literal_eval(node.value)
    raise ValueError(f"Migration file is missing {name!r}")


def discover_expected_head(migrations_directory: str | Path | None = None) -> str:
    """Read the packaged migration graph and return its single release head."""

    directory = (
        Path(migrations_directory)
        if migrations_directory is not None
        else _default_migrations_directory()
    )
    if not directory.is_dir():
        raise RuntimeError(f"Migration versions directory is missing: {directory}")

    revisions: dict[str, tuple[str, ...]] = {}
    for path in sorted(directory.glob("*.py")):
        if path.name == "__init__.py":
            continue
        try:
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            revision = _literal_assignment(module, "revision")
            down_revision = _literal_assignment(module, "down_revision")
        except (OSError, SyntaxError, ValueError) as error:
            raise RuntimeError(f"Could not parse migration metadata from {path.name}") from error
        if not isinstance(revision, str) or not revision:
            raise RuntimeError(f"Invalid revision identifier in {path.name}")
        if revision in revisions:
            raise RuntimeError(f"Duplicate migration revision: {revision}")
        if down_revision is None:
            parents = ()
        elif isinstance(down_revision, str):
            parents = (down_revision,)
        elif isinstance(down_revision, (tuple, list)) and all(
            isinstance(value, str) and value for value in down_revision
        ):
            parents = tuple(down_revision)
        else:
            raise RuntimeError(f"Invalid down_revision in {path.name}")
        revisions[revision] = parents

    if not revisions:
        raise RuntimeError(f"No migration revisions found in {directory}")
    referenced = {parent for parents in revisions.values() for parent in parents}
    missing = sorted(referenced - set(revisions))
    if missing:
        raise RuntimeError(f"Migration graph references missing revisions: {missing}")
    heads = sorted(set(revisions) - referenced)
    if len(heads) != 1:
        raise RuntimeError(f"Expected exactly one migration head, found: {heads}")
    return heads[0]


@dataclass(frozen=True)
class DatabaseTarget:
    """Parsed target with a redacted public representation."""

    url: URL = field(repr=False)
    database_type: str
    driver: str
    safe_url: str
    host: str | None
    port: int | None
    database: str | None
    username: str | None
    query_options: tuple[tuple[str, str], ...] = field(default=(), repr=False)
    dangerous_options: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "database_type": self.database_type,
            "driver": self.driver,
            "safe_url": self.safe_url,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "username": self.username,
        }


def _redacted_url(url: URL) -> str:
    safe_query: dict[str, Any] = {}
    for key, value in url.query.items():
        safe_query[key] = (
            "***"
            if key.lower() in SENSITIVE_QUERY_NAMES or SENSITIVE_QUERY_FRAGMENT.search(key)
            else value
        )
    return url.set(query=safe_query).render_as_string(hide_password=True)


def parse_database_url(uri: str) -> DatabaseTarget:
    """Parse a database URI without exposing its password."""

    if not isinstance(uri, str) or not uri.strip():
        raise ValueError("DATABASE_URL is empty")

    normalized_uri = uri.strip()
    url = make_url(normalized_uri)
    driver_name = url.drivername.lower()
    backend, _, driver = driver_name.partition("+")
    if backend == "sqlite":
        database_type = "sqlite"
    elif backend == "mysql":
        database_type = "mysql"
    else:
        database_type = "unsupported"

    query_options: dict[str, str] = {}
    if database_type == "mysql":
        query_options = _validated_mysql_query(normalized_uri, url)
    return DatabaseTarget(
        url=url,
        database_type=database_type,
        driver=driver,
        safe_url=_redacted_url(url),
        host=url.host,
        port=url.port,
        database=url.database,
        username=url.username,
        query_options=tuple(query_options.items()),
    )


def _base_report(expected_head: str | None, require_tls: bool) -> dict[str, Any]:
    return {
        "report_version": REPORT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "target": None,
        "policy": {
            "expected_alembic_head": expected_head,
            "require_tls": bool(require_tls),
        },
        "checks": [],
        "summary": {},
    }


def _add_check(
    report: dict[str, Any],
    check_id: str,
    status: str,
    severity: str,
    message: str,
    details: Any | None = None,
    *,
    retryable: bool = False,
) -> None:
    item = {
        "id": check_id,
        "status": status,
        "severity": severity,
        "message": message,
    }
    if details is not None:
        item["details"] = details
    if retryable:
        item["retryable"] = True
    report["checks"].append(item)


def _pass(
    report: dict[str, Any], check_id: str, message: str, details: Any | None = None
) -> None:
    _add_check(report, check_id, "pass", "info", message, details)


def _warn(
    report: dict[str, Any], check_id: str, message: str, details: Any | None = None
) -> None:
    _add_check(report, check_id, "warn", "warning", message, details)


def _block(
    report: dict[str, Any],
    check_id: str,
    message: str,
    details: Any | None = None,
    *,
    retryable: bool = False,
) -> None:
    _add_check(
        report,
        check_id,
        "fail",
        "blocking",
        message,
        details,
        retryable=retryable,
    )


def _finalize(report: dict[str, Any]) -> dict[str, Any]:
    blocking_checks = [
        item for item in report["checks"] if item["severity"] == "blocking"
    ]
    blocking = len(blocking_checks)
    retryable_blocking = sum(bool(item.get("retryable")) for item in blocking_checks)
    warnings = sum(item["severity"] == "warning" for item in report["checks"])
    passed = sum(item["status"] == "pass" for item in report["checks"])
    overall = "blocked" if blocking else "warning" if warnings else "passed"
    report["summary"] = {
        "overall": overall,
        "blocking": blocking,
        "retryable": bool(blocking) and retryable_blocking == blocking,
        "retryable_blocking": retryable_blocking,
        "permanent_blocking": blocking - retryable_blocking,
        "warnings": warnings,
        "passed": passed,
        "total": len(report["checks"]),
    }
    return report


def _sanitize_error(
    error: BaseException,
    target: DatabaseTarget | None,
    sensitive_values: Iterable[Any] = (),
) -> dict[str, str]:
    message = str(error)
    if target is not None and target.url.password:
        password = str(target.url.password)
        for candidate in {password, quote(password, safe="")}:
            if candidate:
                message = message.replace(candidate, "***")
    if target is not None:
        for key, value in target.url.query.items():
            if key.lower() not in SENSITIVE_QUERY_NAMES and not SENSITIVE_QUERY_FRAGMENT.search(key):
                continue
            values = value if isinstance(value, tuple) else (value,)
            for item in values:
                for candidate in {str(item), quote(str(item), safe="")}:
                    if candidate:
                        message = message.replace(candidate, "***")
    for name in ("MYSQL_SSL_CA", "MYSQL_SSL_CERT", "MYSQL_SSL_KEY"):
        value = os.environ.get(name)
        if value:
            message = message.replace(value, "***")
    for value in sensitive_values:
        if value:
            message = message.replace(str(value), "***")
    return {
        "error_type": type(error).__name__,
        "error": message[:1000],
    }


_PERMANENT_MYSQL_ERROR_CODES = {1044, 1045, 1049, 1142, 1143, 1227}
_PERMANENT_CONNECTION_ERROR_FRAGMENTS = (
    "access denied",
    "authentication plugin",
    "certificate verify failed",
    "hostname mismatch",
    "not allowed to connect",
    "unknown database",
)


def _mysql_error_code(error: BaseException) -> int | None:
    current: Any = error
    for _ in range(3):
        args = getattr(current, "args", ())
        if args and isinstance(args[0], int):
            return args[0]
        next_error = getattr(current, "orig", None)
        if next_error is None or next_error is current:
            break
        current = next_error
    return None


def _is_retryable_database_error(error: BaseException) -> bool:
    """Classify availability failures without retrying known configuration errors."""

    message = str(error).lower()
    code = _mysql_error_code(error)
    if code in _PERMANENT_MYSQL_ERROR_CODES:
        return False
    if any(fragment in message for fragment in _PERMANENT_CONNECTION_ERROR_FRAGMENTS):
        return False
    if isinstance(error, DBAPIError):
        return True
    return isinstance(error, (ConnectionError, TimeoutError, OSError))


def _execute_read_only(connection, statement: str, parameters: dict | None = None):
    stripped = statement.lstrip()
    first_token = stripped.split(None, 1)[0].upper() if stripped else ""
    if first_token not in READ_ONLY_SQL_PREFIXES:
        raise RuntimeError(f"Refusing non-read-only SQL statement: {first_token or '<empty>'}")
    return connection.execute(text(statement), parameters or {})


def _load_model_metadata():
    from backend.app import db
    from backend.app import models as _models  # noqa: F401

    return db.metadata


def _normalized_default(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    while normalized.startswith("(") and normalized.endswith(")"):
        normalized = normalized[1:-1].strip()
    return normalized.strip("'\"")


def _defaults_equal(actual: Any, expected: Any) -> bool:
    actual_value = _normalized_default(actual)
    expected_value = _normalized_default(expected)
    if actual_value == expected_value:
        return True
    if actual_value is None or expected_value is None:
        return False
    try:
        return Decimal(actual_value) == Decimal(expected_value)
    except InvalidOperation:
        return False


def _type_label(column_type: Any) -> str:
    return str(column_type).upper()


def _type_compatible(
    actual: Any, expected: Any, *, dialect_name: str | None = None
) -> bool:
    actual_name = getattr(actual, "__visit_name__", "").lower()
    if isinstance(expected, Boolean):
        return actual_name in {"boolean", "tinyint"} and getattr(
            actual, "display_width", None
        ) in (None, 1)
    if isinstance(expected, Text):
        return actual_name in {"text", "mediumtext", "longtext"}
    if isinstance(expected, String):
        if dialect_name == "sqlite":
            # SQLite does not enforce VARCHAR lengths; TEXT, CHAR, and VARCHAR
            # all have text affinity and are equivalent for the ORM contract.
            return actual_name in {"text", "char", "varchar", "string"}
        actual_length = getattr(actual, "length", None)
        expected_length = getattr(expected, "length", None)
        return (
            actual_name == "varchar"
            and isinstance(actual_length, int)
            and isinstance(expected_length, int)
            and actual_length >= expected_length
        )
    if isinstance(expected, Integer):
        return actual_name in {"integer", "int"} and not getattr(
            actual, "unsigned", False
        )
    if isinstance(expected, Float):
        return actual_name in {"float", "real"}
    if isinstance(expected, DateTime):
        return actual_name == "datetime"
    if isinstance(expected, Date):
        return actual_name == "date"
    return actual_name == getattr(expected, "__visit_name__", "").lower()


def _model_index_semantics(table) -> set[tuple[tuple[str, ...], bool]]:
    semantics = {
        (tuple(column.name for column in index.columns), bool(index.unique))
        for index in table.indexes
    }
    semantics.update(
        {
            (tuple(column.name for column in constraint.columns), True)
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
    )
    return semantics


def _actual_index_semantics(schema_inspector, table_name: str):
    semantics: set[tuple[tuple[str, ...], bool]] = set()
    for index in schema_inspector.get_indexes(table_name):
        columns = tuple(str(value) for value in (index.get("column_names") or ()))
        semantics.add((columns, bool(index.get("unique"))))
    for constraint in schema_inspector.get_unique_constraints(table_name):
        columns = tuple(
            str(value) for value in (constraint.get("column_names") or ())
        )
        semantics.add((columns, True))
    return semantics


def _model_fk_semantics(table):
    return {
        (
            tuple(column.name for column in constraint.columns),
            None,
            constraint.referred_table.name,
            tuple(element.column.name for element in constraint.elements),
            (),
        )
        for constraint in table.foreign_key_constraints
    }


def _actual_fk_semantics(schema_inspector, table_name: str):
    default_schema = schema_inspector.default_schema_name
    semantics = set()
    for foreign_key in schema_inspector.get_foreign_keys(table_name):
        referred_schema = foreign_key.get("referred_schema")
        if referred_schema == default_schema:
            referred_schema = None
        options = []
        for key, value in sorted((foreign_key.get("options") or {}).items()):
            normalized = str(value).upper()
            if key in {"ondelete", "onupdate"} and normalized in {
                "RESTRICT",
                "NO ACTION",
            }:
                continue
            if value is not None:
                options.append((key, normalized))
        semantics.add(
            (
                tuple(foreign_key.get("constrained_columns") or ()),
                referred_schema,
                foreign_key.get("referred_table"),
                tuple(foreign_key.get("referred_columns") or ()),
                tuple(options),
            )
        )
    return semantics


def _semantic_value(value: tuple) -> list[Any]:
    result = []
    for item in value:
        if isinstance(item, tuple):
            result.append(_semantic_value(item))
        else:
            result.append(item)
    return result


def collect_model_schema_diff(schema_inspector, metadata) -> dict[str, list[dict]]:
    """Return blocking and non-destructive differences from ORM metadata."""

    blocking: list[dict] = []
    warnings: list[dict] = []
    bind = getattr(schema_inspector, "bind", None)
    dialect_name = getattr(getattr(bind, "dialect", None), "name", None)
    expected_tables = set(metadata.tables)
    actual_tables = set(schema_inspector.get_table_names())

    for table_name in sorted(expected_tables - actual_tables):
        blocking.append({"kind": "missing_table", "table": table_name})
    for table_name in sorted(actual_tables - expected_tables - {"alembic_version"}):
        warnings.append({"kind": "extra_table", "table": table_name})

    for table_name in sorted(expected_tables & actual_tables):
        model_table = metadata.tables[table_name]
        actual_columns = {
            column["name"]: column
            for column in schema_inspector.get_columns(table_name)
        }
        model_columns = set(model_table.columns.keys())

        for column_name in sorted(model_columns - set(actual_columns)):
            blocking.append(
                {"kind": "missing_column", "table": table_name, "column": column_name}
            )
        for column_name in sorted(set(actual_columns) - model_columns):
            warnings.append(
                {"kind": "extra_column", "table": table_name, "column": column_name}
            )

        for column_name in sorted(model_columns & set(actual_columns)):
            model_column = model_table.columns[column_name]
            actual_column = actual_columns[column_name]
            if not _type_compatible(
                actual_column["type"],
                model_column.type,
                dialect_name=dialect_name,
            ):
                blocking.append(
                    {
                        "kind": "type_mismatch",
                        "table": table_name,
                        "column": column_name,
                        "actual": _type_label(actual_column["type"]),
                        "expected": _type_label(model_column.type),
                    }
                )
            if bool(actual_column.get("nullable")) != bool(model_column.nullable):
                blocking.append(
                    {
                        "kind": "nullable_mismatch",
                        "table": table_name,
                        "column": column_name,
                        "actual": bool(actual_column.get("nullable")),
                        "expected": bool(model_column.nullable),
                    }
                )
            expected_default = (
                model_column.server_default.arg
                if model_column.server_default is not None
                else None
            )
            if not _defaults_equal(actual_column.get("default"), expected_default):
                warnings.append(
                    {
                        "kind": "server_default_mismatch",
                        "table": table_name,
                        "column": column_name,
                        "actual": _normalized_default(actual_column.get("default")),
                        "expected": _normalized_default(expected_default),
                    }
                )

        expected_pk = tuple(column.name for column in model_table.primary_key.columns)
        actual_pk = tuple(
            schema_inspector.get_pk_constraint(table_name).get("constrained_columns")
            or ()
        )
        if actual_pk != expected_pk:
            blocking.append(
                {
                    "kind": "primary_key_mismatch",
                    "table": table_name,
                    "actual": list(actual_pk),
                    "expected": list(expected_pk),
                }
            )

        expected_indexes = _model_index_semantics(model_table)
        actual_indexes = _actual_index_semantics(schema_inspector, table_name)
        for semantics in sorted(expected_indexes - actual_indexes):
            blocking.append(
                {
                    "kind": "missing_index",
                    "table": table_name,
                    "semantics": _semantic_value(semantics),
                }
            )

        expected_fks = _model_fk_semantics(model_table)
        actual_fks = _actual_fk_semantics(schema_inspector, table_name)
        for semantics in sorted(expected_fks - actual_fks, key=repr):
            blocking.append(
                {
                    "kind": "missing_or_changed_foreign_key",
                    "table": table_name,
                    "semantics": _semantic_value(semantics),
                }
            )
        for semantics in sorted(actual_fks - expected_fks, key=repr):
            warnings.append(
                {
                    "kind": "extra_or_changed_foreign_key",
                    "table": table_name,
                    "semantics": _semantic_value(semantics),
                }
            )

        allowed_indexes = expected_indexes | {
            (foreign_key[0], False) for foreign_key in expected_fks
        }
        for semantics in sorted(actual_indexes - allowed_indexes):
            warnings.append(
                {
                    "kind": "extra_index",
                    "table": table_name,
                    "semantics": _semantic_value(semantics),
                }
            )

    key = lambda item: json.dumps(item, sort_keys=True, ensure_ascii=True)
    return {
        "blocking": sorted(blocking, key=key),
        "warnings": sorted(warnings, key=key),
    }


def _check_alembic_head(
    report: dict[str, Any], connection, schema_inspector, expected_head: str | None
) -> None:
    if expected_head is None:
        _pass(report, "alembic.head", "Alembic head check was disabled")
        return
    if "alembic_version" not in set(schema_inspector.get_table_names()):
        _block(report, "alembic.head", "alembic_version table is missing")
        return
    rows = _execute_read_only(
        connection, "SELECT version_num FROM alembic_version ORDER BY version_num"
    ).scalars().all()
    if rows == [expected_head]:
        _pass(report, "alembic.head", f"Alembic is at {expected_head}")
    else:
        _block(
            report,
            "alembic.head",
            "Alembic head does not match the release",
            {"expected": expected_head, "actual": list(rows)},
        )


def _check_model_schema(report: dict[str, Any], schema_inspector):
    try:
        metadata = _load_model_metadata()
        differences = collect_model_schema_diff(schema_inspector, metadata)
    except Exception as error:
        _block(
            report,
            "schema.model",
            "Model schema comparison could not be completed",
            _sanitize_error(error, None),
        )
        return None

    if differences["blocking"]:
        _block(
            report,
            "schema.model",
            "Database schema is incompatible with the current ORM model",
            differences,
        )
    elif differences["warnings"]:
        _warn(
            report,
            "schema.model",
            "Database schema matches required model objects but has non-blocking differences",
            differences,
        )
    else:
        _pass(report, "schema.model", "Database schema matches the current ORM model")
    return metadata


def _check_model_orphans(
    report: dict[str, Any],
    connection,
    schema_inspector,
    metadata,
    *,
    query_timeout: int | None = None,
) -> None:
    """Count orphan rows for every foreign key declared by the ORM model."""

    if metadata is None:
        _block(
            report,
            "schema.orphans",
            "Foreign-key orphan checks require loadable model metadata",
        )
        return
    actual_tables = set(schema_inspector.get_table_names())
    columns_by_table = {
        table_name: {
            column["name"] for column in schema_inspector.get_columns(table_name)
        }
        for table_name in actual_tables & set(metadata.tables)
    }
    preparer = connection.dialect.identifier_preparer
    timeout_hint = ""
    if query_timeout is not None and connection.dialect.name in {"mysql", "mariadb"}:
        timeout_ms = _bounded_timeout(query_timeout, "query_timeout", 300) * 1000
        timeout_hint = f"/*+ MAX_EXECUTION_TIME({timeout_ms}) */ "
    violations = []
    skipped = []
    checked = 0

    for table_name in sorted(metadata.tables):
        model_table = metadata.tables[table_name]
        for constraint in sorted(
            model_table.foreign_key_constraints,
            key=lambda value: repr(tuple(column.name for column in value.columns)),
        ):
            local_columns = tuple(column.name for column in constraint.columns)
            remote_table = constraint.referred_table.name
            remote_columns = tuple(
                element.column.name for element in constraint.elements
            )
            relationship = {
                "table": table_name,
                "columns": list(local_columns),
                "referred_table": remote_table,
                "referred_columns": list(remote_columns),
            }
            if (
                table_name not in columns_by_table
                or remote_table not in columns_by_table
                or not set(local_columns) <= columns_by_table[table_name]
                or not set(remote_columns) <= columns_by_table[remote_table]
            ):
                skipped.append(relationship)
                continue

            quoted_table = preparer.quote(table_name)
            quoted_remote_table = preparer.quote(remote_table)
            quoted_local = [preparer.quote(column) for column in local_columns]
            quoted_remote = [preparer.quote(column) for column in remote_columns]
            join = " AND ".join(
                f"child.{left} = parent.{right}"
                for left, right in zip(quoted_local, quoted_remote)
            )
            local_non_null = " AND ".join(
                f"child.{column} IS NOT NULL" for column in quoted_local
            )
            remote_missing = " AND ".join(
                f"parent.{column} IS NULL" for column in quoted_remote
            )
            count = _execute_read_only(
                connection,
                f"SELECT {timeout_hint}COUNT(*) FROM {quoted_table} AS child "
                f"LEFT JOIN {quoted_remote_table} AS parent ON {join} "
                f"WHERE {local_non_null} AND {remote_missing}",
            ).scalar_one()
            checked += 1
            if count:
                relationship["orphan_count"] = int(count)
                violations.append(relationship)

    if violations or skipped:
        _block(
            report,
            "schema.orphans",
            "Foreign-key orphan verification failed",
            {
                "violations": violations,
                "skipped_relationships": skipped,
                "checked_relationships": checked,
            },
        )
    else:
        _pass(
            report,
            "schema.orphans",
            "No orphan rows were found for model foreign keys",
            {"checked_relationships": checked},
        )


def _mysql_version_check(
    report: dict[str, Any], version: str, version_comment: str
) -> None:
    match = VERSION_RE.match(version or "")
    is_mariadb = "mariadb" in f"{version} {version_comment}".lower()
    parsed = tuple(map(int, match.groups())) if match else None
    if is_mariadb:
        _block(
            report,
            "mysql.version",
            "MariaDB is not a validated production target",
            {"version": version, "version_comment": version_comment},
        )
    elif parsed is None or parsed < (8, 0, 21):
        _block(
            report,
            "mysql.version",
            "MySQL 8.0.21 or newer is required",
            {"version": version, "version_comment": version_comment},
        )
    else:
        _pass(
            report,
            "mysql.version",
            f"MySQL version {version} is supported",
            {"version_comment": version_comment},
        )


def _mysql_flag(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "on", "true", "yes"}


def _environment_bool(environ: dict[str, str], name: str) -> bool | None:
    value = environ.get(name)
    if value is None or value == "":
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def _query_scalar(query: Mapping[str, str], lower_name: str) -> str | None:
    return query.get(lower_name)


def _boolean_value(value: Any, label: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{label} must be a boolean value")


def _bounded_timeout(value: Any, label: str, maximum: int = 1800) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be an integer") from error
    if not 1 <= normalized <= maximum:
        raise ValueError(f"{label} must be between 1 and {maximum}")
    return normalized


def _validated_direct_string(value: Any, label: str) -> str:
    normalized = str(value)
    if (
        not normalized
        or normalized != normalized.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in normalized)
    ):
        raise ValueError(f"{label} must be a non-empty value without whitespace")
    return normalized


def _validated_configured_mysql_args(
    configured_connect_args: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    if configured_connect_args is None:
        configured_connect_args = {}
    if not isinstance(configured_connect_args, Mapping):
        raise ValueError("MySQL configured connect_args must be a mapping")
    unsupported_connect_args = sorted(
        str(name)
        for name in configured_connect_args
        if name not in MYSQL_ALLOWED_DIRECT_CONNECT_ARGS
    )
    if unsupported_connect_args:
        raise ValueError(
            "MySQL configured connect_args contain unsupported options: "
            + ", ".join(unsupported_connect_args)
        )
    return configured_connect_args


def _resolve_mysql_tls(
    target: DatabaseTarget,
    environ: Mapping[str, str] | None = None,
    configured_connect_args: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, bool]]:
    environ = os.environ if environ is None else environ
    configured_connect_args = _validated_configured_mysql_args(
        configured_connect_args
    )
    query = dict(target.query_options)
    if "init_command" in configured_connect_args:
        raise ValueError("MySQL connection arguments may not contain init_command")
    if "ssl" in configured_connect_args:
        raise ValueError(
            "Nested ssl connection arguments are not accepted; use direct TLS arguments"
        )
    disabled = _query_scalar(query, "ssl_disabled")
    if disabled is not None and _boolean_value(disabled, "ssl_disabled"):
        raise ValueError("MySQL URL may not set ssl_disabled=true")
    configured_ssl_disabled = configured_connect_args.get("ssl_disabled", False)
    if configured_ssl_disabled is not None and _boolean_value(
        configured_ssl_disabled, "ssl_disabled"
    ):
        raise ValueError("MySQL connection arguments may not set ssl_disabled=true")

    path_options = {
        "ssl_ca": "MYSQL_SSL_CA",
        "ssl_cert": "MYSQL_SSL_CERT",
        "ssl_key": "MYSQL_SSL_KEY",
        "ssl_key_password": "MYSQL_SSL_KEY_PASSWORD",
    }
    paths: dict[str, str] = {}
    for argument_name, environment_name in path_options.items():
        value = _query_scalar(query, argument_name)
        if value is None:
            configured_value = configured_connect_args.get(argument_name)
            value = str(configured_value).strip() if configured_value else None
        if value is None:
            value = str(environ.get(environment_name, "")).strip()
        if value:
            paths[argument_name] = value

    verify_identity = _query_scalar(query, "ssl_verify_identity")
    check_hostname = _query_scalar(query, "ssl_check_hostname")
    if verify_identity is not None and check_hostname is not None:
        if _boolean_value(verify_identity, "ssl_verify_identity") != _boolean_value(
            check_hostname, "ssl_check_hostname"
        ):
            raise ValueError(
                "ssl_verify_identity conflicts with ssl_check_hostname"
            )
    if verify_identity is None:
        verify_identity = check_hostname

    booleans: dict[str, bool] = {}
    boolean_options = {
        "ssl_verify_cert": (
            _query_scalar(query, "ssl_verify_cert"),
            "MYSQL_SSL_VERIFY_CERT",
        ),
        "ssl_verify_identity": (
            verify_identity,
            "MYSQL_SSL_VERIFY_IDENTITY",
        ),
    }
    has_ca = bool(paths.get("ssl_ca"))
    explicit_disabled = False
    for argument_name, (query_value, environment_name) in boolean_options.items():
        explicit = query_value is not None
        if query_value is not None:
            value = _boolean_value(query_value, argument_name)
        elif argument_name in configured_connect_args:
            explicit = True
            value = _boolean_value(
                configured_connect_args[argument_name], argument_name
            )
        else:
            environment_value = _environment_bool(dict(environ), environment_name)
            explicit = environment_value is not None
            value = True if environment_value is None and has_ca else bool(environment_value)
        if has_ca or explicit:
            booleans[argument_name] = value
        explicit_disabled = explicit_disabled or (explicit and not value)

    ssl_cert = paths.get("ssl_cert")
    ssl_key = paths.get("ssl_key")
    if bool(ssl_cert) != bool(ssl_key):
        raise ValueError("MySQL SSL certificate and key must be configured together")

    policy = {
        "has_ca": has_ca,
        "verify_cert": booleans.get("ssl_verify_cert", False),
        "verify_identity": booleans.get("ssl_verify_identity", False),
        "verified": (
            has_ca
            and booleans.get("ssl_verify_cert", False)
            and booleans.get("ssl_verify_identity", False)
        ),
        "explicit_verification_disabled": explicit_disabled,
    }
    return {**paths, **booleans}, policy


def mysql_connection_configuration(
    target: DatabaseTarget,
    connect_timeout: int,
    environ: Mapping[str, str] | None = None,
    *,
    read_timeout: int = 30,
    write_timeout: int = 30,
    configured_connect_args: Mapping[str, Any] | None = None,
) -> tuple[URL, dict[str, Any], dict[str, bool]]:
    """Return a query-free URL and matching bounded PyMySQL arguments."""

    configured_connect_args = _validated_configured_mysql_args(
        configured_connect_args
    )
    query = dict(target.query_options)
    configured_charset = configured_connect_args.get("charset")
    if configured_charset is not None:
        configured_charset = _validated_direct_string(
            configured_charset, "MySQL charset"
        )
        if configured_charset.lower() != "utf8mb4":
            raise ValueError("MySQL charset must be utf8mb4")

    query_socket = query.get("unix_socket")
    configured_socket = None
    if "unix_socket" in configured_connect_args:
        configured_socket = _validated_direct_string(
            configured_connect_args["unix_socket"], "MySQL unix_socket"
        )
    if query_socket and configured_socket and query_socket != configured_socket:
        raise ValueError("MySQL URL and configured unix_socket values conflict")
    unix_socket = query_socket or configured_socket
    if unix_socket and (target.host is not None or target.port is not None):
        raise ValueError(
            "MySQL unix_socket must not also configure an authority host or port"
        )

    tls_args, policy = _resolve_mysql_tls(
        target,
        environ=environ,
        configured_connect_args=configured_connect_args,
    )
    connection_url = target.url.set(query={})
    if not target.driver:
        connection_url = connection_url.set(drivername="mysql+pymysql")
    args = {
        "charset": "utf8mb4",
        **({"unix_socket": unix_socket} if unix_socket else {}),
        "connect_timeout": _bounded_timeout(connect_timeout, "connect_timeout", 300),
        "read_timeout": _bounded_timeout(read_timeout, "read_timeout"),
        "write_timeout": _bounded_timeout(write_timeout, "write_timeout"),
        **tls_args,
    }
    return connection_url, args, policy


def mysql_connect_args(
    target: DatabaseTarget,
    connect_timeout: int,
    environ: dict[str, str] | None = None,
    *,
    read_timeout: int = 30,
    write_timeout: int = 30,
    configured_connect_args: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build PyMySQL connection arguments without logging credential material."""

    return mysql_connection_configuration(
        target,
        connect_timeout,
        environ,
        read_timeout=read_timeout,
        write_timeout=write_timeout,
        configured_connect_args=configured_connect_args,
    )[1]


def _is_local_mysql_target(
    target: DatabaseTarget, *, unix_socket: str | None = None
) -> bool:
    if unix_socket:
        return True
    host = (target.host or "").strip().lower().rstrip(".")
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def mysql_tls_policy(
    target: DatabaseTarget,
    environ: dict[str, str] | None = None,
    configured_connect_args: Mapping[str, Any] | None = None,
) -> dict[str, bool]:
    """Resolve whether TLS has a CA and both verification controls enabled."""

    return _resolve_mysql_tls(
        target,
        environ=environ,
        configured_connect_args=configured_connect_args,
    )[1]


GRANT_RE = re.compile(r"^GRANT\s+(.+?)\s+ON\s+(.+?)\s+TO\s+", re.I)
ROLE_GRANT_RE = re.compile(r"^GRANT\s+(.+?)\s+TO\s+", re.I)
REQUIRED_APPLICATION_PRIVILEGES = {"SELECT", "INSERT", "UPDATE", "DELETE"}
ELEVATED_APPLICATION_PRIVILEGES = {
    "ALTER",
    "ALTER ROUTINE",
    "BACKUP_ADMIN",
    "CREATE",
    "CREATE ROUTINE",
    "CREATE ROLE",
    "CREATE TABLESPACE",
    "CREATE TEMPORARY TABLES",
    "CREATE USER",
    "CREATE VIEW",
    "DROP",
    "EVENT",
    "EXECUTE",
    "FILE",
    "GRANT OPTION",
    "INDEX",
    "LOCK TABLES",
    "PROCESS",
    "RELOAD",
    "REPLICATION CLIENT",
    "REPLICATION SLAVE",
    "REFERENCES",
    "ROLE_ADMIN",
    "SHUTDOWN",
    "SHOW VIEW",
    "SUPER",
    "SYSTEM_USER",
    "SYSTEM_VARIABLES_ADMIN",
    "TRIGGER",
}
KNOWN_APPLICATION_PRIVILEGES = (
    REQUIRED_APPLICATION_PRIVILEGES
    | ELEVATED_APPLICATION_PRIVILEGES
    | {"ALL PRIVILEGES", "USAGE"}
)


def _unquote_mysql_identifier(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1].replace("``", "`")
    return value


def evaluate_mysql_grants(
    report: dict[str, Any],
    grants: Iterable[str],
    database: str,
    model_tables: Iterable[str],
    *,
    enforce_runtime_least_privilege: bool = True,
) -> None:
    """Require direct DML grants and reject authority that cannot be bounded."""

    database_name = database.lower()
    table_names = {value.lower() for value in model_tables}
    grants = [str(value).strip() for value in grants]
    global_privileges: set[str] = set()
    schema_privileges: set[str] = set()
    table_privileges: dict[str, set[str]] = {}
    elevated_findings: list[dict[str, Any]] = []
    global_scope_findings: list[dict[str, Any]] = []
    unresolved_grants: list[dict[str, str]] = []

    for grant in grants:
        match = GRANT_RE.match(grant)
        if not match:
            if grant.upper().startswith("GRANT "):
                unresolved_grants.append(
                    {
                        "kind": (
                            "role_grant"
                            if ROLE_GRANT_RE.match(grant)
                            else "unparsed_grant"
                        ),
                        "statement": grant[:1000],
                    }
                )
            continue
        privilege_text, scope_text = match.groups()
        declared_privileges = {
            value.strip().upper()
            for value in privilege_text.split(",")
            if value.strip()
        }
        unknown_privileges = sorted(
            declared_privileges - KNOWN_APPLICATION_PRIVILEGES
        )
        if unknown_privileges:
            unresolved_grants.append(
                {
                    "kind": "unrecognized_privileges",
                    "statement": grant[:1000],
                }
            )
        privileges = {
            value
            for value in declared_privileges
            if value in REQUIRED_APPLICATION_PRIVILEGES
        }
        all_privileges = "ALL PRIVILEGES" in declared_privileges
        if all_privileges:
            privileges = set(REQUIRED_APPLICATION_PRIVILEGES)
        elevated = sorted(declared_privileges & ELEVATED_APPLICATION_PRIVILEGES)
        if all_privileges:
            elevated.append("ALL PRIVILEGES")
        if "WITH GRANT OPTION" in grant.upper():
            elevated.append("GRANT OPTION")
        if elevated:
            elevated_findings.append(
                {"scope": scope_text, "privileges": sorted(set(elevated))}
            )
        if "." not in scope_text:
            unresolved_grants.append(
                {
                    "kind": "unsupported_scope",
                    "statement": grant[:1000],
                }
            )
            continue
        schema_part, table_part = scope_text.split(".", 1)
        schema = _unquote_mysql_identifier(schema_part).lower()
        table = _unquote_mysql_identifier(table_part).lower()
        if schema == "*" and table == "*":
            global_authority = set(declared_privileges)
            if "WITH GRANT OPTION" in grant.upper():
                global_authority.add("GRANT OPTION")
            non_usage_authority = sorted(global_authority - {"USAGE"})
            if non_usage_authority:
                global_scope_findings.append(
                    {
                        "scope": scope_text,
                        "privileges": non_usage_authority,
                    }
                )
            global_privileges.update(privileges)
        elif not privileges:
            continue
        elif schema == database_name and table == "*":
            schema_privileges.update(privileges)
        elif schema == database_name:
            table_privileges.setdefault(table, set()).update(privileges)

    broad_privileges = global_privileges | schema_privileges
    missing: dict[str, list[str]] = {}
    for table_name in sorted(table_names):
        effective = broad_privileges | table_privileges.get(table_name, set())
        absent = sorted(REQUIRED_APPLICATION_PRIVILEGES - effective)
        if absent:
            missing[table_name] = absent

    if missing:
        add_missing_result = (
            _warn
            if unresolved_grants and not enforce_runtime_least_privilege
            else _block
        )
        add_missing_result(
            report,
            "mysql.grants",
            (
                "Direct grants do not prove required DML privileges; unresolved grants may supply them"
                if unresolved_grants and not enforce_runtime_least_privilege
                else "Application account is missing required DML privileges"
            ),
            {
                "missing_by_table": missing,
                **(
                    {"unresolved_grant_count": len(unresolved_grants)}
                    if unresolved_grants
                    else {}
                ),
            },
        )
    else:
        _pass(
            report,
            "mysql.grants",
            "Application account has SELECT/INSERT/UPDATE/DELETE on every model table",
            {"model_table_count": len(table_names)},
        )

    if elevated_findings:
        add_result = _block if enforce_runtime_least_privilege else _warn
        add_result(
            report,
            "mysql.grants_elevated",
            (
                "Runtime account has elevated privileges; use a separate migration account"
                if enforce_runtime_least_privilege
                else "Migration account has elevated privileges and must not be used at runtime"
            ),
            {"findings": elevated_findings},
        )
    else:
        _pass(
            report,
            "mysql.grants_elevated",
            "Application account grants do not include known high-risk privileges",
        )

    authority_result = _block if enforce_runtime_least_privilege else _warn
    if global_scope_findings:
        authority_result(
            report,
            "mysql.grants_global_scope",
            (
                "Runtime account has non-USAGE global privileges"
                if enforce_runtime_least_privilege
                else "Migration account has global privileges and must not be used at runtime"
            ),
            {"findings": global_scope_findings},
        )
    else:
        _pass(
            report,
            "mysql.grants_global_scope",
            "Application account has no non-USAGE global privileges",
        )

    if unresolved_grants:
        authority_result(
            report,
            "mysql.grants_unresolved",
            (
                "Runtime account has role or unparseable grants that cannot be bounded"
                if enforce_runtime_least_privilege
                else "Migration account has role or unparseable grants that cannot be expanded"
            ),
            {"findings": unresolved_grants},
        )
    else:
        _pass(
            report,
            "mysql.grants_unresolved",
            "All GRANT statements were directly attributable to explicit scopes",
        )


def evaluate_mysql_server_state(
    report: dict[str, Any],
    settings: dict[str, Any],
    tls_cipher: str,
    *,
    require_tls: bool,
) -> None:
    """Add policy checks for a previously queried MySQL server state."""

    _mysql_version_check(
        report,
        str(settings.get("version") or ""),
        str(settings.get("version_comment") or ""),
    )

    if tls_cipher:
        _pass(
            report,
            "mysql.tls",
            "MySQL connection uses TLS",
            {"cipher": tls_cipher},
        )
    elif require_tls:
        _block(report, "mysql.tls", "MySQL connection is not using TLS")
    else:
        _warn(
            report,
            "mysql.tls",
            "MySQL connection is plaintext and TLS was explicitly made optional",
        )

    database_charset = str(settings.get("character_set_database") or "").lower()
    connection_charset = str(settings.get("character_set_connection") or "").lower()
    server_charset = str(settings.get("character_set_server") or "").lower()
    charset_details = {
        "server": server_charset,
        "database": database_charset,
        "connection": connection_charset,
        "server_collation": settings.get("collation_server"),
        "database_collation": settings.get("collation_database"),
        "connection_collation": settings.get("collation_connection"),
    }
    if database_charset != "utf8mb4" or connection_charset != "utf8mb4":
        _block(
            report,
            "mysql.utf8mb4",
            "Database and connection character sets must be utf8mb4",
            charset_details,
        )
    elif server_charset != "utf8mb4":
        _warn(
            report,
            "mysql.utf8mb4",
            "Current database uses utf8mb4 but the server default does not",
            charset_details,
        )
    else:
        _pass(report, "mysql.utf8mb4", "MySQL character sets use utf8mb4", charset_details)

    session_modes = {
        value.strip().upper()
        for value in str(settings.get("session_sql_mode") or "").split(",")
        if value.strip()
    }
    global_modes = {
        value.strip().upper()
        for value in str(settings.get("global_sql_mode") or "").split(",")
        if value.strip()
    }
    strict_names = {"STRICT_TRANS_TABLES", "STRICT_ALL_TABLES"}
    strict_details = {
        "session": sorted(session_modes),
        "global": sorted(global_modes),
    }
    if not session_modes.intersection(strict_names):
        _block(
            report,
            "mysql.strict_mode",
            "Current MySQL session is not in strict SQL mode",
            strict_details,
        )
    elif not global_modes.intersection(strict_names):
        _warn(
            report,
            "mysql.strict_mode",
            "Current session is strict but the MySQL global default is not",
            strict_details,
        )
    else:
        _pass(report, "mysql.strict_mode", "MySQL strict SQL mode is enabled", strict_details)

    default_engine = str(settings.get("default_storage_engine") or "").upper()
    if default_engine != "INNODB":
        _block(
            report,
            "mysql.default_engine",
            "MySQL default storage engine must be InnoDB",
            {"actual": default_engine},
        )
    else:
        _pass(report, "mysql.default_engine", "MySQL default storage engine is InnoDB")

    read_only = _mysql_flag(settings.get("read_only"))
    super_read_only = _mysql_flag(settings.get("super_read_only"))
    if read_only or super_read_only:
        _block(
            report,
            "mysql.read_only",
            "MySQL server is read-only and cannot serve the application writer",
            {"read_only": read_only, "super_read_only": super_read_only},
        )
    else:
        _pass(report, "mysql.read_only", "MySQL server accepts application writes")

    offset = settings.get("utc_offset_seconds")
    timezone_details = {
        "global": settings.get("global_time_zone"),
        "session": settings.get("session_time_zone"),
        "utc_offset_seconds": offset,
    }
    if offset in (0, "0", Decimal("0")):
        _pass(report, "mysql.time_zone", "MySQL session resolves to UTC", timezone_details)
    else:
        _warn(
            report,
            "mysql.time_zone",
            "MySQL session is not UTC; verify all DATETIME values remain naive UTC",
            timezone_details,
        )


MYSQL_SERVER_STATE_SQL = """
SELECT
    VERSION() AS version,
    @@version_comment AS version_comment,
    @@default_storage_engine AS default_storage_engine,
    @@character_set_server AS character_set_server,
    @@character_set_database AS character_set_database,
    @@character_set_connection AS character_set_connection,
    @@collation_server AS collation_server,
    @@collation_database AS collation_database,
    @@collation_connection AS collation_connection,
    @@SESSION.sql_mode AS session_sql_mode,
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@GLOBAL.time_zone AS global_time_zone,
    @@SESSION.time_zone AS session_time_zone,
    TIMESTAMPDIFF(SECOND, UTC_TIMESTAMP(), NOW()) AS utc_offset_seconds,
    @@GLOBAL.read_only AS read_only,
    @@GLOBAL.super_read_only AS super_read_only
""".strip()


def _check_mysql_table_storage(report: dict[str, Any], connection) -> None:
    rows = _execute_read_only(
        connection,
        """
        SELECT TABLE_NAME, ENGINE, TABLE_COLLATION
        FROM information_schema.tables
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
        """,
    ).all()
    non_innodb = [row[0] for row in rows if str(row[1] or "").upper() != "INNODB"]
    non_utf8mb4 = [
        row[0]
        for row in rows
        if row[2] is not None and not str(row[2]).lower().startswith("utf8mb4_")
    ]
    if non_innodb or non_utf8mb4:
        _block(
            report,
            "mysql.table_storage",
            "One or more MySQL tables have unsafe engine or collation settings",
            {"non_innodb": non_innodb, "non_utf8mb4": non_utf8mb4},
        )
    else:
        _pass(
            report,
            "mysql.table_storage",
            "All base tables use InnoDB and utf8mb4 collations",
            {"table_count": len(rows)},
        )


def _inspect_mysql(
    report: dict[str, Any],
    target: DatabaseTarget,
    *,
    expected_head: str | None,
    require_tls: bool,
    connect_timeout: int,
    read_timeout: int,
    write_timeout: int,
    query_timeout: int,
    deep_checks: bool,
    enforce_runtime_least_privilege: bool,
    configured_connect_args: Mapping[str, Any] | None,
) -> None:
    if target.driver not in SUPPORTED_MYSQL_DRIVERS:
        _block(
            report,
            "config.driver",
            "Only the mysql+pymysql driver is supported",
            {"driver": target.driver or "default"},
        )
        return
    if target.dangerous_options:
        _block(
            report,
            "config.options",
            "DATABASE_URL contains an option that can execute SQL while connecting",
            {"options": list(target.dangerous_options)},
        )
        return
    if not target.database:
        _block(report, "config.database", "MySQL DATABASE_URL must select a database")
        return
    try:
        connection_url, dbapi_connect_args, tls_policy = mysql_connection_configuration(
            target,
            connect_timeout,
            read_timeout=read_timeout,
            write_timeout=write_timeout,
            configured_connect_args=configured_connect_args,
        )
    except ValueError as error:
        configured_connect_args = configured_connect_args or {}
        sensitive_config_values = (
            configured_connect_args.get(name)
            for name in (
                "ssl_ca",
                "ssl_cert",
                "ssl_key",
                "ssl_key_password",
                "unix_socket",
            )
        )
        _block(
            report,
            "config.options",
            "MySQL connection options are invalid",
            _sanitize_error(error, target, sensitive_config_values),
        )
        return
    unix_socket = dbapi_connect_args.get("unix_socket")
    if not target.host and not unix_socket:
        _block(
            report,
            "config.host",
            "MySQL DATABASE_URL must select a host or Unix socket",
        )
        return
    if require_tls and tls_policy["explicit_verification_disabled"]:
        _block(
            report,
            "config.tls",
            "TLS certificate and hostname verification must remain enabled",
            tls_policy,
        )
        return
    if (
        require_tls
        and not _is_local_mysql_target(target, unix_socket=unix_socket)
        and not tls_policy["verified"]
    ):
        _block(
            report,
            "config.tls",
            "Remote MySQL requires a CA with certificate and hostname verification before connecting",
            tls_policy,
        )
        return

    engine = None
    try:
        engine = create_engine(
            connection_url,
            poolclass=NullPool,
            connect_args=dbapi_connect_args,
        )
        with engine.connect() as connection:
            identity = _execute_read_only(
                connection,
                "SELECT 1 AS ok, DATABASE() AS database_name, CURRENT_USER() AS current_user",
            ).mappings().one()
            if identity["database_name"] != target.database:
                _block(
                    report,
                    "connection",
                    "Connected database does not match DATABASE_URL",
                    {
                        "expected": target.database,
                        "actual": identity["database_name"],
                    },
                )
                return
            _pass(
                report,
                "connection",
                "MySQL connection succeeded",
                {
                    "database": identity["database_name"],
                    "current_user": identity["current_user"],
                },
            )

            settings = dict(
                _execute_read_only(connection, MYSQL_SERVER_STATE_SQL).mappings().one()
            )
            tls_row = _execute_read_only(
                connection, "SHOW SESSION STATUS LIKE 'Ssl_cipher'"
            ).first()
            tls_cipher = str(tls_row[1] or "") if tls_row else ""
            evaluate_mysql_server_state(
                report, settings, tls_cipher, require_tls=require_tls
            )
            _check_mysql_table_storage(report, connection)

            schema_inspector = sa_inspect(connection)
            _check_alembic_head(report, connection, schema_inspector, expected_head)
            metadata = _check_model_schema(report, schema_inspector)
            if metadata is not None:
                grant_rows = _execute_read_only(
                    connection, "SHOW GRANTS FOR CURRENT_USER()"
                ).all()
                evaluate_mysql_grants(
                    report,
                    (str(row[0]) for row in grant_rows),
                    target.database,
                    metadata.tables,
                    enforce_runtime_least_privilege=enforce_runtime_least_privilege,
                )
            else:
                _block(
                    report,
                    "mysql.grants",
                    "Grant checks require loadable model metadata",
                )
            if deep_checks:
                _check_model_orphans(
                    report,
                    connection,
                    schema_inspector,
                    metadata,
                    query_timeout=query_timeout,
                )
            else:
                _warn(
                    report,
                    "schema.orphans",
                    "Foreign-key orphan scan was skipped by the bounded startup profile",
                    {"run_deep_check": True},
                )
    except Exception as error:
        sensitive_connect_values = (
            dbapi_connect_args.get(name)
            for name in ("ssl_ca", "ssl_cert", "ssl_key", "ssl_key_password")
        )
        _block(
            report,
            "connection" if not any(c["id"] == "connection" for c in report["checks"]) else "mysql.inspection",
            "MySQL preflight query failed",
            _sanitize_error(error, target, sensitive_connect_values),
            retryable=_is_retryable_database_error(error),
        )
    finally:
        if engine is not None:
            engine.dispose()


def _sqlite_database_path(target: DatabaseTarget) -> Path | None:
    database = target.database
    if not database or database == ":memory:" or database.startswith("file::memory:"):
        return None
    if database.startswith("file:"):
        database = database[5:].split("?", 1)[0]
        if database.startswith("///"):
            database = database[2:]
    path = Path(database).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


@contextmanager
def _sqlite_read_only_engine(path: Path, timeout: int):
    sqlite_uri = path.as_uri() + f"?mode=ro&_busy_timeout={max(1, int(timeout)) * 1000}"

    def creator():
        return sqlite3.connect(sqlite_uri, uri=True, timeout=max(1, int(timeout)))

    engine = create_engine("sqlite+pysqlite://", creator=creator, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


def _inspect_sqlite(
    report: dict[str, Any],
    target: DatabaseTarget,
    *,
    expected_head: str | None,
    connect_timeout: int,
    deep_checks: bool,
) -> None:
    if target.driver not in SUPPORTED_SQLITE_DRIVERS:
        _block(
            report,
            "config.driver",
            "Only the sqlite+pysqlite driver is supported",
            {"driver": target.driver},
        )
        return
    path = _sqlite_database_path(target)
    if path is None:
        _block(
            report,
            "config.database",
            "Production SQLite preflight requires a persistent database file",
        )
        return
    report["target"]["resolved_path"] = str(path)
    if not path.is_file():
        _block(
            report,
            "connection",
            "SQLite database file does not exist; it was not created",
            {"path": str(path)},
        )
        return

    try:
        with _sqlite_read_only_engine(path, connect_timeout) as engine:
            with engine.connect() as connection:
                version = _execute_read_only(
                    connection, "SELECT sqlite_version()"
                ).scalar_one()
                _pass(
                    report,
                    "connection",
                    "SQLite connection succeeded in mode=ro",
                    {"path": str(path), "sqlite_version": version},
                )
                schema_inspector = sa_inspect(connection)
                _check_alembic_head(report, connection, schema_inspector, expected_head)
                metadata = _check_model_schema(report, schema_inspector)
                if deep_checks:
                    _check_model_orphans(
                        report, connection, schema_inspector, metadata
                    )
                else:
                    _warn(
                        report,
                        "schema.orphans",
                        "Foreign-key orphan scan was skipped by the bounded startup profile",
                        {"run_deep_check": True},
                    )
    except Exception as error:
        _block(
            report,
            "sqlite.inspection",
            "SQLite preflight query failed",
            _sanitize_error(error, target),
        )


def inspect_database(
    uri: str,
    expected_head: str | None = None,
    require_tls: bool = True,
    *,
    connect_timeout: int = 5,
    read_timeout: int = 30,
    write_timeout: int = 30,
    query_timeout: int = 10,
    deep_checks: bool = True,
    enforce_runtime_least_privilege: bool = True,
    configured_connect_args: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Inspect a production database and return a structured, read-only report."""

    head_source = "explicit"
    if expected_head is None:
        head_source = "packaged_migrations"
        try:
            expected_head = discover_expected_head()
        except Exception as error:
            report = _base_report(None, require_tls)
            _block(
                report,
                "release.head",
                "The packaged release migration head could not be determined",
                _sanitize_error(error, None),
            )
            return _finalize(report)
    elif not isinstance(expected_head, str) or not expected_head.strip():
        report = _base_report(None, require_tls)
        _block(report, "release.head", "Explicit Alembic head must not be empty")
        return _finalize(report)

    expected_head = expected_head.strip()
    report = _base_report(expected_head, require_tls)
    report["policy"].update(
        {
            "deep_checks": bool(deep_checks),
            "query_timeout_seconds": query_timeout,
            "enforce_runtime_least_privilege": bool(
                enforce_runtime_least_privilege
            ),
        }
    )
    _pass(
        report,
        "release.head",
        f"Release expects Alembic head {expected_head}",
        {"source": head_source},
    )
    target = None
    try:
        target = parse_database_url(uri)
    except Exception as error:
        _block(
            report,
            "config.parse",
            "DATABASE_URL could not be parsed",
            {"error_type": type(error).__name__},
        )
        return _finalize(report)

    report["target"] = target.to_dict()
    _pass(
        report,
        "config.parse",
        f"DATABASE_URL identifies {target.database_type}",
        {"safe_url": target.safe_url},
    )
    if target.database_type == "mysql":
        _inspect_mysql(
            report,
            target,
            expected_head=expected_head,
            require_tls=require_tls,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            write_timeout=write_timeout,
            query_timeout=query_timeout,
            deep_checks=deep_checks,
            enforce_runtime_least_privilege=enforce_runtime_least_privilege,
            configured_connect_args=configured_connect_args,
        )
    elif target.database_type == "sqlite":
        _inspect_sqlite(
            report,
            target,
            expected_head=expected_head,
            connect_timeout=connect_timeout,
            deep_checks=deep_checks,
        )
    else:
        _block(
            report,
            "config.backend",
            "Only SQLite and MySQL are supported",
            {"driver": target.url.drivername},
        )
    return _finalize(report)


def format_json_report(report: dict[str, Any]) -> str:
    return json.dumps(
        report, ensure_ascii=False, indent=2, sort_keys=True, default=str
    )


def format_human_report(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    target = report.get("target") or {}
    lines = [
        f"Production database preflight: {str(summary.get('overall', 'unknown')).upper()}",
        f"Target: {target.get('safe_url', '<unparseable>')}",
        f"Type: {target.get('database_type', 'unknown')}",
        "",
    ]
    labels = {"pass": "PASS", "warn": "WARN", "fail": "BLOCK"}
    for item in report.get("checks", []):
        lines.append(
            f"[{labels.get(item['status'], item['status'].upper()):5}] "
            f"{item['id']}: {item['message']}"
        )
        if item["status"] != "pass" and "details" in item:
            lines.append(
                "        "
                + json.dumps(
                    item["details"], ensure_ascii=False, sort_keys=True, default=str
                )
            )
    lines.extend(
        [
            "",
            "Summary: "
            f"{summary.get('blocking', 0)} blocking, "
            f"{summary.get('warnings', 0)} warning, "
            f"{summary.get('passed', 0)} passed",
            "All preflight SQL is read-only; no schema or data changes are attempted.",
        ]
    )
    return "\n".join(lines)


def _default_sqlite_uri() -> str:
    app_root = Path(os.environ.get("APP_ROOT") or ROOT).resolve()
    return URL.create(
        "sqlite+pysqlite", database=str(app_root / "data" / "app.db")
    ).render_as_string(hide_password=False)


def _effective_database_uri(cli_value: str | None) -> str:
    if cli_value:
        return cli_value
    return (
        os.environ.get("DATABASE_URL")
        or os.environ.get("SQLALCHEMY_DATABASE_URI")
        or _default_sqlite_uri()
    )


def parse_args(argv: Iterable[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Run read-only production database preflight checks."
    )
    parser.add_argument(
        "--database-url",
        help="Override DATABASE_URL. Prefer the environment to avoid exposing passwords in process lists.",
    )
    parser.add_argument(
        "--expected-head",
        default=None,
        help="Override the single head discovered from packaged migrations.",
    )
    parser.add_argument(
        "--connect-timeout", type=int, default=5, help="Connection timeout in seconds."
    )
    parser.add_argument(
        "--read-timeout", type=int, default=30, help="Socket read timeout in seconds."
    )
    parser.add_argument(
        "--write-timeout", type=int, default=30, help="Socket write timeout in seconds."
    )
    parser.add_argument(
        "--query-timeout",
        type=int,
        default=10,
        help="Maximum time for each deep MySQL integrity query in seconds.",
    )
    parser.add_argument(
        "--skip-deep-checks",
        dest="deep_checks",
        action="store_false",
        default=True,
        help="Skip full foreign-key orphan scans for a bounded startup check.",
    )
    parser.add_argument(
        "--allow-migration-privileges",
        dest="enforce_runtime_least_privilege",
        action="store_false",
        default=True,
        help="Allow elevated grants when explicitly checking a dedicated migration account.",
    )
    tls_group = parser.add_mutually_exclusive_group()
    tls_group.add_argument(
        "--require-tls", dest="require_tls", action="store_true", default=True
    )
    tls_group.add_argument(
        "--allow-plaintext",
        dest="require_tls",
        action="store_false",
        help="Downgrade a plaintext MySQL connection from blocking to warning.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    from dotenv import load_dotenv

    args = parse_args(argv)
    load_dotenv(ROOT / ".env")
    report = inspect_database(
        _effective_database_uri(args.database_url),
        expected_head=args.expected_head,
        require_tls=args.require_tls,
        connect_timeout=args.connect_timeout,
        read_timeout=args.read_timeout,
        write_timeout=args.write_timeout,
        query_timeout=args.query_timeout,
        deep_checks=args.deep_checks,
        enforce_runtime_least_privilege=args.enforce_runtime_least_privilege,
    )
    print(format_json_report(report) if args.json else format_human_report(report))
    overall = report["summary"]["overall"]
    return 2 if overall == "blocked" else 1 if overall == "warning" else 0


if __name__ == "__main__":
    raise SystemExit(main())
