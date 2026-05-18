# 开发日志 open0.0.7（2026-05-16）

## 版本主题：耗材库存报表修复与全链路耗材支持完善

### 问题背景

用户反馈：注射器等物品从药品（type=1）转移到耗材（type=3）后，护士能正常查看和管理这些耗材，但在库存报表中无法找到这些耗材的记录。

### 调查发现

经全面代码审查，发现以下 5 个关键问题：

---

## 一、Bug修复 - 护士入库耗材功能失效（严重）

### 问题描述

`nurse.py` 中 `inbound_stock` 函数的条件判断 `if item_type != 1:` 会捕获 type=3 的耗材请求，将其错误创建为 **type=2（诊疗项目）**，stock 设为 -1。导致 `if item_type == 3:` 代码块成为死代码，永远不会执行。

### 修复方案

将 `if item_type != 1:` 改为 `if item_type == 2:`，使 type=3 的耗材正确进入下方的 `if item_type == 3:` 处理分支。

### 改动文件

| 文件 | 改动说明 |
|------|---------|
| `backend/app/api/nurse.py` | `inbound_stock` 条件从 `item_type != 1` 改为 `item_type == 2` |

---

## 二、Bug修复 - 药品类型变更时 variant_type 不同步

### 问题描述

通过管理员编辑将药品 type 从 1 改为 3 时，`variant_type` 不会同步更新为 `"consumable"`，散装相关字段（`has_scattered`、`scattered_price`、`conversion_rate`）也不会清除。

### 修复方案

在 `update_drug` 中增加类型变更时的联动逻辑：
- type=3 → 设置 `variant_type='consumable'`，清除散装字段
- type=2 → 设置 `variant_type='service'`，清除散装字段
- type=1 → 如果原先是 service/consumable，重置 `variant_type=None`

### 改动文件

| 文件 | 改动说明 |
|------|---------|
| `backend/app/api/admin.py` | `update_drug` 增加类型变更时 variant_type 和散装字段联动更新 |

---

## 三、增强 - 月度盘点报表区分耗材

### 改动说明

- 月度报表 API 返回数据新增 `type` 和 `variant_type` 字段
- 前端月度报表表格新增"类型"列，使用 `el-tag` 区分药品/耗材
- Excel 导出新增"类型"列

### 改动文件

| 文件 | 改动说明 |
|------|---------|
| `backend/app/api/nurse.py` | `_compute_monthly_report` 返回数据增加 `type`、`variant_type` 字段 |
| `backend/app/api/nurse.py` | `export_monthly_report` Excel 导出增加"类型"列 |
| `frontend/src/views/nurse/Inventory.vue` | 月度报表表格新增"类型"列 |

---

## 四、Bug修复 - 医生端耗材库存校验遗漏

### 问题描述

`doctor.py` 中药品搜索和就诊创建时，库存校验（零库存过滤、库存组校验）仅检查 `type==1`，遗漏了 type=3 耗材。

### 修复方案

将相关条件从 `drug.type == 1` 改为 `drug.type in (1, 3)`。

### 改动文件

| 文件 | 改动说明 |
|------|---------|
| `backend/app/api/doctor.py` | 药品搜索零库存过滤条件包含 type=3 |
| `backend/app/api/doctor.py` | 就诊创建库存组校验条件包含 type=3 |

---

## 五、增强 - 营收统计展示耗材收入

### 问题描述

后端已正确计算 `consumable_revenue` 和 `consumable_amount`，但前端营收统计页面未展示。

### 修复方案

- 新增"耗材收入"汇总卡片
- 明细表格新增"耗材"金额列

### 改动文件

| 文件 | 改动说明 |
|------|---------|
| `frontend/src/views/admin/Statistics.vue` | 新增耗材收入卡片和明细列 |

---

## 六、修复 - merge_drugs 脚本兼容耗材

### 改动文件

| 文件 | 改动说明 |
|------|---------|
| `backend/merge_drugs.py` | 药品合并时库存累加条件从 `type == 1` 改为 `type in (1, 3)` |

---

