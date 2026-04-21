from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
import sqlalchemy

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
            with app.app_context():
                db.create_all()
    except Exception:
        pass

    return app
