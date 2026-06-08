from flask import Flask, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
import sqlalchemy
import os
import sys

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
        from datetime import datetime
        with app.app_context():
            from backend.app.models import ParkedVisit
            now = datetime.utcnow()
            ParkedVisit.query.filter(ParkedVisit.expires_at <= now).delete(synchronize_session=False)
            db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

def _ensure_sqlite_column(app, table_name, column_name, column_def):
    uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    if not isinstance(uri, str) or not uri.startswith("sqlite"):
        return
    try:
        with app.app_context():
            with db.engine.connect() as conn:
                exists = conn.execute(
                    sqlalchemy.text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name=:name"
                    ),
                    {"name": table_name},
                ).fetchone()
                if not exists:
                    return
                cols = conn.execute(sqlalchemy.text(f"PRAGMA table_info({table_name})")).fetchall()
                col_names = {row[1] for row in cols}
                if column_name in col_names:
                    return
                conn.execute(sqlalchemy.text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}"))
    except Exception:
        return

def create_app(config_class=None):
    from backend.config import Config

    if config_class is None:
        config_class = Config

    app = Flask(__name__)
    app.config.from_object(config_class)

    # 初始化CORS
    CORS(app)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    _ensure_sqlite_column(app, "patient", "is_temporary", "BOOLEAN DEFAULT 0")
    _ensure_sqlite_column(app, "patient", "age", "INTEGER")
    _ensure_sqlite_column(app, "patient", "id_card", "VARCHAR(20)")
    _ensure_sqlite_column(app, "patient", "counselor_name", "VARCHAR(64)")

    # visit 表新增列
    _ensure_sqlite_column(app, "visit", "verified_by", "INTEGER")
    _ensure_sqlite_column(app, "visit", "verified_at", "DATETIME")
    _ensure_sqlite_column(app, "visit", "rejected_by", "INTEGER")
    _ensure_sqlite_column(app, "visit", "rejected_at", "DATETIME")
    _ensure_sqlite_column(app, "visit", "reject_reason", "TEXT")
    _ensure_sqlite_column(app, "visit", "special_note", "TEXT")
    _ensure_sqlite_column(app, "visit", "revoked_by", "INTEGER")
    _ensure_sqlite_column(app, "visit", "revoked_at", "DATETIME")
    _ensure_sqlite_column(app, "visit", "revoke_reason", "TEXT")

    # prescription_item 表新增列
    _ensure_sqlite_column(app, "prescription_item", "original_price", "FLOAT")
    _ensure_sqlite_column(app, "prescription_item", "original_amount", "FLOAT")
    _ensure_sqlite_column(app, "prescription_item", "new_price", "FLOAT")
    _ensure_sqlite_column(app, "prescription_item", "new_amount", "FLOAT")
    _ensure_sqlite_column(app, "prescription_item", "modified_by", "INTEGER")
    _ensure_sqlite_column(app, "prescription_item", "modified_at", "DATETIME")
    _ensure_sqlite_column(app, "prescription_item", "modify_reason", "TEXT")
    _ensure_sqlite_column(app, "prescription_item", "is_scattered", "BOOLEAN DEFAULT 0")
    _ensure_sqlite_column(app, "prescription_item", "purchase_cost", "FLOAT DEFAULT 0.0")
    _ensure_sqlite_column(app, "prescription_item", "is_intravenous", "BOOLEAN DEFAULT 0")
    _ensure_sqlite_column(app, "prescription_item", "infusion_group", "INTEGER")
    _ensure_sqlite_column(app, "prescription_item", "infusion_dosage_value", "FLOAT")
    _ensure_sqlite_column(app, "prescription_item", "infusion_dosage_unit", "VARCHAR(10)")
    _ensure_sqlite_column(app, "prescription_item", "infusion_method", "VARCHAR(50)")

    # drug 表新增列
    _ensure_sqlite_column(app, "drug", "type", "INTEGER DEFAULT 1")
    _ensure_sqlite_column(app, "drug", "purchase_price", "FLOAT DEFAULT 0.0")
    _ensure_sqlite_column(app, "drug", "has_scattered", "BOOLEAN DEFAULT 0")
    _ensure_sqlite_column(app, "drug", "scattered_price", "FLOAT")
    _ensure_sqlite_column(app, "drug", "conversion_rate", "INTEGER")
    _ensure_sqlite_column(app, "drug", "variant_type", "VARCHAR(20)")
    _ensure_sqlite_column(app, "drug", "stock_group_code", "VARCHAR(36)")
    _ensure_sqlite_column(app, "drug", "unit_amount", "INTEGER")
    _ensure_sqlite_column(app, "drug", "base_name", "VARCHAR(128)")
    _ensure_sqlite_column(app, "drug", "storage_location", "VARCHAR(10)")
    _ensure_sqlite_column(app, "drug", "expiry_date", "DATE")

    # payment 表新增列
    _ensure_sqlite_column(app, "payment", "receipt_printed", "BOOLEAN DEFAULT 0")
    _ensure_sqlite_column(app, "payment", "is_employee_discount", "BOOLEAN DEFAULT 0")
    _ensure_sqlite_column(app, "payment", "original_amount", "FLOAT")
    _ensure_sqlite_column(app, "payment", "receipt_snapshot", "TEXT")

    from backend.app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    from backend.app import models

    try:
        uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
        if isinstance(uri, str) and uri.startswith("sqlite"):
            # 即使数据库文件已存在，也调用 db.create_all()
            # 确保旧数据库中缺失的新表能被创建（不会影响已有表和数据）
            with app.app_context():
                db.create_all()
    except Exception:
        pass

    # 启动挂单过期清理调度（仅初始化一次）
    if scheduler is not None and not getattr(scheduler, '_yws_started', False):
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
            # 调度器初始化失败不应阻断应用启动
            pass

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
        dist_dir = _get_dist_dir()
        # Try serving the exact file first (JS, CSS, images, etc.)
        full_path = os.path.join(dist_dir, path)
        if path != 'index.html' and not os.path.isfile(full_path):
            # File doesn't exist — this is a Vue Router client-side route,
            # fall back to index.html so the SPA can handle it
            path = 'index.html'
        return send_from_directory(dist_dir, path)

    return app
