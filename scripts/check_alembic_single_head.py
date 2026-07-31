"""Static Alembic single-head gate (no database required).

下沉自 .github/workflows/build-linux-release.yml 的内联校验段：确认 Alembic
迁移链只有一个 head，且与 scripts/validate_mysql_alembic.py 声明的 CURRENT_HEAD
一致，同时验证 PyMySQL 驱动可导入。

本地等价入口（与 CI 行为一致）：

    python scripts/check_alembic_single_head.py

退出码：0 通过；1 校验失败（多 head 或 head 不匹配）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alembic.config import Config
from alembic.script import ScriptDirectory
import pymysql
from sqlalchemy.dialects.mysql import pymysql as mysql_pymysql  # noqa: F401  确保打包/驱动可用

from scripts.validate_mysql_alembic import CURRENT_HEAD

MIGRATIONS_DIR = ROOT / "backend" / "migrations"


def check_single_head() -> int:
    config = Config(str(MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    heads = ScriptDirectory.from_config(config).get_heads()
    if heads != [CURRENT_HEAD]:
        print(f"Expected one Alembic head {CURRENT_HEAD}, got {heads}", file=sys.stderr)
        return 1
    print(f"MySQL static gate passed: PyMySQL {pymysql.__version__}, head {heads[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(check_single_head())
