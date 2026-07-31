# backend/app 域约定

后端核心域。硬约束（数据资产、迁移通道等）见根 `AGENTS.md`，本文件不重复。

## 边界

- `api/`：按角色分蓝图。热点：`admin.py`、`nurse.py`（均为高频改动的大文件），其次 `doctor.py`；`auth.py`、`finance.py`、`routes.py` 较稳定。
- `models/`：全部 ORM 模型集中在 `models/__init__.py`，只放表结构与关系，不放业务逻辑。
- `services/`：跨路由复用的业务逻辑（`drug_stock.py`、`inventory_ledger.py`、`revenue.py`、`stock_lock.py`、`bootstrap.py`、`time_utils.py`）。库存/营收类逻辑优先改这里，不在 api 层内联。
- `utils/`：无业务的通用工具（`decorators.py`、`query.py`、`spreadsheet.py`）。

## 验证入口

- 唯一测试入口：项目根 `python run_backend_tests.py`（全量发现 `backend/tests/`）。

## 风险提示

- `admin.py`（约 10 万字符）、`nurse.py`（约 9 万字符）为高 churn 大文件：一次只改一个端点/函数，小步提交，每次改动后立即跑上述测试入口。
