<div align="center">

[![中文](https://img.shields.io/badge/Lang-中文-red?style=for-the-badge)](README.md)
[![English](https://img.shields.io/badge/Lang-English-blue?style=for-the-badge)](README.en.md)

---

# 🏥 Medical Room Management System

**校医务室诊疗管理系统**

---

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Backend-Flask-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![Vue.js](https://img.shields.io/badge/Frontend-Vue%203-4FC08D?logo=vue.js&logoColor=white)](https://vuejs.org)
[![Element Plus](https://img.shields.io/badge/UI-Element%20Plus-409EFF?logo=element&logoColor=white)](https://element-plus.org)
[![SQLite](https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white)](https://sqlite.org)
[![License](https://img.shields.io/badge/License-AGPLv3-blue?logo=opensourceinitiative&logoColor=white)](LICENSE)
[![Version](https://img.shields.io/badge/Version-open0.0.17-red?logo=semver&logoColor=white)]()

---

> 🎯 **One-stop clinic management platform designed for school medical rooms**
>
> Covers the full workflow: **Registration → Consultation → Prescription → Review → Payment → Inventory**

</div>

---

> ⚠️ **Project Status: Active Development**
> 
> The system is still in **small-scale trial and feedback collection**. Now supports **Windows + Linux** dual-platform deployment (tar.gz / AppImage). **MySQL + Docker** migration planned for late 2026. Currently runs on SQLite, suitable for standalone or small LAN setups.
>
> Despite active development, **the current version can smoothly run the full workflow** and can be used in real business scenarios.
>
> ✅ **This system is free forever.** If you encounter anyone selling this system directly (rather than technical services), please be cautious.
>
> 📬 Issues and feedback are typically responded to **within 2 working days**; accepted suggestions are implemented and released **within 3 working days**.

---

## ✨ Introduction

A **full-stack clinic and medication/consumables management system** designed for university and school medical rooms, covering the complete business loop: "Consultation & Prescription → Nurse Review → Dispensing & Settlement → Inventory & Revenue Statistics."

The system features **Doctor / Nurse / Admin / Finance** four independent interfaces with clear role-based permissions.

### 🌟 Core Advantages

- 🔄 **Full Workflow Closure**: From patient registration to prescription settlement, every step is system-supported
- 🎒 **Three-Type Material Management**: Medications + Services + Consumables, unified yet separate
- 🔒 **Security First**: Backend strong validation on prescription submission and review
- 💊 **Smart Inventory**: Supports "whole pack + split unit" linked inbound and deduction
- 🏗️ **Role Clarity**: Admin / Doctor / Nurse / Finance — capabilities separated by role
- 🚀 **Easy Deployment**: SQLite zero-config startup, PyInstaller single-file packaging
- 🔄 **Smooth Upgrade**: Automatic detection and migration of missing columns and tables
- 📊 **Data Insights**: Revenue stats (drugs/services/consumables split), drug consumption, multi-dimension reports

---

## 📋 Feature Overview

<details>
<summary>Click to expand full feature list</summary>

| Module | Feature | Description |
|:---:|------|------|
| 🩺 **Doctor** | Smart Consultation | Quick/full consultation modes; `##` medical history template shortcut |
| 🩺 **Doctor** | ICD-10 Diagnosis | Pinyin/abbreviation/code multi-dimension search |
| 🩺 **Doctor** | Medical History | View all patient visit records and details |
| 🩺 **Doctor** | Record Editing | Edit history records with change tracking |
| 🩺 **Doctor** | Scattered Dosing | Auto-calculate total dosage, support half-tablet/split units |
| 🩺 **Doctor** | IV Compatibility | Independent compatibility management, solute + solution binding |
| 🩺 **Doctor** | Usage Options | Added `--` empty option for ointments and external use |
| 💊 **Nurse** | Prescription Handling | Review, confirm payment, reject operations |
| 💊 **Nurse** | Visit History | Multi-dimension filtering (nurse/doctor/date/name/status), paginated |
| 💊 **Nurse** | Transaction Revoke | Final-state revocation with auto inventory restore |
| 💊 **Nurse** | Smart Inventory | Custom threshold alerts, scattered drug quick filter |
| 💊 **Nurse** | Inventory Management | Unified drugs/consumables, monthly reports |
| 💊 **Nurse** | Consumables | Add/remove consumables during prescription execution |
| 💰 **Finance** | Dashboard | Revenue summary cards, 30-day trend chart, revenue type pie chart |
| 💰 **Finance** | Revenue Reports | Daily/monthly/yearly stats, doctor/nurse filter, Excel export |
| 💰 **Finance** | Drug Outbound | Outbound records with date/doctor/keyword filter |
| 💰 **Finance** | Drug Prices (Read-only) | View prices without edit permissions |
| 📊 **Admin** | Statistics & Reports | Revenue split by drugs/services/consumables, Excel export |
| 📊 **Admin** | Drug Management | Full CRUD for drugs/services/consumables, expiry date management |
| 📊 **Admin** | Patient Records | Student/employee/temporary personnel management |
| 📊 **Admin** | Operation Logs | Full audit trail for all system operations |
| 👤 **System** | Role Permissions | 4 independent interfaces with role isolation |
| 🔧 **System** | Smooth Upgrade | Auto database migration, zero data loss |

</details>

---

## 🛠️ Tech Stack

| Layer | Technology | Version | Notes |
|:---:|------|------|------|
| 🖥️ Backend | Python / Flask / SQLAlchemy / JWT | 3.8+ | |
| 🎨 Frontend | Vue 3 / Element Plus / Vite / Axios | Vue 3.x | |
| 💾 Database | SQLite (current) / MySQL (planned) | — | Auto DB creation + schema migration, zero-config |
| 🔧 Migration | Alembic + auto column migration | — | |
| 📦 Deployment | PyInstaller (Windows + Linux) | — | Windows EXE / Linux tar.gz + AppImage |

---

## 🚀 Quick Start

### Option 1: Windows (Recommended)

```
1. Download the latest Release package
2. Double-click 医务室管理系统.exe
3. Open http://localhost:5000 in browser
```

### Option 2: Linux Deployment

Two packaging formats for different scenarios:

**Format A: tar.gz (Server / Remote Machines)**
```bash
tar xzf medical-room-v0.0.16-linux.tar.gz
cd medical-room-v0.0.16-linux
./run.sh start     # Start in background
./run.sh stop      # Stop
./run.sh restart   # Restart
./run.sh status    # Check status
./run.sh log       # Tail logs
```

**Format B: AppImage (Desktop Linux / Portable)**
```bash
chmod +x medical-room-v0.0.16-linux.AppImage
./medical-room-v0.0.16-linux.AppImage
```

> 💡 Database and logs are auto-created in the same directory as the executable — no manual setup needed.

**Build Linux packages from source:**
```bash
# Requires Python 3.8+ and Node.js 16+
bash build_linux.sh
# Output in dist_linux/ (both tar.gz and AppImage)
```

### Option 3: Source Code Development

**Backend (Python 3.8+)**
```bash
cd backend
python -m venv .venv
# Activate: Windows: .venv\Scripts\activate | Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
python init_db.py
python run.py
```

**Frontend (Node.js 18+)**
```bash
cd frontend
npm install
npm run dev
```

### 🔑 Default Accounts

| Role | Username | Password |
|:---:|:---:|:---:|
| Admin | `admin` | `123456` |
| Doctor | `doctor` | `123456` |
| Nurse | `nurse` | `123456` |
| Finance | `finance` | `123456` |

---

## 🔄 System Workflow

```
Consultation → Doctor Prescribes → Nurse Reviews → Dispense & Settlement → Inventory Deduction → Revenue Stats
```

---

## 📖 Documentation

| Document | Description |
|------|------|
| 📌 [Project Introduction (中文)](docs/项目介绍.md) | Goals, architecture, roles, key workflows |
| 🚀 [Deployment Guide (中文)](docs/部署与维护说明.md) | Environment setup, dev launch, production deploy |
| 💻 [Dev Guide (中文)](docs/二次开发指南.md) | Tech stack, frontend-backend integration, DB migration |
| 📂 [Code Structure (中文)](docs/代码结构说明.md) | Directory structure and responsibilities |
| 🏗️ [Architecture (中文)](docs/架构说明.md) | Module interaction, state machines, review logic |
| 🔌 [API List (中文)](docs/接口清单.md) | All APIs organized by role |

---

## 📋 Changelog

### 🏷️ open0.0.17 (2026-06-12) 🔍🔁📋🗓️🔑

**Nurse Inbound "Lost" Items Fix & Expiry Date Support & Admin Password Change:**
- 🔍 **Zero-Stock Items Visible**: Fixed doctor search silently hiding drugs/consumables with stock=0, now marked `out_of_stock` with gray tag
- 🔁 **409 Duplicate Inbound UX**: Confirm dialog now offers "Go to Restock" button navigating to inventory list
- 📋 **Nurse List Sorting**: Added `Drug.id DESC` secondary sort, newly inbound items appear on first page
- 🗓️ **Inbound Expiry Date**: Nurse drug/consumable inbound forms now support optional expiry date picker
- 🔑 **Admin Password Change**: New `POST /auth/change-password` API endpoint with JWT auth

---

### 🏷️ open0.0.16 (2026-06-11) 🐧🚀

**Linux Dual-Format Packaging & Cross-Platform Support:**
- 🐧 **Linux Packaging**: New `medical_room_linux.spec` PyInstaller config for Linux x86_64
- 📦 **tar.gz Archive**: Self-contained package with `run.sh` service manager (start/stop/restart/status/log)
- 📦 **AppImage Single File**: Double-click to run, no installation needed, portable via USB
- 🔧 **One-Click Build**: `build_linux.sh` automates dependency install, frontend build, PyInstaller packaging
- 🖥️ **Cross-Platform**: `run_prod.py` adapts console output for Windows/Linux, safe stdin handling

---

### 🏷️ open0.0.16 (2026-06-09) 🔐🚀

- 🔐 **Nurse Report Permissions**: Added `'nurse'` role to revenue stats and drug outbound report endpoints
- 🚀 **Full Rebuild**: `vite build` + `pyinstaller` full package build

---

### 🏷️ open0.0.15 (2026-06-08) 🗓️⚠️👩‍⚕️

- 🗓️ **Drug Expiry Management**: New `expiry_date` field on Drug model, date picker in management UI, validation prevents past dates
- ⚠️ **Smart Inventory Expiry Alerts**: New "expiry threshold days" input (1-365), returns soon-to-expire and expired drugs sorted by remaining days
- 🏷️ **Expiry Status Tags**: Three-color tags in drug list — expired (red), expiring within 30 days (yellow), normal (green)
- 👩‍⚕️ **Nurse UI Cleanup**: Hidden "Packaging" and "Scattered Price" columns in nurse drug management
- 📦 **Smart Inventory Category Filter**: New checkboxes for "Stock Warning" and "Expiry Warning" categories — filter individually or combined, unchecking hides corresponding parameters and results
- 📖 **Bilingual README**: Added `README.en.md` with language toggle badges
- 📋 **Feature Table Collapsed**: Feature overview now uses `<details>` tag, collapsed by default

> 📝 Details (中文): [开发日志-open0.0.15.md](docs/开发日志-open0.0.15.md)

---

### 🏷️ open0.0.14 (2026-06-03) 🔄📝📦🔧💰🛡️

- 🔄 **Revoked Prescription Re-edit**: "Re-prescribe" button now available for revoked records — load original prescription as draft, modify and resubmit
- 📝 **Medical History Template**: Type `##` in history input to pop up template list and insert content
- 📦 **Storage Location**: New `storage_location` field (A-Z + custom suffix), all drug lists sorted by location
- 🔧 **Build Fix**: Frontend directory `frontend/` → `dist/`, backend now supports both names
- 💰 **Finance Role**: New `finance` role with dedicated dashboard (3 new APIs: summary, trend, revenue-by-type)
- 🔒 **Patient Name Masking**: Finance role sees masked names (`Zhang San` → `Z***`) in reports and Excel exports
- 🛡️ **Permission Cleanup**: Admin dashboard gets finance view; finance loses operation log access

> 📝 Details (中文): [开发日志-open0.0.14.md](docs/开发日志-open0.0.14.md)

### 🏷️ open0.0.13 (2026-05-29) 🐛📝🛡️

- 🐛 **Critical Fix**: Missing `monthly_sort_order` DDL migration caused 500 errors on all joinedload Drug queries
- 📝 **Receipt Snapshot**: Payment receipt data now persisted as JSON snapshot, viewable even after drug deletion
- 🛡️ **Null Safety**: `GET /nurse/visits/<id>` handles deleted drugs with null safety checks
- 🛡️ **Print API**: `PUT /nurse/payments/<id>/print` now has try/except error handling

> 📝 Details (中文): [开发日志-open0.0.13.md](docs/开发日志-open0.0.13.md)

*(Full changelog available in Chinese version)*

---

## 🤝 Contributing

Issues and Pull Requests are welcome!

1. Fork this repository
2. Create feature branch: `git checkout -b feature/your-feature`
3. Commit changes: `git commit -m 'feat: add some feature'`
4. Push: `git push origin feature/your-feature`
5. Submit a Pull Request

---

## 📄 License

This project is licensed under **GNU Affero General Public License v3.0 (AGPL-3.0)**.

Key requirements:
- ✅ **Free to use** — for personal, institutional, or commercial purposes
- ✅ **Modifications must be open-sourced** — if you modify and distribute or provide network services, you must publish the full source code
- ✅ **Web application clause** — ensures modified versions running on servers also give back to the community

> 💡 In short: You can use and deploy this system freely, and build upon it. But if you use it commercially or provide it as a service, **you must contribute your improvements back to the community**.

Full license text: [LICENSE](LICENSE)

---

## ☕ Support

<div align="center">

<p><em>If you like this project, you can buy the author a coffee ☕</em></p>

</div>

---

<div align="center">

**Made with ❤️ for School Medical Rooms**

</div>
