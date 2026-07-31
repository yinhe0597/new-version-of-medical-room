# 🚀 校医务室诊疗管理系统 — Go 语言重构参考文档

> **目标**: 从 Python/Flask → Go 的完整技术映射与实施指南
> **参考**: backend-java 原型代码 | Python 源码 | 现有文档 | 56 个测试用例

---

## 目录

1. [Go 技术栈选型建议](#1-go-技术栈选型建议)
2. [从 Flask → Go 的架构映射](#2-从-flask--go-的架构映射)
3. [核心模块重构清单](#3-核心模块重构清单)
4. [数据模型 GORM 定义](#4-数据模型-gorm-定义)
5. [关键算法实现参考](#5-关键算法实现参考)
6. [测试策略](#6-测试策略)
7. [迁移清单（按优先级）](#7-迁移清单按优先级)

---

## 1. Go 技术栈选型建议

### 1.1 推荐组合

| 层 | 推荐方案 | 备选 | 理由 |
|----|---------|------|------|
| **Web 框架** | `gin` | `echo` / `fiber` | 社区最大、中间件丰富、性能优秀 |
| **ORM** | `gorm` v2 | `ent` / `sqlc` | 最接近 SQLAlchemy 体验、Hooks/Migration 完整 |
| **JWT** | `golang-jwt/jwt/v5` | — | 标准库级别 |
| **密码** | `golang.org/x/crypto/bcrypt` | — | 与 Python werkzeug 兼容 |
| **配置** | `viper` | `envconfig` | 支持文件+环境变量 |
| **日志** | `zap` | `slog` (标准库) | 结构化、高性能 |
| **验证** | `go-playground/validator` | — | 与 gin binding 集成 |
| **迁移** | `golang-migrate` | `atlas` | 轻量、文件化 |
| **Excel** | `excelize` | — | 读写 xlsx |
| **拼音** | `go-pinyin` | — | 中文拼音转换 |
| **测试** | `testify` + `httptest` | — | 断言 + HTTP 测试 |
| **定时任务** | `cron` (robfig) | — | 替代 APScheduler |

### 1.2 项目结构（推荐 Layout）

```
yws-go/
├── cmd/
│   └── server/
│       └── main.go                # 入口：初始化DB、注册路由、启动
├── internal/
│   ├── config/
│   │   └── config.go              # Viper 配置加载
│   ├── middleware/
│   │   ├── auth.go                # JWT 解析中间件
│   │   └── rbac.go                # 角色鉴权中间件
│   ├── handler/                   # HTTP Handler（替代 Flask Blueprint）
│   │   ├── auth.go                #   登录、改密
│   │   ├── doctor.go              #   医生端 20 个端点
│   │   ├── nurse.go               #   护士端 22 个端点
│   │   ├── admin.go               #   管理端 30 个端点
│   │   ├── finance.go             #   财务端 3 个端点
│   │   └── router.go              #   路由注册
│   ├── service/                   # 业务逻辑层
│   │   ├── drug_stock.go          #   整散装规格解析+库存计算（参照 backend-java）
│   │   ├── inventory_ledger.go    #   库存流水+日终快照+月报
│   │   ├── revenue.go             #   营收分摊算法
│   │   └── stock_lock.go          #   库存操作并发控制
│   ├── model/                     # GORM 模型
│   │   └── models.go              #   13 个模型（可拆分）
│   ├── dto/                       # 请求/响应结构体
│   │   ├── auth.go
│   │   ├── doctor.go
│   │   ├── nurse.go
│   │   └── admin.go
│   └── util/
│       ├── password.go            #   bcrypt 封装
│       ├── timezone.go            #   北京时间工具
│       ├── pinyin.go              #   中文拼音
│       └── spreadsheet.go         #   CSV 安全导出
├── migrations/                    # SQL 迁移文件
│   ├── 001_init.up.sql
│   └── 001_init.down.sql
├── tests/                         # 集成测试
│   ├── auth_test.go
│   ├── doctor_test.go
│   ├── nurse_test.go
│   └── admin_test.go
├── go.mod
├── go.sum
├── Makefile
├── .env.example
└── docs/
    └── ...
```

---

## 2. 从 Flask → Go 的架构映射

### 2.1 全局对应关系

| Python/Flask 概念 | Go/Gin 等价 | 说明 |
|-------------------|-------------|------|
| `Flask(__name__)` | `gin.Default()` | 应用实例 |
| `Blueprint` | `gin.RouterGroup` | 路由分组 |
| `@bp.route('/path', methods=['POST'])` | `router.POST("/path", handler)` | 路由定义 |
| `@role_required('admin')` | `middleware.RequireRole("admin")` | 中间件链 |
| `request.get_json()` | `c.ShouldBindJSON(&dto)` | 请求绑定 |
| `jsonify({...})` | `c.JSON(200, gin.H{...})` | JSON 响应 |
| `db.session.add(x); db.session.commit()` | `db.Create(&x)` | 单条插入 |
| `db.session.rollback()` | `tx.Rollback()` | 事务回滚 |
| `Model.query.filter_by(...).all()` | `db.Where(...).Find(&result)` | 查询 |
| `get_jwt_identity()` | `c.Get("user_id")` | 从上下文取用户ID |
| `current_app.config.get('KEY')` | `viper.GetString("key")` | 配置读取 |
| `utcnow()` | `time.Now().UTC()` | 时间 |
| `from pypinyin import pinyin` | `github.com/mozillazg/go-pinyin` | 拼音 |
| `flask_migrate` | `golang-migrate` | 数据库迁移 |

### 2.2 请求处理流水线

```
Python (Flask):
  Request → @role_required → @bp.route → handler → jsonify → Response

Go (Gin):
  Request → authMiddleware → RequireRole("admin") → handler → c.JSON → Response
              ↓
         JWT 解析 → DB 查 User → c.Set("user", user)
                                 c.Set("role", user.Role)
```

### 2.3 事务处理模式

```go
// Python: db.session 隐式事务
// Go: 显式事务（推荐，避免并发问题）

func (s *NurseService) ExecutePrescription(ctx context.Context, visitID uint, req ExecuteRequest) error {
    return s.db.Transaction(func(tx *gorm.DB) error {
        // 1. 锁定 Visit + Items
        var visit Visit
        if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).
            Preload("Items.Drug").First(&visit, visitID).Error; err != nil {
            return err
        }
        // 2. 状态校验
        if visit.Status != "nurse_verified" {
            return ErrInvalidVisitStatus
        }
        // 3. 库存扣减
        for _, item := range visit.Items {
            deduct := calculateStockDeduct(item)
            if err := tx.Model(&Drug{}).Where("id = ? AND stock >= ?", item.DrugID, deduct).
                Update("stock", gorm.Expr("stock - ?", deduct)).Error; err != nil {
                return ErrInsufficientStock
            }
        }
        // 4. 创建 Payment
        payment := Payment{...}
        if err := tx.Create(&payment).Error; err != nil {
            return err
        }
        // 5. 更新 Visit 状态
        if err := tx.Model(&visit).Update("status", "completed").Error; err != nil {
            return err
        }
        return nil // 提交
    })
}
```

---

## 3. 核心模块重构清单

### 3.1 auth.go — 认证模块

```go
// POST /api/auth/login
type LoginRequest struct {
    Username string `json:"username" binding:"required"`
    Password string `json:"password" binding:"required"`
}
type LoginResponse struct {
    AccessToken string   `json:"access_token"`
    User        UserInfo `json:"user"`
}

// POST /api/auth/change-password
type ChangePasswordRequest struct {
    OldPassword string `json:"old_password" binding:"required"`
    NewPassword string `json:"new_password" binding:"required,min=12"`
}
```

**关键逻辑**:
1. 查 User → bcrypt 验证 → 生成 JWT（含 user_id + token_version）→ 返回 token+user
2. 改密: 验证旧密码 → bcrypt 生成新 hash → token_version++ → 旧 token 失效

### 3.2 doctor.go — 医生端

**20 个端点**，关键业务:

| 端点 | Go 实现要点 |
|------|-----------|
| `POST /visits` | 事务: 创建 Visit + PrescriptionItems + 库存校验 + 金额计算 |
| `GET /patient/search` | LIKE 查询 name/student_id/phone/name_pinyin/name_initials |
| `POST /patient` | 按 patient_type 分支校验必填字段 + pinyin 自动生成 |
| `POST /parked-visits` | items 序列化为 JSON 存入 items_json 字段 |

### 3.3 nurse.go — 护士端（最复杂模块）

**22 个端点**，核心难点:

| 端点 | 复杂度 | 关键点 |
|------|--------|--------|
| `POST /inbound` | ⭐⭐⭐⭐ | 整散装规格解析 + DrugStockGroup 创建 + 库存组入库 |
| `POST /inventory/group` | ⭐⭐⭐ | 双 Drug 同步盘点 + group.total_units 更新 |
| `GET /monthly-report` | ⭐⭐⭐⭐⭐ | DailyStockSnapshot 日终快照 + 期初/出库/结存计算 + 跨天补快照 |
| `POST /execute` | ⭐⭐⭐⭐ | 事务: 库存校验锁 → 扣减 → 库存组同步 → 生成 Payment → 更新状态 → 生成 InventoryRecord |
| `POST /revoke` | ⭐⭐⭐ | 事务: 状态校验 → 库存返还 → 库存组返还 → 更新状态 |

### 3.4 admin.go — 管理端

**30 个端点**，关键业务:

| 端点 | 复杂度 | 关键点 |
|------|--------|--------|
| `POST /smart-inventory` | ⭐⭐⭐⭐ | 两步确认: 首次返回候选 (merge_candidates) → 前端确认 → 后台合并 + 更新库存组 |
| `GET /backup` | ⭐⭐ | SQLite 用 sqlite3 backup API；MySQL 用 mysqldump |
| `POST /patients/import` | ⭐⭐ | CSV 解析 + 4 种 patient_type 分支 + pinyin 生成 |
| `GET /statistics/revenue` | ⭐⭐⭐⭐ | 营收分摊 + 北京时间日界 + 财务脱敏 + 分页 |

### 3.5 finance.go — 财务端

**3 个端点**，复用 admin 的统计/药品接口:

| 端点 | 说明 |
|------|------|
| `GET /dashboard/summary` | 今日/本月 营收+成本+利润+环比 |
| `GET /profit-trend` | 近N天趋势，每条含 revenue/cost/profit |
| `GET /revenue/by-type` | 按 consultation/drug/service/consumable 分拆 |

---

## 4. 数据模型 GORM 定义

详见 [WIKI-重整版.md §5](WIKI-重整版.md#5-数据模型全量定义)，以下为 GORM 特有的实现要点。

### 4.1 模型关系定义

```go
// Visit → PrescriptionItems (1:N)
type Visit struct {
    gorm.Model  // 替换 ID, CreatedAt, UpdatedAt, DeletedAt
    // ...
    Items []PrescriptionItem `gorm:"foreignKey:VisitID"`
}

// Visit → Payment (1:1)
type Visit struct {
    // ...
    Payment *Payment `gorm:"foreignKey:VisitID"`
}

// Visit → Patient (N:1)
type Visit struct {
    PatientID uint
    Patient   Patient `gorm:"foreignKey:PatientID"`
}

// PrescriptionItem → Drug (N:1)
type PrescriptionItem struct {
    DrugID uint
    Drug   Drug `gorm:"foreignKey:DrugID"`
}

// DrugStockGroup → Drug (N:1) ×2
type DrugStockGroup struct {
    PackDrugID    uint
    PackDrug      Drug `gorm:"foreignKey:PackDrugID"`
    RetailDrugID  *uint
    RetailDrug    *Drug `gorm:"foreignKey:RetailDrugID"`
}
```

### 4.2 迁移注意事项

```go
// 1. 唯一索引
type DailyStockSnapshot struct {
    DrugID uint      `gorm:"uniqueIndex:idx_drug_date"`
    Date   time.Time `gorm:"uniqueIndex:idx_drug_date;type:date"`
}

// 2. Float 精度 → 使用 Decimal（推荐）
//    Python 原版使用 Float，Go 中建议用 string + decimal 库 或 int（分）
//    示例: Amount int64 `json:"amount"` // 单位：分

// 3. 布尔默认值
type User struct {
    IsActive bool `gorm:"default:true;not null"`
}

// 4. 可空指针
type Patient struct {
    Phone *string `gorm:"size:20"` // NULLable
}
```

### 4.3 金额字段建议

| 原 Python | 建议 Go | 理由 |
|-----------|---------|------|
| `db.Float` → `float64` | `int64`（分）或 `decimal` 库 | 避免浮点精度问题 |
| Price, Amount, ConsultationFee 等 | 全部改为单位「分」 | 财务精度要求 |

---

## 5. 关键算法实现参考

### 5.1 整散装规格解析（参照 backend-java）

```go
// 输入: "10粒/盒" → 输出: PackAmount=10, UnitName="粒", PackUnit="盒"
// 输入: "12片*2板/盒" → 输出: PackAmount=24, UnitName="片", PackUnit="盒"

import "regexp"

var packSpecPattern = regexp.MustCompile(`^\s*.+[xX×]\s*(\d+)\s*([^\d/\s]+)\s*/\s*(\S+)\s*$`)

type PackSpec struct {
    PackAmount int
    UnitName   string
    PackUnit   string
}

func ParsePackSpec(spec string) (*PackSpec, error) {
    matches := packSpecPattern.FindStringSubmatch(strings.TrimSpace(spec))
    if matches == nil {
        return nil, errors.New("invalid pack specification")
    }
    amount, _ := strconv.Atoi(matches[1])
    return &PackSpec{
        PackAmount: amount,
        UnitName:   matches[2],
        PackUnit:   matches[3],
    }, nil
}
```

### 5.2 库存组入库生成（参照 backend-java DrugStockService.generate）

```go
func (s *DrugStockService) Generate(dto DrugStockDTO, groupCode string) (*GeneratedResult, error) {
    // 1. 解析整装规格
    pack, err := ParsePackSpec(dto.PackSpec)
    // 2. 创建整装 Drug 记录
    packDrug := Drug{
        Name:          dto.Name,
        Type:          1,
        Specification: dto.PackSpec,
        Unit:          pack.PackUnit,
        Price:         dto.PackPrice,
        Stock:         dto.InboundQuantity,
        BatchNo:       dto.BatchNo,
        VariantType:   "pack",
        StockGroupCode: &gc,
        UnitAmount:    &pack.PackAmount,
    }
    // 3. 如果不启用散装 → 只创建整装
    if !dto.RetailEnabled {
        return &GeneratedResult{PackRecord: &packDrug}, nil
    }
    // 4. 解析最小销售单位 → 创建散装 Drug
    minUnit, _ := ParseMinUnit(dto.MinSaleUnit)
    totalUnits := dto.InboundQuantity * pack.PackAmount
    retailQty := totalUnits / minUnit.MinSaleAmount
    retailDrug := Drug{
        Name:           dto.Name + "(散)",
        Type:           1,
        Specification:  fmt.Sprintf("%d%s", minUnit.MinSaleAmount, minUnit.UnitName),
        Unit:           minUnit.UnitName,
        Price:          dto.MinSalePrice,
        Stock:          retailQty,
        HasScattered:   true,
        ConversionRate: &minUnit.MinSaleAmount,  // ❗ 散装的 conversion_rate = 散装单位数
        VariantType:    "retail",
        StockGroupCode: &gc,
    }
    // 5. 创建 DrugStockGroup
    group := DrugStockGroup{
        GroupCode:    gc,
        BatchNo:      dto.BatchNo,
        BaseName:     dto.Name,
        UnitName:     pack.UnitName,
        TotalUnits:   totalUnits,
        PackAmount:   dto.InboundQuantity,
        RetailAmount: &retailQty,
    }
    return &GeneratedResult{PackRecord: &packDrug, RetailRecord: &retailDrug, Group: &group}, nil
}
```

### 5.3 营收分摊（参照 revenue.py）

```go
// allocatePaymentRevenue → []RevenueBreakdown
type RevenueBreakdown struct {
    Consultation float64 `json:"consultation"`
    Drug         float64 `json:"drug"`
    Service      float64 `json:"service"`
    Consumable   float64 `json:"consumable"`
    Total        float64 `json:"total"`
    Cost         float64 `json:"cost"`
    Profit       float64 `json:"profit"`
}

func AllocateRevenue(payment *Payment, visit *Visit, items []PrescriptionItem) RevenueBreakdown {
    // 1. 归类原始金额
    var consultation, drug, service, consumable, cost float64
    consultation = visit.ConsultationFee
    for _, item := range items {
        amount := item.Amount
        if item.NewAmount != nil { amount = *item.NewAmount }
        switch item.Drug.Type {
        case 1: drug += amount
        case 3: consumable += amount
        default: service += amount
        }
        cost += item.PurchaseCost
    }
    // 2. 按比例分摊实收总额
    originalTotal := consultation + drug + service + consumable
    actualTotal := payment.Amount
    result := RevenueBreakdown{
        Consultation: actualTotal * consultation / originalTotal,
        Drug:         actualTotal * drug / originalTotal,
        Service:      actualTotal * service / originalTotal,
        Consumable:   actualTotal * consumable / originalTotal,
        Total:        actualTotal,
        Cost:         cost,
        Profit:       actualTotal - cost,
    }
    // 3. 处理职工优惠显式分项
    if payment.ActualConsultationFee != nil && payment.ActualDrugAmount != nil {
        result.Consultation = *payment.ActualConsultationFee
        // 剩余按比例分到 drug/service/consumable
        // ...
    }
    return result
}
```

### 5.4 日终快照与月报

```go
// 日终快照: 每天首次操作某药品时创建
func EnsureDailySnapshot(db *gorm.DB, drugID uint, date time.Time) error {
    var snap DailyStockSnapshot
    err := db.Where("drug_id = ? AND date = ?", drugID, date).First(&snap).Error
    if err == nil { return nil } // 已存在
    if !errors.Is(err, gorm.ErrRecordNotFound) { return err }

    // 获取昨日快照作为今日期初
    yesterday := date.AddDate(0, 0, -1)
    var yesterdaySnap DailyStockSnapshot
    db.Where("drug_id = ? AND date = ?", drugID, yesterday).First(&yesterdaySnap)

    // 今日入库量
    var inbound int64
    db.Model(&InventoryRecord{}).
        Where("drug_id = ? AND operation_type = 'inbound' AND date(timestamp) = ?", drugID, date).
        Select("COALESCE(SUM(new_stock - old_stock), 0)").Scan(&inbound)

    // 创建今日快照
    todaySnap := DailyStockSnapshot{
        DrugID: drugID,
        Date:   date,
        Stock:  yesterdaySnap.Stock + int(inbound), // 将从出库扣减中更新
    }
    return db.Create(&todaySnap).Error
}

// 月报: 期初/出库/结存
func MonthlyReport(db *gorm.DB, start, end time.Time) ([]MonthlyReportRow, error) {
    // 对每种药品:
    // opening_stock = start 日期的快照 stock
    // outbound = 期间 dispense/reversal 的 Σ(new_stock - old_stock)
    // closing_stock = opening_stock + 期间inbound - 期间outbound
    //   (或直接取 end+1 天快照的 stock)
}
```

---

## 6. 测试策略

### 6.1 测试对应关系

| Python 测试 (56 个) | Go 等价 |
|---------------------|---------|
| `test_auth_login` | 2 测试: 登录+密码策略 |
| `test_nurse_visit_workflow` | 7 测试: 审核→改价→执行→撤销 全流程 |
| `test_drug_inbound_stock` | 10 测试: 入库+库存组+月报 |
| `test_prescription_validation_and_verify` | 6 测试: 处方校验规则 |
| `test_revenue_allocation` | 2 测试: 营收分摊+职工优惠 |
| `test_timezone_and_privacy` | 2 测试: 时区+脱敏 |
| `test_admin_safety_workflows` | 4 测试: 备份+智能盘库+密码策略 |
| `test_runtime_configuration` | 4 测试: 密钥生成+并发安全 |

### 6.2 Go 测试框架

```go
func TestLogin(t *testing.T) {
    // setup: gin.CreateTestContext + httptest.NewRecorder
    gin.SetMode(gin.TestMode)
    w := httptest.NewRecorder()
    c, _ := gin.CreateTestContext(w)
    c.Request = httptest.NewRequest("POST", "/api/auth/login", 
        strings.NewReader(`{"username":"admin","password":"123456"}`))
    c.Request.Header.Set("Content-Type", "application/json")
    
    // 使用 testify
    assert := assert.New(t)
    handler.Login(c)
    assert.Equal(200, w.Code)
    
    var resp LoginResponse
    json.Unmarshal(w.Body.Bytes(), &resp)
    assert.NotEmpty(resp.AccessToken)
    assert.Equal("admin", resp.User.Role)
}

func TestNurseWorkflow(t *testing.T) {
    db := setupTestDB(t)
    // 1. 创建就诊 → 状态=pending
    // 2. 审核通过 → 状态=nurse_verified
    // 3. 改价 → 审计字段更新
    // 4. 执行 → 状态=completed, 库存扣减, Payment 生成
    // 5. 撤销 → 状态=revoked, 库存返还
}
```

### 6.3 测试数据库

```go
func setupTestDB(t *testing.T) *gorm.DB {
    // 方案1: SQLite 内存数据库（最快）
    db, _ := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
    db.AutoMigrate(&User{}, &Patient{}, &Drug{}, ...)
    
    // 方案2: 测试容器（CI 环境）
    // 使用 testcontainers-go 启动 MySQL
    
    // Seed 数据
    seedTestData(db)
    return db
}
```

---

## 7. 迁移清单（按优先级）

### Phase 1: 基础设施（1-2 周）

- [ ] `cmd/server/main.go` — 启动入口
- [ ] `internal/config/config.go` — Viper 配置
- [ ] `internal/model/models.go` — 13 个 GORM 模型
- [ ] `internal/middleware/auth.go` — JWT 中间件
- [ ] `internal/middleware/rbac.go` — 角色鉴权中间件
- [ ] `internal/handler/auth.go` — 登录 + 改密
- [ ] `internal/handler/router.go` — 路由注册
- [ ] `internal/util/password.go` — bcrypt
- [ ] `internal/util/timezone.go` — 北京时间工具
- [ ] `migrations/001_init.sql` — 数据库建表
- [ ] `tests/` — 测试框架搭建

### Phase 2: 核心业务（2-3 周）

- [ ] `internal/handler/doctor.go` — 医生端 20 个端点
- [ ] `internal/service/drug_stock.go` — 整散装（参照 backend-java）
- [ ] `internal/handler/nurse.go` — 护士端 22 个端点
- [ ] `internal/service/inventory_ledger.go` — 库存流水+日终快照+月报
- [ ] `internal/service/stock_lock.go` — 库存并发控制
- [ ] `internal/service/revenue.go` — 营收分摊

### Phase 3: 管理与报表（1-2 周）

- [ ] `internal/handler/admin.go` — 管理端 30 个端点
- [ ] `internal/handler/finance.go` — 财务端 3 个端点
- [ ] `internal/util/spreadsheet.go` — CSV 安全导出
- [ ] `internal/util/pinyin.go` — 中文拼音

### Phase 4: 增强与优化（1-2 周）

- [ ] 金额 Float → Decimal/分
- [ ] 完整测试覆盖（56+ 个测试用例）
- [ ] API 文档（Swagger/OpenAPI 自动生成）
- [ ] Docker 部署支持
- [ ] 性能基准测试
- [ ] 前端适配（API 路径不变则无需改动）

---

## 附录 A: Python → Go 快速对照

| Python 代码 | Go 代码 |
|------------|---------|
| `if not value:` | `if value == "" || value == nil` |
| `isinstance(value, str)` | `_, ok := value.(string)` |
| `value or 0` | `if value == nil { 0 } else { *value }` |
| `db.session.add(obj)` | `db.Create(&obj)` |
| `db.session.commit()` | `tx.Commit()` |
| `Model.query.filter_by(id=x).first()` | `db.Where("id = ?", x).First(&result)` |
| `Model.query.filter_by(id=x).all()` | `db.Where("id = ?", x).Find(&results)` |
| `func.count()` | `select count(*) from ...` |
| `@jwt_required()` | `middleware.AuthRequired()` |
| `jsonify({"msg": "ok"})` | `c.JSON(200, gin.H{"msg": "ok"})` |
| `request.get_json()` | `c.ShouldBindJSON(&req)` |
| `datetime.utcnow()` | `time.Now().UTC()` |
| `try: ... except Exception: ...` | `if err != nil { ... }` |

## 附录 B: 参照代码清单

| 参照源 | 用途 | 可靠度 |
|--------|------|--------|
| `backend/app/models/__init__.py` | 模型定义 | ✅ 权威 |
| `backend/app/api/*.py` | 接口逻辑 | ✅ 权威 |
| `backend/tests/*.py` (56 个) | 业务规则验证 | ✅ 权威 |
| `backend-java/.../DrugStockService.java` | 整散装解析算法 | ✅ 已验证 |
| `docs/WIKI-重整版.md` | 系统全貌 | ✅ 刚整理 |
| `docs/接口清单.md` | API 字典 | ✅ 权威 |
| `docs/主线全方位修复记录-2026-07-10.md` | 修复记录+规则清单 | ✅ 最新 |

---

> **文档版本**: v1.0 | **生成日期**: 2026-07-10
> **配套文档**: `WIKI-重整版.md` | `项目功能结构参考.md`
