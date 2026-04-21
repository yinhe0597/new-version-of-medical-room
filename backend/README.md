# 后端（Flask）

## 环境要求
- Python 3.8+（推荐 3.10+）

## 启动（开发环境）
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt

# 初始化数据库结构与基础账号（admin/doctor/nurse，默认密码 123456）
python init_db.py

# 启动开发服务器（默认 http://127.0.0.1:5000）
python run.py
```

## 数据库
- 默认：未设置 `DATABASE_URL` 时使用 SQLite（落盘在 `instance/app.db`）
- 可选：使用 MySQL（参考仓库根目录 `init_database.sql` 与 `docs/部署与维护说明.md`）

## 结构
- `app/api/`：按角色划分接口（admin/doctor/nurse/auth）
- `app/models/`：数据模型
- `migrations/`：Alembic 迁移脚本
