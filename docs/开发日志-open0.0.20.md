# 开发日志 open0.0.20（2026-06-24）

## 版本主题：库存盘点完整性修复 & 单独购药诊查费Bug修复 & 职工优惠功能细分

---

## 一、库存逻辑修复 — 防止新增药品/耗材"无故丢失"

### 问题背景

月度盘点报表依赖 `InventoryRecord` 追踪库存变化。管理员通过以下途径新增或修改药品/耗材库存时，没有创建对应的 `InventoryRecord` 盘点记录，导致月度报表中这些库存变化"消失"：

- ❌ `create_drug` — 新增药品/耗材（初始入库）
- ❌ `update_drug` — 编辑药品/耗材库存
- ❌ `import_drugs`（CSV导入）— 批量导入药品
- ❌ `import_drugs_xls`（Excel导入）— 批量导入药品

### 修复内容

在 `backend/app/api/admin.py` 中所有库存变更点添加 `InventoryRecord` 创建：

| 接口 | 触发条件 | remark |
|------|------|------|
| `create_drug` | 药品/耗材初始 stock > 0 | `初始入库(管理员新增)` |
| `update_drug` | 药品/耗材 stock 发生变化 | `管理员编辑库存` |
| `import_drugs` (CSV) | 既有药品 stock 增加 | `CSV批量入库` |
| `import_drugs` (CSV) | 新药品 stock > 0 | `CSV初始入库` |
| `import_drugs_xls` (Excel) | 新药品 stock > 0 | `Excel批量初始入库` |

### 影响范围

- 药品（type=1）和耗材（type=3）均受此修复保护
- 诊疗项目（type=2）不涉及库存追踪，无需 InventoryRecord
- 月度盘点报表将正确反映所有历史库存变化

---

## 二、单独购药诊查费 Bug 修复

### 问题背景

当医生使用"单独购药"功能（默认诊查费为 0 元）开具处方后，若被护士驳回，医生点击"重新开方"时，诊查费会错误地显示为 **8 元**而非 **0 元**。

### 根本原因

`frontend/src/views/doctor/VisitForm.vue` 第 642 行：

```javascript
// 修复前（错误）
visitForm.value.consultation_fee = Number(detail.consultation_fee || 8)
```

JavaScript 中 `0` 是 falsy 值，`0 || 8` 的求值结果为 `8`，导致诊查费为 0 时被错误替换为 8 元。

### 修复方案

```javascript
// 修复后
visitForm.value.consultation_fee = detail.consultation_fee != null ? Number(detail.consultation_fee) : 8
```

使用 `!= null` 判断值是否存在（仅 `null`/`undefined` 时使用默认值 8），`0` 作为有效值不会被错误替换。

---

## 三、护士"职工优惠"功能细分

### 问题背景

原有"职工优惠"功能仅允许护士填写一个"实收金额"，无法区分诊查费优惠和药价优惠，也未提供药品成本价参考。

### 改动方案

#### 3.1 数据模型

`Payment` 模型新增两个字段（`backend/app/models/__init__.py`）：

```python
actual_consultation_fee = db.Column(db.Float, nullable=True)  # 实收诊查费
actual_drug_amount = db.Column(db.Float, nullable=True)       # 实收药价
```

#### 3.2 数据库迁移

`backend/app/__init__.py` 添加 SQLite 自动迁移：

```python
_ensure_sqlite_column(app, "payment", "actual_consultation_fee", "FLOAT")
_ensure_sqlite_column(app, "payment", "actual_drug_amount", "FLOAT")
```

#### 3.3 后端接口

**`GET /nurse/visits/<id>`** — 每个药品条目新增返回：
- `purchase_price`：药品进货价（单位成本参考）
- `purchase_cost`：该条目的成本合计

**`POST /nurse/visits/<id>/execute`** — 支持分项实收参数：
- 新模式：传入 `actual_consultation_fee` + `actual_drug_amount`，分别存储到 Payment
- 兼容旧模式：仍支持 `actual_amount` 单一实收金额

#### 3.4 前端 UI（`ExecutePrescription.vue`）

勾选"职工优惠"后，原单一"实收金额"输入框替换为：

- **实收诊查费**：默认填入应收诊查费，括号显示"应收 ¥XX"
- **实收药价**：默认填入应收药价，括号显示"应收 ¥XX，成本参考 ¥XX"
- **合计实收**：实时计算两项之和

药品成本参考值取自 `purchase_price`（进货价）× 数量，或 `purchase_cost`（处方条目成本），供护士填写实收药价时参考。

---

## 四、营收统计报表分页功能

### 问题背景

管理员端营收统计报表（`/admin/statistics/revenue`）一次性返回全部明细数据。随着业务数据增长，历史就诊记录越来越多，全量返回导致：

- 接口响应变慢，前端渲染卡顿
- 明细表格一次性加载数千行数据，用户体验差

### 改动方案

#### 4.1 后端分页（`backend/app/api/admin.py`）

`GET /admin/statistics/revenue` 接口新增分页参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|------|------|
| `page` | int | 1 | 页码（≥1） |
| `per_page` | int | 20 | 每页条数（1-200） |

响应新增分页元数据：

```json
{
  "data": {
    "total_revenue": ...,
    "details": [...],   // 分页后的明细数据
    "total": 156,       // 明细总条数（全量）
    "page": 1,          // 当前页码
    "per_page": 20      // 每页条数
  }
}
```

> 汇总统计（总收入、成本、利润等）始终基于全量数据计算，仅明细列表受分页影响。

#### 4.2 前端分页（`frontend/src/views/admin/Statistics.vue`）

- 明细表格下方新增 `<el-pagination>` 分页组件，支持 10/20/50/100 条/页切换
- 筛选条件（日期范围、医生、护士）变更时自动重置到第 1 页
- 统计类型切换（日报/月报/年报）时自动重置到第 1 页

---

## 五、涉及文件清单

| 文件 | 改动类型 | 说明 |
|------|------|------|
| `backend/app/models/__init__.py` | 新增字段 | Payment 模型增加 actual_consultation_fee / actual_drug_amount |
| `backend/app/__init__.py` | 新增迁移 | SQLite 自动迁移新 Payment 字段 |
| `backend/app/api/admin.py` | 修复+增强 | create_drug / update_drug / import_drugs / import_drugs_xls 增加 InventoryRecord；营收统计新增分页参数 |
| `backend/app/api/nurse.py` | 增强 | get_visit_detail 返回成本价；execute_visit 支持分项实收 |
| `frontend/src/views/doctor/VisitForm.vue` | 修复 | 驳回重开方诊查费 0 值 bug |
| `frontend/src/views/nurse/ExecutePrescription.vue` | 重构 | 职工优惠 UI 拆分为实收诊查费 + 实收药价 + 成本参考 |
| `frontend/src/views/admin/Statistics.vue` | 增强 | 营收统计明细表格新增分页组件 |

---

## 六、Git 提交记录

```
d20149c feat: open0.0.20 库存盘点完整性修复 & 单独购药诊查费Bug修复 & 职工优惠功能细分
40545bc feat: open0.0.20 营收统计报表分页功能
```

---

## 七、部署信息

| 项目 | 详情 |
|------|------|
| 分支 | main |
| 数据库兼容 | 旧数据库自动补齐 Payment 新字段，无需手动迁移 |
| 前端兼容 | 旧版前端仍可通过 actual_amount 单一字段正常使用职工优惠 |
