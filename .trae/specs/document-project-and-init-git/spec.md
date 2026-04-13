# 项目介绍文档与 Git 初始化 Spec

## Why

该项目将医务室线下纸质流程信息化，后续二次开发需要对现有架构、职责拆分与关键流程形成统一认知，并把仓库纳入 Git 版本管理以支撑协作与迭代。

## What Changes

- 新增一份面向开发者的项目介绍文档：覆盖项目目标、架构、模块边界、角色与主要业务流程、功能清单、关键入口点与本地开发方式
- 适度更新根 README：在首页给出“项目是什么/有什么功能/如何启动”的最小信息，并链接到详细介绍文档
- 初始化 Git 仓库：`git init`，设置仓库级 `user.name` 与 `user.email`，并创建首次提交（包含现有代码与新增文档）

## Impact

- Affected specs: 文档与工程化（项目概览、开发上手、版本管理）
- Affected code: 仅文档与仓库元信息（README、docs/ 新文档、.git/ 初始化与本地 git config）

## ADDED Requirements

### Requirement: 项目介绍文档

系统 SHALL 提供一份开发者可读的项目介绍文档，用于二次开发与协作对齐。

#### 内容范围（必须包含）

- 项目定位：医务室信息化，按角色拆分职责，覆盖诊疗、处方流转、库存/进销存、收费与统计
- 技术栈：前端（Vue3/Vite/Pinia/Element Plus）与后端（Flask/SQLAlchemy/Flask-Migrate/JWT）及其边界
- 架构与目录结构：前后端分离、API 前缀约定、主要目录职责（backend/app/api、backend/app/models、frontend/src/views 等）
- 鉴权与权限：前端路由角色守卫、后端接口角色校验（以“管理员/医生/护士”为核心）
- 关键业务闭环：患者检索/建档 → 医生接诊开方 → 护士审核/执行/扣减库存 → 支付/结算 → 统计与维护
- 功能清单：按角色列出主要页面与能力（管理员/医生/护士）
- 关键入口点：前端入口、路由、请求封装；后端启动入口、应用工厂、蓝图、登录接口等
- 本地开发：如何分别启动前端与后端、以及常见问题提示（不写入任何密钥）

#### Scenario: 成功

- **WHEN** 开发者阅读该文档
- **THEN** 能在 5 分钟内理解系统的三端角色能力与关键数据流，并能定位前后端主要入口文件开始二次开发

### Requirement: 根 README 最小可用信息

系统 SHALL 在根 README 中提供最小可用的“项目概述 + 功能概览 + 快速启动 + 文档入口”信息，并链接到详细介绍文档。

#### Scenario: 成功

- **WHEN** 开发者打开仓库首页
- **THEN** 能在无需翻找目录的情况下找到项目介绍、功能范围与启动指引入口

### Requirement: Git 初始化与身份信息

系统 SHALL 在当前项目目录初始化 Git 仓库，并设置仓库级别提交身份信息：

- `user.name = Vincentluo`
- `user.email = yhkjsj@foxmail.com`

#### 约束

- 不修改全局 Git 配置，仅设置当前仓库的本地配置
- 不自动添加远端地址（remote），除非后续明确要求

#### Scenario: 成功

- **WHEN** 执行 `git status`
- **THEN** 能看到仓库已初始化且文件可被跟踪
- **WHEN** 查看 `git config --local user.name/user.email`
- **THEN** 输出与上述身份信息一致

## MODIFIED Requirements

无。

## REMOVED Requirements

无。

