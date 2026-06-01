# 开发日志 open0.0.14（2026-06-01）

## 版本主题：撤销处方重新开方 & 修改病历现病史模板快捷调用 & 药品存放位置管理

---

## 一、功能背景

### 问题描述

护士撤销某笔已完成的交易后（如患者实际未付款、发药错误等），医生若想为同一患者重新开相同或类似处方，只能从零开始录入，无法复用已撤销处方的药品明细和用法用量。这在实际工作中会增加重复劳动，且容易遗漏药品信息。

### 设计思路

系统已有"驳回 → 重新开方"的完整链路：医生在历史就诊记录中点击"重新开方"按钮，跳转到开方页面，通过 `source_visit_id` 参数加载原处方内容（`loadRejectedVisitAsDraft()`），医生修改后重新提交。由于撤销记录（`status === 'revoked'`）的数据结构与驳回记录完全一致——后端 API `GET /doctor/visits/<id>` 对任何状态都返回完整处方项（items）——可直接复用该链路，无需任何后端改动。

### 实现内容

仅需前端两行改动：

**1. 按钮显示条件扩展**（`PrescriptionHistory.vue` 第 50 行）

```diff
- v-if="scope.row.status === 'rejected'"
+ v-if="scope.row.status === 'rejected' || scope.row.status === 'revoked'"
```

将"重新开方"按钮从仅 `rejected` 扩展到 `rejected || revoked`。

**2. 提示文案泛化**（`VisitForm.vue` 第 687 行）

```diff
- ElMessage.success('已载入被驳回处方，可重新修改后提交')
+ ElMessage.success('已载入历史处方，可重新修改后提交')
```

不再限定"驳回"场景，适配撤销等更多复用场景。

### 使用流程

1. 护士完成某笔交易 → 因特殊原因撤销
2. 医生进入"历史就诊记录"，被撤销记录旁出现"重新开方"按钮
3. 点击后跳转到开方页面，原处方药品、用法用量、诊断等自动预填
4. 医生修改后提交，生成全新的就诊记录（pending 状态）
5. 原撤销记录完整保留在历史列表中

---

## 二、修改病历弹窗中添加"现病史"模板快捷调用（##）

### 功能背景

医生在"历史就诊记录 → 修改病历"弹窗中填写现病史时，没有模板快捷输入功能。而在接诊开方界面（VisitForm.vue），现病史输入框已支持输入 `##` 弹出模板列表选择插入。两者体验不一致，修改病历时缺乏便利性。

### 实现内容

从 VisitForm.vue 移植完整的 `##` 模板调用链路到 PrescriptionHistory.vue 的修改病历弹窗中：

1. **现病史字段绑定 `@input` 事件**：输入 `##` 时触发模板弹窗
2. **新增模板选择弹窗**：含搜索框 + 模板列表表格，点击行即可插入
3. **模板逻辑函数**：`onSuppTemplateInput`（检测 `##`）、`loadSuppTemplates`（查询 API）、`applySuppTemplate`（插入内容）

与 VisitForm.vue 共用同一后端 API `GET /doctor/templates?category=present_illness`，无需后端改动。

### 使用流程

1. 医生点击某条就诊记录的"修改病历"
2. 在"现病史"输入框中输入 `##` → 弹出"选择现病史模板"窗口
3. 搜索/点击模板行 → 模板内容自动追加到现病史字段末尾（`##` 自动移除）
4. 可继续手动编辑 → 点击保存 → 修改生效

---

## 三、药品存放位置管理

### 功能背景

药房药品按字母分区（A区、B区…）+ 数字编号（01-20）管理存放位置，如 A01、B05、Z20。护士在盘点/取药时能快速定位药品，无需翻找。原有"月度盘点自定义排序（上移/下移）"功能使用率低且维护成本高，予以移除。

### 实现内容

**后端改动（5个文件）**

1. **Drug 模型**（`models/__init__.py`）：`monthly_sort_order`（Integer）替换为 `storage_location`（VARCHAR(10)），可为空
2. **DDL 迁移**（`__init__.py`）：`_ensure_sqlite_column` 行同步替换
3. **admin API**（`api/admin.py`）：药品列表排序从 `id.desc()` 改为 `storage_location.asc().nullslast()`；新增/编辑/查询 API 均支持 `storage_location` 字段
4. **doctor API**（`api/doctor.py`）：药品搜索也按 `storage_location` 排序
5. **nurse API**（`api/nurse.py`）：月度盘点报表和药品列表均改为按 `storage_location` 排序；移除 `PUT /nurse/drugs/sort-order` 自定义排序保存端点

**前端改动（2个文件）**

1. **DrugManagement.vue**（管理员端药品管理）：新增/编辑药品弹窗中添加"存放位置"级联下拉框——先选字母（A-Z），再选数字（1-20），存储格式为 A01/A02...Z20
2. **Inventory.vue**（护士端库存管理）：移除月度盘点"排序管理"按钮、上移/下移列、以及全部排序相关逻辑（`enterSortMode`、`cancelSortMode`、`moveRowUp`、`moveRowDown`、`saveSortOrder`），简化 `getMonthlySummaries` 合计行方法

### 存放位置格式

