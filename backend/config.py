import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from backend.runtime_secrets import ensure_runtime_secrets


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


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


def _cors_origins():
    raw = os.environ.get("CORS_ORIGINS", "http://localhost:5888,http://127.0.0.1:5888")
    return [item.strip() for item in raw.split(",") if item.strip()]


_RUNTIME_SECRETS = ensure_runtime_secrets(_data_dir())


class Config:
    SECRET_KEY = _RUNTIME_SECRETS["SECRET_KEY"]

    _RAW_SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("SQLALCHEMY_DATABASE_URI")
        or _default_db_uri()
    )
    SQLALCHEMY_DATABASE_URI = _ensure_mysql_utf8mb4(_RAW_SQLALCHEMY_DATABASE_URI)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = _RUNTIME_SECRETS["JWT_SECRET_KEY"]
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=7)  # 延长令牌过期时间到7天
    JSON_AS_ASCII = False
    CORS_ORIGINS = _cors_origins()
    MAX_CONTENT_LENGTH = 12 * 1024 * 1024
    SCHEDULER_ENABLED = True
    STARTUP_DATA_REPAIRS_ENABLED = True
    SQLALCHEMY_ENGINE_OPTIONS = (
        {"pool_pre_ping": True, "connect_args": {"charset": "utf8mb4"}}
        if isinstance(SQLALCHEMY_DATABASE_URI, str) and SQLALCHEMY_DATABASE_URI.startswith("mysql")
        else {"pool_pre_ping": True, "connect_args": {"timeout": 15}}
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
