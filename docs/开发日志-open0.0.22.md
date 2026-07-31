# 开发日志 open0.0.22（2026-07-31）

## 版本主题

Go 重构版后端维护记录：MySQL 备份修复、财务查询性能优化与全链路 MySQL 验收（Go 源码暂未入库）。

## 1. 范围说明

- 本轮全部改动发生在 Go 重构版后端代码库（Gin + GORM，SQLite/MySQL 双驱动），按当前决定 **Go 源码暂不上传**，本仓库仅同步维护记录与版本文档。
- Go 代码库结构：`cmd/`（server、migrate、dbinspect 入口）、`internal/`（config、handler、middleware、model、service、util）、`tests/`（PowerShell 冒烟/E2E/入库/修复验证脚本）、`tools_gen_testusers/`（测试账号生成工具）。

## 2. MySQL 备份修复（原备份在 MySQL 模式下失效）

- `GET/POST /api/admin/backup` 与 `GET /api/admin/backup/mysql` 在 MySQL 模式下均改为导出真正的 MySQL 逻辑备份（`.sql`，含 `DROP TABLE`/`CREATE TABLE`/`INSERT`），SQLite 模式行为不变。
- 纯 Go 实现 dump：REPEATABLE READ 只读事务保证一致性快照；`SHOW FULL TABLES WHERE Table_type='BASE TABLE'` 过滤视图；表名反引号转义；流式导出每 500 行合并一条 INSERT。
- `time.Time` 按 `2006-01-02 15:04:05.000` 输出，保留 `datetime(3)` 毫秒精度；字符串按字节转义，兼容非 UTF-8 字节。
- 备份文件名追加纳秒后缀，避免同秒并发备份互相覆盖；自动清理仅保留最近 20 份。
- 验收：dump 约 14.9MB / 217 条 INSERT / 约 3~5 秒；还原到临时库后 13 张表行数与源库完全一致（patient=14693、visit=4145、diagnosis_dict=35968 等），毫秒精度与中文内容完好。

## 3. 财务接口性能优化

- 新增 `internal/service/revenue_query.go`：`LoadRevenueVisits` 用 JOIN 直接过滤子表，替代 Preload 生成的巨型 `IN (...)` 子句。（Go 代码库内路径）
- 财务看板三段查询合一后内存分桶；利润趋势从 N 次逐日查询改为单次范围查询按天分桶。

| 接口 | 修复前 | 修复后 |
| --- | --- | --- |
| `/finance/dashboard/summary` | 271ms+（SLOW SQL） | 37ms |
| `/finance/profit-trend?days=30` | 30 次查询 | 8ms |
| `/finance/revenue/by-type` | 慢且参数失效 | 30~62ms |
| `/admin/statistics/revenue/export` | SLOW SQL | 51~134ms |

## 4. 其它缺陷修复

- 营收分类接口 `revenue/by-type` 此前完全忽略 `start_date`/`end_date` 参数，已修复。
- 日期解析统一改为 `time.ParseInLocation(..., time.Local)`，消除 UTC 解析在东八区产生的 8 小时过滤偏移。
- 财务看板"今日"区间上界改为今日 0 点 +24h，不再把未来时间的缴费计入。
- JWT 未配置密钥时不再回退到硬编码开发密钥，改为 `crypto/rand` 随机临时密钥并输出警告，杜绝伪造 token 风险。

## 5. 代码审查与安全扫描

- CodeReview 审查结论：无必须阻断的严重缺陷；提出的 7 项反馈（一致性快照、并发文件名、毫秒精度、时区解析、字节转义、视图过滤、未来时间计入）已全部落实并二次验证。
- L2 轻量安全扫描：未发现安全问题。

## 6. 验证结果

- `go build` / `go vet` / `go test` 全部通过。
- 接口冒烟回归 35/36 通过（唯一失败项为已知的月报测试脚本参数写法问题，非代码缺陷）。
- 服务器日志无 SLOW SQL、无错误。
- MySQL 备份还原校验：13 张表行数一致、毫秒与中文完好。

## 7. 主要文件（Go 代码库内，暂未入库）

| 范围 | 文件 |
| --- | --- |
| 备份修复 | `internal/handler/admin.go` |
| 财务优化 | `internal/handler/finance.go`、`internal/service/revenue_query.go` |
| JWT 加固 | `cmd/server/main.go` |
| 验证脚本 | `tests/fix_verify_test.ps1`、`tests/api_smoke_test.ps1` |
| 本仓库文档 | `VERSION`、`README.md`、本日志 |

## 8. 边界说明

1. Go 重构版源码暂不上传；Python 成品的生产候选状态仍以 open0.0.21 及其上线执行清单为准。
2. Go 版生产部署必须设置 `JWT_SECRET_KEY` 环境变量（≥32 位），否则每次重启后所有登录失效。
3. 本地 MySQL 测试库（yws_test）中存在 E2E 测试遗留数据，作生产基础前需清理。
