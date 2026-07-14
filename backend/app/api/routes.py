from flask import current_app, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import text
from sqlalchemy.engine import make_url
from threading import Lock
from time import monotonic
from backend.app.api import bp
from backend.app import db
from backend.app.models import User
from backend.app.utils.decorators import role_required


_readiness_warning_lock = Lock()
_last_readiness_warning_at = 0.0
_readiness_cache_init_lock = Lock()
_MYSQL_DEEP_READINESS_TTL_SECONDS = 5.0
_MYSQL_DEEP_READINESS_EXTENSION_KEY = "medical_room_mysql_deep_readiness"


def _mysql_flag(value):
    return str(value).strip().lower() in {"1", "on", "true", "yes"}


def _assert_mysql_runtime_settings(settings, *, expected_database):
    if settings.get("database_name") != expected_database:
        raise RuntimeError("connected database changed")
    read_only_flags = (
        settings.get("read_only"),
        settings.get("super_read_only"),
        settings.get("transaction_read_only"),
    )
    if any(_mysql_flag(value) for value in read_only_flags):
        raise RuntimeError("MySQL writer became read-only")

    sql_modes = {
        value.strip().upper()
        for value in str(settings.get("sql_mode") or "").split(",")
        if value.strip()
    }
    if not sql_modes.intersection({"STRICT_TRANS_TABLES", "STRICT_ALL_TABLES"}):
        raise RuntimeError("MySQL strict mode is no longer enabled")


def _assert_mysql_deep_ready(
    *,
    expected_database,
    expected_heads,
    current_heads,
    grants,
    model_tables,
):
    if set(current_heads) != set(expected_heads):
        raise RuntimeError("Alembic head changed after startup")

    from scripts.check_production_database import evaluate_mysql_grants

    grant_report = {"checks": []}
    evaluate_mysql_grants(
        grant_report,
        grants,
        expected_database,
        model_tables,
        enforce_runtime_least_privilege=True,
    )
    if any(item.get("severity") == "blocking" for item in grant_report["checks"]):
        raise RuntimeError("MySQL runtime grants are no longer safe")


def _assert_mysql_runtime_ready(
    settings,
    *,
    expected_database,
    expected_heads,
    current_heads,
    grants,
    model_tables,
):
    _assert_mysql_runtime_settings(
        settings,
        expected_database=expected_database,
    )
    _assert_mysql_deep_ready(
        expected_database=expected_database,
        expected_heads=expected_heads,
        current_heads=current_heads,
        grants=grants,
        model_tables=model_tables,
    )


def _mysql_deep_readiness_state():
    app = current_app._get_current_object()
    state = app.extensions.get(_MYSQL_DEEP_READINESS_EXTENSION_KEY)
    if state is not None:
        return state
    with _readiness_cache_init_lock:
        state = app.extensions.get(_MYSQL_DEEP_READINESS_EXTENSION_KEY)
        if state is None:
            state = {"lock": Lock(), "record": None}
            app.extensions[_MYSQL_DEEP_READINESS_EXTENSION_KEY] = state
    return state


def _run_mysql_deep_readiness(*, expected_database, expected_heads, model_tables):
    current_heads = db.session.execute(
        text("SELECT version_num FROM alembic_version")
    ).scalars().all()
    grant_rows = db.session.execute(text("SHOW GRANTS FOR CURRENT_USER()")).all()
    _assert_mysql_deep_ready(
        expected_database=expected_database,
        expected_heads=expected_heads,
        current_heads=current_heads,
        grants=(str(row[0]) for row in grant_rows),
        model_tables=model_tables,
    )


def _check_cached_mysql_deep_readiness(
    *,
    expected_database,
    expected_heads,
    model_tables,
):
    fingerprint = (
        expected_database,
        tuple(sorted(str(head) for head in expected_heads)),
        tuple(sorted(str(table) for table in model_tables)),
    )
    state = _mysql_deep_readiness_state()
    with state["lock"]:
        now = monotonic()
        record = state["record"]
        if record is not None:
            cached_fingerprint, expires_at, error_type = record
            if cached_fingerprint == fingerprint and now < expires_at:
                if error_type is not None:
                    raise RuntimeError(
                        "MySQL deep readiness check is temporarily unavailable "
                        f"({error_type})"
                    )
                return

        try:
            _run_mysql_deep_readiness(
                expected_database=expected_database,
                expected_heads=expected_heads,
                model_tables=model_tables,
            )
        except Exception as error:
            state["record"] = (
                fingerprint,
                monotonic() + _MYSQL_DEEP_READINESS_TTL_SECONDS,
                type(error).__name__,
            )
            raise
        state["record"] = (
            fingerprint,
            monotonic() + _MYSQL_DEEP_READINESS_TTL_SECONDS,
            None,
        )


def _check_database_readiness():
    if db.engine.dialect.name != "mysql":
        db.session.execute(text("SELECT 1")).scalar_one()
        return

    settings = db.session.execute(
        text(
            """
            SELECT
                DATABASE() AS database_name,
                @@GLOBAL.read_only AS read_only,
                @@GLOBAL.super_read_only AS super_read_only,
                @@SESSION.transaction_read_only AS transaction_read_only,
                @@SESSION.sql_mode AS sql_mode
            """
        )
    ).mappings().one()
    expected_database = make_url(
        current_app.config["SQLALCHEMY_DATABASE_URI"]
    ).database
    _assert_mysql_runtime_settings(
        dict(settings),
        expected_database=expected_database,
    )
    # Do not hold one pooled connection per waiter while a cache miss performs
    # the single deep check under the application-level lock.
    db.session.rollback()
    _check_cached_mysql_deep_readiness(
        expected_database=expected_database,
        expected_heads=current_app.config.get("EXPECTED_ALEMBIC_HEADS", ()),
        model_tables=db.metadata.tables,
    )


def _recover_failed_readiness_session():
    try:
        db.session.rollback()
        return
    except Exception:
        pass
    try:
        db.session.remove()
        return
    except Exception:
        pass
    try:
        # Last-resort discard: teardown must not retry a broken Session object.
        db.session.registry.clear()
    except Exception:
        pass


@bp.route('/')
def index():
    return "Hello, World!"


@bp.route('/health/live', methods=['GET'])
def health_live():
    return jsonify(status="ok"), 200


@bp.route('/health/ready', methods=['GET'])
def health_ready():
    global _last_readiness_warning_at
    try:
        _check_database_readiness()
    except Exception as error:
        _recover_failed_readiness_session()
        now = monotonic()
        with _readiness_warning_lock:
            if now - _last_readiness_warning_at >= 30:
                current_app.logger.warning(
                    "Database readiness probe failed (%s)", type(error).__name__
                )
                _last_readiness_warning_at = now
        return jsonify(status="not_ready"), 503
    return jsonify(status="ready"), 200

@bp.route('/protected', methods=['GET'])
@jwt_required()
def protected():
    current_user_id = get_jwt_identity()
    user = db.session.get(User, int(current_user_id))
    return jsonify(logged_in_as=user.username), 200

@bp.route('/admin-only', methods=['GET'])
@jwt_required()
@role_required(['admin'])
def admin_only():
    return jsonify(msg="Welcome admin!"), 200

@bp.route('/doctor-only', methods=['GET'])
@jwt_required()
@role_required(['doctor', 'admin'])
def doctor_only():
    return jsonify(msg="Welcome doctor!"), 200
