# 处方强制检查、护士审核闭环与护士端扩权 Spec

## Why

当前系统已具备“医生开方 → 护士执行/结算”的基本链路，但对“医生开具处方后的强制检查/校验”与“护士端库存/报表能力边界”需要进一步制度化与信息化，以减少漏填、错填、越权与返工，并满足护士端实际操作需求。

## What Changes

- 强化医生端开方提交前的强制检查（前端 + 后端一致校验）
- 固化护士端“审核 → 执行（抓药/扣库存/结算）”的必经流程，并在审核时执行可复现的校验
- 将管理员端的部分能力下放至护士端：
  - 药品库存管理的全部能力（药品/项目 CRUD、启停用、批量入库、模板下载、智能盘库、库存调整流水）
  - 营收统计的导出能力，并细化导出内容（至少提供可审计的明细字段）
- MySQL 支持：确保新增字段/索引/导出查询在 MySQL 下可正常迁移与运行（保留通过环境变量配置数据库连接的方式）

## Impact

- Affected specs: 处方质量控制、护士审核闭环、库存管理权限、报表与导出、数据库迁移（MySQL）
- Affected code:
  - Backend: `backend/app/api/doctor.py`、`backend/app/api/nurse.py`、`backend/app/api/admin.py`、`backend/app/models/__init__.py`、migrations
  - Frontend: `frontend/src/views/doctor/VisitForm.vue`、`frontend/src/views/nurse/*`、`frontend/src/views/admin/*`、`frontend/src/router/index.js`

## ADDED Requirements

### Requirement: 医生开方强制检查

系统 SHALL 在医生提交处方时执行强制检查，不满足条件不得生成就诊记录（Visit）与处方明细（PrescriptionItem）。

#### 强制检查规则（最小集合）

- 必须选择患者（patient\_id）
- 处方明细 items 必须非空
- `diagnosis` 必须非空（允许多条文本，但不能为空字符串）
- 对每个药品类明细（Drug.type == 1）：
  - `quantity` 必须为正整数
  - `usage`、`dosage`、`frequency`、`timing` 必须非空（任意一项为空即不通过）
  - 如 `is_scattered == true`，则该药品必须支持零卖（has\_scattered == true），并具备可用 conversion\_rate
  - 必须通过库存校验（与后端扣减规则一致：散装按 conversion\_rate 折算并向上取整）

#### Scenario: 成功

- **WHEN** 医生提交处方，且所有强制检查规则通过
- **THEN** 系统创建 Visit，状态为 `pending`，并创建处方明细；前端获得 visit\_id

#### Scenario: 失败（缺字段）

- **WHEN** 医生提交处方且缺少 diagnosis 或 items 为空或药品明细缺少用法用量信息
- **THEN** 后端返回 400，并给出可直接展示给用户的错误信息（指出缺少的字段/明细行）

#### Scenario: 失败（库存不足）

- **WHEN** 医生提交处方且任一药品库存不足
- **THEN** 后端返回 400，并给出明确提示（包含药品名称与需要/现有库存信息）

### Requirement: 护士审核必经流程

系统 SHALL 要求护士在执行抓药/扣库存/结算前完成“审核确认或驳回”流程，并记录审核人/审核时间/驳回原因（如有）。

#### 规则

- 执行接口（执行扣库存与生成 Payment）必须要求 Visit 状态为 `nurse_verified`
- 审核确认接口在写入 `verified_by/verified_at` 前，必须重新校验：
  - Visit 必须存在且状态允许迁移
  - 处方明细满足执行所需的最小完整性（至少包含药品库存校验）

#### Scenario: 成功（审核后执行）

- **WHEN** 护士对 `pending` 处方执行“确认审核”
- **THEN** Visit 状态变为 `nurse_verified`，并记录 `verified_by/verified_at`
- **WHEN** 护士对已审核处方执行“结算”
- **THEN** 系统扣减库存、生成 Payment、Visit 状态变为 `completed`

#### Scenario: 失败（未审核直接执行）

- **WHEN** 护士尝试对 `pending` 处方直接执行结算
- **THEN** 后端返回 400，并提示必须先审核

### Requirement: 护士端药品库存管理全量能力

系统 SHALL 允许护士执行与“药品库存管理”相关的全量操作能力（与管理员端能力对齐），包括：

- 药品/诊疗项目列表查询、创建、编辑、启用/停用、删除（删除受处方引用约束）
- 批量入库（CSV 与 XLS/XLSX）
- 导入模板下载
- 智能盘库（合并重复项、迁移引用、低库存预警）
- 库存调整与调整流水查询\
  库存导出等功能

#### 约束

- 权限：上述能力对 `nurse` 与 `admin` 角色均可用（管理员功能保留，不做破坏性移除）
- 审计：库存调整必须记录操作者与原因（已有 InventoryRecord 结构沿用）

#### Scenario: 成功

- **WHEN** 护士在护士端进入“库存管理”页面并执行新增/编辑/批量入库/智能盘库
- **THEN** 与管理员端一致生效，并可在药品列表中看到变化

### Requirement: 报表导出与内容细化

系统 SHALL 提供可由护士发起的营收统计导出能力，并细化导出字段，至少包含：

- 统计维度：日报/月报/年报（与现有统计接口一致的筛选方式）
- 汇总字段：总收入、药品收入、诊察费收入、总利润
- 明细字段（至少 Visit 级别）：
  - 支付时间、visit\_id、患者姓名/学号、医生姓名、护士姓名、支付方式
  - 诊察费、药品金额、总金额
  - 成本（按处方明细 purchase\_cost 汇总）、利润

#### 导出格式

- 默认导出为 `.xlsx`（UTF-8 不适用的字段使用 Excel 单元格原生存储）

#### Scenario: 成功

- **WHEN** 护士选择维度与日期范围并点击导出
- **THEN** 浏览器下载 Excel 文件，文件名包含维度与日期，并包含汇总 + 明细

## MODIFIED Requirements

### Requirement: 数据库迁移（MySQL）

系统 SHALL 为新增的处方强制检查与导出所需字段/索引提供可迁移的数据库变更，并确保在 MySQL 下可执行。

#### 说明

- 数据库连接仍通过 `DATABASE_URL`/`SQLALCHEMY_DATABASE_URI` 环境变量配置
- 需要新增列/索引时，必须提供 Alembic 迁移脚本

## REMOVED Requirements

无。
