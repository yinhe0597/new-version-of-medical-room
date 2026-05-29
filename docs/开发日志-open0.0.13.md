# 开发日志 open0.0.13（2026-05-29）

## 版本主题：小票打印空安全修复 + 小票快照持久化

### 功能背景

护士端"历史诊疗记录"页面点击任意患者的"打印小票"按钮时，系统弹出"服务器内部错误，请稍后重试"的警告提示。根因是 `GET /nurse/visits/<id>` 接口在遍历处方项时直接访问 `item.drug.name`，若该药品已被从数据库中删除，`item.drug` 为 `None` 导致 `AttributeError`，被全局异常处理器捕获后返回 500。

---

## 一、小票快照持久化（根本解决方案）

### 问题描述

当前小票显示依赖实时数据库关联查询（`Visit` → `PrescriptionItem` → `Drug`）。若处方中的药品后续被管理员删除，关联断裂导致 500 错误。之前的空安全修复治标不治本，无法保证历史小票的长期可用性。

### 实现方案

在支付执行时（`execute_visit`）将小票所需的所有数据以 JSON 快照形式保存到 `Payment` 模型，前端优先使用快照数据渲染小票，彻底消除对药品实时关联的依赖。

**存储设计：**

- `Payment` 模型新增 `receipt_snapshot` TEXT 字段，存储 JSON 序列化的小票快照
- 自动 DDL 迁移：`_ensure_sqlite_column` 确保旧数据库自动添加该列

**快照包含的数据：**

```json
{
  "patient_name": "张三",
  "patient_student_id": "2024001",
  "diagnosis": "上呼吸道感染",
  "doctor_advice": "多喝水，注意休息",
  "special_note": "",
  "items": [
    {
      "drug_name": "阿莫西林胶囊",
      "type": 1,
      "specification": "0.5g*24粒",
      "quantity": 2,
      "usage": "口服",
      "dosage": "1粒",
      "frequency": "tid",
      "timing": "饭后",
      "is_intravenous": false,
      "infusion_group": null,
      "infusion_dosage_value": null,
      "infusion_dosage_unit": null,
      "infusion_method": null
    }
  ]
}
```

**后端变更：**

1. `execute_visit`：Payment 创建后立即生成快照并保存至 `payment.receipt_snapshot = json.dumps(snapshot, ensure_ascii=False)`
2. `get_visit_detail`：读取 `payment.receipt_snapshot`，解析后以 `receipt_snapshot` 字段返回

**前端变更：**

- `openReceipt` 函数：收到响应后判断 `res.data.receipt_snapshot` 是否存在
  - 有快照：用快照数据构建 `receiptVisit` 对象（患者信息、诊断、处方明细）
  - 无快照（旧记录）：回退使用实时数据（已做好空安全保护）
- 模板无需任何修改，快照数据结构与现有 `receiptVisit` 字段名完全一致

### 效果

- 新执行收费的处方 → 快照已保存，即使药品被删除小票也正常显示
- 旧记录（无快照）→ 回退实时查询，已有空安全保护，不会崩溃

---

## 二、空安全修复（即时修复 + 兜底保护）

### 问题描述

`get_visit_detail` 中多个位置直接访问关联对象的属性，未做 null 检查：

```python
# 修改前 — 若 item.drug 为 None 直接崩溃
"drug_name": item.drug.name,
"type": item.drug.type,
"specification": item.drug.specification,
"stock": item.drug.stock,
```

### 修复内容

| 位置 | 修改内容 |
|------|----------|
| `get_visit_detail` | `item.drug.name` → `drug.name if drug else "（已删除药品）"` |
| `get_visit_detail` | `item.drug.type` → `drug.type if drug else None` |
| `get_visit_detail` | `item.drug.specification` → `drug.specification if drug else ""` |
| `get_visit_detail` | `item.drug.stock` → `drug.stock if drug else 0` |
| `get_visit_detail` | `item.drug.conversion_rate` → `drug.conversion_rate if drug else 1` |
| `get_visit_detail` | `visit.patient.name/student_id` — 添加 null 检查 |

### `mark_printed` 异常处理

`PUT /nurse/payments/<id>/print` 接口添加 try/except 异常处理，防止数据库异常时返回空响应。

### 前端 `printReceipt` 错误提示

`HistoryList.vue` 的 `printReceipt` 函数中，标记打印状态的 PUT 请求失败时，从静默 `console.error` 改为显示 `ElMessage.warning` 提示用户。

---

## 三、配置文件变更

| 文件 | 说明 |
|------|------|
| `backend/app/models/__init__.py` | `Payment` 模型新增 `receipt_snapshot` TEXT 列 |
| `backend/app/__init__.py` | 注册 `payment.receipt_snapshot` 自动 DDL 迁移 |
| `backend/app/api/nurse.py` | `execute_visit` 新增快照生成逻辑；`get_visit_detail` 读取并返回快照 + 空安全修复；`mark_printed` 添加异常处理 |
| `frontend/src/views/nurse/HistoryList.vue` | `openReceipt` 优先使用快照数据；`printReceipt` 错误提示增强 |
| `run_prod.py` | 版本号更新 open0.0.12 → open0.0.13 |

---

## 四、设计决策记录

### 为什么选择 JSON 快照而非独立表？

| 方案 | 优点 | 缺点 |
|-----|------|------|
| A: Payment 表加 JSON 字段 ✅ | 实现简单，无需建表，快照随支付记录一同删除（撤销时自动清理） | 大字段与支付主表同表存储 |
| B: 独立 ReceiptSnapshot 表 | 职责分离，可独立管理 | 需额外建表、关联查询、撤销时级联删除 |

校医务室小票数据量有限（单条快照 < 10KB），JSON 字段足以满足需求，且撤销交易时 `db.session.delete(payment)` 自动连带清理快照，无需额外维护。

### 快照为什么不包含价格/金额？

处方项的价格/金额存储在 `PrescriptionItem` 表的 `price_at_visit`、`amount`、`new_price`、`new_amount` 等字段中，这些数据不会因药品删除而丢失。快照的核心目的是保存**药品元数据**（名称、规格、类型），这部分数据在药品删除后会丢失。金额数据从实时查询即可，无需冗余存储。

---

## 五、验证情况

| 验证项 | 结果 |
|-------|------|
| 后端语法检查（`ast.parse`） | ✅ 通过 |
| 所有 Python 文件语法检查 | ✅ 通过 |
| 导入检查（json、Payment、db） | ✅ 全部就绪 |
| 空安全保护（item.drug 为 None 场景） | ✅ 有兜底值 |
| 快照优先逻辑（新记录） | ✅ 使用快照 |
| 回退逻辑（旧记录无快照） | ✅ 使用实时数据 |
