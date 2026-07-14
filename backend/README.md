# 后端（Flask）

## 环境要求
- Python 3.10+（推荐并由 CI 验证：3.11）

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
- 可选：使用 MySQL 8.0.21+（参考仓库根目录 `init_database.sql` 与 `docs/部署与维护说明.md`）

从项目根目录执行只读生产预检：

```bash
python scripts/check_production_database.py
```

远程 MySQL 在连接前要求 verified TLS。所有 MySQL 都强制要求当前 Alembic head、
只读生产预检并关闭运行时隐式 schema 同步，危险环境变量覆盖会直接失败。正式 schema 升级使用
`python run_prod.py --migrate-database --backup-file <backup.zip> --yes`；
`backend.migration_app:create_app` 仅供隔离验证和底层 Alembic 工具调用。不要用会写入开发初始化数据的 `init_db.py` 代替生产迁移。
MySQL URL query 仅允许 `charset`、`unix_socket` 和文档化的 `ssl_*` 项；连接目标、凭据、超时、连接时 SQL 及未知 query 会在连接前阻断。允许项会转入直接 PyMySQL 参数，engine 初始化前的应用配置不保留用户 query；框架可能补回固定的 `charset=utf8mb4`。自定义 `connect_args` 也不能覆盖目标。
迁移 ZIP 的 manifest 必须处于允许时效内，并与当前 MySQL `server_uuid`、Alembic head
及查询成功后得到的 GTID 状态一致；默认最大时效为 60 分钟，整个迁移窗口必须保持停写。GTID 查询错误会阻断备份与迁移，只有成功返回空值才表示 GTID 未启用。

SQLite 到 MySQL 搬迁默认只做 dry-run：

```bash
python backend/migrate_to_mysql.py --source data/app.db
```

只有停写后，才能把 dry-run 输出的 SHA-256 传给 `--execute --yes
--expected-source-sha256=<digest>`。迁移器会拒绝版本不一致、字段丢失、任何实际外键悬空、
模型表与扩展表交叉外键、非 strict session、只读目标或任何非 InnoDB 模型表。

开发配置可从根目录 `.env.example` 开始。生产打包入口会在未配置密钥时生成
`data/.runtime-secrets.json`，不要复制或提交该文件。

## 结构
- `app/api/`：按角色划分接口（admin/doctor/nurse/auth）
- `app/models/`：数据模型
- `migrations/`：Alembic 迁移脚本
