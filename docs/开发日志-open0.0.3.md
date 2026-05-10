# 开发日志 open0.0.3

## 更新日期
2026-05-10

## 版本
open0.0.3

## 本次更新内容

### 一、新功能 - 耗材管理（type=3 耗材类型）

#### 功能概述
在药品管理体系中新增"耗材"类型（type=3），与"药品"（type=1）和"诊疗项目"（type=2）并列，形成完整的三类物资管理。耗材与药品一样具有真实库存，支持入库、盘点、处方中增删、执行时扣减库存及撤销时还原库存等完整生命周期管理。

#### 后端改动

**`backend/app/api/nurse.py`（~15 处修改）**
- 搜索接口 `search_drug_names`：查询范围从 `Drug.type == 1` 扩展为 `Drug.type.in_([1, 3])`
- 入库接口 `inbound_stock`：新增 type=3 分支，包含入库校验、去重检测、InventoryRecord 创建
- 药品列表 `list_drugs`：筛选条件包含 type=3
- 处方审核 `verify_visit`：type=3 耗材视为库存药品参与库存校验
- 处方执行 `execute_visit`：type=3 耗材在执行时扣减库存（与药品一致的库存扣减逻辑）
- 处方撤销 `revoke_visit`：撤销时还原 type=3 耗材库存
- 月度报表 `_compute_monthly_report`：药品消耗统计包含 type=3
- 诊疗项目搜索 `search_services`：搜索范围包含 type=2 和 type=3，护士可在处方审核时添加耗材
- 诊疗项目增删改 `add_service_item/update_service_item/delete_service_item`：type 检查覆盖 type=3，区分操作日志（"护士新增诊疗项目" vs "护士新增耗材"）

**`backend/app/api/admin.py`（~7 处修改）**
- 药品创建 `create_drug`：新增 `elif drug_type == 3` 分支，设置 `variant_type="consumable"`，清除散装相关字段
- 智能盘库 `smart_inventory`：合并和筛选条件包含 type=3
- 营收统计 `get_revenue_stats`：新增 `consumable_revenue` 累加器，三路拆分（药品/诊疗/耗材），明细中增加 `consumable_amount` 字段
- 营收导出 `export_revenue_stats`：Excel 新增"耗材金额"列和"耗材收入"汇总行
- 出库记录 `get/export_drug_outbound_records`：筛选条件从 `type == 1` 改为 `type.in_([1, 3])`

**`backend/app/api/doctor.py`（1 处修改）**
- 处方创建 `create_visit`：库存校验逻辑扩展为 `drug.type in (1, 3) or drug.type is None`

**`scripts/init_demo_db.py`**
- 新增 4 条耗材演示数据：一次性手套、医用棉签、输液贴、一次性注射器(5ml)
- 每条数据设置 `variant_type='consumable'`

#### 前端改动

**`frontend/src/components/DrugEntry.vue`**
- 入库类型选择：新增 `<el-radio :label="3">耗材</el-radio>` 选项
- 耗材入库表单：新增 `v-else-if="form.type === 3"` 模板，包含规格、单位、单价、入库数量等字段
- 表单验证规则：新增 type=3 对应字段的验证规则

**`frontend/src/views/admin/DrugManagement.vue`**
- 类型列：`scope.row.type === 3` 显示"耗材"标签
- 变体类型列：新增 consumable 标签的显示
- 新增/编辑对话框：新增 type=3 单选按钮
- `handleTypeChange`：切换到 type=3 时清除散装相关字段
- 库存字段和操作区域：`v-if="form.type === 1 || form.type === 3"`（耗材与药品一样显示库存字段）

**`frontend/src/views/nurse/ExecutePrescription.vue`**
- `getStockNeeded`：`item.type !== 1 && item.type !== 3` 时返回 0（不参与库存计算）
- `serviceItems` 计算属性：包含 type=2 和 type=3
- `drugItems` 计算属性：排除 type=2 和 type=3
- UI 文案调整："诊疗项目/耗材管理"、"+ 添加项目"、"输入项目/耗材名称搜索"

**`frontend/src/views/nurse/Inventory.vue`**
- 变体类型列：新增 consumable 标签 `<el-tag type="info">耗材</el-tag>`

**`frontend/src/views/doctor/VisitForm.vue`**
- 库存显示：`(item.type === 1 || item.type === 3)` 时显示库存信息
- 最大可开数量：type=3 时使用实际库存作为上限（与药品一致）
- 搜索结果处理：新增 `variant_type === 'consumable'` 的处理分支

---

### 二、系统稳定性 - 数据库自动迁移增强

#### 修复内容
- 补全 `drug` 表缺失列的自动迁移声明：`type`、`purchase_price`、`has_scattered`、`scattered_price`、`conversion_rate`
- 补全 `prescription_item` 表缺失列的自动迁移声明：`is_scattered`、`purchase_cost`
- 优化 `db.create_all()` 执行策略：由"仅在数据库文件不存在时创建"改为"始终调用"（`db.create_all()` 是幂等的，只创建缺失的表，不影响已有表和数据），确保旧数据库缺失的 `drug_stock_group`、`diagnosis_dict`、`text_template`、`daily_stock_snapshot`、`operation_log` 等表也能自动创建

#### 改动文件
- `backend/app/__init__.py` - 新增 7 个 `_ensure_sqlite_column` 调用；移除 `db.create_all()` 的 `os.path.exists` 文件存在性检查

#### 验证结果
- 用模拟旧数据库（缺少 9 列 + 5 表）测试升级：9 列自动添加，5 表自动创建，数据零丢失

---

## 影响范围

- **前端**：5 个文件修改（DrugEntry.vue、DrugManagement.vue、ExecutePrescription.vue、Inventory.vue、VisitForm.vue）
- **后端 API**：3 个文件修改（nurse.py、admin.py、doctor.py）
- **数据库初始化**：1 个文件修改（__init__.py）
- **演示数据**：1 个文件修改（init_demo_db.py）

## 测试验证

- 后端 API 端到端测试通过：药品列表返回 16 条（12 药品 + 4 耗材），诊疗项目搜索返回 type=2 和 type=3
- 数据库迁移测试通过：模拟旧数据库升级场景，列和表自动补充，数据无丢失
