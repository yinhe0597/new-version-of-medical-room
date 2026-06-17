# 开发日志 open0.0.17（2026-06-12）

## 版本主题：护士入库"丢失"问题修复 & 耗材有效期入库支持 & 管理员修改密码

---

## 一、功能概述

本版本修复了护士反映的入库药品/耗材"丢失"问题（3 个根因），同时补全耗材入库有效期支持，并新增管理员端修改密码 API。

### 修复问题

| 问题 | 说明 |
|------|------|
| 🔍 医生端零库存药品"消失" | 医生搜索接口将库存为 0 的药品/耗材静默跳过，导致医生无法开方，护士误以为入库记录丢失 |
| 🔁 409 重复入库无引导 | 护士入库同名+同规格+同批次物资时后端返回 409，前端仅弹警告，未引导补货 |
| 📋 护士列表新项目难找 | 护士药品列表仅按存放位置排序，新入库项目排在最后，分页下需翻到末页 |

### 新增功能

| 功能 | 说明 |
|------|------|
| 🗓️ 耗材入库有效期 | 护士端药品/耗材入库表单新增有效期日期选择器，后端同步接收并存储 |
| 🔑 管理员修改密码 | 新增 `POST /auth/change-password` 接口，管理员端对接真实 API |

---

## 二、后端变更

### 2.1 医生端搜索零库存修复（doctor.py）

**修复前**：零库存药品/耗材被 `continue` 跳过，搜索接口不返回。

```python
# 修复前
if (drug.type in (1, 3) or drug.type is None) and (drug.stock or 0) <= 0:
    if drug.variant_type in ["retail", "pack"] or drug.has_scattered:
        continue  # 静默隐藏
```

**修复后**：删除 `continue`，改为标记 `out_of_stock` 后仍然返回：

```python
is_oos = (drug.type in (1, 3) or drug.type is None) and (drug.stock or 0) <= 0
data.append({
    ...,
    "stock": drug.stock,
    "out_of_stock": is_oos
})
```

### 2.2 护士药品列表排序优化（nurse.py）

增加 `Drug.id DESC` 作为二级排序，新入库项目优先显示：

```python
# 修复前
query = query.order_by(Drug.storage_location.asc().nullslast())

# 修复后
query = query.order_by(Drug.storage_location.asc().nullslast(), Drug.id.desc())
```

### 2.3 护士入库有效期支持（nurse.py）

耗材（type=3）和药品（type=1，整包+拆零）入库均新增 `expiry_date` 解析与校验：

```python
expiry_val = None
expiry_str = (data.get("expiry_date") or "").strip()
if expiry_str:
    expiry_val = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    if expiry_val < date.today():
        return jsonify({"msg": "expiry_date cannot be in the past"}), 400
```

创建 Drug 对象时传入 `expiry_date=expiry_val`。

### 2.4 管理员修改密码 API（auth.py）

新增 `POST /auth/change-password` 接口：

- 需要 JWT 认证，通过 `get_jwt_identity()` 获取当前用户
- 校验原密码、新密码长度（≥6 位）
- 成功后调用 `set_password` 更新密码

```python
@bp.route('/auth/change-password', methods=['POST'])
@jwt_required()
def change_password():
    data = request.get_json() or {}
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    ...
```

---

## 三、前端变更

### 3.1 医生端搜索结果零库存标识（VisitForm.vue / DirectPurchase.vue）

对 `out_of_stock: true` 的药品显示灰色半透明 + 红色"库存为0"标签，但不从列表中移除：

```html
:style="item.out_of_stock ? 'opacity: 0.5;' : ''"
<el-tag v-if="item.out_of_stock" type="danger" size="small">库存为0</el-tag>
```

### 3.2 409 重复入库引导（DrugEntry.vue）

将 `ElMessageBox.alert` 改为 `ElMessageBox.confirm`，提供"前往补货"按钮跳转库存列表：

```javascript
ElMessageBox.confirm(
  (error.msg || '该物资已存在重复批次记录') + '\n是否前往库存列表进行补货？',
  '重复校验',
  { confirmButtonText: '前往补货', cancelButtonText: '取消', type: 'warning' }
).then(() => { router.push('/nurse/drugs') }).catch(() => {})
```

### 3.3 护士入库有效期表单（DrugEntry.vue）

药品（type=1）和耗材（type=3）入库表单均新增有效期日期选择器：

```html
<el-form-item label="有效期">
  <el-date-picker v-model="form.expiry_date" type="date"
    placeholder="选择有效期（可选）" value-format="YYYY-MM-DD"
    :disabled-date="(r) => r < new Date(new Date().setHours(0,0,0,0))" clearable />
</el-form-item>
```

### 3.4 管理员药品管理耗材有效期（DrugManagement.vue）

有效期日期选择器条件从 `form.type === 1` 扩展为 `form.type === 1 || form.type === 3`。

### 3.5 智能盘库文案优化（Inventory.vue）

预警表格列标题和文案从"药品"改为通用的"名称"和"物资"，覆盖耗材。

### 3.6 管理员修改密码对接（SystemSettings.vue）

将 mock `changePassword` 替换为真实 API 调用 `/auth/change-password`，增加前端校验和 loading 状态。

---

## 四、修改文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `backend/app/api/doctor.py` | 修改 | 搜索接口删除零库存 continue，增加 out_of_stock 标记 |
| `backend/app/api/nurse.py` | 修改 | 入库有效期解析（耗材+药品）；列表排序增加 id DESC |
| `backend/app/api/auth.py` | 修改 | 新增 change-password 接口 |
| `frontend/src/components/DrugEntry.vue` | 修改 | 入库有效期选择器；409 confirm 引导补货 |
| `frontend/src/views/admin/DrugManagement.vue` | 修改 | 耗材表单显示有效期选择器 |
| `frontend/src/views/admin/SystemSettings.vue` | 修改 | 修改密码对接真实 API |
| `frontend/src/views/doctor/VisitForm.vue` | 修改 | 搜索结果零库存灰色+标签 |
| `frontend/src/views/doctor/DirectPurchase.vue` | 修改 | 搜索结果零库存灰色+标签 |
| `frontend/src/views/nurse/Inventory.vue` | 修改 | 预警表格文案从"药品"改为"物资" |

---

## 五、Git 提交记录

```
fix: 护士入库药品/耗材"丢失"问题修复 — 零库存搜索可见、409补货引导、列表排序优化
feat: 护士入库有效期支持 — 药品和耗材入库表单新增有效期字段
feat: 管理员修改密码API — POST /auth/change-password 前后端对接
```

---

## 六、验证测试

✅ 入库药品后使用至库存为 0，医生搜索仍能找到（显示灰色"库存为0"标签）  
✅ 入库同名+同规格+同批次药品，409 弹窗提供"前往补货"按钮，点击跳转库存列表  
✅ 入库新药品后查看列表，新项目出现在第一页（id DESC 二级排序生效）  
✅ 耗材入库时填写有效期，数据库正确存储 expiry_date  
✅ 药品入库时填写有效期，数据库正确存储 expiry_date  
✅ 管理员端修改密码成功，旧密码校验生效  
✅ `vite build` 前端构建成功  
✅ `pyinstaller medical_room.spec` 打包成功  
✅ EXE 文件正确输出到 `D:\yiwushi\yws20260608`

---

## 七、部署信息

| 项目 | 值 |
|------|-----|
| 版本号 | open0.0.17 |
| 发布日期 | 2026-06-12 |
| 部署路径 | `D:\yiwushi\yws20260608` |
| EXE 大小 | ~82 MB |
