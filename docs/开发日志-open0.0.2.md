# 开发日志 open0.0.2

## 更新日期
2026-05-09

## 本次更新内容

### 一、护士端 - 智能盘库功能增强

#### 新增功能
- 在护士端"库存盘点"页面新增"智能盘库"按钮
- 自定义库存预警阈值：默认30，护士可根据需要调整
- "仅显示含散类目"复选框：勾选后只显示名称或规格含"散"字的药品
- 两项筛选条件可组合使用，支持重新筛选

#### 改动文件
- `frontend/src/views/nurse/Inventory.vue` - 新增智能盘库按钮与增强版对话框
- `backend/app/api/admin.py` - smart_inventory 接口支持 threshold 和 scattered_only 参数

### 二、护士端 - 撤销交易逻辑优化

#### 逻辑调整
- 撤销后处方状态改为 `revoked`（已撤销）终态，不再回退到 `pending`（待处理）
- 保留原始审核信息（verified_by/verified_at），完整保存操作痕迹
- 已撤销状态为终态，不可再进行其他状态转移
- 医生端历史记录中显示"已撤销"灰色标签

#### 改动文件
- `backend/app/models/__init__.py` - 新增 VISIT_STATUS_REVOKED 常量，更新状态转移字典
- `backend/app/api/nurse.py` - 撤销接口状态设为 revoked，不再清除审核信息
- `frontend/src/views/nurse/HistoryList.vue` - 添加 revoked 状态标签和筛选选项
- `frontend/src/views/doctor/PrescriptionHistory.vue` - 添加 revoked 状态标签

### 三、护士端 - 药品管理页面精简

#### 改动
- 删除药品管理页面中不再使用的"批量入库"按钮
- 删除药品管理页面中的"智能盘库"按钮（已迁移到库存盘点页面）
- 清理相关的无用代码（变量、方法、弹窗、导入）

#### 改动文件
- `frontend/src/views/admin/DrugManagement.vue` - 移除批量入库和智能盘库相关代码

### 四、系统稳定性 - 数据库自动迁移修复

#### 修复内容
- 修复旧数据库缺少 Visit 表新增字段（revoked_by, revoked_at, revoke_reason）导致的 500 错误
- 修复旧数据库缺少 Payment 表新增字段（receipt_printed, is_employee_discount, original_amount）导致统计报表无数据
- 应用启动时自动检测并补全缺失字段，确保旧数据库无缝兼容

#### 改动文件
- `backend/app/__init__.py` - 添加 Visit 和 Payment 表的自动字段迁移检测
