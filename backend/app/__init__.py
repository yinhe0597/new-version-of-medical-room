from flask import Flask, abort, jsonify, request, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
import sqlalchemy
import os
import sys
import ipaddress
from pathlib import Path

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()

# 挂单过期清理任务调度器（Flask-APScheduler）
try:
    from flask_apscheduler import APScheduler
    scheduler = APScheduler()
except Exception:  # pragma: no cover - 依赖未安装时不阻断启动
    scheduler = None


def _clean_expired_parked_visits(app):
    """清理过期挂单记录。"""
    try:
        from datetime import datetime, timezone
        with app.app_context():
            from backend.app.models import ParkedVisit
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            ParkedVisit.query.filter(ParkedVisit.expires_at <= now).delete(synchronize_session=False)
            db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        app.logger.exception("Failed to clean expired parked visits")


def _mysql_legacy_type_upgrades(dialect, table, existing_columns):
    """Return narrowly scoped MySQL type upgrades for known legacy schemas."""
    if dialect.name not in {"mysql", "mariadb"}:
        return []

    columns_by_name = {column["name"]: column for column in existing_columns}
    target_columns = []

    if table.name == "user":
        existing = columns_by_name.get("password_hash")
        target = table.c.get("password_hash")
        existing_type = existing and existing.get("type")
        existing_length = getattr(existing_type, "length", None)
        target_length = getattr(target.type, "length", None) if target is not None else None
        type_name = getattr(existing_type, "__visit_name__", "").upper()
        if (
            existing is not None
            and target is not None
            and type_name == "VARCHAR"
            and isinstance(existing_length, int)
            and isinstance(target_length, int)
            and existing_length < target_length
        ):
            target_columns.append((existing, target, None))

    if table.name == "patient":
        for column_name in ("name_pinyin", "name_initials"):
            existing = columns_by_name.get(column_name)
            target = table.c.get(column_name)
            existing_type = existing and existing.get("type")
            type_name = getattr(existing_type, "__visit_name__", "").upper()
            target_length = getattr(target.type, "length", None) if target is not None else None
            if (
                existing is not None
                and target is not None
                and type_name == "TEXT"
                and isinstance(target_length, int)
            ):
                target_columns.append((existing, target, target_length))

    preparer = dialect.identifier_preparer
    table_name = preparer.quote(table.name)
    upgrades = []
    for existing, target, checked_length in target_columns:
        column_name = preparer.quote(target.name)
        type_sql = target.type.compile(dialect=dialect)
        nullable_sql = " NULL" if existing.get("nullable", True) else " NOT NULL"
        upgrades.append({
            "column_name": target.name,
            "sql": (
                f"ALTER TABLE {table_name} MODIFY COLUMN {column_name} "
                f"{type_sql}{nullable_sql}"
            ),
            "max_length": checked_length,
            "max_length_sql": (
                f"SELECT MAX(CHAR_LENGTH({column_name})) FROM {table_name}"
                if checked_length is not None else None
            ),
        })
    return upgrades


