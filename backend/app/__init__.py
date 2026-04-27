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

    from backend.app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    from backend.app import models

    try:
        uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
        if isinstance(uri, str) and uri.startswith("sqlite"):
            # 检查SQLite数据库文件是否存在
            db_path = uri.replace("sqlite:///", "")
            if not os.path.exists(db_path):
                with app.app_context():
                    db.create_all()
    except Exception:
        pass

    # 静态文件和前端文件支持
    @app.route('/static/<path:path>')
    def serve_static(path):
        if hasattr(sys, '_MEIPASS'):
            static_dir = os.path.join(sys._MEIPASS, 'frontend', 'dist', 'assets')
        else:
            static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'frontend', 'dist', 'assets')
        return send_from_directory(static_dir, path)

    @app.route('/')
    @app.route('/<path:path>')
    def serve_frontend(path='index.html'):
        if hasattr(sys, '_MEIPASS'):
            dist_dir = os.path.join(sys._MEIPASS, 'frontend', 'dist')
        else:
            dist_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'frontend', 'dist')
        return send_from_directory(dist_dir, path)

    return app
