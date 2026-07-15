<div align="center">

[中文](README.md) | [English](README.en.md)

# Medical Room Management System

Clinic, prescription, payment, inventory, and reporting for school medical rooms

[![Version](https://img.shields.io/badge/version-open0.0.21-red)](docs/开发日志-open0.0.21.md)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![Vue](https://img.shields.io/badge/Vue-3-42b883)](https://vuejs.org)
[![Database](https://img.shields.io/badge/Database-SQLite%20%7C%20MySQL-336791)](docs/部署与维护说明.md)
[![License](https://img.shields.io/badge/License-AGPL--3.0-blue)](LICENSE)

</div>

## Status

`open0.0.21` is a production candidate. Local release gates pass, but the target production environment has not yet been accepted.

| Gate | Result |
| --- | --- |
| Backend | 244 tests passed; one native Linux `/proc` test skipped on Windows |
| Frontend | Vite production build passed with 1,693 modules |
| Dependencies | No known Python or npm production vulnerabilities |
| Local SQLite | Production preflight: 0 blocking, 1 non-blocking extension warning |
| Historical data | 1,227 orphaned foreign-key references still require business approval |
| Target MySQL | TLS, restore, PITR, failover, and rollback RTO acceptance remain open |

See the [production rollout checklist](docs/生产上线执行清单-2026-07-15.md) for the authoritative Go/No-Go status.

## open0.0.21 Highlights

- Repaired Gitee gates for `main`, branches, and pull requests.
- Made the GitHub Linux release discover the Alembic head and all migration resources dynamically.
- Added an exact Python transitive dependency constraint set and removed a yanked dependency release.
- Unified tags, Linux artifacts, Windows version resources, and runtime banners through `VERSION`.
- Documented Python 3.11, Node.js 22.12, and glibc 2.35+ as the supported build/runtime floor for official Linux artifacts.

Full details are in the [open0.0.21 development log](docs/开发日志-open0.0.21.md).

## Capabilities

| Role / Area | Main capabilities |
| --- | --- |
| Doctor | Patient search, quick/full consultation, ICD-10 assistance, prescriptions, templates, visit history |
| Nurse | Prescription review and execution, payment, reversal, inventory, stocktake, outbound reports |
| Admin | Users, patient records, drugs/services, revenue, inventory reports, settings, operation logs |
| Finance | Revenue dashboard and reports, outbound reports, read-only drug pricing |
| Platform | Role isolation, token invalidation, audit trail, inventory ledger, health checks, backup and migration gates |

```text
Patient -> Consultation -> Prescription -> Nurse review -> Payment and dispensing -> Inventory and revenue reports
```

## Stack

| Layer | Technology and support boundary |
| --- | --- |
| Backend | Python 3.11+, Flask, SQLAlchemy, JWT, Waitress |
| Frontend | Vue 3, Element Plus, Vite, Axios, Pinia |
| Database | SQLite by default; MySQL Community Server 8.0.21+ |
| Migration | Forward-only Alembic migrations bound to a verified backup |
| Artifacts | Windows EXE, Linux tar.gz, AppImage |

## Quick Start

### Windows candidate

1. Copy `.env.production.example` to `.env` beside the executable and select the database.
2. Run the preflight before startup:

```powershell
& '.\医务室管理系统.exe' --check-database
```

3. Start only when there are no blocking findings, then open `http://127.0.0.1:5000`.

Keep the app bound to loopback and publish it through an HTTPS reverse proxy. The Windows candidate still requires trusted code signing before public distribution.

### Linux artifacts

Official artifacts are built on Ubuntu 22.04 and require Linux x86_64 with glibc 2.35+. The tar package also requires `flock`.

```bash
tar xzf medical-room-v0.0.21-linux-x86_64.tar.gz
cd medical-room-v0.0.21-linux-x86_64
./run.sh start
./run.sh status
./run.sh log
```

```bash
chmod +x medical-room-v0.0.21-linux-x86_64.AppImage
./medical-room-v0.0.21-linux-x86_64.AppImage
```

Build from source with Python 3.11+ and Node.js 22.12+:

```bash
bash build_linux.sh
```

### Source development

From the repository root on Windows:

```powershell
python -m venv backend\.venv
& backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
& backend\.venv\Scripts\python.exe -m backend.init_db
& backend\.venv\Scripts\python.exe -m backend.run
```

Frontend:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Backend tests:

```powershell
& backend\.venv\Scripts\python.exe run_backend_tests.py
```

## Bootstrap and Secrets

The system creates `admin`, `doctor`, and `nurse` accounts when missing. Their first password comes from `BOOTSTRAP_PASSWORD`; otherwise a random temporary password is written to the startup log. Change it immediately. Finance accounts are created by an administrator.

When `SECRET_KEY` and `JWT_SECRET_KEY` are absent, random stable values are stored in `data/.runtime-secrets.json`. Treat secrets, databases, logs, and backups as sensitive runtime data. Never commit or distribute them with public artifacts.

## Production Boundaries

- Start from `.env.production.example`; never commit production credentials or private keys.
- Give the runtime MySQL account only model-table DML privileges and keep migration credentials separate.
- Remote MySQL requires verified TLS, the current Alembic head, read-only preflight, and the protected migration entry point.
- Restore a real backup to an isolated database and complete upgrade, preflight, smoke, and reconciliation before every cutover.
- Do not switch back to a frozen SQLite database after MySQL accepts writes; recover to a new database through verified backup or PITR.

See the [deployment and maintenance guide](docs/部署与维护说明.md).

## Documentation

| Document | Purpose |
| --- | --- |
| [Project introduction](docs/项目介绍.md) | Goals, roles, and workflows |
| [Development quick start](docs/二次开发快速入门.md) | Setup and common code entry points |
| [Architecture](docs/架构说明.md) | State machines, inventory, and module interaction |
| [API list](docs/接口清单.md) | APIs organized by role |
| [open0.0.21 development log](docs/开发日志-open0.0.21.md) | Release-gate and dependency changes |
| [Deployment guide](docs/部署与维护说明.md) | SQLite/MySQL deployment, migration, backup, rollback |
| [Production rollout checklist](docs/生产上线执行清单-2026-07-15.md) | Target environment, data decisions, canary, Go/No-Go |

Additional historical records are available in [`docs/`](docs/).

## Recent Versions

| Version | Date | Summary |
| --- | --- | --- |
| [open0.0.21](docs/开发日志-open0.0.21.md) | 2026-07-15 | CI repair, dependency lock, unified versioning, rollout checklist |
| [open0.0.20](docs/开发日志-open0.0.20.md) | 2026-06-24 | Inventory ledger, direct purchase, employee discount, revenue pagination |
| [open0.0.19](docs/开发日志-open0.0.19.md) | 2026-06-23 | Legacy database compatibility |

## License

Licensed under [GNU Affero General Public License v3.0](LICENSE). Modified versions distributed or offered as a network service must provide the corresponding source code as required by AGPL-3.0.