def _sync_model_schema(app):
    """Create missing tables/columns from the current ORM model, idempotently.

    Alembic remains the preferred migration mechanism. This compatibility layer
    keeps legacy SQLite and MySQL installations bootable when their historical
    migration state is incomplete. It intentionally never drops data or columns.
    """
    with app.app_context():
        db.create_all()
        engine = db.engine
        preparer = engine.dialect.identifier_preparer

        with engine.begin() as conn:
            inspector = sqlalchemy.inspect(conn)
            existing_tables = set(inspector.get_table_names())

            for table in db.metadata.sorted_tables:
                if table.name not in existing_tables:
                    continue

                reflected_columns = inspector.get_columns(table.name)
                existing_columns = {column["name"] for column in reflected_columns}
                for column in table.columns:
                    if column.name in existing_columns:
                        continue
                    if column.primary_key:
                        raise RuntimeError(
                            f"Cannot add missing primary key column {table.name}.{column.name} automatically"
                        )

                    type_sql = column.type.compile(dialect=engine.dialect)
                    nullable_sql = "" if column.nullable else " NOT NULL"
                    if not column.nullable and column.server_default is None:
                        raise RuntimeError(
                            f"Missing non-null column {table.name}.{column.name} requires an explicit migration"
                        )
                    default_sql = ""
                    if column.server_default is not None:
                        default_sql = f" DEFAULT {column.server_default.arg}"

                    table_name = preparer.quote(table.name)
                    column_name = preparer.quote(column.name)
                    conn.execute(sqlalchemy.text(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} "
                        f"{type_sql}{default_sql}{nullable_sql}"
                    ))

                # create_all() cannot alter existing column types. Upgrade only
                # the exact legacy MySQL shapes known to block current hashes or
                # pinyin indexes; other type differences require Alembic.
                for upgrade in _mysql_legacy_type_upgrades(
                    engine.dialect, table, reflected_columns
                ):
                    if upgrade["max_length_sql"] is not None:
                        actual_length = conn.execute(
                            sqlalchemy.text(upgrade["max_length_sql"])
                        ).scalar()
                        if actual_length is not None and actual_length > upgrade["max_length"]:
                            raise RuntimeError(
                                f"Cannot safely convert {table.name}.{upgrade['column_name']} "
                                f"to VARCHAR({upgrade['max_length']}): existing data is "
                                f"{actual_length} characters long"
                            )
                    conn.execute(sqlalchemy.text(upgrade["sql"]))

            # Historical databases may have columns but miss non-unique indexes.
            refreshed = sqlalchemy.inspect(conn)
            for table in db.metadata.sorted_tables:
                if table.name not in existing_tables:
                    continue
                existing_indexes = {
                    item["name"] for item in refreshed.get_indexes(table.name) if item.get("name")
                }
                for index in table.indexes:
                    if index.name and index.name not in existing_indexes:
                        index.create(bind=conn, checkfirst=True)


def _assert_database_at_alembic_head(app):
    """Fail before runtime writes when a production database is not at head."""
    from alembic.script import ScriptDirectory

    migrations_dir = Path(
        app.config.get("ALEMBIC_MIGRATIONS_DIR")
        or Path(__file__).resolve().parents[1] / "migrations"
    ).resolve()
    if not migrations_dir.is_dir():
        raise RuntimeError(f"Alembic migrations directory is missing: {migrations_dir}")

    expected_heads = set(ScriptDirectory(str(migrations_dir)).get_heads())
    if not expected_heads:
        raise RuntimeError(f"No Alembic head found in {migrations_dir}")

    with app.app_context():
        with db.engine.connect() as conn:
            inspector = sqlalchemy.inspect(conn)
            if not inspector.has_table("alembic_version"):
                current_heads = set()
            else:
                current_heads = set(
                    conn.execute(
                        sqlalchemy.text("SELECT version_num FROM alembic_version")
                    ).scalars()
                )

    if current_heads != expected_heads:
        current_label = ", ".join(sorted(current_heads)) or "<unversioned>"
        expected_label = ", ".join(sorted(expected_heads))
        raise RuntimeError(
            "Database schema is not at the required Alembic head "
            f"(current={current_label}, expected={expected_label}). Stop all "
            "application instances, take a verified backup, and run the "
            "dedicated migration command before starting production."
        )
    return expected_heads


def _configure_database(app):
    with app.app_context():
        engine = db.engine
        if engine.dialect.name != "sqlite":
            return

        def set_sqlite_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=15000")
            cursor.close()

        sqlalchemy.event.listen(engine, "connect", set_sqlite_pragmas)
        with engine.connect() as conn:
            conn.execute(sqlalchemy.text("PRAGMA foreign_keys=ON"))
            conn.execute(sqlalchemy.text("PRAGMA busy_timeout=15000"))


def _runtime_config_bool(app, name):
    value = app.config.get(name)
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise RuntimeError(f"{name} must be configured as a boolean")


