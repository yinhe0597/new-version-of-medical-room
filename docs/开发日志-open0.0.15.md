# 开发日志 open0.0.15（2026-06-09）

## 版本主题：药品有效期管理 & 智能盘库过期预警 & 护士端界面优化 & 患者类型扩展

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
| 📦 智能盘库类目勾选 | 支持勾选"库存预警"和"有效期预警"类目，单独或组合筛选 |
| 👥 患者类型扩展 | 支持学生/教职工/商铺员工/临时人员四种类型区分管理 |
| 🪪 身份证自动算年龄 | 教职工/商铺员工录入身份证号后自动计算年龄 |
| 📋 多模板批量导入 | 三种CSV模板（学生/教职工/商铺员工），按类型独立导入去重 |

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

## 四、患者类型扩展功能

### 4.1 需求背景

系统原有患者管理仅区分"学生"和"临时人员"（通过 `is_temporary` 布尔值），实际使用中出现教师与学生同名同姓导致混淆的问题。需要将患者类型细分为四种：**学生**（student）、**教职工**（staff）、**商铺员工**（shop）、**临时人员**（temporary）。

### 4.2 数据模型（models/__init__.py）

Patient 模型新增三个字段：

```python
patient_type = db.Column(db.String(20), default='student', index=True)
department = db.Column(db.String(100), nullable=True)   # 教职工二级单位
shop_name = db.Column(db.String(100), nullable=True)     # 商铺员工所在商铺
```

`id_card` 字段新增 `index=True` 以支持按身份证去重查询。

**自动迁移**（`__init__.py`）：
```python
_ensure_sqlite_column(app, "patient", "patient_type", "VARCHAR(20) DEFAULT 'student'")
_ensure_sqlite_column(app, "patient", "department", "VARCHAR(100)")
_ensure_sqlite_column(app, "patient", "shop_name", "VARCHAR(100)")
```

**历史数据兼容迁移**：启动时自动将 `is_temporary=1` 的记录更新为 `patient_type='temporary'`，其余为 `'student'`。

### 4.3 后端 API（admin.py & doctor.py）

#### 工具函数

- `_is_valid_cn_id_card()`：18位中国身份证校验（加权因子校验码验证）
- `_age_from_id_card()`：从身份证出生日期字段计算周岁

#### 管理员端变更

| 端点 | 变更 |
|------|------|
| `GET /admin/patients/template` | 支持 `type` 参数返回不同CSV模板（学生/教职工/商铺员工） |
| `POST /admin/patients/import` | 三种导入分支：学生按 `student_id` 去重，教职工/商铺员工按 `id_card` 去重 |
| `GET /admin/patients` | 新增 `patient_type` 过滤参数，响应增加 `department`、`shop_name` 字段 |
| `POST /admin/patients` | 根据 `patient_type` 差异化校验和创建 |
| `PUT /admin/patients/<id>` | 支持类型变更、新字段更新、`id_card` 变更自动重算 `age` |

#### 医生端变更

| 端点 | 变更 |
|------|------|
| `GET /doctor/patient/search` | 响应增加 `patient_type`、`department`、`shop_name`、`id_card` |
| `POST /doctor/patient` | 支持 `patient_type` 参数，staff/shop 类型按 `id_card` 去重 |

### 4.4 前端变更

#### 管理员端 PatientManagement.vue

- 新增类型筛选下拉框（全部/学生/教职工/商铺员工/临时人员）
- 表格列按筛选类型动态显示/隐藏（如学生显示学号/班级，教职工显示单位）
- 新增/编辑表单：四类型下拉选择器，按类型条件渲染专属字段
- `calcAgeFromIdCard()` 前端函数实现身份证自动算年龄
- 批量导入弹窗：新增导入类型选择，下载模板和上传URL带 `type` 参数

#### 医生端 PatientSearch.vue

- 搜索建议下拉项增加 `el-tag` 类型标签（如 "教职工"、"商铺员工"）
- 患者信息展示区新增"人员类型"展示，不同专属字段按类型条件显示
- 确认接诊弹窗 HTML 动态生成人员类型和对应专属信息

