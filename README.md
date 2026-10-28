<div align="center">

[中文](README.md) | [English](README.en.md)

# 校医务室诊疗管理系统

**面向学校医务室的诊疗、处方、收费、库存与统计一体化系统**

![Version](https://img.shields.io/badge/version-open0.0.22-red)
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

## Linux 生产部署（systemd + nginx + MySQL）

以下流程已在 Ubuntu 26.04 / Python 3.14 / MySQL 8.4 / nginx 1.28 上完整跑通。

### 目录与依赖

- 代码和数据盘可以放在独立卷（含 NTFS），但 **virtualenv 必须建在 ext4**：NTFS 默认没有可执行位，venv 里的脚本无法运行。
- 需要 Python 3.11+、Node.js 22.12+、MySQL 8.0.21+、nginx。

```bash
python3 -m venv ~/venvs/medical-room
~/venvs/medical-room/bin/pip install -r backend/requirements.txt
```

### 配置 `.env`

从 `.env.production.example` 复制为项目根目录的 `.env`（权限 `600`），至少确认：

| 变量 | 值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `mysql+pymysql://...` | 本机 127.0.0.1 可省略 TLS |
| `REQUIRE_ALEMBIC_HEAD` | `1` | MySQL 上 fail-closed，必须开启 |
| `RUNTIME_SCHEMA_SYNC_ENABLED` | `0` | 禁止运行时自动改表 |
| `PRODUCTION_DATABASE_PREFLIGHT_ENABLED` | `1` | 启动时执行只读预检 |
| `SERVER_HOST` | `127.0.0.1` | 只监听回环，由 nginx 对外发布 |
| `TRUST_PROXY_HEADERS` | `1` | 反代场景必须，否则限流与审计只能看到 127.0.0.1 |

### 升级数据库并构建前端

```bash
cd backend && ../venvs/medical-room/bin/flask db upgrade && cd ..
cd frontend && npm ci && npm run build && cd ..
rm -rf dist && cp -r frontend/dist dist
```

`dist/` 必须是真正的构建产物。系统会跳过仍引用 `/src/main.*` 的 Vite 开发入口目录，避免线上加载开发版 `index.html`。

### systemd

```ini
# /etc/systemd/system/medical-room.service
[Unit]
Description=Medical Room Management System
After=network-online.target mysql.service
Wants=network-online.target
Requires=mysql.service
# 数据在独立卷上时补上：RequiresMountsFor=/data/yws

[Service]
User=vincrnt
WorkingDirectory=/data/yws
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/home/vincrnt/venvs/medical-room/bin/python run_prod.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now medical-room
systemctl is-active medical-room
```

如果项目放在独立数据盘上（例如按 UUID 挂载的 NTFS），请同时配置 `.mount` 单元，并让服务通过 `RequiresMountsFor=` 依赖该路径，否则重启后服务会在空目录上启动失败。

### nginx（80 跳转 HTTPS）

```nginx
server {
    listen 80 default_server;
    server_name _;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl default_server;
    http2 on;
    server_name _;

    ssl_certificate     /etc/nginx/ssl/medical-room.crt;
    ssl_certificate_key /etc/nginx/ssl/medical-room.key;
    ssl_protocols TLSv1.2 TLSv1.3;

    client_max_body_size 64m;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_read_timeout 120s;
    }
}
```

内网可用自签 CA：先 `openssl req -x509` 生成 CA，再签发带 `subjectAltName=IP:<服务器IP>` 的服务器证书（有效期建议不超过 397 天），最后把 CA 公钥分发给客户端导入受信任根。未安装 CA 的客户端会提示证书不受信任。

### 部署自检

```bash
curl -k https://127.0.0.1/api/health/live
curl -k https://127.0.0.1/api/health/ready
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/   # 期望 301
```

再验证客户端 IP 透传：连续 5 次错误登录应依次返回 `401…429`，且本机直连 `127.0.0.1:5000` 的失败计数与局域网来源相互独立。

### 本次部署遇到的问题与处理

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 页面白屏，浏览器加载 `/src/main.js` | 服务命中了源码目录里的 Vite 开发版 `index.html` | 构建产物放到 `dist/`；代码已改为只接受构建版 index |
| 限流不生效，操作日志 IP 全是 `127.0.0.1` | Waitress 3 默认清除 `X-Forwarded-*`，ProxyFix 拿不到头 | `.env` 设置 `TRUST_PROXY_HEADERS=1`，代码已联动 Waitress 保留该头 |
| 重启后服务启动失败或目录为空 | 数据盘开机未挂载 | 配置 `.mount` 单元并给服务加 `RequiresMountsFor=` |
| JWT 立即过期、日志时间错乱 | 主板时钟漂移且未启用 NTP | `timedatectl set-ntp true`，必要时先手动校准 |
| `mysqldump` 备份报 `PROCESS` 权限不足 | 备份账号缺少 `PROCESS` 权限 | 使用本机 root socket，或单独授予备份账号该权限 |
| venv 内脚本提示 `Permission denied` | venv 建在 NTFS 分区 | 把 venv 移到了 ext4 |
| 旧 SQLite 库导入被拒绝 | 存在废弃字段与外键孤儿 | 先在隔离副本升级到 Alembic head、处置孤儿并删废弃列，再执行 `migrate_to_mysql.py` |

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

`open0.0.22` 为当前维护版本；Python 成品的生产候选版本为 `open0.0.21`。

| 项目 | 结果 |
| --- | --- |
| 后端测试 | 259 项全部通过，1 项因 Windows 无原生 /proc 语义跳过 |
| 前端测试/构建 | Vitest 8/8 通过，Vite 生产构建通过 |
| 依赖安全 | Python 与 npm 生产依赖均为 0 个已知漏洞 |
| 本地 SQLite | 生产预检 0 blocking、1 个非阻断警告 |
| 历史业务库 | 仍有 1,227 条外键孤儿，须审批后在隔离副本处置 |
| 目标 MySQL | TLS、恢复、PITR、故障转移与回退 RTO 尚待目标环境验收 |

近期版本：

| 版本 | 日期 | 摘要 |
| --- | --- | --- |
| open0.0.22 | 2026-07-31 | 维护版本 |
| [open0.0.21](docs/开发日志-open0.0.21.md) | 2026-07-15 | 修复发布流水线、锁定依赖、统一版本、建立上线清单 |
| [open0.0.20](docs/开发日志-open0.0.20.md) | 2026-06-24 | 库存流水、单独购药、职工优惠和营收分页 |
| [open0.0.19](docs/开发日志-open0.0.19.md) | 2026-06-23 | 旧数据库字段兼容修复 |

更多历史开发与设计记录位于 [`docs/`](docs/)。

## 许可证

项目使用 [GNU Affero General Public License v3.0](LICENSE)。修改后对外分发或通过网络提供服务时，须按 AGPL-3.0 提供对应源代码。
