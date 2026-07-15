# 📋 校医务室诊疗管理系统 — 项目 Wiki（重整版）

> **版本**: open0.0.21 | **最后更新**: 2026-07-15
> **用途**: 面向 Go 语言重构的完整项目知识库

---

## 目录

1. [项目概览](#1-项目概览)
2. [技术架构](#2-技术架构)
3. [角色与权限体系](#3-角色与权限体系)
4. [核心业务闭环](#4-核心业务闭环)
5. [数据模型全量定义](#5-数据模型全量定义)
6. [API 接口全量清单](#6-api-接口全量清单)
7. [状态机与业务规则](#7-状态机与业务规则)
8. [安全与认证](#8-安全与认证)
9. [部署与运维](#9-部署与运维)

---

## 1. 项目概览

### 1.1 系统定位

面向**高校/中小学医务室**的诊疗业务信息化系统，覆盖从挂号到结算的完整诊疗闭环。

### 1.2 业务流程

```
挂号/建档 → 医生接诊开方 → 护士审核 → 改价/追加项目 → 执行收费 → 库存扣减 → 营收统计
```

### 1.3 关键能力

| 能力域 | 说明 |
|--------|------|
| **患者管理** | 学生（学号+班级+辅导员）、教职工、商铺员工、临时患者四类档案 |
| **电子病历** | 主诉、现病史、既往史、体格检查、诊断、医嘱、特别备注 |
| **处方流转** | 医生开方 → 护士审核/驳回/改价/追加/执行 完整工作流 |
| **库存管理** | 整装/散装双模式、库存组联动、批次/效期追踪、日终快照 |
| **收费结算** | 诊查费+药品+项目+耗材分项实收、职工优惠、营收分摊 |
| **统计报表** | 营收（实收/成本/利润）、出库月报（期初/出库/结存）、环比趋势 |
| **ICD-10** | 国家临床版 2.0 疾病诊断编码库，支持中文/拼音/编码检索 |

### 1.4 技术栈

| 层 | 现用技术 (Python) | 目标技术 (Go) |
|----|-------------------|---------------|
| Web 框架 | Flask 3.x | `gin` / `echo` / `fiber` |
| ORM | Flask-SQLAlchemy | `gorm` |
| 认证 | Flask-JWT-Extended | `golang-jwt` |
| 数据库迁移 | Alembic | `golang-migrate` / `atlas` |
| 前端 | Vue 3 + Vite + Element Plus | **不变** |
| 数据库 | SQLite / MySQL | MySQL / PostgreSQL / SQLite |

---

## 2. 技术架构

### 2.1 总体架构

```
┌──────────────────────────────────────────┐
│            Browser (Vue 3 SPA)           │
│   Port 5888 (dev) / Nginx (prod)        │
├──────────────────────────────────────────┤
│         HTTP/JSON + JWT Bearer           │
├──────────────────────────────────────────┤
│           API Server (Flask → Go)        │
│  ┌──────────────────────────────────┐    │
│  │  Middleware: JWT Auth + Role ACL │    │
│  ├──────────────────────────────────┤    │
│  │  Routes: /api/auth, /doctor,     │    │
│  │           /nurse, /admin, /finance│   │
│  ├──────────────────────────────────┤    │
│  │  Services: Revenue, StockLock,   │    │
│  │            InventoryLedger, etc. │    │
│  ├──────────────────────────────────┤    │
│  │  Models: GORM (13 tables)        │    │
│  └──────────────────────────────────┘    │
├──────────────────────────────────────────┤
│          Database (SQLite / MySQL)        │
└──────────────────────────────────────────┘
```

### 2.2 后端分层（Go 重构后）

```
cmd/server/main.go           # 入口
internal/
├── config/config.go         # 配置（Viper）
├── middleware/
│   ├── auth.go              # JWT 解析 + 注入 Claims
│   └── rbac.go              # 角色鉴权中间件
├── handler/                 # HTTP Handler (替代 Flask blueprint)
│   ├── auth.go              # POST /api/auth/login, change-password
│   ├── doctor.go            # 医生端 16 个端点
│   ├── nurse.go             # 护士端 22 个端点
│   ├── admin.go             # 管理端 24 个端点
│   └── finance.go           # 财务端 3 个端点
├── service/                 # 业务逻辑层
│   ├── drug_stock.go        # 整散装规格解析 + 库存计算
│   ├── inventory_ledger.go  # 库存流水 + 日终快照
│   ├── revenue.go           # 营收分摊算法
│   └── stock_lock.go        # 库存操作并发控制
├── model/                   # GORM 模型定义
│   └── models.go            # 13 个模型（单文件或拆分）
├── repository/              # 数据访问层 (可选)
└── util/
    ├── password.go          # bcrypt 密码
    ├── timezone.go          # 北京时间工具
    └── pinyin.go            # 中文拼音转换
```

### 2.3 文件职责速查

| 原 Python 文件 | 对应 Go 文件 | 职责 |
|---------------|-------------|------|
| `app/__init__.py` | `cmd/server/main.go` | App 启动、DB 初始化、中间件注册 |
| `app/models/__init__.py` | `internal/model/models.go` | 全部 ORM 模型定义 |
| `app/api/auth.py` | `internal/handler/auth.go` | 登录、改密 |
| `app/api/doctor.py` | `internal/handler/doctor.go` | 医生端 API |
| `app/api/nurse.py` | `internal/handler/nurse.go` | 护士端 API |
| `app/api/admin.py` | `internal/handler/admin.go` | 管理端 API |
| `app/api/finance.py` | `internal/handler/finance.go` | 财务端 API |
| `app/utils/decorators.py` | `internal/middleware/rbac.go` | 角色鉴权 |
| `app/services/revenue.py` | `internal/service/revenue.go` | 营收分摊 |
| `app/services/stock_lock.py` | `internal/service/stock_lock.go` | 库存锁 |
| `app/services/drug_stock.py` | `internal/service/drug_stock.go` | 整散装计算 |
| `app/services/inventory_ledger.py` | `internal/service/inventory_ledger.go` | 库存流水 |
| `config.py` | `internal/config/config.go` | 配置 |
| `runtime_secrets.py` | `internal/config/secrets.go` | 密钥管理 |
| `backend-java/...DrugStockService.java` | → `internal/service/drug_stock.go` | ✅ 已有 Java 参照 |

---

## 3. 角色与权限体系

### 3.1 角色定义

| 角色 | 值 | 前端路由前缀 | 职责范围 |
|------|-----|-------------|---------|
| 管理员 | `admin` | `/admin` | 账号管理、药品字典、患者导入、统计、备份、运营日志 |
| 医生 | `doctor` | `/doctor` | 患者检索/建档、接诊开方、病历、文本模板、挂单 |
| 护士 | `nurse` | `/nurse` | 处方审核/执行、库存管理、药品入库、收费、出库报表 |
| 财务 | `finance` | `/finance` | 财务看板、营收/趋势、药品价格（只读） |

### 3.2 鉴权链路

```
1. POST /api/auth/login { username, password }
   → 验证密码 → 生成 JWT (含 user_id, 7天过期)
   → 返回 { access_token, user: { id, username, real_name, role } }

2. 前端 localStorage 存储 token + userInfo

3. 每次请求: Axios 拦截器 → Authorization: Bearer <token>

4. 后端中间件: 解析 JWT → 查 DB 获取 User → 校验 role ∈ 允许角色
   → 校验 is_active == true → 通过/403

5. 前端路由守卫: meta.role 匹配 user.role → 允许/跳转登录页
```

### 3.3 角色权限矩阵

| API 前缀 | admin | doctor | nurse | finance |
|----------|:-----:|:------:|:-----:|:-------:|
| `/api/auth/*` | ✅ | ✅ | ✅ | ✅ |
| `/api/doctor/*` | ✅ | ✅ | ❌ | ❌ |
| `/api/nurse/*` | ✅ | ❌ | ✅ | ❌ |
| `/api/admin/statistics/*` | ✅ | ❌ | ✅ | ✅ |
| `/api/admin/drugs` (GET) | ✅ | ❌ | ✅ | ✅ |
| `/api/admin/drugs` (写) | ✅ | ❌ | ✅ | ❌ |
| `/api/admin/users` | ✅ | ❌ | ❌ | ❌ |
| `/api/admin/backup` | ✅ | ❌ | ❌ | ❌ |
| `/api/admin/operation-logs` | ✅ | ❌ | ❌ | ❌ |
| `/api/finance/*` | ✅ | ❌ | ❌ | ✅ |

### 3.4 财务隐私脱敏

财务角色访问以下数据时自动脱敏：
- **患者姓名**: 保留首字，其余 `*` (如 `张*`)
- **学号**: 不返回
- **诊断**: 不返回
- **主诉**: 不返回
- **出库报表**: 患者姓名脱敏

---

## 4. 核心业务闭环

### 4.1 患者建档（医生/管理员）

```
输入: 姓名(必填) + 性别 + 患者类型
  ├── student:  学号 + 班级 + 辅导员(可选)
  ├── staff:    身份证号 + 部门(可选)
  ├── shop:     商铺名称(必填)
  └── temporary: 手机号(必填) + 年龄(必填) + 身份证号(可选)
→ 自动生成 name_pinyin + name_initials → Patient
```

### 4.2 接诊开方（医生）

```
1. 搜索患者 → 选择 → 进入 VisitForm
2. 填写病历: 主诉, 现病史, 既往史, 体格检查, 诊断(ICD-10辅助), 医嘱, 特别备注
3. 添加处方药:
   - 搜索药品(拼音/中文) → 选择 → 填入 用法/用量/频次/服用时间/天数/数量
   - 整装: 选整装price → quantity
   - 散装: 选散装scattered_price → quantity
   - 静脉给药: 标记 is_intravenous → 配伍组 infusion_group
   - 零散用药: 不关联 Visit 直接生成 PrescriptionItem
4. 可选: 保存为挂单 (ParkedVisit) → 后续从挂单恢复
5. 提交: POST /doctor/visits → 后端校验:
   - 诊断非空
   - 至少一个用药项且至少一个用法字段非空
   - type=1/3 项库存校验
   - 计算 total_amount (consultation_fee + Σ items.amount)
   - 创建 Visit(status=pending) + PrescriptionItems
```

### 4.3 护士审核与执行

```
护士端流程:
┌─────────────────────────────────────────────┐
│ 1. 待处理列表 (GET /nurse/pending-visits)    │
│    筛选: status=pending | nurse_verified     │
│    ● 患者名、诊断、金额、状态、时间           │
├─────────────────────────────────────────────┤
│ 2. 处方详情 (GET /nurse/visits/<id>)         │
│    病历全文 + 处方明细 + 状态时间线            │
│    + 药品当前库存 + 库存不足标记              │
├─────────────────────────────────────────────┤
│ 3. 操作选择:                                 │
│    ├── 审核通过 (POST /verify)                │
│    │   → status → nurse_verified             │
│    │   → 可改价、追加项目                     │
│    ├── 驳回 (POST /reject)                    │
│    │   → 填写驳回原因 → status → rejected     │
│    │   → 医生可修改病历后重新提交              │
│    └── 执行 (POST /execute)【审核后】          │
│        → 库存扣减（整散装折算）               │
│        → 生成 Payment                        │
│        → visit.status → completed            │
├─────────────────────────────────────────────┤
│ 4. 改价（审核后/执行前）                      │
│    PUT /nurse/visits/<id>/items/<iid>/modify │
│    → 记录 original_price/new_price 审计       │
│ 5. 追加项目（审核后/执行前）                  │
│    POST /nurse/visits/<id>/service-items     │
│    → 附加诊疗项目/耗材                        │
│ 6. 撤销（执行后）                             │
│    POST /nurse/visits/<id>/revoke            │
│    → 返还库存 → status → revoked             │
└─────────────────────────────────────────────┘
```

### 4.4 库存管理

```
入库:
  POST /nurse/inbound
  ├── type=1 药品: 必传 purchase_price, batch_no, 可选 group
  │   ├── 库存组模式: 整装规格 "10粒/盒" → DrugStockGroup
  │   │   整装Drug + 散装Drug + 共享 total_units
  │   └── 普通模式: 单条 Drug
  ├── type=2 诊疗项目: stock=-1 不参与库存
  └── type=3 耗材: 类似药品

盘点:
  POST /nurse/inventory       → 普通盘点
  POST /nurse/inventory/group → 库存组联合盘点
  → 生成 InventoryRecord (old_stock, new_stock, operation_type)

日终快照 (DailyStockSnapshot):
  每天首次对某药品操作时: 取昨日快照 → 今日期初 = 昨日结存
  结存 = 期初 + 入库 - 出库

月报:
  GET /nurse/inventory/monthly-report
  参数: start_date, end_date (北京时间)
  → 每种药品: 期初库存, 入库合计, 出库合计, 结存库存
```

---

## 5. 数据模型全量定义

### 5.1 模型关系图

```
User ────────────┐                     Drug ──────────────┐
 │1              │                      │1                 │
 │               │                      │                  │
 ├─< Visit(doctor)                     ├─< PrescriptionItem
 │   │1           │                    │   │*             │
 │   │            │                    │   │              │
 │   ├─< Patient  │                    │   ├─< InventoryRecord
 │   │1   │       │                    │   │              │
 │   │    │       │                    │   ├─< DailyStockSnapshot
 │   ├─1─ Payment │                    │   │              │
 │   │            │                    │   └── DrugStockGroup
 │   └─< PrescriptionItem              │       │1
 │                                     │       │
 ├─< Payment(nurse)                    │   ┌───┘
 │                                     │   │
 ├─< TextTemplate                      │   │
 │                                     │   │
 └─< OperationLog                      └───┘

Patient ──< Visit ──1── Payment
               │
               └─< PrescriptionItem ──1── Drug
                                        │
DiagnosisDict                           ├── DrugStockGroup(pack_drug)
TextTemplate ──1── User                 └── DrugStockGroup(retail_drug)
ParkedVisit ──1── Patient
            ──1── User (doctor)
```

### 5.2 全量字段定义

> ⚠️ 以下为 Go 结构体标签风格伪代码，便于重构时直接参考。

#### User（用户）
```go
type User struct {
    ID            uint      `gorm:"primaryKey"`
    Username      string    `gorm:"size:64;uniqueIndex;not null"`
    PasswordHash  string    `gorm:"size:256;not null"`
    RealName      string    `gorm:"size:64"`
    Role          string    `gorm:"size:20;not null"` // admin|doctor|nurse|finance
    TokenVersion  int       `gorm:"default:0"`        // 改密时+1使旧JWT失效
    IsActive      bool      `gorm:"not null;default:true;index"` // 软停用
}
```
> **业务规则**: 改密 → token_version++ → 旧JWT因版本不匹配而失效；停用 → is_active=false → 拒绝所有请求但保留历史数据

#### Patient（患者）
```go
type Patient struct {
    ID           uint      `gorm:"primaryKey"`
    StudentID    *string   `gorm:"size:20;uniqueIndex"`   // 学号(可空)
    Name         string    `gorm:"size:64;index;not null"`
    Gender       string    `gorm:"size:10"`
    ClassName    *string   `gorm:"size:100"`              // 班级
    Phone        *string   `gorm:"size:20"`
    Grade        *string   `gorm:"size:50"`               // 年级
    College      *string   `gorm:"size:100"`              // 学院
    Major        *string   `gorm:"size:100"`              // 专业
    NamePinyin   *string   `gorm:"size:255;index"`        // 全拼
    NameInitials *string   `gorm:"size:255;index"`        // 首字母
    IsTemporary  bool      `gorm:"default:false;index"`   // [遗留] 用 patient_type 替代
    Age          *int      // 临时患者年龄
    IDCard       *string   `gorm:"size:20;index"`         // 身份证号
    CounselorName *string  `gorm:"size:64"`               // 辅导员
    PatientType  string    `gorm:"size:20;default:student;index"` // student|staff|shop|temporary
    Department   *string   `gorm:"size:100"`              // 教职工部门
    ShopName     *string   `gorm:"size:100"`              // 商铺名称
    CreatedAt    time.Time
}
```

#### Drug（药品/项目/耗材字典+库存）
```go
type Drug struct {
    ID              uint      `gorm:"primaryKey"`
    Name            string    `gorm:"size:128;index;not null"`
    Type            int       `gorm:"default:1"`          // 1=药品, 2=诊疗项目, 3=耗材
    Specification   string    `gorm:"size:50"`            // 规格
    Unit            string    `gorm:"size:10"`            // 单位
    Price           float64   // 销售单价
    Stock           int       `gorm:"default:0"`          // 当前库存
    Status          int       `gorm:"default:1"`          // 1=启用, 0=停用
    BatchNo         *string   `gorm:"size:50"`            // 批号
    InboundAt       *time.Time                            // 入库时间
    PurchasePrice   float64   `gorm:"default:0"`          // 进货价
    HasScattered    bool      `gorm:"default:false"`      // 是否支持散装
    ScatteredPrice  *float64                              // 散装售价
    ConversionRate  *int                                  // 换算率(散装数/整装)
    VariantType     *string   `gorm:"size:20"`            // pack|retail
    StockGroupCode  *string   `gorm:"size:36;index"`      // 库存组编码(UUID)
    UnitAmount      *int                                  // 整装内含散装单位数
    BaseName        *string   `gorm:"size:128"`           // 基本药品名
    StorageLocation *string   `gorm:"size:10"`            // 库位
    ExpiryDate      *time.Time                            // 效期
}
```
> **type 枚举**:
> - `1` 药品: 参与库存校验/扣减
> - `2` 诊疗项目: stock=-1，不参与库存
> - `3` 耗材: 参与库存校验/扣减

#### DrugStockGroup（库存组）
```go
type DrugStockGroup struct {
    ID            uint      `gorm:"primaryKey"`
    GroupCode     string    `gorm:"size:36;uniqueIndex;not null"` // UUID
    BatchNo       string    `gorm:"size:50;index;not null"`
    BaseName      string    `gorm:"size:128;index;not null"`
    UnitName      string    `gorm:"size:20;not null"`             // 最小单位名
    TotalUnits    int       `gorm:"not null"`                     // 总散装单位数
    PackAmount    int       `gorm:"not null"`                     // 整装数
    RetailAmount  *int                                           // 散装数
    PackDrugID    uint      `gorm:"not null"`                     // FK→Drug
    RetailDrugID  *uint                                          // FK→Drug(可空)
    CreatedBy     *uint                                          // FK→User
    CreatedAt     time.Time
}
```

#### Visit（就诊记录—核心表）
```go
type Visit struct {
    ID              uint      `gorm:"primaryKey"`
    PatientID       uint      // FK→Patient
    DoctorID        uint      // FK→User
    Timestamp       time.Time `gorm:"index;not null"`
    // 病历
    ChiefComplaint  string    `gorm:"type:text"`
    PresentIllness  string    `gorm:"type:text"`
    PastHistory     string    `gorm:"type:text"`
    PhysicalExam    string    `gorm:"type:text"`
    Diagnosis       string    `gorm:"type:text"`
    DoctorAdvice    string    `gorm:"type:text"`
    SpecialNote     string    `gorm:"type:text"`
    // 金额
    ConsultationFee float64   `gorm:"default:0"`
    TotalAmount     float64   `gorm:"default:0"`
    // 状态流
    Status          string    `gorm:"size:20;default:pending"` // pending|nurse_verified|completed|rejected|revoked
    VerifiedBy      *uint     // FK→User
    VerifiedAt      *time.Time
    RejectedBy      *uint     // FK→User
    RejectedAt      *time.Time
    RejectReason    string    `gorm:"type:text"`
    RevokedBy       *uint     // FK→User
    RevokedAt       *time.Time
    RevokeReason    string    `gorm:"type:text"`
    // 关联
    Items           []PrescriptionItem
    Payment         *Payment  // 1:1
}
```

#### PrescriptionItem（处方明细）
```go
type PrescriptionItem struct {
    ID                uint      `gorm:"primaryKey"`
    VisitID           uint      // FK→Visit
    DrugID            uint      // FK→Drug
    // 用法
    Usage             string    `gorm:"size:100"`
    Dosage            string    `gorm:"size:50"`
    Frequency         string    `gorm:"size:50"`
    Timing            string    `gorm:"size:50"`
    Days              int       `gorm:"default:1"`
    Quantity          int       // 开药数量
    // 价格
    PriceAtVisit      float64   // 开方时单价
    Amount            float64   // 开方时金额=price*quantity
    // 改价审计
    OriginalPrice     *float64  // 原始单价
    OriginalAmount    *float64  // 原始金额
    NewPrice          *float64  // 改后单价
    NewAmount         *float64  // 改后金额
    ModifiedBy        *uint     // FK→User
    ModifiedAt        *time.Time
    ModifyReason      string    `gorm:"type:text"`
    // 散装
    IsScattered       bool      `gorm:"default:false"`
    // 成本
    PurchaseCost      float64   `gorm:"default:0"`
    // 静脉给药
    IsIntravenous     bool      `gorm:"default:false"`
    InfusionGroup     *int      // 配伍组号
    InfusionDosageValue *float64
    InfusionDosageUnit *string   `gorm:"size:10"`
    InfusionMethod    *string   `gorm:"size:50"`
}
```

#### Payment（收费记录）
```go
type Payment struct {
    ID                    uint      `gorm:"primaryKey"`
    VisitID               uint      `gorm:"uniqueIndex"`  // 1:1
    NurseID               uint      // FK→User
    Amount                float64   // 实收总额
    PaymentDate           time.Time
    PaymentMethod         string    `gorm:"size:50"`      // 现金/微信/支付宝
    ReceiptPrinted        bool      `gorm:"default:false"`
    IsEmployeeDiscount    bool      `gorm:"default:false"` // 职工优惠
    OriginalAmount        *float64  // 优惠前金额
    ReceiptSnapshot       string    `gorm:"type:text"`    // 小票快照JSON
    ActualConsultationFee *float64  // 实收诊查费
    ActualDrugAmount      *float64  // 实收物资及项目费
}
```

#### 其他模型

```go
// 诊断字典
type DiagnosisDict struct {
    ID     uint   `gorm:"primaryKey"`
    Code   string `gorm:"size:50;index"`   // ICD-10编码
    Name   string `gorm:"size:200;index"`  // 诊断名
    Pinyin string `gorm:"size:200;index"`  // 全拼
}

// 文本模板(医生快捷录入)
type TextTemplate struct {
    ID        uint   `gorm:"primaryKey"`
    DoctorID  uint   `gorm:"index;not null"`
    Category  string `gorm:"size:50;index;not null"` // present_illness|physical_exam|doctor_advice
    Title     string `gorm:"size:200;not null"`
    Content   string `gorm:"type:text;not null"`
    CreatedAt time.Time
    UpdatedAt time.Time
}

// 库存流水
type InventoryRecord struct {
    ID            uint      `gorm:"primaryKey"`
    DrugID        uint
    NurseID       uint
    VisitID       *uint     `gorm:"index"`
    OldStock      int
    NewStock      int
    OperationType string    `gorm:"size:20;index"` // inbound|adjustment|merge|dispense|reversal
    Remark        string    `gorm:"size:200"`
    Timestamp     time.Time
}

// 日终快照
type DailyStockSnapshot struct {
    ID        uint      `gorm:"primaryKey"`
    DrugID    uint      `gorm:"index"`
    Date      time.Time `gorm:"type:date;index"`
    Stock     int
    CreatedAt time.Time
    // UniqueConstraint: (drug_id, date)
}

// 挂单(草稿)
type ParkedVisit struct {
    ID               uint   `gorm:"primaryKey"`
    PatientID        uint   `gorm:"index;not null"`
    DoctorID         uint   `gorm:"index;not null"`
    ChiefComplaint   string `gorm:"type:text"`
    PresentIllness   string `gorm:"type:text"`
    PastHistory      string `gorm:"type:text"`
    PhysicalExam     string `gorm:"type:text"`
    Diagnosis        string `gorm:"type:text"`
    DoctorAdvice     string `gorm:"type:text"`
    SpecialNote      string `gorm:"type:text"`
    ConsultationFee  float64
    ItemsJSON        string `gorm:"type:text"` // JSON序列化的处方项目
    QuickMode        bool
    CreatedAt        time.Time
    UpdatedAt        time.Time
}

// 运营日志
type OperationLog struct {
    ID        uint      `gorm:"primaryKey"`
    UserID    uint      `gorm:"index"`
    Action    string    `gorm:"size:100;index"`
    Detail    string    `gorm:"type:text"`
    IPAddress string    `gorm:"size:45"`
    CreatedAt time.Time `gorm:"index"`
}
```

---

## 6. API 接口全量清单

### 6.1 公共接口（公开 / 登录用户）

| 方法 | 路径 | 权限 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/api/auth/login` | 公开 | `{ username, password }` | `{ access_token, user }` |
| POST | `/api/auth/change-password` | 登录 | `{ old_password, new_password }` | `{ msg }` |

### 6.2 医生端（/api/doctor/*）

| # | 方法 | 路径 | 说明 | 关键入参 | 关键出参 |
|---|------|------|------|---------|---------|
| 1 | GET | `/doctor/patient/search` | 患者搜索 | `?q=` (姓名/学号/手机/拼音) | `[{ id, name, student_id, ... }]` |
| 2 | POST | `/doctor/patient` | 建档 | `{ name, gender, patient_type, ... }` | `{ id, name, ... }` |
| 3 | PUT | `/doctor/patient/<id>` | 更新患者 | `{ phone?, age?, id_card? }` | `{ msg }` |
| 4 | GET | `/doctor/patient/<pid>/visits` | 患者历史 | — | `[{ id, timestamp, diagnosis, status }]` |
| 5 | GET | `/doctor/drugs/search` | 药品搜索 | `?q=` | `[{ id, name, stock, price, ... }]` |
| 6 | GET | `/doctor/diagnoses/search` | ICD-10搜索 | `?q=` | `[{ id, code, name }]` |
| 7 | POST | `/doctor/visits` | 创建就诊 | `{ patient_id, diagnosis, items[], ... }` | `{ visit_id }` |
| 8 | GET | `/doctor/visits/history` | 历史记录 | `?page=&per_page=&start=&end=` | `{ visits[], total }` |
| 9 | GET | `/doctor/visits/<id>` | 就诊详情 | — | `{ visit, items[], timeline }` |
| 10 | PUT | `/doctor/visits/<id>/medical-record` | 补充病历 | `{ diagnosis?, ... }` | `{ msg }` |
| 11 | GET | `/doctor/visits/<id>/revisions` | 修改记录 | — | `[{ field, old, new, time }]` |
| 12 | GET | `/doctor/templates` | 模板列表 | `?category=` | `[{ id, title, content }]` |
| 13 | POST | `/doctor/templates` | 新建模板 | `{ category, title, content }` | `{ id }` |
| 14 | PUT | `/doctor/templates/<id>` | 更新模板 | `{ title?, content? }` | `{ msg }` |
| 15 | DELETE | `/doctor/templates/<id>` | 删除模板 | — | `{ msg }` |
| 16 | POST | `/doctor/parked-visits` | 保存挂单 | `{ patient_id, ...items_json }` | `{ id }` |
| 17 | GET | `/doctor/parked-visits` | 挂单列表 | — | `[{ id, patient_name, ... }]` |
| 18 | GET | `/doctor/parked-visits/<id>` | 挂单详情 | — | `{ ...visit_fields }` |
| 19 | DELETE | `/doctor/parked-visits/<id>` | 删除挂单 | — | `{ msg }` |
| 20 | GET | `/doctor/patient/<pid>/parked-visit` | 患者挂单 | — | `{ id ... } ` 或 404 |

### 6.3 护士端（/api/nurse/*）

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | GET | `/nurse/pending-visits` | 待处理列表 `?status=pending&page=&per_page=` |
| 2 | GET | `/nurse/drug-names/search` | 入库物资搜索 `?q=` |
| 3 | POST | `/nurse/inbound` | 物资入库 `{ name, type, stock, batch_no, purchase_price, ... }` |
| 4 | POST | `/nurse/inventory` | 普通盘点 `{ drug_id, new_stock }` |
| 5 | POST | `/nurse/inventory/group` | 库存组盘点 `{ group_code, pack_stock, retail_stock }` |
| 6 | GET | `/nurse/inventory/records` | 库存流水 `?drug_id=&page=` |
| 7 | GET | `/nurse/inventory/monthly-report` | 月报 `?start_date=&end_date=&drug_name=` |
| 8 | GET | `/nurse/inventory/monthly-report/export` | 月报Excel导出 |
| 9 | GET | `/nurse/visits/<id>` | 处方详情+库存+成本 |
| 10 | POST | `/nurse/visits/<id>/verify` | 审核通过 |
| 11 | POST | `/nurse/visits/<id>/reject` | 驳回 `{ reason }` |
| 12 | PUT | `/nurse/visits/<id>/items/<iid>/modify` | 改价 `{ new_price, reason? }` |
| 13 | POST | `/nurse/visits/<id>/service-items` | 追加项目 `{ drug_id, quantity, price }` |
| 14 | PUT | `/nurse/visits/<id>/service-items/<iid>` | 修改项目 |
| 15 | DELETE | `/nurse/visits/<id>/service-items/<iid>` | 删除项目 |
| 16 | GET | `/nurse/services/search` | 搜索项目/耗材 `?q=` |
| 17 | POST | `/nurse/visits/<id>/execute` | 执行收费 `{ payment_method, is_employee_discount?, ... }` |
| 18 | PUT | `/nurse/payments/<pid>/print` | 标记已打印 |
| 19 | GET | `/nurse/drugs` | 护士库存列表 |
| 20 | GET | `/nurse/my-history` | 全诊疗历史 `?start=&end=&doctor_id=&patient_name=` |
| 21 | GET | `/nurse/staff-list` | 医生/护士列表（报表筛选） |
| 22 | POST | `/nurse/visits/<id>/revoke` | 撤销 `{ reason }` → 返还库存 |

### 6.4 管理员端（/api/admin/*）

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | GET | `/admin/backup/mysql` | MySQL备份下载 |
| 2 | GET | `/admin/backup` | SQLite在线备份下载 |
| 3 | POST | `/admin/backup` | [兼容]旧客户端SQLite备份 |
| 4 | GET | `/admin/patients/template` | 四类患者CSV模板 |
| 5 | POST | `/admin/patients/import` | CSV批量导入 |
| 6 | GET | `/admin/patients` | 患者分页 `?q=&type=&page=` |
| 7 | POST | `/admin/patients` | 新建患者 |
| 8 | PUT | `/admin/patients/<id>` | 更新患者 |
| 9 | DELETE | `/admin/patients/<id>` | 删除（无就诊引用的） |
| 10 | GET | `/admin/patients/<id>/visits` | 患者历史 |
| 11 | GET | `/admin/visits/<id>` | 就诊详情 |
| 12 | GET | `/admin/drugs` | 物资分页 `?search=&type=&status=&page=` |
| 13 | POST | `/admin/drugs` | 新建物资 |
| 14 | PUT | `/admin/drugs/<id>` | 更新/启停用 |
| 15 | POST | `/admin/drugs/<id>/inbound` | 普通补货 |
| 16 | DELETE | `/admin/drugs/<id>` | 删除（无引用、非库存组） |
| 17 | POST | `/admin/drugs/import` | CSV导入 |
| 18 | POST | `/admin/drugs/import_xls` | Excel导入 |
| 19 | GET | `/admin/drugs/template` | 导入模板下载 |
| 20 | POST | `/admin/drugs/smart-inventory` | 智能盘库（两步确认） |
| 21 | GET | `/admin/statistics/revenue` | 营收统计 `?start=&end=&page=` |
| 22 | GET | `/admin/statistics/revenue/users` | 报表人员筛选项 |
| 23 | GET | `/admin/statistics/revenue/export` | 营收Excel导出 |
| 24 | GET | `/admin/statistics/drug-outbound` | 出库明细 `?start=&end=&drug_name=&page=` |
| 25 | GET | `/admin/statistics/drug-outbound/export` | 出库Excel导出 |
| 26 | GET | `/admin/users` | 用户列表 |
| 27 | POST | `/admin/users` | 创建用户 `{ username, password, real_name, role }` |
| 28 | PUT | `/admin/users/<id>` | 更新用户 |
| 29 | DELETE | `/admin/users/<id>` | 软停用 |
| 30 | GET | `/admin/operation-logs` | 运营日志 `?user_id=&action=&page=` |

### 6.5 财务端（/api/finance/*）

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | GET | `/finance/dashboard/summary` | 今日/本月摘要 `{ today, month: { revenue, cost, profit } }` |
| 2 | GET | `/finance/profit-trend` | 近N天趋势 `?days=30` → `[{ date, revenue, cost, profit }]` |
| 3 | GET | `/finance/revenue/by-type` | 分项营收 `{ consultation, drug, service, consumable }` |

> 财务端复用 admin 的 `/admin/statistics/*` 和 `/admin/drugs`(GET) 接口。

---

## 7. 状态机与业务规则

### 7.1 Visit 状态流转

```
                   ┌──────────┐
                   │  pending  │  ← 医生开方完成
                   └────┬─────┘
                        │
             ┌──────────┼──────────┐
             │          │          │
             ▼          ▼          ▼
       ┌──────────┐ ┌──────────────┐
       │ rejected │ │nurse_verified│ ← 护士审核通过
       └──────────┘ └──────┬───────┘
             │              │
             │              ├── 改价/追加项目
             │              │
             │              ▼
             │        ┌───────────┐
             │        │ completed │ ← 护士执行（扣库存+收费）
             │        └─────┬─────┘
             │              │
             │              ▼
             │        ┌──────────┐
             │        │ revoked  │ ← 护士撤销（返还库存）
             │        └──────────┘
             │
             └── 医生修改病历后 → pending
```

**允许的状态转移**:
```
pending        → nurse_verified, rejected
nurse_verified → completed, rejected
completed      → revoked
rejected       → (终端)
revoked        → (终端)
```

### 7.2 库存计算规则

**基本扣减**: `new_stock = old_stock - quantity`

**整散装扣减**:
```
if is_scattered:
    stock_deduct = ceil(quantity / conversion_rate)  // 散装数→整装单位
else:
    stock_deduct = quantity                           // 整装直接扣
```

**库存组同步扣减**:
```
group.total_units -= stock_deduct
pack_record.stock = floor(group.total_units / pack_amount)
retail_record.stock = group.total_units  // 散装单位
```

### 7.3 营收分摊算法

```python
# 输入: Payment + Visit + PrescriptionItems
# 1. 按 type 归类原始金额:
#    type=1 → drug,  type=2 → service,  type=3 → consumable
#    consultation → consultation_fee
# 2. 按比例分摊实收总额:
#    consultation_actual = actual_total * (consultation / original_total)
#    drug_actual = actual_total * (drug / original_total)
#    service_actual = actual_total * (service / original_total)
#    consumable_actual = actual_total * (consumable / original_total)
# 3. 误差归入权重最大项
# 4. 利润 = 实收 - 进货成本
```

### 7.4 关键校验规则

| 校验点 | 规则 |
|--------|------|
| 密码 | ≥12位，不能与原密码相同 |
| 诊查费 | ≥0 |
| 处方创建 | diagnosis 非空，items 非空，每个 item 至少一个用法字段非空 |
| 库存校验 | type=1 或 type=3 的 drug 库存 ≥ 扣减量 |
| 改价 | 仅 nurse_verified 状态可改，completed 后不可改 |
| 执行 | 必须先 verify 才能 execute |
| 撤销 | 仅 completed 状态可撤销 |
| 入库批号 | 同 drug 下 batch_no 唯一 |
| 软停用 | 不删除 User，设置 is_active=false + token_version++ |
| 职工优惠 | 必须提交分项金额且加总=实收总额 |

### 7.5 并发控制

```
库存操作序列化:
├── 进程内: threading.RLock
├── MySQL: GET_LOCK('medical_room_stock_mutation', 15s)
├── 超时返回: 503 "库存操作繁忙，请稍后重试"
└── 行锁: SELECT ... FOR UPDATE (Drug + DrugStockGroup, ORDER BY id/code)
```

---

## 8. 安全与认证

### 8.1 JWT 设计
- **算法**: HS256
- **密钥**: `JWT_SECRET_KEY`（32+位随机字符串，首次启动生成）
- **有效期**: 7天（`JWT_ACCESS_TOKEN_EXPIRES`）
- **载荷**: `{ sub: user_id }`
- **版本控制**: `User.token_version` → 改密/停用时递增 → 旧 token 的 version 不匹配则 401

### 8.2 密码安全
- **哈希**: `werkzeug.security.generate_password_hash` → bcrypt
- **最小长度**: 12 位
- **占位符检测**: 拒绝 `replace-with-*`, `dev-secret-*` 等前缀的密钥

### 8.3 运行时密钥
- 首次启动自动生成 `SECRET_KEY` + `JWT_SECRET_KEY`
- 存储: `data/.runtime-secrets.json`（权限 600）
- 加锁: 跨平台文件锁（Windows Mutex / Unix flock）

### 8.4 导出安全
- CSV 导出: 对以 `=`, `+`, `-`, `@` 开头的文本加单引号前缀防止公式注入
- 财务脱敏: 患者姓名掩码、移除学号/诊断/主诉

---

## 9. 部署与运维

### 9.1 开发环境
```bash
# 后端
cd backend && python run.py          # :5000
# 前端
cd frontend && npm run dev           # :5888 → proxy → :5000
```

### 9.2 生产部署
```bash
# 后端: waitress WSGI
python run_prod.py                   # :5000 (loopback)

# 前端: 构建 + Nginx
cd frontend && npm run build         # → dist/
# Nginx serve dist/ + proxy /api → :5000
```

### 9.3 数据库
- **SQLite**: `data/app.db`（默认，零配置）
- **MySQL**: 设置环境变量 `DATABASE_URL=mysql+pymysql://user:pass@host/db`
- **备份**: SQLite → `sqlite3.backup()` API, MySQL → `mysqldump --single-transaction`, 自动保留最近 20 份

### 9.4 关键环境变量
| 变量 | 用途 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | 数据库连接 | `sqlite:///data/app.db` |
| `SECRET_KEY` | Flask Session | 运行时生成 |
| `JWT_SECRET_KEY` | JWT 签名 | 运行时生成 |
| `JWT_ACCESS_TOKEN_EXPIRES` | Token 有效期 | `604800` (7天) |
| `MAX_CONTENT_LENGTH` | 请求体限制 | `16MB` |

---

> **Wiki 版本**: v3.0 (Go 重构版) | **生成日期**: 2026-07-10
> **相关文档**: `Go重构技术参考.md` | `项目功能结构参考.md` | `docs/接口清单.md`
