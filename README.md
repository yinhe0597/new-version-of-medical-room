# 校医务室诊疗管理系统 (Medical Room Management System)

本项目为一套专为学校医务室设计的全栈诊疗与库存管理系统。支持医生开方（结合 ICD-10 诊断库）、护士处方审核与改价、药品进销存、学生批量导入以及管理员营收统计等核心功能。

系统全面迁移至 MySQL，使用 Flask (Python) 提供后端 API 服务，前端基于 Vue 3 + Element Plus 构建。

## 快速开始

请阅读 `docs/` 目录下的相关文档，以了解系统部署、使用与二次开发的详细说明。

### 文档导读指南：

- 📌 **项目介绍（先读）**：[项目介绍.md](docs/项目介绍.md)
  - 适合接手开发：用一份文档快速理解目标、架构、角色边界、关键流程与主要功能。

- 🚀 **部署与上线**：[部署与维护说明.md](docs/部署与维护说明.md)
  - 包含了 MySQL 数据库环境准备（`init_database.sql` 的使用）、开发环境启动命令、以及生产环境部署建议。

- 💻 **二次开发入门**：[二次开发指南.md](docs/二次开发指南.md)
  - 专为接手项目的开发人员编写，说明了技术栈、前后端本地联调、数据库迁移 (Alembic) 的标准流程。

- 📂 **源码导航**：[代码结构说明.md](docs/代码结构说明.md)
  - 详细梳理了项目根目录、后端 `backend/` 和前端 `frontend/` 各个核心文件与目录的职责，帮助你快速定位业务代码。

- 🏗️ **系统架构与业务流**：[架构说明.md](docs/架构说明.md)
  - 描述了系统各模块的交互关系、处方状态机（Pending -> Nurse Verified -> Completed / Rejected）、护士审核/改价逻辑、库存扣减机制等。

- 🔌 **API 接口字典**：[接口清单.md](docs/接口清单.md)
  - 整理了当前系统所有后端接口（按 Admin, Doctor, Nurse 角色划分），二次开发对接时可随时查阅。

---

## 项目基础命令速查

**后端 (Python 3.8+ / MySQL 5.7+)**
```bash
cd backend
python -m venv .venv
# 激活虚拟环境 (Windows: .venv\Scripts\activate | Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt

# 初始化数据库结构与基础账号
python init_db.py

# (可选) 导入 ICD-10 疾病字典数据
python import_icd10.py

# 启动开发服务器
python run.py
```

**前端 (Node.js 18+)**
```bash
cd frontend
npm install
npm run dev
```

*（注：更详细的环境要求和 MySQL 前置操作请务必参考 `部署与维护说明.md`。）*