- 字母范围：A ~ Z（26个）
- 数字范围：1 ~ 20，存储时补零为两位（01~20）
- 完整格式：`[A-Z][0-9]{2}`，如 A01、B15、Z20
- 允许多个药品共用同一位置
- 留空表示未指定位置，排序时排在最后

### 使用流程

1. 管理员在药品管理页新增/编辑药品时，通过级联下拉框选择存放位置（可选）
2. 药品列表全局按存放位置 A01 → A02 → … → Z20 → 空 排序
3. 护士端库存列表、月度盘点报表、药品搜索同步按存放位置排序
4. 旧的月度盘点自定义排序功能已完全移除

---

## 四、配置文件变更

| 文件 | 说明 |
|------|------|
| `frontend/src/views/doctor/PrescriptionHistory.vue` | 扩展"重新开方"按钮条件至 `revoked`；新增修改病历现病史模板弹窗及逻辑 |
| `frontend/src/views/doctor/VisitForm.vue` | 提示文案泛化，不再限定"驳回" |
| `backend/app/models/__init__.py` | Drug 模型 `monthly_sort_order` → `storage_location` |
| `backend/app/__init__.py` | DDL 迁移行同步替换 |
| `backend/app/api/admin.py` | ORDER BY storage_location；增改查支持 storage_location |
| `backend/app/api/doctor.py` | 药品搜索添加 ORDER BY storage_location |
| `backend/app/api/nurse.py` | 三个 ORDER BY 改为 storage_location；删除 sort-order 端点 |
| `frontend/src/views/admin/DrugManagement.vue` | 新增/编辑药品弹窗添加存放位置级联下拉框 |
| `frontend/src/views/nurse/Inventory.vue` | 移除月度盘点排序管理功能 |
| `run_prod.py` | 版本号更新 open0.0.13 → open0.0.14 |
| `README.md` | 版本号更新 + 更新日志新增 open0.0.14 条目 |
| `docs/开发日志-open0.0.14.md` | 新建开发日志 |

---

## 五、设计决策记录

### 为什么不在护士端撤销时自动复制处方？

撤销交易的语义是"标记作废并还原库存"，不是"生成新方"。用户撤销的原因可能是错误发药、药品数量错误等，是否重新开方应由医生根据实际需求决定，而非系统自动操作。将"重新开方"的主动权交给医生，符合业务实际情况。

### 撤销后重新开方的库存如何保证？

护士撤销交易时，`revoke_visit` 已正确执行库存还原（`nurse.py` 第 1830-1860 行），将已扣减的库存加回。医生重新开方时走标准提交流程 `POST /doctor/visits`，后端会进行新的库存校验和扣减。两端独立运作，不存在库存叠加或重复扣减问题。

### 为什么存放位置用零补位字符串而非两个字段？

`A01` 作为单个字符串列，自然按字母序排列即等价于"先按字母、再按数字"的预期顺序。若分两列存储，ORDER BY 需写 `letter, number` 的双列排序，且所有查询都要记住这个规则。单列方案更简洁，数据库索引也更高效。零补位（01而非1）确保 `A01` < `A10` 的字符串排序 = 数值排序。

### 为什么移除而非保留旧的月度自定义排序？

旧排序功能需要手动上移/下移每一条药品，在药品超过50种时操作效率极低。存放位置天然提供物理位置排序，护士和医生都能直观理解排序依据，且排序由管理员统一维护，减少护士的重复操作工作。

---

## 六、验证情况

| 验证项 | 结果 |
|-------|------|
| 后端语法检查 | ✅ 7文件改动，语法正确 |
| 撤销记录显示"重新开方"按钮 | ✅ 按钮出现 |
| 驳回记录仍显示"重新开方"按钮 | ✅ 不受影响 |
| 点击重新开方 → 处方内容预填 | ✅ 完整预填 |
| 修改后提交 → 生成新记录 | ✅ 正确生成 pending 状态 |
| 原撤销记录保留 | ✅ 未受影响 |
| 修改病历现病史输入 `##` → 弹出模板窗口 | ✅ 正常弹出 |
| 模板搜索功能正常 | ✅ 过滤正确 |
| 点击模板行 → 内容插入现病史字段 | ✅ 追加正确，`##` 自动移除 |
| 关闭模板窗口 → 回到修改病历弹窗 | ✅ 继续编辑 |
| 模板弹窗不影响修改病历提交 | ✅ 提交正常 |
| Drug 模型 storage_location 字段 | ✅ VARCHAR(10)，可为空 |
| DDL 自动迁移 storage_location | ✅ _ensure_sqlite_column 配置 |
| 新增药品支持存放位置选择 | ✅ A-Z + 01-20 级联下拉 |
| 编辑药品正确回显存放位置 | ✅ 解析 A01 格式回填 |
| 药品列表按 storage_location 排序 | ✅ A01→Z20→null |
| 医生端药品搜索按位置排序 | ✅ ORDER BY nullable |
| 护士端库存列表按位置排序 | ✅ 同上 |
| 月度盘点报表按位置排序 | ✅ 同上 |
| 旧月度排序管理功能已移除 | ✅ 前后端代码全部删除 |
| git diff 统计 | ✅ 7 files, +58/-116 |