_MYSQL_RUNTIME_ALLOWED_QUERY_OPTIONS = {
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
_MYSQL_RUNTIME_ALLOWED_CONNECT_ARGS = {
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
_MYSQL_RUNTIME_TIMEOUT_LIMITS = {
    "connect_timeout": (1, 300),
    "read_timeout": (1, 1800),
    "write_timeout": (1, 1800),
}


def _assert_safe_mysql_runtime_configuration(app, *, enforce_runtime_policy=True):
    """Reject unsafe MySQL connection settings before an engine is created."""

    uri = app.config.get("SQLALCHEMY_DATABASE_URI")
    if isinstance(uri, str) and not uri.lower().startswith("mysql"):
        return
    try:
        url = sqlalchemy.engine.make_url(uri)
    except Exception as error:
        if isinstance(uri, str) and uri.lower().startswith("mysql"):
            raise RuntimeError("MySQL connection URL could not be parsed") from error
        return
    if url.get_backend_name().lower() != "mysql":
        return
    if url.drivername.lower() != "mysql+pymysql":
        raise RuntimeError("Only the mysql+pymysql driver is supported")
    if not url.database:
        raise RuntimeError("MySQL connection URL must include a database name")

    query_names = {key.lower(): key for key in url.query}
    unsupported_query_names = sorted(
        set(query_names) - _MYSQL_RUNTIME_ALLOWED_QUERY_OPTIONS
    )
    if unsupported_query_names:
        raise RuntimeError(
            "MySQL runtime URL contains unsupported query options: "
            + ", ".join(unsupported_query_names)
        )
    raw_query_marker = (
        isinstance(uri, str) and "?" in uri.split("#", 1)[0]
    )
    if query_names or raw_query_marker:
        raise RuntimeError(
            "MySQL runtime URL must be normalized to direct connection arguments "
            "before application startup"
        )

    unsafe = []
    engine_options = app.config.get("SQLALCHEMY_ENGINE_OPTIONS") or {}
    if not isinstance(engine_options, dict):
        raise RuntimeError("MySQL SQLALCHEMY_ENGINE_OPTIONS must be a mapping")
    connect_args = engine_options.get("connect_args", {})
    if not isinstance(connect_args, dict):
        raise RuntimeError("MySQL connect_args must be a mapping")
    unsupported_connect_args = sorted(
        str(name)
        for name in connect_args
        if name not in _MYSQL_RUNTIME_ALLOWED_CONNECT_ARGS
    )
    if unsupported_connect_args:
        raise RuntimeError(
            "MySQL runtime connect_args contain unsupported options: "
            + ", ".join(unsupported_connect_args)
        )

    charset = connect_args.get("charset")
    if not isinstance(charset, str) or charset.lower() != "utf8mb4":
        unsafe.append("connect_args.charset=<invalid>")
    for name, (minimum, maximum) in _MYSQL_RUNTIME_TIMEOUT_LIMITS.items():
        value = connect_args.get(name)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not minimum <= value <= maximum
        ):
            unsafe.append(f"connect_args.{name}=<invalid>")

    string_arguments = (
        "unix_socket",
        "ssl_ca",
        "ssl_cert",
        "ssl_key",
        "ssl_key_password",
    )
    for name in string_arguments:
        value = connect_args.get(name)
        if value is None:
            continue
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            unsafe.append(f"connect_args.{name}=<invalid>")
    for name in ("ssl_verify_cert", "ssl_verify_identity"):
        if name in connect_args and not isinstance(connect_args[name], bool):
            unsafe.append(f"connect_args.{name}=<invalid>")

    ssl_cert = connect_args.get("ssl_cert")
    ssl_key = connect_args.get("ssl_key")
    if bool(ssl_cert) != bool(ssl_key):
        unsafe.append("connect_args.ssl_cert/ssl_key=<incomplete>")
    if connect_args.get("ssl_key_password") and not ssl_key:
        unsafe.append("connect_args.ssl_key_password=<key-missing>")

    unix_socket = connect_args.get("unix_socket")
    declared_socket = app.config.get("MYSQL_UNIX_SOCKET")
    if declared_socket:
        if (
            not isinstance(declared_socket, str)
            or declared_socket != declared_socket.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in declared_socket)
        ):
            unsafe.append("MYSQL_UNIX_SOCKET=<invalid>")
        elif declared_socket != unix_socket:
            raise RuntimeError(
                "MYSQL_UNIX_SOCKET must match connect_args.unix_socket"
            )
    if unix_socket:
        if url.host is not None or url.port is not None:
            raise RuntimeError(
                "MySQL unix_socket must not also configure an authority host or port"
            )
    elif not url.host:
        unsafe.append("MySQL host or unix_socket=<missing>")

    host = (url.host or "").strip().lower().rstrip(".")
    local = bool(unix_socket) or host == "localhost"
    if not local:
        try:
            local = ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = False
    if not local:
        if not (
            connect_args.get("ssl_ca")
            and connect_args.get("ssl_verify_cert") is True
            and connect_args.get("ssl_verify_identity") is True
        ):
            unsafe.append("verified TLS connection arguments=<missing>")
        try:
            tls_required = _runtime_config_bool(app, "DATABASE_REQUIRE_TLS")
        except RuntimeError:
            unsafe.append("DATABASE_REQUIRE_TLS=<invalid>")
        else:
            if not tls_required:
                unsafe.append("DATABASE_REQUIRE_TLS=0")

    if enforce_runtime_policy:
        required_settings = {
            "REQUIRE_ALEMBIC_HEAD": True,
            "RUNTIME_SCHEMA_SYNC_ENABLED": False,
            "PRODUCTION_DATABASE_PREFLIGHT_ENABLED": True,
        }
        for name, expected in required_settings.items():
            try:
                actual = _runtime_config_bool(app, name)
            except RuntimeError:
                unsafe.append(f"{name}=<invalid>")
                continue
            if actual is not expected:
                unsafe.append(f"{name}={int(actual)}")
    if unsafe:
        raise RuntimeError(
            "MySQL requires fail-closed runtime safety settings; unsafe: "
            + ", ".join(unsafe)
        )

