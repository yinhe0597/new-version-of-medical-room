# 手工验收脚本（manual checks）

本目录存放**手工验收脚本**，不属于自动化测试套件（`run_backend_tests.py` 只发现
`backend/tests/`）。文件统一以 `check_` 前缀命名，避免被 unittest/pytest 误采集。

## 两类脚本

| 类型 | 前置条件 | 脚本 |
| --- | --- | --- |
| HTTP 验收（requests） | 后端服务已运行在 `MEDICAL_API_BASE_URL`（默认 `http://127.0.0.1:5000/api`），且对应账号存在 | `check_jwt_auth.py`、`check_admin_api.py`、`check_doctor_api.py`、`check_nurse_api.py` |
| 本地 app 验收（test_client） | 本地可导入 `backend.app`（无需启动服务） | `check_patient_search.py`、`check_drug_visibility.py`、`check_disease_search.py`、`check_revenue_stats_date_filters.py` |

## 凭据约定

仓库内不保留任何硬编码口令。HTTP 验收脚本从环境变量读取真实账号口令，缺失时直接退出：

```powershell
$env:MEDICAL_ADMIN_PASSWORD = "..."
$env:MEDICAL_DOCTOR_PASSWORD = "..."
$env:MEDICAL_NURSE_PASSWORD = "..."
backend\.venv\Scripts\python.exe backend\manual_checks\check_admin_api.py
```

本地 app 验收脚本若需临时创建测试用户，口令取自 `MEDICAL_CHECK_PASSWORD`，
未设置时在本次运行内随机生成（不落盘）。
