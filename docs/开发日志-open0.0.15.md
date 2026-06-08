# 开发日志 open0.0.15（2026-06-08）

## 版本主题：药品有效期管理 & 智能盘库过期预警 & 护士端界面优化

---

## 一、功能概述

本版本聚焦于**药品有效期管理**这一核心需求，为医务室提供完整的药品有效期追踪、预警和管理能力。同时优化护士端药品管理界面，隐藏不必要的字段。

### 新增功能

| 功能 | 说明 |
|------|------|
| 🗓️ 有效期属性 | Drug 模型新增 `expiry_date` 字段，支持日期类型 |
| ✅ 入库验证 | 创建/编辑药品时验证有效期不能早于当前日期 |
| ⚠️ 智能盘库预警 | 智能盘库新增过期预警模块，按阈值天数筛选即将过期药品 |
| 🏷️ 前端状态标识 | 药品列表有效期三色标签：已过期（红）/ 30天内到期（黄）/ 正常（绿） |
| 👩‍⚕️ 护士端界面精简 | 隐藏“包装”和“零卖单价”列，减少干扰信息 |
| 📦 智能盘库类目勾选 | 支持勾选“库存预警”和“有效期预警”类目，单独或组合筛选 |

---

## 二、后端变更

### 2.1 数据模型（models/__init__.py）

```python
class Drug(db.Model):
    # ... 现有字段 ...
    expiry_date = db.Column(db.Date, nullable=True)  # 有效期
```

**自动迁移**（`__init__.py`）：
```python
_ensure_sqlite_column(app, "drug", "expiry_date", "DATE")
```

### 2.2 药品管理 API（admin.py）

#### 查询接口 `GET /admin/drugs`

响应新增 `expiry_date` 字段：
```json
{
  "id": 1,
  "name": "阿莫西林",
  "expiry_date": "2026-12-31"
}
```

#### 创建接口 `POST /admin/drugs`

接受 `expiry_date` 参数（YYYY-MM-DD 格式），并进行验证：
```python
# 有效期验证
if data.get('expiry_date'):
    expiry_val = date.fromisoformat(data['expiry_date'])
    if expiry_val < date.today():
        return jsonify({"msg": "有效期不能早于当前日期"}), 400
```

#### 编辑接口 `PUT /admin/drugs/<id>`

支持修改 `expiry_date`，同样进行日期验证。

#### 智能盘库 `POST /admin/drugs/smart-inventory`

新增 `expiry_threshold` 参数（默认30天），返回有效期预警药品：

```python
# 有效期预警药品（阈值天数内到期）
expiry_threshold = int(data.get('expiry_threshold', 30))
today = date.today()
warn_date = today + timedelta(days=expiry_threshold)
expiry_query = Drug.query.filter(
    Drug.type.in_([1, 3]),
    Drug.status == 1,
    Drug.expiry_date != None,
    Drug.expiry_date <= warn_date
)
expiry_drugs = expiry_query.order_by(Drug.expiry_date.asc()).all()
```

响应新增 `expiry_warnings` 字段：
```json
{
  "data": {
    "merged_groups": 0,
    "deleted_duplicates": 0,
    "warnings": [...],
    "expiry_warnings": [
      {
        "id": 460,
        "name": "阿莫西林",
        "specification": "0.5g*24粒",
        "expiry_date": "2026-07-01",
        "days_remaining": 23,
        "stock": 10,
        "is_expired": false
      }
    ],
    "expiry_threshold": 30
  }
}
```

### 2.3 护士端接口（nurse.py）

`GET /nurse/drugs` 响应同步新增 `expiry_date` 字段。

---

## 三、前端变更

### 3.1 药品管理（DrugManagement.vue）

#### 表格新增有效期列

```html
<el-table-column label="有效期" width="120">
  <template #default="scope">
    <template v-if="scope.row.expiry_date">
      <el-tag :type="getExpiryTagType(scope.row.expiry_date)" size="small">
        {{ scope.row.expiry_date }}
        <span v-if="getExpiryDays(scope.row.expiry_date) < 0">已过期</span>
        <span v-else-if="getExpiryDays(scope.row.expiry_date) <= 30">
          {{ getExpiryDays(scope.row.expiry_date) }}天
        </span>
      </el-tag>
    </template>
    <span v-else>—</span>
  </template>
</el-table-column>
```

#### 表单新增日期选择器

