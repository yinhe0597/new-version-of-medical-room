# 药品整散联动与库存管理业务逻辑设计与实现计划

## 1. 业务逻辑设计理念 (Business Logic Design)

针对诊所/校医院场景中的“拆盒零卖”需求，传统的“手动拆零”操作（护士在系统中点击“拆开一盒”，系统整件-1，散件+N）会增加极大的操作负担，且容易忘记操作导致账实不符。

基于当前系统已引入的 `DrugStockGroup.total_units`（最小单位总量）底层设计，我们采取 **“无感拆零 + 统一总量 + 联合盘点”** 的业务逻辑：

1. **无感拆零（物理拆盒无需系统操作）**：
   系统永远以“最小单位总量（`total_units`）”作为唯一事实来源。`整件库存 = 总量 // 包装量`。护士在现实中拆开一个整盒时，不需要在系统中做任何操作。只要总量不变，系统账目就始终是准确的。
2. **智能扣减（开方自动换算）**：
   医生开出整盒或散片时，系统在执行处方时统一换算为“最小单位数量”并在 `total_units` 中扣减，随后自动重新计算并更新整件和散件的显示库存。
3. **整散联合盘点（本次计划核心）**：
   由于日常损耗（如药品掉落、过期报废）的存在，必须允许护士修正库存。对于存在“整散库存组”的药品，不能单独修改整件或散件的库存，必须提供“联合盘点”功能：护士输入【实际物理存在的整盒数】与【实际物理存在的散件数】，系统自动计算新的 `total_units` 并同步所有关联记录。

## 2. 当前状态分析 (Current State Analysis)

*   **数据模型**：已支持 `DrugStockGroup`，维护 `total_units`, `pack_amount`, `retail_amount`。
*   **前端限制**：在 `DrugManagement.vue` 和 `Inventory.vue` 中，为了防止数据破坏，我们已禁用了包含 `stock_group_code` 药品的直接库存编辑和盘点。
*   **缺失环节**：护士目前**没有任何合法途径**去修正整散组药品的库存误差。

## 3. 拟议更改 (Proposed Changes)

### 3.1 后端接口支持联合盘点 (`backend/app/api/nurse.py`)
*   **新增接口**：`POST /nurse/inventory/group`
*   **参数**：`group_code`, `actual_packs` (实际整盒数), `actual_retail_units` (实际散件数), `remark` (备注)。
*   **逻辑**：
    1. 根据 `group_code` 查询 `DrugStockGroup`。
    2. 计算 `new_total_units = actual_packs * pack_amount + actual_retail_units * retail_amount`。
    3. 如果 `new_total_units` 与当前 `total_units` 一致，直接返回成功。
    4. 更新 `group.total_units = new_total_units`。
    5. 调用 `recompute_variant_stocks` 计算新的 `pack_stock` 和 `retail_stock`。
    6. 更新关联的 `pack_drug.stock` 和 `retail_drug.stock`。
    7. 生成两条 `InventoryRecord` 记录（整件和散件的库存变动日志）。

### 3.2 前端盘点交互升级 (`frontend/src/views/nurse/Inventory.vue`)
*   **UI 交互**：当护士点击包含 `stock_group_code` 的药品所在行的“盘点”按钮时，不再提示“请勿直接盘点”，而是弹出一个专用的 **“整散联合盘点”** 弹窗。
*   **弹窗内容**：
    *   显示药品名称和包装规格（如：阿莫西林 20mg×100粒/瓶）。
    *   显示当前系统库存（换算为 X 盒零 Y 粒）。
    *   提供两个输入框：【实际整件数量】和【实际散件数量】。
    *   底部实时预览：“盘点后总计：Z 粒”。
    *   备注输入框。
*   **数据提交**：将数据提交至新的 `/nurse/inventory/group` 接口，并在成功后刷新列表。

### 3.3 护士端与管理端列表信息增强
*   在 `Inventory.vue` 的库存列表中，为组库存药品增加“关联组信息”的友好提示（例如使用 `el-tooltip` 提示“该药品与 XXX 共享库存总量”），提升操作透明度。

## 4. 假设与决策 (Assumptions & Decisions)
*   **决策 1**：不再开发独立的“拆盒”按钮。因为 `pack_stock = total_units // pack_amount`，点击“拆盒”按钮不改变 `total_units`，库存数字不会有任何变化，反而会让用户困惑。向用户培训“无感拆零”的概念是最佳实践。
*   **决策 2**：联合盘点时，不要求护士必须找到组内另一条药品记录。只要点击组内任意一条药品（整装或散装），弹出的都是该“整个组”的联合盘点界面，提升易用性。

## 5. 验证步骤 (Verification Steps)
1. 护士账号登录，进入“入库管理”录入一个支持零卖的新药（如：测试药A，10盒，每盒10粒）。
2. 切换到“库存盘点”，点击“测试药A”的盘点按钮。
3. 在弹出的“联合盘点”对话框中，输入实际整件 9 盒，散件 8 粒。
4. 提交后，验证列表中的整件库存更新为 9，散件库存更新为 98。
5. 检查“盘点记录”Tab，确认生成了准确的库存变更日志。
