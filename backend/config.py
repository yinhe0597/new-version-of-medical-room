import os
import sys

def _ensure_mysql_utf8mb4(uri: str) -> str:
    if not isinstance(uri, str) or not uri:
        return uri
    if not uri.startswith("mysql"):
        return uri
    if "charset=" in uri.lower():
        return uri
    if "?" in uri:
        return uri + "&charset=utf8mb4"
    return uri + "?charset=utf8mb4"

from datetime import timedelta

def _default_db_uri():
    """Calculate default database URI based on APP_ROOT for deployment safety."""
    app_root = os.environ.get('APP_ROOT', '')
    if app_root:
        return "sqlite:///" + os.path.join(app_root, 'data', 'app.db')
    if getattr(sys, 'frozen', False):
        return "sqlite:///" + os.path.join(os.path.dirname(sys.executable), 'data', 'app.db')
    return "sqlite:///" + os.path.abspath("app.db")

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-change-me"

    _RAW_SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("SQLALCHEMY_DATABASE_URI")
        or _default_db_uri()
    )
    SQLALCHEMY_DATABASE_URI = _ensure_mysql_utf8mb4(_RAW_SQLALCHEMY_DATABASE_URI)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") or "dev-jwt-secret-change-me"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=7)  # 延长令牌过期时间到7天
    JSON_AS_ASCII = False
    SQLALCHEMY_ENGINE_OPTIONS = (
        {"pool_pre_ping": True, "connect_args": {"charset": "utf8mb4"}}
        if isinstance(SQLALCHEMY_DATABASE_URI, str) and SQLALCHEMY_DATABASE_URI.startswith("mysql")
        else {"pool_pre_ping": True}
    )

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