## 全部改动文件汇总

| 文件 | 改动类型 |
|------|---------|
| `backend/app/api/nurse.py` | Bug修复 + 增强 |
| `backend/app/api/admin.py` | Bug修复 |
| `backend/app/api/doctor.py` | Bug修复 |
| `backend/merge_drugs.py` | Bug修复 |
| `frontend/src/views/nurse/Inventory.vue` | 增强 |
| `frontend/src/views/admin/Statistics.vue` | 增强 |

---

## 七、稳定性增强 - 系统自动退出问题修复

### 问题背景

用户反馈系统运行一段时间后会自动退出，医护人员频繁掉线需要重新打开系统。

### 日志分析结论

分析客户 app.log（6624 行，涵盖 36 小时），发现：
- 一天内系统被重启 **6 次**
- **0 条**错误/异常记录，**0 条** `Application stopped` 日志
- 每次崩溃前有 6~31 分钟无请求间隙
- 最后一次启动连续运行 27 小时无异常

### 根本原因

1. **Windows Console QuickEdit 模式**（主因）：用户点击控制台窗口时进程被冻结，以为系统退出后关闭窗口
2. **Flask 开发服务器**：单线程、非生产设计，不够健壮
3. **无进程保护**：进程崩溃后无重启机制

### 修复方案

| 修复项 | 说明 |
|--------|------|
| 禁用 QuickEdit | 启动时通过 Windows API (ctypes) 关闭控制台 QuickEdit/Insert 模式 |
| waitress 替代 dev server | 生产级多线程 WSGI 服务器，稳定可靠 |
| 崩溃自动重启 | 最多重试 5 次，间隔 3 秒，记录崩溃日志 |
| 全局异常处理器 | Flask `@app.errorhandler(Exception)` 防止 500 空响应 |
| 日志轮转 | RotatingFileHandler，单文件 5MB，保留 5 个备份 |
| 前端断线检测 | 网络断开时弹出提示，每 5 秒心跳检测，恢复后自动通知 |
| 请求超时调整 | 前端 axios timeout 从 5s 提升到 15s |

### 改动文件

| 文件 | 改动说明 |
|------|----------|
| `run_prod.py` | 禁用 QuickEdit + waitress 替代 dev server + 崩溃自动重启 + 全局异常处理 + 日志轮转 |
| `backend/requirements.txt` | 添加 `waitress`、`Flask-CORS` 依赖 |
| `frontend/src/api/request.js` | 断线检测 + 自动重连提示 + 超时增大 |
| `medical_room.spec` | PyInstaller hiddenimports 添加 waitress 相关模块 |

---

## 全部改动文件汇总

| 文件 | 改动类型 |
|------|----------|
| `backend/app/api/nurse.py` | Bug修复 + 增强 |
| `backend/app/api/admin.py` | Bug修复 |
| `backend/app/api/doctor.py` | Bug修复 |
| `backend/merge_drugs.py` | Bug修复 |
| `frontend/src/views/nurse/Inventory.vue` | 增强 |
| `frontend/src/views/admin/Statistics.vue` | 增强 |
| `run_prod.py` | 稳定性增强 |
| `backend/requirements.txt` | 依赖更新 |
| `frontend/src/api/request.js` | 稳定性增强 |
| `medical_room.spec` | 打包配置更新 |

## 验证要点

### 耗材相关
- 护士端入库耗材（type=3）正确创建 Drug 记录和 InventoryRecord
- 管理员修改药品类型为耗材时 variant_type 自动设为 consumable
- 月度盘点报表包含耗材记录，表格和导出均显示类型列
- 医生端搜索/开方时耗材库存正确校验
- 营收统计页面显示耗材收入卡片和明细列

### 稳定性相关
- 启动后控制台窗口不可选中文本（QuickEdit 已禁用）
- 日志显示 `Starting waitress server` 而非 Flask dev server 警告
- 手动终止进程后自动重启（最多 5 次）
- 前端断网时显示"服务连接中断"通知，恢复后自动消失
- 复杂操作（如导出 Excel）不再超时报错
