# 开发日志 open0.0.19（2026-06-23）

## 版本主题：旧数据库兼容性全面修复 — 自动列迁移补全

---

## 一、问题背景

open0.0.18 在 Drug、Visit、PrescriptionItem 三个表中新增了 **23 个字段**（中药饮片、库存管理、中医诊疗相关），但对应的 `_ensure_sqlite_column()` 自动迁移调用未同步添加。导致编译后的 `yws20260622` 版本在旧数据库上启动时，SQLAlchemy 查询包含不存在的列，抛出 `sqlite3.OperationalError`，服务崩溃进入重启循环。

### 受影响场景

| 场景 | 错误表现 | 根因 |
|------|------|------|
| 系统启动 | `sqlite3.OperationalError` → 5 次重启后停止 | `take_daily_snapshot()` 查询 Drug 表时列不存在 |
| 历史诊疗记录 | "服务器内部错误" | Visit 表缺失 `tcm_enabled` 等 3 个字段 |
| 其他数据查询 | "服务器内部错误" | PrescriptionItem 表缺失 `prescription_type` 等 5 个字段 |

---

## 二、修复内容

### 2.1 补全 `_ensure_sqlite_column` 自动迁移调用

在 `backend/app/__init__.py` 的 `create_app()` 中补充了 **23 个缺失的自动列迁移调用**，覆盖三个表：

#### Drug 表（+15 字段）

```
batch_no, inbound_at,
is_herb, herb_code, herb_category, herb_variety, herb_spec,
alias_name, pinyin_code, processing_type,
safety_stock, max_stock, daily_loss_rate, shelf_life_days, storage_condition
```

#### Visit 表（+3 字段）

```
tcm_enabled, tcm_syndrome, tcm_diagnosis_desc
```

#### PrescriptionItem 表（+5 字段）

```
prescription_type, herb_dosage, special_preparation, herb_sort_order, template_id
```

### 2.2 验证结果

| 验证项 | 方法 | 结果 |
|------|------|------|
| yws20260608 旧数据库启动 | 用 yws20260608 的 app.db 启动应用 | ✅ 成功，字段自动补齐 |
| Drug 查询 | `Drug.query.filter(Drug.status == 1).all()` | ✅ 395 条记录 |
| Visit 查询 | `Visit.query.first()` | ✅ 2728 条记录 |
| PrescriptionItem 查询 | `PrescriptionItem.query.first()` | ✅ 7036 条记录 |
| 数据库字段完整性 | `PRAGMA table_info()` 三表对比 | ✅ Drug 21→34列, Visit 22→25列, PrescriptionItem 25→30列 |

---

## 三、规范强化

更新了项目开发规范记忆 [数据库字段变更必须配套自动迁移检测]：

> **每次在 SQLAlchemy 模型中新增 `db.Column` 字段，必须同步在 `create_app()` 中添加对应的 `_ensure_sqlite_column()` 调用。**
>
> 原因：SQLite 的 `db.create_all()` 只创建新表，不修改已有表结构。`_ensure_sqlite_column()` 通过 `ALTER TABLE ADD COLUMN` 确保旧数据库能自动兼容新代码。
>
> 排查方法：对比模型定义中的 `db.Column` 与 `create_app()` 中的 `_ensure_sqlite_column` 列表，确认无遗漏。

---

## 四、Git 提交记录

```
e6c4dc1 fix: open0.0.19 旧数据库兼容性全面修复 — 补全23个自动列迁移调用
```

---

## 五、部署信息

| 项目 | 详情 |
|------|------|
| 部署路径 | `D:\yiwushi\YWS20260622` |
| 编译方式 | 前端 `npm run build` → PyInstaller `medical_room.spec` |
| EXE 大小 | ~86 MB |
| 数据库 | 启动时自动检测并迁移旧数据库字段 |
