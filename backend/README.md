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

# 初始化数据库结构与基础账号（密码由 BOOTSTRAP_PASSWORD 或控制台随机生成）
python init_db.py

# 启动开发服务器（默认 http://127.0.0.1:5000）
python run.py
```

## 测试
从项目根目录运行完整后端测试：
```bash
python run_backend_tests.py
```

## 数据库
- 默认：未设置 `DATABASE_URL` 时使用 SQLite（统一落盘在项目 `data/app.db`）
- 可选：使用 MySQL（参考仓库根目录 `init_database.sql` 与 `docs/部署与维护说明.md`）

开发配置可从根目录 `.env.example` 开始。生产打包入口会在未配置密钥时生成
`data/.runtime-secrets.json`，不要复制或提交该文件。

## 结构
- `app/api/`：按角色划分接口（admin/doctor/nurse/auth）
- `app/models/`：数据模型
- `migrations/`：Alembic 迁移脚本
