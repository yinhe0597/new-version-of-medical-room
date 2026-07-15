# 开发日志 open0.0.21（2026-07-15）

## 版本主题

生产发布门禁修复、依赖可复现、版本一致性与上线资料收口。

## 1. 发布流程修复

- Gitee 的主分支、普通分支和 PR 流水线不再执行不存在的根目录 `requirements.txt` 与 `main.py`。
- 三条流水线统一运行后端全量测试、Python 漏洞审计、源码编译、`pip check`、前端依赖审计与生产构建。
- 主分支触发目标从旧的 `master` 改为当前使用的 `main`，普通分支明确排除 `main`。
- GitHub Linux 发布工作流不再硬编码旧 Alembic revision，改为读取校验器的 `CURRENT_HEAD`。
- PyInstaller 归档检查改为动态枚举全部 migration 文件，新增迁移后不会因静态清单漏项而失去门禁。

## 2. 可复现依赖与供应链检查

- 新增 `backend/constraints.txt`，锁定运行、构建和审计工具的完整传递依赖版本。
- 新增 `backend/requirements-ci.txt`，让 CI 使用与生产构建一致的依赖集合并固定 `pip-audit`。
- `backend/requirements-build.txt` 接入约束锁，继续固定 PyInstaller 6.20.0。
- 全新解析时发现 `charset-normalizer 3.4.8` 已被 PyPI 撤回，锁文件已切换到未撤回的 `3.4.9`。
- 忽略本机已安装包重新解析完整依赖成功；Python 与 npm 生产依赖审计均为 0 个已知漏洞。

## 3. 版本与构建边界

- 新增根目录 `VERSION`，当前值为 `0.0.21`；Linux 构建与 GitHub 发布统一读取该文件。
- 推送的 `v*` 标签与 `VERSION` 不一致时，发布工作流直接失败。
- Windows 文件版本、产品版本和生产启动横幅同步升级到 `open0.0.21`。
- Linux 手工构建最低环境调整为 Python 3.11 和 Node.js 22.12。
- 修正 Linux 制品兼容性声明：Ubuntu 22.04 CI 制品要求 Linux x86_64 与 glibc 2.35+，AppImage 不绕过 glibc 下限。

## 4. 防回归测试

新增 `backend/tests/test_release_configuration.py`，覆盖：

- 唯一 Alembic head 与 Linux 发布工作流一致。
- 发布归档动态检查所有迁移文件。
- Gitee 流水线使用真实项目入口并面向 `main`。
- 所有直接构建/CI 依赖均被精确约束。
- `VERSION`、Windows 资源与生产启动版本一致。

本轮后端全量测试结果为 244 项通过，另有 1 项因 Windows 不具备原生 Linux `/proc` 语义而跳过。前端 Vite 构建完成 1,693 个模块，最大公共 chunk 约 764 KB，保留非阻断性能告警。

## 5. 生产数据与环境复核

- `data/app.db` 只读预检为 0 blocking、1 warning；warning 为历史扩展列，不阻断本地候选验证。
- `data/ture.db` 仍位于 `bbf28ffdb4c0`，只读复核确认 1,227 条历史外键孤儿：834 条库存快照、97 条库存流水、295 条处方明细、1 条操作日志。
- 历史库不得原地修改。关联重建或置空必须由业务负责人逐项批准，并只在隔离副本执行。
- 本机旧 MySQL login-path 可被配置工具识别，但 MySQL 客户端未加载其密码；隔离迁移验收停在认证前，未创建或修改任何 schema/账号。
- 新增生产上线执行清单，集中记录目标 MySQL、历史数据、签名、灰度、回退和 Go/No-Go 条件。

## 6. 文档收口

- 中文 README 从 739 行压缩到 190 行，英文 README 从 357 行压缩到 169 行。
- 首页移除无效截图占位、过期路线图、重复维护公告和逐版本长篇复制内容。
- 当前状态、生产边界和最近版本前置展示，详细历史统一下沉到 `docs/`。
- 快速开始命令统一到当前目录结构、Python 3.11、Node.js 22.12 和 `open0.0.21` 制品命名。
- 当前版本同步到二次开发快速入门、重整版 Wiki、项目分析、API 清单和上线执行清单。

## 7. 主要文件

| 范围 | 文件 |
| --- | --- |
| 发布版本 | `VERSION`、`version_info.txt`、`run_prod.py` |
| GitHub 发布 | `.github/workflows/build-linux-release.yml` |
| Gitee 门禁 | `.workflow/branch-pipeline.yml`、`.workflow/master-pipeline.yml`、`.workflow/pr-pipeline.yml` |
| Python 依赖 | `backend/constraints.txt`、`backend/requirements-build.txt`、`backend/requirements-ci.txt` |
| 回归测试 | `backend/tests/test_release_configuration.py` |
| 项目入口 | `README.md`、`README.en.md` |
| 运维资料 | `docs/部署与维护说明.md`、`docs/生产上线执行清单-2026-07-15.md` |

## 8. 发布边界

`open0.0.21` 是生产候选版本，不等于目标环境已验收。正式放量前仍必须完成：

1. 推送代码并取得远端 Gitee `main` 流水线绿色结果。
2. 在 Ubuntu 22.04 原生完成 Linux、AppImage、`/proc` 和成品 MySQL 门禁。
3. 使用可信证书签署 Windows EXE，并在签名后重做哈希和成品冒烟。
4. 在目标 MySQL/云数据库完成 verified TLS、真实备份恢复、PITR、故障转移和回退 RTO 演练。
5. 完成历史孤儿数据处置审批、迁移对账和单实例内网灰度。

详细执行状态见[生产上线执行清单](生产上线执行清单-2026-07-15.md)。