---

## 五、修改文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `backend/app/models/__init__.py` | 修改 | Drug 模型新增 `expiry_date` 字段 |
| `backend/app/__init__.py` | 修改 | 新增 `expiry_date` 自动迁移；新增 `patient_type`、`department`、`shop_name` 迁移及历史数据兼容 |
| `backend/app/api/admin.py` | 修改 | 药品 CRUD 支持有效期，智能盘库新增过期预警；患者管理支持四种类型 |
| `backend/app/api/nurse.py` | 修改 | 护士端药品列表返回有效期字段 |
| `backend/app/api/doctor.py` | 修改 | 患者搜索返回类型字段，创建患者支持多类型，就诊日志改进 |
| `frontend/src/views/admin/DrugManagement.vue` | 修改 | 新增有效期列、表单日期选择器、角色判断隐藏字段 |
| `frontend/src/views/admin/PatientManagement.vue` | 修改 | 类型筛选、四类型表单、批量导入多模板、身份证自动算年龄 |
| `frontend/src/views/doctor/PatientSearch.vue` | 修改 | 搜索标签、类型展示、接诊弹窗动态信息 |
| `frontend/src/views/nurse/Inventory.vue` | 修改 | 智能盘库新增有效期预警清单、类目勾选筛选机制 |

---

## 六、Git 提交记录

```
494b220 fix: 智能盘库弹窗新增类目勾选 — 支持单独筛选库存预警或有效期预警
2fbbadb fix: 护士端药品管理隐藏包装和零卖单价列
5a00029 feat: 药品有效期管理功能 — 新增expiry_date字段，入库验证、智能盘库过期预警、前端状态标识
39e588e docs: 功能总览默认缩起 — 使用 <details> 标签折叠中文/英文版功能表格
d886da9 docs: README 支持中英切换 — 新增 README.en.md，顶部添加语言切换栏
75cf4cb docs: 编译打包防遗漏检查清单 — 避免代码修改后未重新打包EXE
```

---

## 七、验证测试

### 7.1 有效期入库验证

✅ 创建有效期为 `2026-07-01` 的药品成功  
✅ 尝试创建过去日期 `2020-01-01` 被拒绝，返回 `400: 有效期不能早于当前日期`

### 7.2 智能盘库过期预警

✅ `expiry_threshold: 30` 正确返回 23 天内到期的药品  
✅ 已过期药品 `is_expired: true`，剩余天数为负数

### 7.3 前端显示

✅ 药品列表有效期三色标签正常显示  
✅ 智能盘库弹窗有效期预警清单正常渲染  
✅ 护士端“包装”和“零卖单价”列正确隐藏

### 7.4 智能盘库类目勾选

✅ 勾选/取消"库存预警"类目，对应阈值输入和结果表动态显示/隐藏  
✅ 勾选/取消"有效期预警"类目，对应天数输入和结果表动态显示/隐藏  
✅ 全部取消时"重新筛选"按钮禁用，提示"请至少勾选一个筛选类目"

### 7.5 患者类型扩展

✅ Patient 模型新增 `patient_type`、`department`、`shop_name` 字段，`id_card` 加索引  
✅ 历史数据自动迁移：`is_temporary=1` → `patient_type='temporary'`，其余 → `'student'`  
✅ 管理员端列表支持按类型筛选，新增/编辑支持四种类型差异化字段  
✅ 批量导入三种模板，学生按 `student_id` 去重，教职工/商铺员工按 `id_card` 去重  
✅ 身份证18位校验 + 自动计算年龄（前后端均实现）  
✅ 医生端搜索显示类型标签，不同专属字段按类型条件展示  
✅ Python `ast.parse` 语法检查通过，`vite build` 前端构建成功

---

## 八、部署信息

| 项目 | 值 |
|------|-----|
| 版本号 | open0.0.15 |
| 发布日期 | 2026-06-09 |
| 部署路径 | `D:\yiwushi\yws20260608` |
| EXE 大小 | 81.9 MB |
