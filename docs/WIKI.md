# 校医务室诊疗管理系统 Wiki

> **School Clinic Medical Information System (CMIS)**
> 面向学校医务室的诊疗业务 + 处方流转 + 库存进销存 + 收费结算 + 统计报表的完整信息化系统。

---

## 目录

1. [项目概述](#1-项目概述)
2. [技术栈](#2-技术栈)
3. [系统架构](#3-系统架构)
4. [目录结构](#4-目录结构)
5. [角色与权限](#5-角色与权限)
6. [数据模型](#6-数据模型)
7. [核心业务流程](#7-核心业务流程)
8. [API 总览](#8-api-总览)
9. [处方状态机](#9-处方状态机)
10. [库存管理](#10-库存管理)
11. [部署指南](#11-部署指南)
12. [开发指南](#12-开发指南)
13. [常见问题](#13-常见问题)

---

## 1. 项目概述

### 1.1 背景

校医务室日常诊疗涉及患者挂号、医生接诊开方、护士审核执行、库存扣减、收费结算等多个环节。传统纸质流程存在记录难追溯、库存难管理、统计难汇总等问题。本项目旨在将这些流程在线化，形成可追溯、可统计、可协作的工作闭环。

### 1.2 核心能力

- **患者管理**：支持校内学生（学号关联）和校外临时人员就诊
- **电子病历**：结构化病历记录（主诉、现病史、既往史、体格检查、诊断、医嘱）
- **处方流转**：医生开方 -> 护士审核 -> 改价/驳回/执行 -> 库存扣减 -> 收费结算
- **药品库存**：整装/散装双模式库存管理、入库/出库/盘点/月度报表
- **诊断字典**：ICD-10 标准诊断库 + 自定义诊断沉淀
- **统计报表**：营收统计（按日/月/年）、药品出库明细、Excel 导出

---

## 2. 技术栈

| 层次 | 技术 | 说明 |
|------|------|------|
| **前端** | Vue 3 + Vite + Pinia + Element Plus | Composition API，SPA 架构 |
| **后端** | Flask + Flask-SQLAlchemy + Flask-Migrate + Flask-JWT-Extended | Python 轻量框架 |
| **数据库** | SQLite（默认）/ MySQL | 通过环境变量 `DATABASE_URL` 切换 |
| **辅助服务** | Java (Maven) | 药品库存服务模块（`backend-java/`） |
| **CI/CD** | 自建 Workflow 流水线 | `.workflow/` 目录定义 |

### 2.1 后端依赖

详见 `backend/requirements.txt`：

- Flask（Web 框架）
- Flask-SQLAlchemy（ORM）
- Flask-Migrate / Alembic（数据库迁移）
- Flask-JWT-Extended（JWT 认证）
- pymysql（MySQL 驱动）
- pandas / openpyxl / xlrd（Excel 导入导出）
- pypinyin（中文拼音转换）
- python-dotenv（环境变量加载）

### 2.2 前端依赖

- Vue 3 + Vue Router
- Pinia（状态管理）
- Element Plus（UI 组件库）
- Axios（HTTP 客户端）
- Vite（构建工具）

---

## 3. 系统架构

### 3.1 总体形态

前后端分离的 B/S 架构：

```
浏览器 (Vue SPA)  <--HTTP/JSON-->  Flask API  <--SQL-->  Database
       │                                │
       │                          [JWT Auth]
       │                         [Role Guard]
  [Vue Router]                     
  [Role Guard]                     
```

### 3.2 前后端通信

- API 前缀：`/api`
- 认证方式：`Authorization: Bearer <JWT Token>`
- 数据格式：JSON
- 开发环境代理：Vite 配置 `/api` 代理到 `http://127.0.0.1:5000`

### 3.3 分层设计

**后端分层：**

```
backend/
├── run.py                 # 启动入口
├── config.py              # 配置（数据库、JWT、Secret Key）
├── app/__init__.py        # 应用工厂 (create_app)
├── app/api/               # API 蓝图（按角色拆分）
│   ├── auth.py            # 登录认证
│   ├── doctor.py          # 医生接口
│   ├── nurse.py           # 护士接口
│   └── admin.py           # 管理员接口
├── app/models/            # ORM 数据模型
├── app/utils/decorators.py# 鉴权装饰器
└── app/services/          # 业务服务层
```

**前端分层：**

```
frontend/src/
├── api/request.js         # Axios + Token 拦截
├── router/index.js        # 路由 + 角色守卫
├── store/user.js          # Pinia 用户状态
└── views/                 # 页面组件
    ├── Login.vue
    ├── doctor/            # 医生端
    ├── nurse/             # 护士端
    └── admin/             # 管理端
```

---

## 4. 目录结构

```
new-version-of-medical-room/
├── backend/                    # Python Flask 后端
│   ├── app/
│   │   ├── __init__.py         # 应用工厂（create_app、DB初始化、CORS、静态文件）
│   │   ├── api/
│   │   │   ├── __init__.py     # Blueprint 注册
│   │   │   ├── auth.py         # POST /api/auth/login
│   │   │   ├── doctor.py       # 医生端全部 API
│   │   │   ├── nurse.py        # 护士端全部 API
│   │   │   ├── admin.py        # 管理端全部 API
│   │   │   └── routes.py       # 通用路由（示例/鉴权测试）
│   │   ├── models/__init__.py  # 全部 ORM 模型
│   │   ├── services/           # 业务服务层
│   │   │   └── drug_stock.py   # 药品入库/拆零/库存组逻辑
│   │   └── utils/decorators.py # @role_required 装饰器
│   ├── migrations/             # Alembic 数据库迁移
│   │   └── versions/           # 版本迁移脚本
│   ├── tests/                  # 单元测试
│   ├── config.py               # 配置项
│   ├── init_db.py              # 数据库初始化 + 种子数据
│   ├── run.py                  # 开发启动入口
│   └── requirements.txt        # 依赖清单
│
├── backend-java/               # Java 库存服务模块（实验性）
│   ├── pom.xml                 # Maven 配置
│   └── src/main/java/com/medical/stock/service/DrugStockService.java
│
├── frontend/                   # Vue 3 前端
│   ├── dist/                   # 构建产物（可直接部署）
│   ├── src/
│   │   ├── main.js             # 应用入口
│   │   ├── App.vue             # 根组件
│   │   ├── router/index.js     # 路由定义
│   │   ├── store/user.js       # Pinia store
│   │   ├── api/request.js      # Axios 封装
│   │   └── views/
│   │       ├── Login.vue
│   │       ├── doctor/         # Dashboard, PatientSearch, VisitForm, PrescriptionHistory
│   │       ├── nurse/          # Dashboard, PendingList, ExecutePrescription, Inventory
│   │       └── admin/          # Dashboard, DrugManagement, PatientManagement, Statistics, UserManagement, SystemSettings
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
├── docs/                       # 文档目录
│   ├── 项目介绍.md              # 项目简介
│   ├── 架构说明.md              # 架构细节
│   ├── 代码结构说明.md           # 代码目录职责
│   ├── 系统使用说明书.md         # 用户操作手册
│   ├── 接口清单.md              # API 字典
│   ├── api.md                  # 接口文档（节选）
│   ├── 二次开发指南.md           # 二次开发指引
│   ├── 部署与维护说明.md         # 生产部署
│   ├── 本地开发与部署常见问题记录.md # 排错手册
│   ├── 疾病诊断检索库（ICD-10）构建与自定义诊断沉淀.md
│   └── 更新日志-V*.md           # 版本更新日志
│
└── open0.0/                    # 开放版数据目录
    └── data/app.db             # 数据库文件
```

---

## 5. 角色与权限

系统采用三角色权限模型：

| 角色 | 职责 | 前端路由前缀 | 后端 API 前缀 |
|------|------|-------------|--------------|
| **doctor** | 患者检索/建档、接诊开方、病历查询 | `/doctor` | `/api/doctor/` |
| **nurse** | 处方审核/执行、库存管理、收费结算 | `/nurse` | `/api/nurse/` |
| **admin** | 药品字典、用户管理、统计报表、系统维护 | `/admin` | `/api/admin/` |

### 5.1 鉴权机制

1. **登录**：`POST /api/auth/login` 验证用户名密码，返回 JWT `access_token`
2. **前端拦截**：`request.js` 在请求头自动注入 `Authorization: Bearer <token>`
3. **后端校验**：`@role_required(roles)` 装饰器从 JWT 提取用户身份，查询 `User.role` 做权限校验
4. **路由守卫**：`router/index.js` `beforeEach` 钩子根据 `meta.role` 限制页面访问
5. **Token 过期**：默认 7 天（`config.py` `JWT_ACCESS_TOKEN_EXPIRES`）

---

## 6. 数据模型

### 6.1 实体关系总览

```
User ──┐                    Drug ──┐
       │                           │
       ├──< Visit (doctor)         ├──< PrescriptionItem
       │       │                   │
       │       ├──< Patient        ├──< InventoryRecord
       │       │                   │
       │       ├──< PrescriptionItem ──< DrugStockGroup
       │       │                   │
       │       └──< Payment        └──< DailyStockSnapshot
       │
       └──< Payment (nurse)
       
DiagnosisDict          TextTemplate          OperationLog
```

### 6.2 核心模型字段

#### User（系统用户）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | PK |
| username | String(64) | 登录名，唯一 |
| password_hash | String(256) | bcrypt 哈希 |
| real_name | String(64) | 真实姓名 |
| role | String(20) | `admin` / `doctor` / `nurse` |

#### Patient（患者档案）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | PK |
| student_id | String(20) | 学号（临时患者为 NULL） |
| name | String(64) | 姓名 |
| gender | String(10) | 性别 |
| class_name | String(100) | 班级 |
| grade | String(50) | 年级 |
| college | String(100) | 学院 |
| major | String(100) | 专业 |
| phone | String(20) | 手机号 |
| is_temporary | Boolean | 是否为临时人员 |
| age | Integer | 年龄 |
| id_card | String(20) | 身份证号 |
| counselor_name | String(64) | 辅导员姓名 |
| name_pinyin | Text | 姓名全拼（用于搜索） |
| name_initials | Text | 姓名首字母（用于搜索） |

#### Drug（药品/项目 + 库存）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | PK |
| name | String(128) | 药品/项目名称 |
| type | Integer | 1=药品, 2=诊疗项目, 3=耗材 |
| specification | String(50) | 规格 |
| unit | String(10) | 单位 |
| price | Float | 售价 |
| purchase_price | Float | 进价/成本价 |
| stock | Integer | 库存数量 |
| status | Integer | 1=启用, 0=停用 |
| has_scattered | Boolean | 是否支持散装售卖 |
| scattered_price | Float | 散装单价 |
| conversion_rate | Integer | 整装到散装的转换率 |
| batch_no | String(50) | 批号 |
| inbound_at | DateTime | 入库时间 |
| variant_type | String(20) | `pack` / `retail` / `service` / `consumable` |
| stock_group_code | String(36) | 库存组编码 |
| unit_amount | Integer | 组内单位含量 |
| base_name | String(128) | 基础名称（库存组共享） |

#### DrugStockGroup（整散装库存组）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | PK |
| group_code | String(36) | 唯一组编码（UUID） |
| batch_no | String(50) | 批号 |
| base_name | String(128) | 药品基础名 |
| unit_name | String(20) | 基础单位名 |
| total_units | Integer | 总基础单位数 |
| pack_amount | Integer | 每盒含量 |
| retail_amount | Integer | 每散卖单位含量 |
| pack_drug_id | FK→Drug | 整装药品 |
| retail_drug_id | FK→Drug | 散装药品 |

#### Visit（就诊记录）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | PK |
| patient_id | FK→Patient | 患者 |
| doctor_id | FK→User | 接诊医生 |
| timestamp | DateTime | 就诊时间 |
| chief_complaint | Text | 主诉 |
| present_illness | Text | 现病史 |
| past_history | Text | 既往史 |
| physical_exam | Text | 体格检查 |
| diagnosis | Text | 诊断（含 ICD-10 编码） |
| doctor_advice | Text | 医生建议/医嘱 |
| special_note | Text | 特殊备注 |
| consultation_fee | Float | 诊察费 |
| total_amount | Float | 总金额 |
| status | String(20) | pending / nurse_verified / rejected / completed / revoked |
| verified_by | FK→User | 审核护士 |
| verified_at | DateTime | 审核时间 |
| rejected_by | FK→User | 驳回护士 |
| rejected_at | DateTime | 驳回时间 |
| reject_reason | Text | 驳回原因 |
| revoked_by | FK→User | 撤销人 |
| revoked_at | DateTime | 撤销时间 |
| revoke_reason | Text | 撤销原因 |

#### PrescriptionItem（处方明细）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | PK |
| visit_id | FK→Visit | 关联就诊 |
| drug_id | FK→Drug | 关联药品/项目 |
| usage | String(100) | 用法 |
| dosage | String(50) | 用量 |
| frequency | String(50) | 频次 |
| timing | String(50) | 服用时间 |
| days | Integer | 天数 |
| quantity | Integer | 数量 |
| price_at_visit | Float | 开方时单价 |
| amount | Float | 金额 |
| original_price | Float | 原始单价（改价前） |
| original_amount | Float | 原始金额（改价前） |
| new_price | Float | 改价后单价 |
| new_amount | Float | 改价后金额 |
| modified_by | FK→User | 改价护士 |
| modified_at | DateTime | 改价时间 |
| modify_reason | Text | 改价原因 |
| is_scattered | Boolean | 是否散装售卖 |
| purchase_cost | Float | 成本 |

#### Payment（支付记录）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | PK |
| visit_id | FK→Visit | 唯一（一对一） |
| nurse_id | FK→User | 收款护士 |
| amount | Float | 实收金额 |
| payment_date | DateTime | 支付时间 |
| payment_method | String(50) | 支付方式 |
| receipt_printed | Boolean | 票据是否已打印 |
| is_employee_discount | Boolean | 是否职工优惠 |
| original_amount | Float | 原始应收金额（优惠前） |

#### InventoryRecord（库存调整流水）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | PK |
| drug_id | FK→Drug | 药品 |
| nurse_id | FK→User | 操作护士 |
| old_stock | Integer | 原库存 |
| new_stock | Integer | 新库存 |
| remark | String(200) | 备注 |
| timestamp | DateTime | 操作时间 |

#### DiagnosisDict（诊断字典）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | PK |
| code | String(50) | ICD-10 编码 |
| name | String(200) | 诊断名称 |
| pinyin | String(200) | 拼音（首字母\|全拼） |

#### TextTemplate（文本模板）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | PK |
| doctor_id | FK→User | 所属医生 |
| category | String(50) | `present_illness` / `physical_exam` / `doctor_advice` |
| title | String(200) | 标题 |
| content | Text | 内容 |

#### OperationLog（运营日志）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | PK |
| user_id | FK→User | 操作用户 |
| action_type | String(50) | 操作类型 |
| target_type | String(50) | 目标类型 |
| target_id | Integer | 目标 ID |
| summary | String(200) | 摘要 |
| details | Text | 详情（JSON） |
| timestamp | DateTime | 操作时间 |

---

## 7. 核心业务流程

### 7.1 接诊开方 -> 收费结算 全流程

```
医生                         护士                         患者
│                            │                            │
├─ 检索/创建患者 ──────────── │ ─────────────────────────── │
│                            │                            │
├─ 填写电子病历 ───────────── │ ─────────────────────────── │
│  (主诉/现病史/诊断)         │                            │
│                            │                            │
├─ 开立处方 ───────────────── │ ─────────────────────────── │
│  (药品/用法用量)            │                            │
│  [status: pending]         │                            │
│                            │                            │
│                            ├─ 查看待处理列表 ──────────── │
│                            │                            │
│                            ├─ [可选] 改价 ───────────── │
│                            │                            │
│                            ├─ [可选] 驳回 ───────────── │
│                            │  [status: rejected]        │
│                            │       ↓                    │
│                            │  医生修改后重新提交         │
│                            │                            │
│                            ├─ 审核通过 ───────────────── │
│                            │  [status: nurse_verified]  │
│                            │                            │
│                            ├─ [可选] 追加项目 ────────── │
│                            │  (诊疗项目/耗材)            │
│                            │                            │
│                            ├─ 执行/扣库存 ────────────── │
│                            │  [status: completed]       │
│                            │  + 生成 Payment            │
│                            │                            │
│                            ├─ [可选] 撤销交易 ────────── │
│                            │  [status: revoked]         │
│                            │  + 还原库存 + 删除 Payment  │
│                            │                            │
```

### 7.2 关键规则

1. **库存校验双重保障**：开方时校验一次（可用量检查），执行时再校验一次（防止并发超卖）
2. **改价留痕**：护士修改价格后，`PrescriptionItem` 中保留 `original_price` / `original_amount` / `new_price` / `new_amount` 审计字段
3. **整散装转换**：`conversion_rate` 定义整装到散装的换算比例，散装扣库存时按 `ceil(quantity / conversion_rate)` 计算
4. **库存组模式**：整装 + 散装共享 `total_units`，出库时自动同步调整两者库存

---

## 8. API 总览

所有 API 前缀为 `/api`。

### 8.1 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/login` | 用户登录，返回 JWT |

### 8.2 医生端

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/doctor/patient/search?keyword=` | 患者搜索（支持学号/姓名/拼音） |
| POST | `/doctor/patient` | 创建新患者 |
| PUT | `/doctor/patient/<id>` | 更新患者信息 |
| GET | `/doctor/patient/<id>/visits` | 患者就诊历史 |
| GET | `/doctor/drugs/search?keyword=` | 药品搜索 |
| GET | `/doctor/diagnoses/search?keyword=` | 诊断搜索（ICD-10，支持汉字/编码/拼音） |
| POST | `/doctor/visits` | 创建就诊 + 处方（核心接口） |
| GET | `/doctor/visits/history` | 就诊历史 |
| GET | `/doctor/visits/<id>` | 就诊详情 |
| PUT | `/doctor/visits/<id>/medical-record` | 修改电子病历 |
| GET | `/doctor/visits/<id>/revisions` | 病历修改历史 |
| GET/POST/PUT/DELETE | `/doctor/templates` | 文本模板管理 |

### 8.3 护士端

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/nurse/pending-visits` | 待处理处方列表 |
| GET | `/nurse/visits/<id>` | 处方详情 |
| POST | `/nurse/visits/<id>/verify` | 审核通过 |
| POST | `/nurse/visits/<id>/reject` | 驳回 |
| POST | `/nurse/visits/<id>/execute` | 执行（扣库存 + 结算） |
| POST | `/nurse/visits/<id>/revoke` | 撤销交易 |
| PUT | `/nurse/visits/<id>/items/<item_id>/modify` | 改价 |
| POST | `/nurse/visits/<id>/service-items` | 追加诊疗项目/耗材 |
| PUT/DELETE | `/nurse/visits/<id>/service-items/<item_id>` | 修改/删除追加项目 |
| GET | `/nurse/drugs` | 药品列表（库存盘点） |
| POST | `/nurse/inventory` | 库存调整 |
| POST | `/nurse/inventory/group` | 库存组联合盘点 |
| GET | `/nurse/inventory/records` | 库存操作记录 |
| GET | `/nurse/inventory/monthly-report` | 月度盘点报表 |
| POST | `/nurse/inbound` | 药品入库 |
| GET | `/nurse/my-history` | 历史诊疗记录（所有护士可见，支持 nurse_id / doctor_id / date_from / date_to 筛选） |
| GET | `/nurse/staff-list` | 获取医护人员列表（筛选下拉用） |
| GET | `/nurse/services/search` | 诊疗项目搜索 |
| GET | `/nurse/drug-names/search` | 药品名称搜索 |
| PUT | `/nurse/payments/<id>/print` | 标记票据已打印 |

### 8.4 管理端

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/admin/drugs` | 药品列表/新增 |
| PUT/DELETE | `/admin/drugs/<id>` | 修改/删除药品 |
| POST | `/admin/drugs/<id>/inbound` | 药品入库 |
| GET | `/admin/drugs/template` | 下载导入模板 (CSV) |
| POST | `/admin/drugs/import` | CSV 批量导入 |
| POST | `/admin/drugs/import_xls` | Excel 批量导入 |
| POST | `/admin/drugs/smart-inventory` | 智能盘库（合并重复 + 低库存预警） |
| GET | `/admin/users` | 用户列表 |
| POST | `/admin/users` | 创建用户 |
| PUT/DELETE | `/admin/users/<id>` | 修改/删除用户 |
| GET | `/admin/statistics/revenue` | 营收统计 |
| GET | `/admin/statistics/revenue/export` | 导出营收报表 (Excel) |
| GET | `/admin/statistics/revenue/users` | 获取医生/护士列表（统计筛选用） |
| GET | `/admin/statistics/drug-outbound` | 药品出库明细 |
| GET | `/admin/statistics/drug-outbound/export` | 导出出库明细 (Excel) |
| POST | `/admin/backup` | SQLite 数据库备份 |
| GET | `/admin/backup/mysql` | MySQL 数据库备份 |
| GET | `/admin/patients/template` | 患者导入模板 (CSV) |
| POST | `/admin/patients/import` | CSV 导入患者 |
| GET | `/admin/operation-logs` | 运营日志 |

---

## 9. 处方状态机

```
                    ┌──────────┐
                    │  pending  │  ← 医生开方完成
                    └────┬─────┘
                         │
              ┌──────────┼──────────┐
              │          │          │
              ▼          ▼          ▼
        ┌──────────┐ ┌──────────┐
        │rejected  │ │nurse_    │  ← 护士审核通过
        │          │ │verified  │
        └──────────┘ └────┬─────┘
              │            │
              │            ├── 护士改价/追加项目
              │            │
              │            ▼
              │      ┌──────────┐
              │      │completed │  ← 护士执行（扣库存+结算）
              │      └────┬─────┘
              │            │
              │            ▼
              │      ┌──────────┐
              │      │ revoked  │  ← 护士撤销
              │      └──────────┘
              │
              └── 医生修改病历后重新变为 pending
```

状态转移规则（`models/__init__.py`）：

| 当前状态 | 允许的下一个状态 |
|----------|----------------|
| pending | nurse_verified, rejected |
| nurse_verified | completed, rejected |
| completed | revoked |
| rejected | (终端状态) |
| revoked | (终端状态) |

---

## 10. 库存管理

### 10.1 药品类型

| type | 含义 | 库存行为 |
|------|------|---------|
| 1 | 药品 | 参与库存校验和扣减 |
| 2 | 诊疗项目 | 不占用库存（stock=-1） |
| 3 | 耗材 | 参与库存校验和扣减 |

### 10.2 整散装模式

药品可以同时支持两种售卖方式：

- **整装**：按盒/瓶售卖，`price` 为整装价
- **散装**：按最小单位售卖，需开启 `has_scattered`，设置 `scattered_price`（散装单价）和 `conversion_rate`（每盒含多少散装单位）

**扣库存逻辑**：`stock_deduct = ceil(quantity / conversion_rate)`

### 10.3 库存组模式（Group Stock）

适用于需要同时维护整装和散装库存的场景：

- `DrugStockGroup` 维护 `total_units`（总基础单位数）
- 整装药品：`variant_type="pack"`，每盒含 `unit_amount` 单位
- 散装药品：`variant_type="retail"`，每份含 `unit_amount` 单位
- 出库时按实际消耗单位数扣减 `total_units`，然后同步重新计算整装和散装的账面库存

### 10.4 月度盘点报表

系统支持生成月度盘点报表，计算逻辑：

```
期初库存 + 入库 - 出库 ± 调整 = 期末库存
```

- 从 `DailyStockSnapshot` 取快照
- 回退计算空缺日期的库存
- 支持导出为 Excel

### 10.5 智能盘库

管理员可一键执行智能盘库：

1. 查找同名同规格的重复药品
2. 合并库存、迁移处方引用
3. 删除重复药品记录
4. 返回低库存预警列表（低于阈值）

---

## 11. 部署指南

### 11.1 开发环境

**后端：**

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
python init_db.py    # 初始化数据库 + 种子数据
python run.py        # 启动 http://127.0.0.1:5000
```

**前端：**

```bash
cd frontend
npm install
npm run dev          # 启动 http://127.0.0.1:5888
```

**默认账号（密码均为 `123456`）：**

| 角色 | 用户名 |
|------|--------|
| 管理员 | admin |
| 医生 | doctor |
| 护士 | nurse |

### 11.2 生产部署

**方式一：前后端分离部署**

- 后端：使用 `gunicorn` / `waitress` 等 WSGI 服务器（参考 `run.py` 中的 `create_app()`）
- 前端：`npm run build` 生成 `dist/` 目录，使用 Nginx 托管

**方式二：Flask 托管前端（当前配置）**

后端会自动从 `frontend/dist/` 目录提供前端文件，访问根路径即可进入 SPA。`create_app()` 中的 `serve_frontend()` 和 `serve_static()` 处理了这一逻辑。

**方式三：PyInstaller 打包**

支持使用 `APP_ROOT` 环境变量指定生产环境路径。

### 11.3 MySQL 切换

设置环境变量 `DATABASE_URL`：

```bash
export DATABASE_URL="mysql+pymysql://user:password@host:port/dbname?charset=utf8mb4"
```

系统自动处理 `utf8mb4` 字符集和连接池配置。

### 11.4 数据库备份

- **SQLite**：`POST /api/admin/backup` 复制数据库文件到 `backups/` 目录
- **MySQL**：`GET /api/admin/backup/mysql` 通过 `mysqldump` 导出

---

## 12. 开发指南

### 12.1 数据库迁移

使用 Alembic（通过 Flask-Migrate）管理迁移：

```bash
flask db init          # 初始化迁移目录（已完成）
flask db migrate -m "描述"  # 生成迁移脚本
flask db upgrade       # 应用到数据库
```

迁移脚本位于 `backend/migrations/versions/`。

### 12.2 添加新 API

1. 在 `backend/app/models/__init__.py` 中定义或修改模型
2. 在 `backend/app/api/` 下对应的角色文件中添加路由
3. 使用 `@role_required` 装饰器控制权限
4. 在 `backend/migrations/` 生成迁移脚本
5. 在 `backend/tests/` 添加测试

### 12.3 添加新前端页面

1. 在 `frontend/src/views/` 对应角色目录下创建 Vue 组件
2. 在 `frontend/src/router/index.js` 添加路由（设置 `meta.role`）
3. 在对应角色的 Dashboard 中添加导航菜单

### 12.4 数据库兼容性

`create_app()` 中的 `_ensure_sqlite_column()` 函数提供了 SQLite 的在线列添加（SQLite 不支持原生 `ALTER TABLE ADD COLUMN`）。当添加新字段到模型时，需要同时在 `create_app()` 中注册对应的兼容性处理。

### 12.5 拼音搜索

- 患者搜索支持学号、姓名汉字、拼音首字母、全拼
- 诊断搜索支持汉字、ICD 编码、拼音首字母、全拼
- 使用 `pypinyin` 库进行拼音转换，结果存储在 `name_pinyin` 和 `name_initials` 字段

### 12.6 诊断字典

- 医生开方时录入的诊断会自动沉淀到 `DiagnosisDict`（`_upsert_diagnosis_dict_from_text`）
- 支持 ICD-10 标准编码导入（`backend/import_icd10.py`）
- 诊断显示时会自动修复乱码（`_normalize_diagnosis_text_for_output`）

### 12.7 ICD-10 编码

诊断录入格式：`疾病名称（编码）` 或 `疾病名称 (编码)`

示例：`感冒 (J00)`、`急性扁桃体炎（J03.9）`

录入时会自动从诊断文本中提取编码和名称，存入 `DiagnosisDict`。

---

## 13. 常见问题

### Q: 如何重置密码？

运行 `backend/reset_default_passwords.py` 将默认用户密码重置为 `123456`。

### Q: 数据库文件在哪？

默认路径为 `backend/app.db`，可通过 `DATABASE_URL` 环境变量修改。

### Q: 如何从 SQLite 迁移到 MySQL？

1. 设置 `DATABASE_URL` 指向 MySQL
2. 运行 `python init_db.py` 自动创建表
3. 使用 `backend/migrate_to_mysql.py` 迁移数据

### Q: 如何导入药品数据？

1. 获取模板：`GET /api/admin/drugs/template`
2. 按模板格式填写 CSV
3. 上传：`POST /api/admin/drugs/import`

### Q: 如何导入患者数据？

1. 获取模板：`GET /api/admin/patients/template`
2. 填写 CSV（学号、姓名、性别、班级必填）
3. 上传：`POST /api/admin/patients/import`

### Q: 前端开发时端口是多少？

Vite 开发服务器默认监听 `5888` 端口，`/api` 代理到 `localhost:5000`。

### Q: 药品入库时提示"Duplicate drug batch"？

同一药品、规格、批号的记录已存在，不允许重复入库。如需增加库存，应使用入库接口追加。

---

## 附录

### A. 日志与审计

- 后端日志：`backend/app.log`
- 运营日志：`OperationLog` 表记录所有关键操作（药品创建/编辑、临时人员就诊、病历修改）
- 库存流水：`InventoryRecord` 表记录所有库存变动

### B. 限流

医生端患者搜索接口使用内存令牌桶限流：同一用户 10 秒内最多 30 次请求，超限返回 429。

### C. CSV 导入安全防护

所有 CSV 导入导出时自动转义以 `= + - @` 开头的单元格内容，防止 CSV 注入攻击。

### D. 患者导入规则

CSV 导入患者时，学号已存在的记录会被更新（而非跳过），包括姓名、性别、年级、学院、专业、班级、辅导员等信息。
