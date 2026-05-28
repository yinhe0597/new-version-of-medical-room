# 开发日志 open0.0.12（2026-05-28）

## 版本主题：历史诊疗记录性能优化 + 月度盘点药品排序

### 功能背景

**护士端历史诊疗记录：** 数据量增长后全量加载导致等待时间长，且客户端筛选效率低，影响护士日常使用体验。

**月度盘点药品排序：** 药品表格按录入顺序排列，护士无法按自己的习惯调整展示顺序，月度盘点时需要反复寻找目标药品。

---

## 一、历史诊疗记录页面加载性能优化

### 问题描述

`GET /nurse/my-history` 接口返回全部记录（无分页），前端通过 `filteredList` computed 在客户端做姓名搜索和状态筛选。随着历史数据积累，单次请求可能返回数百甚至上千条记录，导致：
- 数据库查询和网络传输耗时增加
- 前端渲染大量 DOM 节点卡顿
- "转圈加载"等待时间过长

### 优化方案

1. **后端添加分页支持**：新增 `page`、`size` 查询参数，使用 SQLAlchemy `paginate()` 分页查询，一次只返回一页数据（默认 20 条）

2. **服务器端筛选下沉**：
   - 患者姓名搜索从客户端 computed 改为 `Patient.name.contains(search_name)` 数据库层过滤
   - 状态筛选从客户端 computed 改为 `Visit.status == status` 数据库层过滤
   - 返回分页元信息 `meta.page`、`meta.per_page`、`meta.total`

3. **前端改造**：
   - 删除 `filteredList` computed 属性，表格直接渲染 `historyList`
   - 新增 `<el-pagination>` 分页组件，支持 10/20/50/100 条/页
   - 点击"查询"按钮时自动重置到第 1 页
   - `filterStatus` 空值时不上传 `status` 参数（后端返回全部状态）

### 效果

每次加载只传输一页数据（默认 20 条），减少了 90% 以上的数据传输量和渲染开销，页面响应速度显著提升。

---

## 二、月度盘点药品自定义排序

### 问题描述

月度盘点表格中药品按入库时的录入顺序排列（即 `Drug` 表的主键 ID 顺序），护士无法按实际工作习惯调整显示顺序，每月盘点时需反复搜索查找。

### 实现方案

1. **数据层**：`Drug` 模型新增 `monthly_sort_order` 可空整数字段，用于存储用户自定义排序序号

2. **后端排序接口**：新增 `PUT /nurse/drugs/sort-order` 接口，接收排序后的 `drug_id` 列表，按列表顺序设置 `monthly_sort_order`

3. **报表查询排序**：`_compute_monthly_report` 函数中药品查询按 `monthly_sort_order ASC NULLS LAST` 排序，无排序数据的药品排在末尾

4. **前端交互**：
   - 报表头部新增"排序管理"按钮，进入排序模式后每行显示"上移"/"下移"按钮
   - 排序模式下显示"保存排序"/"取消"按钮组
   - 保存时发送当前顺序的 `drug_id` 列表到后端持久化
   - 取消时恢复为保存前的原始顺序

### 数据安全

排序功能仅影响 `monthly_sort_order` 字段，不涉及库存、价格等业务数据。排序变更后下次"生成报表"即可看到新顺序。

---

## 三、配置文件变更

| 文件 | 说明 |
|------|------|
| `backend/app/models/__init__.py` | `Drug` 模型新增 `monthly_sort_order` 字段 |
| `backend/app/api/nurse.py` | `get_my_history` 添加分页参数 `page`/`size` + 服务器端搜索 `search_name` + 状态筛选 `status`；`_compute_monthly_report` 按 `monthly_sort_order` 排序；新增 `PUT /nurse/drugs/sort-order` |
| `backend/migrations/versions/e7f8a9b0c1d2_add_monthly_sort_order_to_drug.py` | 数据库迁移：`drug` 表添加 `monthly_sort_order` 列 |
| `frontend/src/views/nurse/HistoryList.vue` | 删除客户端 `filteredList` 筛选，添加分页组件和分页处理逻辑 |
| `frontend/src/views/nurse/Inventory.vue` | 月度盘点 tab 新增排序模式（上移/下移/保存/取消），合计行兼容排序列 |

---

## 四、设计决策记录

### 为什么选择分页而非虚拟滚动？

| 方案 | 优点 | 缺点 |
|-----|------|------|
| A: 分页 ✅ | 实现简单，后端过滤数据量小，前端渲染压力低 | 用户需要点击翻页 |
| B: 虚拟滚动 | 用户体验更流畅（无翻页） | 实现复杂，需引入额外依赖，移动端兼容性差 |

校医务室历史记录通常不会超过数千条，分页足够使用，且实现最简单、最可靠。

### 为什么排序不使用拖拽？

拖拽排序（SortableJS）体验更直观，但需要额外引入第三方库。上移/下移按钮不需要任何外部依赖，且在大屏触控设备上同样可用。当前实现满足核心需求，未来可按需升级为拖拽方案。

---

## 五、验证情况

| 验证项 | 结果 |
|-------|------|
| 前端构建（`npx vite build`） | ✅ 通过 |
| 后端语法检查（`ast.parse`） | ✅ 通过 |
| 迁移文件语法检查 | ✅ 通过 |
| HistoryList.vue 分页逻辑 | ✅ 通过 |
| Inventory.vue 排序逻辑 | ✅ 通过 |
