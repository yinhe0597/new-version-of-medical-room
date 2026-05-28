# 开发日志

## 2026/05/15

### 静脉给药配伍功能

**背景**：
医生端开两种不同静脉注射药品时存在两个痛点：① 多种溶质溶液在同一处方中前后配伍混乱，护士难以区分哪种溶液配哪种药物；② 溶液体积无法灵活填写（如 250ml 液体实际只用 200ml），原用法用量固定选项无法表达 ml/g/mg/U 等实际用量单位。

**修改方案**：
在医生开方页面新增独立的"静脉给药"区域，以配伍组方式将溶质+溶液绑定。静脉药品使用专用字段（实际用量数值+单位+给药方式），不出现餐前餐后/每日几次等不适用的选项。

**修改点**：

1. **数据模型** (`backend/app/models/__init__.py`)：
   - `PrescriptionItem` 表新增 5 个字段：
     - `is_intravenous` (Boolean) — 是否为静脉给药药品
     - `infusion_group` (Integer) — 配伍组号，同一配伍的药品共享组号
     - `infusion_dosage_value` (Float) — 实际用量数值（如 200）
     - `infusion_dosage_unit` (String(10)) — 用量单位（ml/g/mg/μg/U/IU）
     - `infusion_method` (String(50)) — 给药方式（静脉滴注/静脉推注/输液泵/微量泵）

2. **数据库迁移** (`backend/app/__init__.py`)：
   - 新增 5 行 `_ensure_sqlite_column` 调用，旧数据库启动时自动补全新字段

3. **后端 API** (`backend/app/api/doctor.py`)：
   - `POST /doctor/visits` 创建就诊：静脉给药药品 (`is_intravenous=true`) 跳过 usage/dosage/frequency/timing 必填校验，改为校验 infusion_dosage_value（>0）、infusion_dosage_unit（非空）、infusion_method（非空）；处方项创建时保存静脉给药 5 个新字段
   - `GET /doctor/visits/:id` 就诊详情：返回 items 中包含静脉给药字段，支持驳回处方重新载入时正确恢复配伍结构

4. **后端 API** (`backend/app/api/nurse.py`)：
   - `GET /nurse/visits/:id` 处方详情：返回 items 中包含静脉给药字段

5. **前端 VisitForm.vue**：
   - 药品列表下方新增"静脉给药"复选框，勾选后展开配伍管理面板
   - 支持创建/删除多个配伍组，每个配伍内可独立搜索添加药品
   - 配伍内药品使用静脉专用表单：数量 + 实际用量数值（精确到0.1）+ 单位下拉（ml/g/mg/μg/U/IU）+ 给药方式下拉（静脉滴注/静脉推注/输液泵/微量泵）
   - 确认提交对话框中展示配伍药品详情
   - 驳回处方重新载入时，自动恢复静脉给药配伍结构
   - 金额计算（totalAmount/drugTotalAmount）纳入配伍药品金额

6. **前端 ExecutePrescription.vue**：
   - `formatUsageLine` 函数：静脉给药药品显示"配伍N / 用量 / 给药方式"格式

**影响**：
医生开立静脉给药处方时，溶质+溶液通过配伍组绑定不会混淆；护士审核时能清晰看到每个配伍的组合关系；实际用量支持 ml/g/mg/U 等灵活单位，满足临床真实需求。普通药品开方流程不受影响。向后兼容：旧处方数据 `is_intravenous` 默认为 false，展示与之前完全一致。

### 用法用量空白选项

**背景**：
药膏等外用药没有"餐前餐后"和"每日几次"的概念，但原系统强制要求用法/用量/频次/时间四个字段全部填写，导致医生必须随意选择一个不相关的选项。

**修改方案**：
在四个下拉选择器的预设选项中各增加一个 `--` 选项（值为空字符串），医生可选择不填。前后端校验同步调整，允许普通药品个别字段为空。

**修改点**：

