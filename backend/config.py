import ipaddress
import os
import re
import sys
from pathlib import Path
from typing import Mapping
from urllib.parse import parse_qsl, urlsplit

from dotenv import load_dotenv
from sqlalchemy.engine import make_url
from backend.runtime_secrets import ensure_runtime_secrets


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _mapping_bool(
    environ: Mapping[str, str], name: str, default: bool = False
) -> bool:
    raw = environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise RuntimeError(f"{name} must be one of: 1/0, true/false, yes/no, on/off")


def _env_bool(name: str, default: bool = False) -> bool:
    return _mapping_bool(os.environ, name, default)


def _mapping_int(
    environ: Mapping[str, str],
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    return _mapping_int(os.environ, name, default, minimum, maximum)


def _is_mysql_uri(uri: str) -> bool:
    return isinstance(uri, str) and uri.lower().startswith("mysql")


def _is_loopback_host(host: str | None) -> bool:
    normalized = (host or "").strip().lower().rstrip(".")
    if normalized in {"", "localhost"}:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _is_remote_mysql_uri(uri: str, *, unix_socket: str | None = None) -> bool:
    if not _is_mysql_uri(uri):
        return False
    try:
        url = make_url(uri)
    except Exception as exc:
        raise RuntimeError("MySQL connection URL could not be parsed") from exc
    if url.drivername.lower() == "mysql":
        url = url.set(drivername="mysql+pymysql")
    elif url.drivername.lower() != "mysql+pymysql":
        raise RuntimeError("Only the mysql+pymysql driver is supported")
    if not url.database:
        raise RuntimeError("MySQL connection URL must include a database name")
    query = _validated_mysql_query(uri, url)
    if unix_socket or query.get("unix_socket"):
        return False
    return not _is_loopback_host(url.host)


def _database_requires_tls(
    uri: str,
    environ: Mapping[str, str] | None = None,
    *,
    unix_socket: str | None = None,
) -> bool:
    environ = os.environ if environ is None else environ
    explicit = environ.get("DATABASE_REQUIRE_TLS")
    if explicit is not None and explicit.strip():
        configured = _mapping_bool(environ, "DATABASE_REQUIRE_TLS")
        if _is_remote_mysql_uri(uri, unix_socket=unix_socket) and not configured:
            raise RuntimeError("Remote MySQL may not disable DATABASE_REQUIRE_TLS")
        return configured
    if not _is_mysql_uri(uri):
        return False
    return _is_remote_mysql_uri(uri, unix_socket=unix_socket)


_MYSQL_ALLOWED_QUERY_OPTIONS = {
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
_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")


def _validated_mysql_query(uri: str, url=None) -> dict[str, str]:
    """Parse MySQL query options without losing blanks or duplicate values."""

    if url is None:
        try:
            url = make_url(uri)
        except Exception as exc:
            raise RuntimeError("MySQL connection URL could not be parsed") from exc
    try:
        raw_query = urlsplit(uri).query
    except ValueError as exc:
        raise RuntimeError("MySQL connection URL could not be parsed") from exc
    if not raw_query:
        if "?" in uri.split("#", 1)[0]:
            raise RuntimeError("MySQL URL query must not be empty")
        return {}
    if _INVALID_PERCENT_ESCAPE.search(raw_query):
        raise RuntimeError("MySQL URL query contains an invalid percent escape")
    try:
        pairs = parse_qsl(
            raw_query,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
            max_num_fields=32,
        )
    except (UnicodeError, ValueError) as exc:
        raise RuntimeError("MySQL URL query could not be parsed safely") from exc

    query: dict[str, str] = {}
    for raw_name, raw_value in pairs:
        name = str(raw_name).lower()
        if name in query:
            raise RuntimeError(f"MySQL URL contains duplicate {name} options")
        if name not in _MYSQL_ALLOWED_QUERY_OPTIONS:
            raise RuntimeError(f"MySQL URL contains unsupported query option {raw_name}")
        value = str(raw_value)
        if (
            not value
            or value != value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise RuntimeError(f"MySQL URL option {raw_name} must be non-empty")
        query[name] = value

    charset = query.get("charset")
    if charset is not None:
        if charset.lower() != "utf8mb4":
            raise RuntimeError("MySQL URL charset must be utf8mb4")
        query["charset"] = "utf8mb4"

    unix_socket = query.get("unix_socket")
    if unix_socket and (url.host is not None or url.port is not None):
        raise RuntimeError(
            "MySQL unix_socket URL must not also configure an authority host or port"
        )
    return query


def _query_scalar(query: Mapping[str, str], lower_name: str) -> str | None:
    return query.get(lower_name)


def _bool_value(value: str, label: str) -> bool:
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise RuntimeError(
        f"{label} must be one of: 1/0, true/false, yes/no, on/off"
    )


def _normalize_mysql_connection(
    uri: str,
    environ: Mapping[str, str] | None = None,
) -> tuple[str, dict]:
    """Move supported MySQL URL options into direct PyMySQL arguments."""

    environ = os.environ if environ is None else environ
    if not _is_mysql_uri(uri):
        return uri, {}
    try:
        url = make_url(uri)
    except Exception as exc:
        raise RuntimeError("MySQL connection URL could not be parsed") from exc
    if url.drivername.lower() == "mysql":
        url = url.set(drivername="mysql+pymysql")
    elif url.drivername.lower() != "mysql+pymysql":
        raise RuntimeError("Only the mysql+pymysql driver is supported")
    if not url.database:
        raise RuntimeError("MySQL connection URL must include a database name")
    query = _validated_mysql_query(uri, url)

    ssl_disabled = _query_scalar(query, "ssl_disabled")
    if ssl_disabled is not None and _bool_value(ssl_disabled, "ssl_disabled"):
        raise RuntimeError("MySQL URL may not set ssl_disabled=true")

    path_options = {
        "ssl_ca": "MYSQL_SSL_CA",
        "ssl_cert": "MYSQL_SSL_CERT",
        "ssl_key": "MYSQL_SSL_KEY",
        "ssl_key_password": "MYSQL_SSL_KEY_PASSWORD",
    }
    resolved_paths: dict[str, str] = {}
    for query_name, environment_name in path_options.items():
        value = _query_scalar(query, query_name)
        if value is None:
            value = str(environ.get(environment_name, "")).strip()
        if value:
            resolved_paths[query_name] = value

    verify_identity_value = _query_scalar(query, "ssl_verify_identity")
    check_hostname_value = _query_scalar(query, "ssl_check_hostname")
    if verify_identity_value is not None and check_hostname_value is not None:
        if _bool_value(verify_identity_value, "ssl_verify_identity") != _bool_value(
            check_hostname_value, "ssl_check_hostname"
        ):
            raise RuntimeError(
                "ssl_verify_identity conflicts with ssl_check_hostname"
            )
    if verify_identity_value is None:
        verify_identity_value = check_hostname_value

    boolean_options = {
        "ssl_verify_cert": (
            _query_scalar(query, "ssl_verify_cert"),
            "MYSQL_SSL_VERIFY_CERT",
        ),
        "ssl_verify_identity": (
            verify_identity_value,
            "MYSQL_SSL_VERIFY_IDENTITY",
        ),
    }
    resolved_booleans: dict[str, bool] = {}
    has_ca = bool(resolved_paths.get("ssl_ca"))
    for argument_name, (query_value, environment_name) in boolean_options.items():
        if query_value is not None:
            resolved_booleans[argument_name] = _bool_value(query_value, argument_name)
            continue
        environment_value = str(environ.get(environment_name, "")).strip()
        if environment_value:
            resolved_booleans[argument_name] = _bool_value(
                environment_value, environment_name
            )
        elif has_ca:
            resolved_booleans[argument_name] = True

    ssl_cert = resolved_paths.get("ssl_cert")
    ssl_key = resolved_paths.get("ssl_key")
    if bool(ssl_cert) != bool(ssl_key):
        raise RuntimeError("MySQL SSL certificate and key must be configured together")

    unix_socket = query.get("unix_socket")
    requires_tls = _database_requires_tls(
        uri, environ, unix_socket=unix_socket
    )
    if requires_tls and (
        not has_ca
        or not resolved_booleans.get("ssl_verify_cert", False)
        or not resolved_booleans.get("ssl_verify_identity", False)
    ):
        if has_ca:
            raise RuntimeError(
                "Remote MySQL may not disable certificate or hostname verification"
            )
        raise RuntimeError(
            "Remote MySQL requires verified TLS before connecting; configure "
            "MYSQL_SSL_CA or an ssl_ca URL option"
        )

    normalized_url = url.set(query={})
    connect_args = {
        **({"unix_socket": unix_socket} if unix_socket else {}),
        **resolved_paths,
        **resolved_booleans,
    }
    return normalized_url.render_as_string(hide_password=False), connect_args


def _engine_configuration(
    uri: str, environ: Mapping[str, str] | None = None
) -> tuple[str, dict]:
    """Return a sanitized SQLAlchemy URL and its matching bounded engine options."""

    environ = os.environ if environ is None else environ
    if not _is_mysql_uri(uri):
        return uri, {"pool_pre_ping": True, "connect_args": {"timeout": 15}}

    normalized_uri, tls_args = _normalize_mysql_connection(uri, environ)
    connect_args = {
        "charset": "utf8mb4",
        "connect_timeout": _mapping_int(
            environ, "MYSQL_CONNECT_TIMEOUT", 10, 1, 300
        ),
        "read_timeout": _mapping_int(environ, "MYSQL_READ_TIMEOUT", 30, 1, 1800),
        "write_timeout": _mapping_int(
            environ, "MYSQL_WRITE_TIMEOUT", 30, 1, 1800
        ),
        **tls_args,
    }
    return normalized_uri, {
        "pool_pre_ping": True,
        "pool_recycle": _mapping_int(
            environ, "MYSQL_POOL_RECYCLE", 1800, 30, 86400
        ),
        "pool_timeout": _mapping_int(environ, "MYSQL_POOL_TIMEOUT", 30, 1, 600),
        "pool_size": _mapping_int(environ, "MYSQL_POOL_SIZE", 5, 1, 100),
        "max_overflow": _mapping_int(
            environ, "MYSQL_MAX_OVERFLOW", 10, 0, 200
        ),
        "connect_args": connect_args,
    }


def _engine_options(uri: str) -> dict:
    return _engine_configuration(uri)[1]


def _runtime_database_policy(uri: str) -> dict[str, bool]:
    mysql = _is_mysql_uri(uri)
    policy = {
        "require_alembic_head": _env_bool("REQUIRE_ALEMBIC_HEAD", mysql),
        "runtime_schema_sync": _env_bool("RUNTIME_SCHEMA_SYNC_ENABLED", not mysql),
        "production_preflight": _env_bool(
            "PRODUCTION_DATABASE_PREFLIGHT_ENABLED", mysql
        ),
    }
    if mysql:
        unsafe = []
        if not policy["require_alembic_head"]:
            unsafe.append("REQUIRE_ALEMBIC_HEAD=0")
        if policy["runtime_schema_sync"]:
            unsafe.append("RUNTIME_SCHEMA_SYNC_ENABLED=1")
        if not policy["production_preflight"]:
            unsafe.append("PRODUCTION_DATABASE_PREFLIGHT_ENABLED=0")
        if unsafe:
            raise RuntimeError(
                "MySQL requires fail-closed runtime safety settings; unsafe: "
                + ", ".join(unsafe)
            )
    return policy

from datetime import timedelta


def _data_dir():
    app_root = os.environ.get('APP_ROOT', '')
    if not app_root and getattr(sys, 'frozen', False):
        app_root = os.path.dirname(sys.executable)
    root = Path(app_root).resolve() if app_root else PROJECT_ROOT
    return root / "data"


def _default_db_uri():
    """Use one project-local data directory for source and packaged runs."""
    data_dir = _data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return "sqlite:///" + str((data_dir / "app.db").resolve())


def _resolve_database_uri() -> str:
    primary = os.environ.get("DATABASE_URL", "").strip()
    secondary = os.environ.get("SQLALCHEMY_DATABASE_URI", "").strip()
    if primary and secondary:
        try:
            same_target = make_url(primary) == make_url(secondary)
        except Exception as exc:
            raise RuntimeError("Database connection URL could not be parsed") from exc
        if not same_target:
            raise RuntimeError(
                "DATABASE_URL conflicts with SQLALCHEMY_DATABASE_URI; configure exactly "
                "one production database target"
            )
    return primary or secondary or _default_db_uri()


def _cors_origins():
    raw = os.environ.get("CORS_ORIGINS", "http://localhost:5888,http://127.0.0.1:5888")
    return [item.strip() for item in raw.split(",") if item.strip()]


_RUNTIME_SECRETS = ensure_runtime_secrets(_data_dir())


class Config:
    SECRET_KEY = _RUNTIME_SECRETS["SECRET_KEY"]

    _RAW_SQLALCHEMY_DATABASE_URI = _resolve_database_uri()
    _ENGINE_CONFIGURATION = _engine_configuration(_RAW_SQLALCHEMY_DATABASE_URI)
    SQLALCHEMY_DATABASE_URI = _ENGINE_CONFIGURATION[0]
    _EXTERNAL_MYSQL = _is_mysql_uri(SQLALCHEMY_DATABASE_URI)
    _RUNTIME_DATABASE_POLICY = _runtime_database_policy(SQLALCHEMY_DATABASE_URI)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = _RUNTIME_SECRETS["JWT_SECRET_KEY"]
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=7)  # 延长令牌过期时间到7天
    JSON_AS_ASCII = False
    CORS_ORIGINS = _cors_origins()
    MAX_CONTENT_LENGTH = 12 * 1024 * 1024
    SCHEDULER_ENABLED = _env_bool("SCHEDULER_ENABLED", True)
    STARTUP_DATA_REPAIRS_ENABLED = _env_bool("STARTUP_DATA_REPAIRS_ENABLED", True)
    BOOTSTRAP_USERS_ENABLED = _env_bool("BOOTSTRAP_USERS_ENABLED", True)
    MYSQL_UNIX_SOCKET = _ENGINE_CONFIGURATION[1]["connect_args"].get(
        "unix_socket", ""
    )
    DATABASE_REQUIRE_TLS = _database_requires_tls(
        SQLALCHEMY_DATABASE_URI, unix_socket=MYSQL_UNIX_SOCKET
    )
    MYSQL_SSL_CA = _ENGINE_CONFIGURATION[1]["connect_args"].get("ssl_ca", "")
    MYSQL_SSL_CERT = _ENGINE_CONFIGURATION[1]["connect_args"].get("ssl_cert", "")
    MYSQL_SSL_KEY = _ENGINE_CONFIGURATION[1]["connect_args"].get("ssl_key", "")
    MYSQLDUMP_PATH = os.environ.get("MYSQLDUMP_PATH", "mysqldump").strip() or "mysqldump"
    REQUIRE_ALEMBIC_HEAD = _RUNTIME_DATABASE_POLICY["require_alembic_head"]
    RUNTIME_SCHEMA_SYNC_ENABLED = _RUNTIME_DATABASE_POLICY["runtime_schema_sync"]
    PRODUCTION_DATABASE_PREFLIGHT_ENABLED = _RUNTIME_DATABASE_POLICY[
        "production_preflight"
    ]
    PRODUCTION_DATABASE_DEEP_CHECKS_ENABLED = _env_bool(
        "PRODUCTION_DATABASE_DEEP_CHECKS_ENABLED", False
    )
    MYSQL_PREFLIGHT_QUERY_TIMEOUT = _env_int(
        "MYSQL_PREFLIGHT_QUERY_TIMEOUT", 10, 1, 300
    )
    MIGRATION_BACKUP_MAX_AGE_MINUTES = _env_int(
        "MIGRATION_BACKUP_MAX_AGE_MINUTES", 60, 1, 1440
    )
    SQLALCHEMY_ENGINE_OPTIONS = _ENGINE_CONFIGURATION[1]

    # 挂单（草稿就诊）过期时长，默认 12 小时
    try:
        PARKED_VISIT_TTL_HOURS = int(os.environ.get("PARKED_VISIT_TTL_HOURS", "12"))
    except (TypeError, ValueError):
        PARKED_VISIT_TTL_HOURS = 12
    # 挂单过期清理任务调度间隔（分钟）
    try:
        PARKED_VISIT_CLEAN_INTERVAL_MINUTES = int(os.environ.get("PARKED_VISIT_CLEAN_INTERVAL_MINUTES", "30"))
    except (TypeError, ValueError):
        PARKED_VISIT_CLEAN_INTERVAL_MINUTES = 30
    SCHEDULER_API_ENABLED = False
