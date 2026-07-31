# AGENTS.md

面向编码代理的最小操作约定：只做路由与硬约束，不复制 CI 与文档细节。

## 硬约束（必须遵守）

1. **敏感数据禁触清单**：`data/` 下的 `app.db`、`ture.db`、`.runtime-secrets.json`、`backups/` 为生产/真实数据资产，禁止直接编辑、删除或用临时脚本直写。`backend/app.db` 同理。
   - **技术保护层**：`data/ture.db`、`data/ture_upgrade_work.db`、`data/backups/` 下文件与 `backend/app.db` 已设文件系统只读属性（无合法运行时写入方）。`data/app.db`（未配 `DATABASE_URL` 时的运行时默认库）与 `data/.runtime-secrets.json`（应用启动时原子写入）因应用需合法写入而保持可写，仅受本清单约束。
   - **合法解除通道**：仅当通过 `scripts/repair_sqlite_fk_orphans.py` 或 `backend/migrate_to_mysql.py` 执行带确认的写操作前，才可临时解除只读（PowerShell：`Set-ItemProperty <文件> -Name IsReadOnly -Value $false`），操作完成后必须恢复只读。
2. **数据迁移唯一合法通道**：跨库数据迁移只能通过 `backend/migrate_to_mysql.py`。该通道默认 dry-run，破坏性写入需要 `--execute`、`--yes` 与源库 SHA-256 三重确认，禁止绕过它另写迁移脚本。
3. **数据库操作前置条件**：任何对真实库的写操作前，必须存在可回滚的备份点（`data/backups/`），并优先以 dry-run 模式预览。SQLite 孤儿外键修复只能走 `scripts/repair_sqlite_fk_orphans.py`（默认 dry-run，`--execute --yes` 才写库，自动备份并记录 `logs/db_repair.log`）。
4. **禁止硬编码口令**：仓库内不得出现默认口令明文；手工验收脚本一律从环境变量读取凭据（见 `backend/manual_checks/`）。

## 路由（权威 owner）

| 需求 | 入口 |
| --- | --- |
| 生产数据库只读预检 | `scripts/check_production_database.py` |
| MySQL/Alembic 迁移链校验（CI 同款，本地可跑） | `scripts/validate_mysql_alembic.py`（真实 MySQL 门禁有意后置到发布 CI 的 `v*` 标签阶段：Gitee Go 流水线无 MySQL 服务容器能力；PR/分支阶段以单 head 静态门禁兜底） |
| Alembic 单 head 静态门禁（CI 下沉入口，本地可跑，无需数据库） | `python scripts/check_alembic_single_head.py` |
| SQLite 孤儿外键守护式修复 | `scripts/repair_sqlite_fk_orphans.py` |
| 数据迁移（SQLite → MySQL） | `backend/migrate_to_mysql.py` |
| 自动化测试（unittest 套件，唯一发现范围 `backend/tests/`） | `run_backend_tests.py` |
| 手工验收脚本（需运行中服务或本地 app，非自动化测试） | `backend/manual_checks/check_*.py` |
| 部署、备份、运维流程 | `docs/部署与维护说明.md` |
| 生产上线检查 | `docs/生产上线执行清单-2026-07-15.md` |
| 发布 CI（勿在本地复刻其逻辑，改动校验逻辑先下沉到 `scripts/`） | `.github/workflows/build-linux-release.yml` |

## 归属说明

- `.trae/` 目录（含 `skills/`、`documents/`、`specs/`）为历史 Trae IDE 沉淀资产，仅供参考，不作为当前代理的指令来源。