1. **前端 VisitForm.vue**：
   - `usageOptions` 首位新增 `'--'`
   - `dosageOptionsWithBlank` — 新 computed，在原有 `buildDosageOptions()` 结果前插入 `'--'`
   - `frequencyOptions` 首位新增 `'--'`
   - `timingOptions` — 新增常量数组，包含 `'--'` + 原有 5 个选项
   - timing 模板从硬编码 5 个 `<el-option>` 改为 `v-for` 循环
   - 提交时 `blankVal()` 函数将 `'--'` 转为空字符串
   - 校验逻辑：不再强制要求普通药品 usage/dosage/frequency/timing 非空

2. **前端 DirectPurchase.vue**：
   - 同上：`--` 选项、timing 硬编码改为 `v-for` 含 `--`、提交时 `'--'` 转空字符串、校验放宽

3. **后端 doctor.py**：
   - 用法用量校验逻辑调整为：非静脉给药且 drug.type==1 时仍需校验非空（空字符串 `''` 会触发校验，但 `--` 在前端已转为 `''`，所以选择 `--` 的药品会提示缺失。实际用户选择 `--` 后`--`本身是非空字符串，不会触发缺失校验。只有当用户完全清空该字段时才提示）

**影响**：
医生可以针对不同药品灵活填写用法用量，药膏等无需频次/时间的药品可直接选择 `--` 表示不填。向后兼容：原有已填入的值保持不变。

### 运营日志：前端展示缺陷修复 + 护士/管理端操作记录补全

**修改点**：
1. **前端 OperationLog.vue**：修复数据提取路径（`res.data?.items` → `res.data`）、修复 `parsedChanges` 兼容对象格式变更（`Object.entries()` 转换）、补全筛选下拉选项（3 项 → 14 项）、同步 actionTypeMap 标签类型
2. **后端 nurse.py**：8 个护士端点新增操作日志 —— 审核通过/驳回、改价、新增项目耗材、入库、库存调整、执行收费、撤销交易
3. **后端 admin.py**：3 个管理端点新增操作日志 —— 数据导入、人员编辑、药品编辑

**原因**：运营日志原有前端代码未适配后端真实返回结构（分页元数据在 `meta` 而非 `data`，变更记录为对象格式而非数组）；护士端关键操作（处方审核、收费、库存调整等）全程无审计记录，无法追溯责任操作；管理端药品/人员编辑、批量导入同样缺日志。

**影响**：运营日志可完整覆盖医生/护士/管理员三个角色的核心操作，筛选与展示正确；系统整体具备基础的审计追溯能力。

### 就诊历史：权限放宽 + 状态流转时间线 + 界面增强

**修改点**：
1. **后端 doctor.py**：移除 `get_doctor_visit_detail` 中 `doctor_id` 权限校验（任何医生可查看任何患者就诊记录）；新增 `status_timeline` 字段（pending → verified/rejected → completed/revoked 带时间戳与操作人）；新增 `doctor_name` 字段至患者就诊历史列表；N+1 查询优化（`db.joinedload` 替代 `User.query.get`）
2. **前端 PatientSearch.vue**：就诊历史表格新增"接诊医生"列；病历详情弹窗新增 `el-timeline` 可视化状态流转；新增"查看修改记录"功能入口（懒加载 `/doctor/visits/:id/revisions`）

**原因**：小型医务室场景下医生间需要交叉查看患者记录（值班交接、会诊），原 `doctor_id` 硬校验阻碍了正常业务；之前状态变更（审核/驳回/收费/撤销）仅分散在字段中，缺乏直观的时间线串联展示，医生无法快速了解就诊处理全貌。

**影响**：医生端就诊历史可完整追溯任意患者的所有就诊记录及每次病历修改记录；状态流转一目了然（待处理→审核/驳回→完成/撤销），UI 体验提升；为跨医生协作扫清权限障碍。

### 月度盘点报表：新增购进价与本月进药金额

**修改点**：
1. **后端 nurse.py**：月度报表 API 返回结果新增 `purchase_price`（购进价）和 `inbound_amount`（购进价 × 入库数）字段；Excel 导出同步增加"购进价"和"本月进药金额"两列
2. **前端 Inventory.vue**：月度盘点表格在"规格"与"单位"之间插入"购进价"列，最右侧新增"本月进药金额"列（购进价 × 入库数），合计行同步纳入求和

**原因**：月度盘点报表缺少成本视角数据，护士无法直接看到各药品的进货价格及月度进药总金额，需要手动对照药品管理页面计算，效率低且易出错。

