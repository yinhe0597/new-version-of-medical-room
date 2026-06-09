# 开发日志 open0.0.16（2026-06-09）

## 版本主题：护士端报表权限修复 & 全量编译部署

---

## 一、功能概述

本版本修复了护士角色无法访问统计报表和药品出库报表的权限问题，并进行全量编译重新部署。

### 修复问题

| 问题 | 说明 |
|------|------|
| 🔐 护士端统计报表权限拒绝 | 护士访问营收统计时显示 "Access denied: insufficient permissions" |
| 🔐 护士端药品出库报表权限拒绝 | 护士访问药品出库报表时显示 "Access denied: insufficient permissions" |

### 部署

| 项目 | 值 |
|------|-----|
| 全量编译输出 | `D:\yiwushi\yws20260608` |

---

## 二、后端变更

### 2.1 权限配置修复（admin.py）

5 个统计报表相关接口的 `@role_required` 装饰器补充 `'nurse'` 角色：

```python
# 修复前
@role_required(['admin', 'finance'])

# 修复后
@role_required(['admin', 'nurse', 'finance'])
```

#### 受影响的接口

| 接口路径 | 说明 |
|----------|------|
| `GET /admin/statistics/revenue` | 营收统计 |
| `GET /admin/statistics/revenue/users` | 营收统计医护人员列表（筛选用） |
| `GET /admin/statistics/revenue/export` | 营收统计导出 Excel |
| `GET /admin/statistics/drug-outbound` | 药品出库明细 |
| `GET /admin/statistics/drug-outbound/export` | 药品出库导出 Excel |

### 2.2 根因分析

- 护士端前端页面（`nurse/Statistics.vue` 和 `nurse/DrugOutboundReport.vue`）复用管理员组件，调用的是 `/admin/statistics/*` 接口
- 但这些接口的权限装饰器仅配置了 `['admin', 'finance']`，未包含 `'nurse'`
- 前端路由和导航菜单配置均正确，问题仅在后端权限装饰器

---

## 三、修改文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `backend/app/api/admin.py` | 修改 | 5 个统计接口 role_required 补充 nurse 角色 |

---

## 四、Git 提交记录

```
(本次提交)
```

---

## 五、验证测试

✅ 护士登录后访问 `/nurse/statistics` — 统计报表正常加载  
✅ 护士登录后访问 `/nurse/drug-outbound-report` — 药品出库报表正常加载  
✅ 护士登录后导出营收报表和出库报表 Excel — 正常下载  
✅ 管理员端统计和出库功能 — 不受影响，正常访问  
✅ `vite build` 前端构建成功  
✅ `pyinstaller medical_room.spec` 打包成功  
✅ exe 文件正确输出到 `D:\yiwushi\yws20260608`

---

## 六、部署信息

| 项目 | 值 |
|------|-----|
| 版本号 | open0.0.16 |
| 发布日期 | 2026-06-09 |
| 部署路径 | `D:\yiwushi\yws20260608` |
| EXE 大小 | ~82 MB |
