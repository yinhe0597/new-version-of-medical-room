<div align="center">

[中文](README.md) | [English](README.en.md)

# 校医务室诊疗管理系统

**面向学校医务室的诊疗、处方、收费、库存与统计一体化系统**

[![Version](https://img.shields.io/badge/version-open0.0.22-red)](docs/开发日志-open0.0.22.md)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![Vue](https://img.shields.io/badge/Vue-3-42b883)](https://vuejs.org)
[![Database](https://img.shields.io/badge/Database-SQLite%20%7C%20MySQL-336791)](docs/部署与维护说明.md)
[![License](https://img.shields.io/badge/License-AGPL--3.0-blue)](LICENSE)

</div>

---

## 这是什么？

一套给学校医务室用的**门诊工作台**：从患者建档、医生接诊开方，到护士审核收费、药品库存扣减，再到营收统计，全流程都在一个系统里完成。

```text
患者建档/检索 → 医生接诊开方 → 护士审核执行 → 收费与库存扣减 → 营收/库存统计
```

系统内置四种角色，各司其职：

| 角色 | 主要能力 |
| --- | --- |
| 🩺 医生 | 患者检索、快速/完整接诊、ICD-10 辅助诊断、开处方、单独购药、病历模板、历史病历 |
| 💉 护士 | 处方审核与执行、收费与撤销、药品/耗材管理、整散装库存、盘点与出库报表 |
| ⚙️ 管理员 | 用户与人员档案、药品与诊疗项目、营收统计、库存报表、系统设置、操作日志 |
| 💰 财务 | 营收看板、日报/月报/年报、出库报表、药品价格只读查询 |

系统层面还提供多角色权限、账号停用与令牌失效、审计追踪、库存流水、健康检查、备份与迁移等能力。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 后端 | Python 3.11+ · Flask · SQLAlchemy · JWT · Waitress |
| 前端 | Vue 3 · Element Plus · Vite · Axios · Pinia |
| 数据库 | SQLite（默认） / MySQL 8.0.21+ |
| 迁移 | Alembic（forward-only，生产升级需绑定已验证备份） |
| 制品 | Windows EXE · Linux tar.gz · AppImage |

## 快速开始

### 方式一：Windows 候选包（最省事）

1. 将 `.env.production.example` 复制为 EXE 同目录下的 `.env`，按需选择数据库。
2. 首次启动前先做一次数据库预检：

   ```powershell
   & '.\医务室管理系统.exe' --check-database
   ```

3. 预检通过后启动 EXE，浏览器打开 `http://127.0.0.1:5000`。

### 方式二：Linux 制品

要求 Linux x86_64、glibc 2.35+（tar 包还需 `flock`）。

```bash
tar xzf medical-room-v0.0.21-linux-x86_64.tar.gz
cd medical-room-v0.0.21-linux-x86_64
./run.sh start      # 启动
./run.sh status     # 查看状态
./run.sh log        # 查看日志
```

AppImage：

```bash
chmod +x medical-room-v0.0.21-linux-x86_64.AppImage
./medical-room-v0.0.21-linux-x86_64.AppImage
```

### 方式三：从源码跑（开发调试）

后端（Python 3.11+）：

```powershell
python -m venv backend\.venv
& backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
& backend\.venv\Scripts\python.exe -m backend.init_db
& backend\.venv\Scripts\python.exe -m backend.run
```

前端（Node.js 22.12+）：

```powershell
Set-Location frontend
npm ci
npm run dev
```

运行后端全量测试：

```powershell
& backend\.venv\Scripts\python.exe run_backend_tests.py
```

> 提交改动前请运行后端测试、前端生产构建与依赖审计；数据库或发布配置变更需补充回归测试与文档。

## 首次登录与密钥

系统按需创建 `admin`、`doctor`、`nurse` 三个基础账号：

- 首次密码来自环境变量 `BOOTSTRAP_PASSWORD`；未配置时生成随机临时密码并写入启动日志。
- **首次登录后请立即修改密码**；财务账号由管理员创建。

未配置 `SECRET_KEY` / `JWT_SECRET_KEY` 时，系统会在 `data/.runtime-secrets.json` 生成并复用随机密钥。该文件与数据库、日志、备份同属**敏感运行数据**，不要提交到 Git，也不要随制品分发。

## 生产部署须知

正式上线前请确认以下要点，完整边界与签字项见[部署与维护说明](docs/部署与维护说明.md)和[生产上线执行清单](docs/生产上线执行清单-2026-07-15.md)：

- 正式对外访问时应监听 `127.0.0.1`，通过 **HTTPS 反向代理**发布；Windows EXE 需完成可信代码签名后再对外分发。
- 生产配置从 `.env.production.example` 开始；**禁止提交**真实 `.env`、证书私钥或数据库密码。
- 远程 MySQL 强制 verified TLS、数据库结构须与当前迁移版本一致（Alembic head）、只读预检与受保护迁移入口。
- 每个候选版本必须恢复真实备份到隔离库，完成升级、预检、业务冒烟与数据对账。

## 文档导航

| 你想…… | 看这里 |
| --- | --- |
| 了解目标、角色与流程 | [项目介绍](docs/项目介绍.md) |
| 学基础操作 | [系统使用说明书](docs/系统使用说明书.md) |
| 参与二次开发 | [二次开发快速入门](docs/二次开发快速入门.md) · [代码结构说明](docs/代码结构说明.md) · [架构说明](docs/架构说明.md) |
| 查接口清单 | [接口清单](docs/接口清单.md) |
| 部署、备份与运维 | [部署与维护说明](docs/部署与维护说明.md) |
| 准备生产上线 | [生产上线执行清单](docs/生产上线执行清单-2026-07-15.md) |

## 当前版本与状态

`open0.0.22` 为文档维护版本，记录 Go 重构版后端的备份修复、财务性能优化与 MySQL 验收（Go 源码暂未入库）；Python 成品的生产候选版本仍为 `open0.0.21`。

| 项目 | 结果 |
| --- | --- |
| 后端测试 | 244 项中 243 通过，1 项存量失败待排查 |
| 前端测试/构建 | Vitest 6/6 通过，Vite 生产构建通过 |
| 依赖安全 | Python 与 npm 生产依赖均为 0 个已知漏洞 |
| 本地 SQLite | 生产预检 0 blocking、1 个非阻断警告 |
| 历史业务库 | 仍有 1,227 条外键孤儿，须审批后在隔离副本处置 |
| 目标 MySQL | TLS、恢复、PITR、故障转移与回退 RTO 尚待目标环境验收 |

近期版本：

| 版本 | 日期 | 摘要 |
| --- | --- | --- |
| [open0.0.22](docs/开发日志-open0.0.22.md) | 2026-07-31 | Go 版 MySQL 备份修复、财务性能优化与验收记录 |
| [open0.0.21](docs/开发日志-open0.0.21.md) | 2026-07-15 | 修复发布流水线、锁定依赖、统一版本、建立上线清单 |
| [open0.0.20](docs/开发日志-open0.0.20.md) | 2026-06-24 | 库存流水、单独购药、职工优惠和营收分页 |
| [open0.0.19](docs/开发日志-open0.0.19.md) | 2026-06-23 | 旧数据库字段兼容修复 |

更多历史开发与设计记录位于 [`docs/`](docs/)。

## 许可证

项目使用 [GNU Affero General Public License v3.0](LICENSE)。修改后对外分发或通过网络提供服务时，须按 AGPL-3.0 提供对应源代码。
