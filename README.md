<div align="center">

[中文](README.md) | [English](README.en.md)

# 校医务室诊疗管理系统

面向学校医务室的诊疗、处方、收费、库存与统计一体化系统

[![Version](https://img.shields.io/badge/version-open0.0.22-red)](docs/开发日志-open0.0.22.md)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![Vue](https://img.shields.io/badge/Vue-3-42b883)](https://vuejs.org)
[![Database](https://img.shields.io/badge/Database-SQLite%20%7C%20MySQL-336791)](docs/部署与维护说明.md)
[![License](https://img.shields.io/badge/License-AGPL--3.0-blue)](LICENSE)

</div>

## 当前状态

`open0.0.22` 为文档维护版本，记录 Go 重构版后端的备份修复、财务性能优化与 MySQL 验收（Go 源码暂未入库）；Python 成品的生产候选版本仍为 `open0.0.21`，不代表目标生产环境已经验收。

| 项目 | 当前结果 |
| --- | --- |
| 后端测试 | 244 项通过；1 项 Linux `/proc` 测试在 Windows 跳过 |
| 前端构建 | Vite 生产构建通过，1,693 个模块 |
| 依赖安全 | Python 与 npm 生产依赖均为 0 个已知漏洞 |
| 本地 SQLite | 生产预检 0 blocking、1 个非阻断扩展列 warning |
| 历史业务库 | 仍有 1,227 条外键孤儿，必须审批后在隔离副本处置 |
| 目标 MySQL | TLS、恢复、PITR、故障转移和回退 RTO 尚待目标环境验收 |

完整边界与签字项见[生产上线执行清单](docs/生产上线执行清单-2026-07-15.md)。

## open0.0.22 重点

- Go 重构版后端：MySQL 模式下备份改为导出真正的 MySQL 逻辑备份（一致性快照、毫秒精度，还原验证 13 张表行数一致）。
- 财务接口性能优化：看板/趋势/分类/导出从 271ms+ 降至 8~62ms，并修复分类接口日期参数失效、时区偏移等缺陷。
- JWT 未配置密钥时改用随机临时密钥，移除硬编码开发密钥。
- 代码审查 7 项反馈全部落实，L2 安全扫描无发现。
- Go 源码暂不上传，本版本仅同步维护记录与版本文档。

详细变更见[开发日志 open0.0.22](docs/开发日志-open0.0.22.md)。

## open0.0.21 重点

- 修复 Gitee `main`、分支和 PR 流水线，使其执行真实测试、审计与前端构建。
- GitHub Linux 发布动态校验唯一 Alembic head 和全部迁移资源，不再依赖旧 revision 常量。
- 增加完整 Python 依赖约束锁，并替换已撤回的传递依赖版本。
- 通过根目录 `VERSION` 统一标签、Linux 包、Windows 资源与启动版本。
- 明确 Python 3.11、Node.js 22.12 和官方 Linux 制品 glibc 2.35+ 的支持边界。

详细变更见[开发日志 open0.0.21](docs/开发日志-open0.0.21.md)。

## 核心能力

| 角色/模块 | 主要能力 |
| --- | --- |
| 医生 | 患者检索、快速/完整接诊、ICD-10 辅助诊断、处方、单独购药、模板、历史病历 |
| 护士 | 处方审核与执行、收费、撤销、药品/耗材管理、整散装库存、盘点与出库报表 |
| 管理员 | 用户与人员档案、药品与诊疗项目、营收统计、库存报表、系统设置、操作日志 |
| 财务 | 营收看板、日报/月报/年报、出库报表、药品价格只读查询 |
| 系统 | 多角色权限、账号停用与令牌失效、审计追踪、库存流水、健康检查、备份与迁移门禁 |

核心业务流程：

```text
患者建档/检索 -> 医生接诊开方 -> 护士审核执行 -> 收费与库存扣减 -> 营收/库存统计
```

## 技术栈

| 层级 | 技术与边界 |
| --- | --- |
| 后端 | Python 3.11+、Flask、SQLAlchemy、JWT、Waitress |
| 前端 | Vue 3、Element Plus、Vite、Axios、Pinia |
| 数据库 | SQLite 默认；MySQL Community Server 8.0.21+ |
| 迁移 | Alembic forward-only 迁移；生产升级必须绑定已验证备份 |
| 制品 | Windows EXE、Linux tar.gz、AppImage |

## 快速开始

### Windows 候选包

1. 将 `.env.production.example` 复制为 EXE 同目录的 `.env` 并选择数据库。
2. 首次启动前执行数据库预检：

```powershell
& '.\医务室管理系统.exe' --check-database
```

3. 预检无 blocking 后启动 EXE，浏览器访问 `http://127.0.0.1:5000`。

正式开放访问时应保持应用监听 `127.0.0.1`，通过 HTTPS 反向代理发布。当前 Windows 候选 EXE 尚需可信代码签名后才能正式对外分发。

### Linux 制品

官方 CI 制品在 Ubuntu 22.04 构建，要求 Linux x86_64、glibc 2.35+；tar 包的进程管理脚本还需要 `flock`。

```bash
tar xzf medical-room-v0.0.21-linux-x86_64.tar.gz
cd medical-room-v0.0.21-linux-x86_64
./run.sh start
./run.sh status
./run.sh log
```

AppImage：

```bash
chmod +x medical-room-v0.0.21-linux-x86_64.AppImage
./medical-room-v0.0.21-linux-x86_64.AppImage
```

从源码构建：

```bash
# Python 3.11+，Node.js 22.12+
bash build_linux.sh
```

### 源码开发

在项目根目录创建后端环境：

```powershell
python -m venv backend\.venv
& backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
& backend\.venv\Scripts\python.exe -m backend.init_db
& backend\.venv\Scripts\python.exe -m backend.run
```

启动前端开发服务器：

```powershell
Set-Location frontend
npm ci
npm run dev
```

运行后端全量测试：

```powershell
& backend\.venv\Scripts\python.exe run_backend_tests.py
```

## 首次账号与密钥

系统按需创建 `admin`、`doctor`、`nurse` 三个基础账号。首次密码来自 `BOOTSTRAP_PASSWORD`；未配置时生成随机临时密码并写入启动日志。首次登录后应立即修改密码，财务账号由管理员创建。

未配置 `SECRET_KEY` 和 `JWT_SECRET_KEY` 时，系统会在 `data/.runtime-secrets.json` 生成并复用随机密钥。该文件和数据库、日志、备份都属于敏感运行数据，不得提交到 Git 或随公开制品分发。

## 生产部署边界

- 生产配置从 `.env.production.example` 开始，禁止提交真实 `.env`、证书私钥或数据库密码。
- MySQL 运行账号仅授予模型表 `SELECT/INSERT/UPDATE/DELETE`；迁移账号必须独立。
- 远程 MySQL 强制 verified TLS、当前 Alembic head、只读预检和受保护迁移入口。
- 每个候选版本必须恢复真实备份到隔离库，完成升级、预检、业务冒烟和数据对账。
- 多实例前必须完成业务幂等约束和并发压力测试；收费作为正式财务账时应先完成 `Numeric/Decimal` 迁移评估。
- MySQL 开始写入后不得回切冻结的旧 SQLite，失败时应从已验证备份或 PITR 恢复到新库。

详细命令和回退流程见[部署与维护说明](docs/部署与维护说明.md)。

## 文档

### 使用与开发

| 文档 | 内容 |
| --- | --- |
| [项目介绍](docs/项目介绍.md) | 目标、角色和业务流程 |
| [系统使用说明书](docs/系统使用说明书.md) | 基础操作说明 |
| [二次开发快速入门](docs/二次开发快速入门.md) | 环境、启动和常见改动入口 |
| [代码结构说明](docs/代码结构说明.md) | 目录和模块职责 |
| [架构说明](docs/架构说明.md) | 状态机、库存和模块交互 |
| [API 接口清单](docs/接口清单.md) | 按角色整理的接口 |

### 发布与运维

| 文档 | 内容 |
| --- | --- |
| [open0.0.22 开发日志](docs/开发日志-open0.0.22.md) | Go 版备份修复、财务优化与 MySQL 验收记录 |
| [open0.0.21 开发日志](docs/开发日志-open0.0.21.md) | 本轮 CI、依赖锁、版本和上线资料改动 |
| [部署与维护说明](docs/部署与维护说明.md) | SQLite/MySQL 部署、迁移、备份与回退 |
| [生产上线执行清单](docs/生产上线执行清单-2026-07-15.md) | 数据处置、目标环境、灰度和 Go/No-Go |
| [生产环境检查报告](docs/生产环境检查与前期部署-2026-07-14.md) | open0.0.20 成品与本机 MySQL 验收基线 |
| [MySQL 发布加固记录](docs/开发日志-2026-07-13-MySQL生产发布加固.md) | 预检、迁移和成品门禁设计 |

更多历史设计与开发记录位于 [`docs/`](docs/)。

## 版本摘要

| 版本 | 日期 | 摘要 |
| --- | --- | --- |
| [open0.0.22](docs/开发日志-open0.0.22.md) | 2026-07-31 | Go 版 MySQL 备份修复、财务性能优化与验收记录 |
| [open0.0.21](docs/开发日志-open0.0.21.md) | 2026-07-15 | 修复发布流水线，锁定依赖，统一版本，建立上线清单 |
| [open0.0.20](docs/开发日志-open0.0.20.md) | 2026-06-24 | 库存流水、单独购药、职工优惠和营收分页 |
| [open0.0.19](docs/开发日志-open0.0.19.md) | 2026-06-23 | 旧数据库字段兼容修复 |

## 参与开发

提交改动前请运行后端测试、前端生产构建和依赖审计，并为数据库或发布配置变化补充回归测试与文档。生产发布相关改动以[上线执行清单](docs/生产上线执行清单-2026-07-15.md)为准。

## 许可证

项目使用 [GNU Affero General Public License v3.0](LICENSE)。修改后对外分发或通过网络提供服务时，须按 AGPL-3.0 提供对应源代码。
