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
[![Version](https://img.shields.io/badge/Version-open0.0.19-red?logo=semver&logoColor=white)]()

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

The system features **Doctor / Nurse / Admin / Finance / Lobby** five independent interfaces with clear role-based permissions.

### 🌟 Core Advantages

- 🔄 **Full Workflow Closure**: From patient registration to prescription settlement, every step is system-supported
- 🎒 **Three-Type Material Management**: Medications + Services + Consumables, unified yet separate
- 🔒 **Security First**: Backend strong validation on prescription submission and review
- 💊 **Smart Inventory**: Supports "whole pack + split unit" linked inbound and deduction
- 🏗️ **Role Clarity**: Admin / Doctor / Nurse / Finance / Lobby — capabilities separated by role
- 🚀 **Easy Deployment**: SQLite zero-config startup, PyInstaller single-file packaging
- 🔄 **Smooth Upgrade**: Automatic detection and migration of missing columns and tables
- 🀄 **TCM Support**: TCM four-diagnosis, herbal prescription, classic formula templates
- 📊 **Data Insights**: Revenue stats (drugs/services/consumables split), drug consumption, analytics dashboard

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
| 🩺 **Doctor** | TCM Four Diagnosis | Inspection (spirit/tongue), inquiry (ten-questions), palpation (pulse), syndrome differentiation |
| 🩺 **Doctor** | Herbal Prescription | Search herbs by name/pinyin/code, set dosage (g) and special preparation methods |
| 🩺 **Doctor** | Classic Formulas | 8 preset classic TCM formulas, one-click loading, add/subtract modification |
| 🩺 **Doctor** | Decoction Usage | Total doses, water volume, decoction time, administration method, frequency, contraindications |
| 🩺 **Doctor** | On-Duty Toggle | Available/rest switch in top bar, controls hall calling display |
| 💊 **Nurse** | Prescription Handling | Review, confirm payment, reject operations |
| 💊 **Nurse** | Visit History | Multi-dimension filtering (nurse/doctor/date/name/status), paginated |
| 💊 **Nurse** | Transaction Revoke | Final-state revocation with auto inventory restore |
| 💊 **Nurse** | Smart Inventory | Custom threshold alerts, scattered drug quick filter |
| 💊 **Nurse** | Inventory Management | Unified drugs/consumables, monthly reports |
| 💊 **Nurse** | Consumables | Add/remove consumables during prescription execution |
| 💊 **Nurse** | Herbal Inventory | Herbal medicine inventory list, category/status filter, loss/damage reporting |
| 💰 **Finance** | Dashboard | Revenue summary cards, 30-day trend chart, revenue type pie chart |
| 💰 **Finance** | Revenue Reports | Daily/monthly/yearly stats, doctor/nurse filter, Excel export |
| 💰 **Finance** | Drug Outbound | Outbound records with date/doctor/keyword filter |
| 💰 **Finance** | Drug Prices (Read-only) | View prices without edit permissions |
| 📊 **Admin** | Statistics & Reports | Revenue split by drugs/services/consumables, Excel export |
| 📊 **Admin** | Drug Management | Full CRUD for drugs/services/consumables, expiry date management |
| 📊 **Admin** | Patient Records | Student/employee/temporary personnel management |
| 📊 **Admin** | Operation Logs | Full audit trail for all system operations |
| 📊 **Admin** | Analytics Dashboard | 8 analysis dimensions (visits/revenue/doctor workload/disease distribution/drug consumption/patient types/hourly heatmap), ECharts visualization |
| 📊 **Admin** | Formula Management | CRUD for classic TCM formula templates |
| 📊 **Admin** | Damage Approval | Review herbal medicine damage reports, auto-deduct inventory on approval |
| 👤 **System** | Role Permissions | 5 independent interfaces with role isolation
| 🔧 **System** | Smooth Upgrade | Auto database migration, zero data loss
| 🏥 **Lobby** | Appointment | Patient search (masked), create temporary patient, book doctor, one-click check-in |
| 🏥 **Lobby** | Digital Calling | Full-screen calling animation + Web Speech API TTS + chime sound, 6-second auto-dismiss |
| 🏥 **Lobby** | Doctor Status | Available doctor list (green/gray status indicators), scrolling notification bar |

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
| Lobby | `lobby` | `123456` |

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

### 🏷️ open0.0.19 (2026-06-23) 🐛🔧🛡️

**Old Database Compatibility Fix — Complete Auto Column Migration (23 fields):**
- 🐛 **Drug table 15 missing migrations**: `batch_no`, `inbound_at`, herb-related 8 fields (`is_herb` ~ `processing_type`), inventory 5 fields (`safety_stock` ~ `storage_condition`), causing `take_daily_snapshot()` crash on startup
- 🐛 **Visit table 3 missing migrations**: `tcm_enabled`, `tcm_syndrome`, `tcm_diagnosis_desc`, breaking visit history queries
- 🐛 **PrescriptionItem table 5 missing migrations**: `prescription_type`, `herb_dosage`, `special_preparation`, `herb_sort_order`, `template_id`, breaking prescription queries
- 🛡️ **Policy enforced**: Updated "DB column change must include auto-migration" rule, every new `db.Column` must now include a matching `_ensure_sqlite_column()` call
- ✅ **Verified**: Drug 21→34 cols, Visit 22→25 cols, PrescriptionItem 25→30 cols auto-migrated on yws20260608 legacy DB

> 📝 Details: [开发日志-open0.0.19.md](docs/开发日志-open0.0.19.md)

---

### 🏷️ open0.0.18-dev (2026-06-17) 📊🏥🔔

> ⚠️ **Dev-branch exclusive — NOT included in `main` branch**

**Analytics Dashboard & Lobby Appointment & Digital Calling & Doctor On-Duty:**
- 📊 **Analytics Dashboard**: 8 backend analytics APIs (overview/visit trend/revenue trend/doctor workload/disease distribution/drug consumption/patient types/hourly heatmap), ECharts visualization (bar/line/pie/heatmap)
- 🏥 **Lobby Appointment**: New `lobby` role, independent appointment workspace + hall display, patient search (masked), temp patient creation, doctor booking, one-click check-in
- 🔔 **Digital Calling**: Full-screen calling animation (bell → number → patient name → room), 6-second auto-dismiss; Web Speech API TTS + Web Audio API chime
- 👨‍⚕️ **Doctor On-Duty**: Available/rest toggle in doctor navbar, controls hall calling display
- 📢 **Notification Bar**: Top-page scrolling notification bar, admin-configurable content/color/speed
- 🎨 **Hall UI**: Dark gradient background + frosted glass + pulse animation + doctor status lights

> 📝 Details: [开发日志-open0.0.18-dev.md](docs/开发日志-open0.0.18-dev.md)

---

### 🏷️ open0.0.18 (2026-06-15) 🀄💊📋

> ⚠️ **Dev-branch exclusive — TCM module release**

**Traditional Chinese Medicine System — DB/API/UI Full Stack:**
- 🀄 **DB Extension**: Drug +13 TCM fields (is_herb~storage_condition), Visit +3 fields, PrescriptionItem +5 fields, 7 new tables (tcm_diagnosis/classic_prescription_template/template_detail/decoction_usage/herb_inventory_log/herb_loss_record/herb_damage_record)
- 🩺 **TCM Four Diagnosis**: Inspection (spirit/tongue coating), inquiry (ten-questions), palpation (pulse), syndrome differentiation, auto-generated TCM description
- 💊 **Herbal Prescription**: Search herbs (name/pinyin/code), set dosage(g) and special preparation (decoct-first/decoct-last/wrap-decoct/etc.), auto-calculate cost
- 📋 **Classic Formula Templates**: 8 preset classic formulas (Sijunzi/Liuwei Dihuang/Xiaoyao/etc.), one-click load, add/subtract modification
- 🔥 **Decoction Usage**: Total doses, water volume, decoction time, administration, frequency, contraindications
- 💊 **Nurse Herbal Inventory**: Herbal stock list, category/status filter, GB/T 31774 coding, loss registration, damage reporting
- 📋 **Admin Formula Mgmt**: CRUD + enable/disable classic formula templates
- 📋 **Admin Damage Approval**: Review damage reports, auto-deduct inventory
- 🐛 **Code Review Fix**: 6 critical issues fixed (inventory validation/deduction/exception handling/duplicate approval check/frontend data submission/permissions)

> 📝 Details: [开发日志-open0.0.18.md](docs/开发日志-open0.0.18.md)

---

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