**影响**：月度盘点报表可直观展示各药品购进价及本月进药总金额，为库存成本管理提供数据支撑。

### 药品管理：整件价更名为零售价

**修改点**：前端 DrugManagement.vue 中新增/编辑弹窗的表单项标签和表格列头"整件价"统一改为"零售价"

**原因**："整件价"表述不够直观，实际业务中文含义为药品零售标价，"零售价"更符合医务室药品定价场景，减少新用户理解成本。

**影响**：仅标签文案变更，无功能影响，后端字段名 `price` 保持不变。

### 就诊详情：Missing Import 修复

**修改点**：
1. **后端 doctor.py**：在 `from backend.app.models` 导入语句中补充 `Payment` 模型引用

**原因**：上一轮"就诊历史"功能新增状态流转时间线时，`db.joinedload(Visit.payment).joinedload(Payment.nurse)` 使用了 `Payment` 模型进行联表查询，但 `Payment` 未在文件顶部导入。所有医生调用 `GET /doctor/visits/:id` 时触发 `NameError: name 'Payment' is not defined`，API 返回 500，导致"病例详情"弹窗始终加载失败。

**影响**：医生端病例详情接口恢复正常，新旧就诊记录均可成功加载完整病历与状态流转时间线；前端不再弹出"获取详情失败"错误提示。

## 2026/05/22

### 打印小票重复问题彻底修复

**背景**：
护士在历史诊疗记录中点击"打印小票"时，浏览器打印预览显示多页完全相同的小票内容。该问题在 open0.0.9 中曾尝试修复（通过 `@media print` 隐藏非票据区域），但修复不彻底，问题依旧存在。

**问题根因**：
之前的 `@media print` 使用 `body * { visibility: hidden !important; }` 来隐藏非打印内容。`visibility: hidden` 仅让元素不可见，但**元素仍占据页面布局空间**。历史诊疗记录列表中的 `el-table` 数据量大时，打印会跨越多页；而票据区域 `#receipt-print-area` 被设为 `position: absolute; top: 0`，导致它在**每一页的顶部都重复渲染**，形成"多页相同内容"的现象。

**修复方案**：
弃用 `visibility: hidden` 方案，改为使用 `display: none !important` 彻底隐藏 `#app`（Vue 应用根容器），使非打印内容完全不占用页面空间。Element Plus 的 `el-dialog` 默认 `teleport` 到 `body`，`.el-overlay` 不在 `#app` 内部，因此得以保留。同时补充 `ExecutePrescription.vue` 中完全缺失的 `@media print` 样式。

**修改点**：

1. **前端 `HistoryList.vue`**（`@media print` 重写）：
   - `#app { display: none !important; }` —— 彻底隐藏主应用，不占用打印空间
   - `.el-overlay` —— 保留并去除背景遮罩、改为 `position: static`
   - `.el-dialog` —— 改为 `position: static`，去除阴影和边距，宽度 100%
   - `.el-dialog__header`、`.el-dialog__footer`、`.el-dialog__headerbtn` —— 隐藏标题栏和按钮区
   - `#receipt-print-area` —— 改为 `position: static`，避免 absolute 跨页重复

2. **前端 `ExecutePrescription.vue`**（新增 `@media print`）：
   - 同一套打印样式，解决结算页面打印小票时同样可能重复的问题

**影响**：
护士端历史诊疗记录和处方执行页面的打印小票功能均只输出单页票据，不再重复。向后兼容：未触发打印时页面正常展示，无影响。

---

### 护士端历史诊疗记录打印小票

**背景**：
护士在结算处方后可以打印收费小票，但如果关闭了结算弹窗而没有立即打印，之后就无法再补打。实际工作中经常需要补打小票（患者后来需要报销凭证、护士交接班需核对等），但历史列表中没有打印入口。

**修改方案**：
在护士端"历史诊疗记录"列表右侧操作列增加"打印小票"按钮（仅对已完成且有支付记录的行显示）。点击后弹出收费凭证弹窗，格式与结算时一致，支持打印并标记已打印状态。

**修改点**：