```html
<el-form-item label="有效期" v-if="form.type === 1">
  <el-date-picker
    v-model="form.expiry_date"
    type="date"
    placeholder="选择有效期"
    value-format="YYYY-MM-DD"
    :disabled-date="(d) => d < new Date(new Date().setHours(0,0,0,0))"
    clearable
  />
</el-form-item>
```

#### 计算工具函数

```javascript
const getExpiryDays = (expiryDate) => {
  if (!expiryDate) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const expiry = new Date(expiryDate)
  return Math.ceil((expiry - today) / (1000 * 60 * 60 * 24))
}

const getExpiryTagType = (expiryDate) => {
  const days = getExpiryDays(expiryDate)
  if (days === null) return 'info'
  if (days < 0) return 'danger'      // 已过期
  if (days <= 30) return 'warning'   // 30天内到期
  return 'success'                   // 正常
}
```

### 3.2 智能盘库（Inventory.vue）

#### 新增有效期预警天数输入

```html
<div style="display: flex; align-items: center; gap: 8px;">
  <span>有效期预警天数：</span>
  <el-input-number
    v-model="smartExpiryThreshold"
    :min="1"
    :max="365"
    style="width: 120px;"
  />
</div>
```

#### 有效期预警清单表格

显示药品名称、规格、有效期、剩余天数、库存、状态，已过期行高亮红色背景。

### 3.3 护士端字段隐藏

通过角色判断隐藏"包装"和"零卖单价"列：

```javascript
import { useUserStore } from '@/store/user'
const userStore = useUserStore()
const isNurse = computed(() => userStore.userInfo?.role === 'nurse')
```

```html
<el-table-column label="包装" v-if="!isNurse">...</el-table-column>
<el-table-column prop="scattered_price" label="零卖单价" v-if="!isNurse">...</el-table-column>
```

---

## 四、修改文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `backend/app/models/__init__.py` | 修改 | Drug 模型新增 `expiry_date` 字段 |
| `backend/app/__init__.py` | 修改 | 新增 `expiry_date` 自动迁移 |
| `backend/app/api/admin.py` | 修改 | 药品 CRUD 支持有效期，智能盘库新增过期预警 |
| `backend/app/api/nurse.py` | 修改 | 护士端药品列表返回有效期字段 |
| `frontend/src/views/admin/DrugManagement.vue` | 修改 | 新增有效期列、表单日期选择器、角色判断隐藏字段 |
| `frontend/src/views/nurse/Inventory.vue` | 修改 | 智能盘库新增有效期预警清单、类目勾选筛选机制 |

---

## 五、Git 提交记录

```
494b220 fix: 智能盘库弹窗新增类目勾选 — 支持单独筛选库存预警或有效期预警
2fbbadb fix: 护士端药品管理隐藏包装和零卖单价列
5a00029 feat: 药品有效期管理功能 — 新增expiry_date字段，入库验证、智能盘库过期预警、前端状态标识
39e588e docs: 功能总览默认缩起 — 使用 <details> 标签折叠中文/英文版功能表格
d886da9 docs: README 支持中英切换 — 新增 README.en.md，顶部添加语言切换栏
75cf4cb docs: 编译打包防遗漏检查清单 — 避免代码修改后未重新打包EXE
```

---

## 六、验证测试

### 6.1 有效期入库验证

✅ 创建有效期为 `2026-07-01` 的药品成功  
✅ 尝试创建过去日期 `2020-01-01` 被拒绝，返回 `400: 有效期不能早于当前日期`

### 6.2 智能盘库过期预警

✅ `expiry_threshold: 30` 正确返回 23 天内到期的药品  
✅ 已过期药品 `is_expired: true`，剩余天数为负数

### 6.3 前端显示

✅ 药品列表有效期三色标签正常显示  
✅ 智能盘库弹窗有效期预警清单正常渲染  
✅ 护士端“包装”和“零卖单价”列正确隐藏

### 6.4 智能盘库类目勾选

✅ 勾选/取消“库存预警”类目，对应阈值输入和结果表动态显示/隐藏  
✅ 勾选/取消“有效期预警”类目，对应天数输入和结果表动态显示/隐藏  
✅ 全部取消时“重新筛选”按钮禁用，提示“请至少勾选一个筛选类目”

---

## 七、部署信息

| 项目 | 值 |
|------|-----|
| 版本号 | open0.0.15 |
| 发布日期 | 2026-06-08 |
| 部署路径 | `D:\yiwushi\yws20260608` |
| EXE 大小 | 85.9 MB |
