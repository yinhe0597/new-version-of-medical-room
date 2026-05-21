# 开发日志 open0.0.10（2026-05-21）

## 版本主题：耗材管理流程纳管流转增强 — 医生端耗材可见性与业务闭环修复

### 问题背景

护士反馈：新增的某些耗材偶尔不见了，库存页面找不到了，医生开方看不到，没有起到纳管流转业务流程。

经全链路代码审查，发现 **6 个 Bug**，其中 3 个严重问题直接导致耗材在医生端"消失"。

---

## 一、Bug修复 - 医生端单独购药页面耗材 variant_type 处理缺失（严重）

### 问题描述

`DirectPurchase.vue` 的 `searchDrugs` 函数中，搜索结果处理逻辑只识别 `retail`、`pack`、`service` 三种 `variant_type`，缺少 `consumable` 分支。耗材落入 else 分支，被错误标记为"整装"，option_id 使用 `:whole` 后缀，与耗材的实际类型不匹配。

### 影响

医生在"单独购药"页面搜索耗材时，耗材显示为"整装"而非"耗材"，身份丢失，医生无法识别。

### 修复方案

在 `variant_type` 分支判断中新增 `consumable` 处理分支：
- `option_id` 设为 `${d.id}:consumable`
- `option_label` 设为 `'耗材'`
- `maxStock` 设为 `d.stock`（与 VisitForm.vue 保持一致）

### 改动文件

| 文件 | 改动说明 |
|------|---------|
| `frontend/src/views/doctor/DirectPurchase.vue` | L436: 新增 `if (d.variant_type === 'consumable')` 分支 |

---

## 二、Bug修复 - 医生端单独购药页面耗材不显示库存（严重）

### 问题描述

`DirectPurchase.vue` 搜索下拉选项中，库存显示条件为 `item.type === 1`，仅药品(type=1)显示库存数量。耗材(type=3)同样拥有真实库存，但搜索下拉中不显示库存信息。

对比 `VisitForm.vue` 已正确处理：`(item.type === 1 || item.type === 3) ? '库存: ...'`。

### 影响

医生无法在单独购药页面看到耗材的库存数量，无法判断是否可开方。

### 修复方案

将库存显示条件从 `item.type === 1` 改为 `(item.type === 1 || item.type === 3)`。

### 改动文件

| 文件 | 改动说明 |
|------|---------|
| `frontend/src/views/doctor/DirectPurchase.vue` | L120: 库存显示条件补充 type=3 |

---

## 三、Bug修复 - 医生端单独购药页面耗材数量上限不受库存限制（严重）

### 问题描述

`DirectPurchase.vue` 处方明细中，数量输入框的 `max` 属性仅对 `type === 1` 使用 `maxStock` 限制，耗材(type=3)的 max 固定为 999，可以开出超过库存的数量。

对比 `VisitForm.vue` 已正确处理：`(scope.row.type === 1 || scope.row.type === 3) ? ... maxStock ... : 999`。

### 影响

医生可以对耗材开出超过实际库存的处方数量，导致库存管理失控，护士执行时库存不足报错。

### 修复方案

将数量上限条件从 `scope.row.type === 1` 改为 `(scope.row.type === 1 || scope.row.type === 3)`。

### 改动文件

| 文件 | 改动说明 |
|------|---------|
| `frontend/src/views/doctor/DirectPurchase.vue` | L158: 数量 max 条件补充 type=3 |

---

## 四、Bug修复 - 医生端接诊开方页面耗材用法显示文案错误

### 问题描述

`VisitForm.vue` 处方明细中，用法/用量区域的 `v-else` 分支统一显示"诊疗项目 (无需填写用法)"。当药品类型为 type=3(耗材) 时，应显示"耗材"而非"诊疗项目"。

### 修复方案

将固定文案改为动态判断：`scope.row.type === 3 ? '耗材 (按数量使用)' : '诊疗项目 (无需填写用法)'`。

### 改动文件

| 文件 | 改动说明 |
|------|---------|
| `frontend/src/views/doctor/VisitForm.vue` | L171: 用法文案按 type 区分耗材/诊疗项目 |

---

## 五、Bug修复 - 医生端单独购药页面耗材用法显示文案

### 问题描述

与问题四类似，`DirectPurchase.vue` 处方明细中 `v-else` 分支统一显示"无需填写用法"，未区分耗材与诊疗项目。

### 修复方案

同问题四，改为动态判断文案。

### 改动文件

| 文件 | 改动说明 |
|------|---------|
| `frontend/src/views/doctor/DirectPurchase.vue` | L152: 用法文案按 type 区分耗材/诊疗项目 |

---

## 六、Bug修复 - 管理员新增药品/耗材未设置 base_name

### 问题描述

`admin.py` 的 `create_drug` 函数创建 Drug 记录时未设置 `base_name` 字段，而护士端入库（`inbound_stock`）对 type=3 耗材会设置 `base_name=name`。两条新增路径数据不一致，可能影响护士端名称搜索（`search_drug_names` 按 `base_name` 查询，虽有 name 回退，但不一致）。

### 修复方案

在 `create_drug` 中添加 `base_name=data['name']`，与护士端入库路径保持一致。

### 改动文件

| 文件 | 改动说明 |
|------|---------|
| `backend/app/api/admin.py` | L531: 新增 `base_name=data['name']` |

---

## 根因分析：为什么"偶尔不见了"

医生端搜索接口 `doctor.py:search_drugs` 中，对 type=1 和 type=3 的药品/耗材有零库存过滤逻辑：

```python
if (drug.type in (1, 3) or drug.type is None) and (drug.stock or 0) <= 0:
    if drug.variant_type in ["retail", "pack"] or drug.has_scattered:
        continue  # 有散装/零售的药品还能显示
    # 耗材 variant_type='consumable' + has_scattered=False → 直接跳过！
```

当耗材库存被消耗到 0 时，由于 `variant_type='consumable'` 和 `has_scattered=False`，耗材会从医生端搜索结果中完全消失。再加上 `DirectPurchase.vue` 不识别 `consumable` 类型（问题一），形成了"新增的耗材偶尔找不到了"的现象——库存充足时可见，库存耗尽后消失。

> 注：库存=0 时过滤是设计决策（药品同理），但耗材的 variant_type 不属于 retail/pack/has_scattered 类别，导致它比药品更容易被过滤。如业务上需要"缺货耗材仍可见"（方便医生提示补货），可单独调整 `doctor.py` 的过滤逻辑。
