# 开发日志

## 2026/05/13

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