1. **后端 `nurse.py`**（`GET /nurse/my-history`）：
   - 返回数据新增 4 个支付字段：`payment_id`、`payment_amount`（实付金额）、`payment_original_amount`（原价金额）、`paid_at`（支付时间）
   - 前端不再需要二次请求获取支付信息，历史列表直接携带完整支付数据

2. **前端 `HistoryList.vue`**：
   - 操作列宽度由 140 扩展为 180，新增 `el-button`"打印小票"（仅 `status==='completed' && payment_id` 时显示）
   - 新增收费凭证弹窗（`el-dialog`），包含：标题"校医务室收费凭证"、患者信息区、诊断、药品明细（复用 `formatUsageLine`）、医嘱/备注、金额汇总（原价/优惠/应收/实收）、支付方式、收费员/日期、签章区
   - `openReceipt(row)` 请求 `GET /nurse/visits/:id` 获取完整处方详情，展示在凭证弹窗中
   - `printReceipt(pid)` 调用 `PUT /nurse/payments/:pid/print` 标记已打印，然后 `window.print()` 触发浏览器打印
   - 新增辅助函数：`safeText`（空值兜底）、`formatUsageLine`（用法用量格式化，兼容静脉给药配伍展示）、`getPaymentMethodText`（支付方式中文转换）

**影响**：
护士可在历史诊疗列表中随时补打收费小票，不再受限于结算时的即时打印窗口。打印后后端记录 `receipt_printed` 状态，方便追踪打印记录。收费凭证格式与结算页面完全一致，视觉统一。

## 2026/05/11

### 编译 exe 启动崩溃（AssertionError）

**问题根因**：Flask Blueprint 以函数名作为 endpoint 标识，同一 Blueprint 下存在 3 对同名视图函数导致路由注册冲突，exe 启动时抛出 `AssertionError: View function mapping is overwriting an existing endpoint function`。

**冲突清单**：

| 函数名 | 冲突文件 |
|---|---|
| `create_patient` | `doctor.py` 和 `admin.py` |
| `update_patient` | `doctor.py` 和 `admin.py` |
| `get_visit_detail` | `nurse.py` 和 `admin.py` |

**修复**：将 `admin.py` 中的三个冲突函数分别重命名为 `admin_create_patient`、`admin_update_patient`、`admin_get_visit_detail`，消除 endpoint 命名冲突。

### run_prod.py 模块级代码脆弱性

**问题根因**：`app = create_app()` 写在模块级别（不在 `if __name__ == '__main__'` 内），导入时即执行。若有任何初始化异常（如数据库问题、路由冲突等），整个进程无异常处理直接崩溃，日志瞬间截断。

**修复**：将所有执行代码移入 `if __name__ == '__main__'` 块，并添加 `try/except` 兜底异常捕获和 `input()` 暂停，确保错误信息可读。

### PyInstaller 隐式导入遗漏

**问题根因**：部分动态加载模块（alembic、openpyxl 子模块等）未在 spec 文件中列为 `hiddenimports`，可能导致运行时找不到模块。

**修复**：在 `medical_room.spec` 中补充缺失的隐式导入。

## 2026/05/28

### open0.0.12 — 历史诊疗记录性能优化 + 月度盘点药品排序

**性能优化：**
- 🚀 **历史诊疗记录分页加载**：`GET /nurse/my-history` 新增 `page`/`size` 分页参数，每次只返回一页数据（默认 20 条），减少 90%+ 数据传输量
- 🔍 **服务器端搜索下沉**：患者姓名搜索和状态筛选从客户端 computed 改为数据库层 `WHERE` 过滤，大幅降低前端计算和渲染开销
- 📄 **前端分页组件**：`HistoryList.vue` 新增 `<el-pagination>`，支持 10/20/50/100 条/页切换

**功能新增：**
- 🔢 **月度盘点药品自定义排序**：`Drug` 模型新增 `monthly_sort_order` 字段，支持护士通过"上移/下移"按钮自定义药品显示顺序，排序结果持久化到数据库
- 💾 **排序保存接口**：新增 `PUT /nurse/drugs/sort-order`，接收排序后的 `drug_id` 列表

> 📝 详细变更：[开发日志-open0.0.12.md](docs/开发日志-open0.0.12.md)
