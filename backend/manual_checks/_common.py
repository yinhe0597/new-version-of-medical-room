"""manual_checks 共享辅助：路径引导与凭据读取。

仓库内不保留硬编码口令：
- HTTP 验收脚本用 require_password(role) 从 MEDICAL_<ROLE>_PASSWORD 读取，缺失即退出；
- 本地 app 验收脚本用 check_password() 读取 MEDICAL_CHECK_PASSWORD，
  未设置时在本次运行内随机生成（不落盘）。
"""

import os
import secrets
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def ensure_repo_root_on_path() -> None:
    """保证可以 import backend.app（替代旧脚本里硬编码的 sys.path.append）。"""
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def api_base_url() -> str:
    return os.environ.get("MEDICAL_API_BASE_URL", "http://127.0.0.1:5000/api")


def require_password(role: str) -> str:
    """读取真实账号口令（如 MEDICAL_ADMIN_PASSWORD），缺失时终止脚本。"""
    env_name = f"MEDICAL_{role.upper()}_PASSWORD"
    value = os.environ.get(env_name)
    if not value:
        print(f"缺少环境变量 {env_name}，请先设置 {role} 账号口令后重试。")
        raise SystemExit(2)
    return value


def check_password() -> str:
    """临时测试用户口令：优先 MEDICAL_CHECK_PASSWORD，否则本次运行随机生成。"""
    return os.environ.get("MEDICAL_CHECK_PASSWORD") or secrets.token_urlsafe(12)