def create_app(config_class=None, *, initialize_database=True):
    if config_class is None:
        from backend.config import Config
        config_class = Config

    app = Flask(__name__)
    app.config.from_object(config_class)
    if app.config.get('MAX_CONTENT_LENGTH') is None:
        app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024
    _assert_safe_mysql_runtime_configuration(
        app, enforce_runtime_policy=initialize_database
    )

    # Only configured development origins need cross-origin API access. Packaged
    # deployments serve the SPA and API from the same origin.
    CORS(app, resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", [])}})

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    @jwt.token_verification_loader
    def verify_token_version(_jwt_header, jwt_payload):
        from backend.app.models import User

        try:
            user_id = int(jwt_payload.get("sub"))
            token_version = int(jwt_payload.get("ver", 0))
        except (TypeError, ValueError):
            return False
        user = db.session.get(User, user_id)
        return bool(
            user
            and user.is_active is not False
            and int(user.token_version or 0) == token_version
        )

    @jwt.token_verification_failed_loader
    def token_verification_failed(_jwt_header, _jwt_payload):
        return jsonify({"msg": "登录状态已失效，请重新登录"}), 401

    @app.errorhandler(413)
    def request_too_large(_error):
        return jsonify({"msg": "请求体过大，最大允许 12MB"}), 413

    @app.errorhandler(404)
    def api_not_found(error):
        if request.path.startswith('/api/'):
            return jsonify({"msg": "API endpoint not found"}), 404
        return error

    _configure_database(app)

    from backend.app import models

    if initialize_database and app.config.get("REQUIRE_ALEMBIC_HEAD", False):
        expected_heads = _assert_database_at_alembic_head(app)
        app.config["EXPECTED_ALEMBIC_HEADS"] = tuple(sorted(expected_heads))

    if initialize_database and app.config.get("RUNTIME_SCHEMA_SYNC_ENABLED", True):
        _sync_model_schema(app)

    from backend.app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    if initialize_database and app.config.get("STARTUP_DATA_REPAIRS_ENABLED", True):
        # 历史数据兼容迁移：is_temporary -> patient_type
        with app.app_context():
            with db.engine.begin() as conn:
                result = conn.execute(
                    sqlalchemy.text(
                        "SELECT COUNT(*) FROM patient WHERE patient_type IS NULL OR patient_type = ''"
                    )
                ).fetchone()
                if result and result[0] > 0:
                    conn.execute(sqlalchemy.text(
                        "UPDATE patient SET patient_type = 'temporary' WHERE is_temporary = 1 AND (patient_type IS NULL OR patient_type = '')"
                    ))
                    conn.execute(sqlalchemy.text(
                        "UPDATE patient SET patient_type = 'student' WHERE (is_temporary = 0 OR is_temporary IS NULL) AND (patient_type IS NULL OR patient_type = '')"
                    ))

            from backend.app.services.inventory_ledger import backfill_revoked_inventory_movements
            from backend.app.services.stock_lock import stock_mutation_guard

            with stock_mutation_guard():
                backfilled = backfill_revoked_inventory_movements(app.logger)
            if backfilled:
                app.logger.info("Backfilled %s revoked inventory ledger rows", backfilled)

    # 启动挂单过期清理调度（仅初始化一次）
    if (
        initialize_database
        and scheduler is not None
        and app.config.get("SCHEDULER_ENABLED", True)
        and not getattr(scheduler, '_yws_started', False)
    ):
        try:
            scheduler.init_app(app)
            scheduler.start()
            interval_minutes = int(app.config.get('PARKED_VISIT_CLEAN_INTERVAL_MINUTES', 30) or 30)
            scheduler.add_job(
                id='clean_expired_parked_visits',
                func=_clean_expired_parked_visits,
                args=[app],
                trigger='interval',
                minutes=interval_minutes,
                replace_existing=True,
            )
            scheduler._yws_started = True
            # 启动时立即执行一次清理
            try:
                _clean_expired_parked_visits(app)
            except Exception:
                pass
        except Exception:
            # Scheduler failure should remain visible even though HTTP can start.
            app.logger.exception("Failed to initialize parked-visit scheduler")

    # 静态文件和前端文件支持
    def _get_dist_dir():
        """Get frontend dist directory, with fallback for different environments."""
        if hasattr(sys, '_MEIPASS'):
            d = os.path.join(sys._MEIPASS, 'frontend', 'dist')
            if os.path.isdir(d):
                return d
        # Fallback: relative to APP_ROOT (for onefile mode or dev)
        app_root = os.environ.get('APP_ROOT', '')
        if app_root:
            # 先尝试 dist/，再尝试 frontend/（兼容旧编译输出目录结构）
            for candidate in ('dist', 'frontend'):
                d = os.path.join(app_root, candidate)
                if os.path.isdir(d):
                    return d
        # Dev environment fallback
        return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'frontend', 'dist')

    @app.route('/static/<path:path>')
    def serve_static(path):
        return send_from_directory(os.path.join(_get_dist_dir(), 'assets'), path)

    @app.route('/')
    @app.route('/<path:path>')
    def serve_frontend(path='index.html'):
        if path.startswith('api/'):
            abort(404)
        dist_dir = _get_dist_dir()
        # Try serving the exact file first (JS, CSS, images, etc.)
        full_path = os.path.join(dist_dir, path)
        if path != 'index.html' and not os.path.isfile(full_path):
            # File doesn't exist — this is a Vue Router client-side route,
            # fall back to index.html so the SPA can handle it
            path = 'index.html'
        return send_from_directory(dist_dir, path)

    return app


def create_migration_app(config_class=None):
    """Create an app without mutating schema before Alembic runs."""
    return create_app(config_class, initialize_database=False)
