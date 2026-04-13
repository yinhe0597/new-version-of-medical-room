# Tasks

- [ ] Task 1: 现状核对与差距清单（对应问题 1/2/3）
  - [ ] 明确医生开方提交时已做/未做的强制校验点，并列出需要补齐的规则
  - [ ] 明确护士端审核状态机与前端交互是否可绕过，并补齐后端防线
  - [ ] 对齐“管理员端 → 护士端”下放范围：库存管理全量能力 + 报表导出

- [ ] Task 2: 后端实现医生端强制检查（API 校验与错误结构）
  - [ ] 为 `/api/doctor/visits` 增加统一的请求校验（必填字段、items 非空、药品明细的用法用量完整性、数量合法性、零卖规则、库存校验）
  - [ ] 规范化错误响应结构，保证前端可定位到具体明细项/字段

- [ ] Task 3: 后端固化护士审核闭环（审核校验 + 状态机约束）
  - [ ] 审核接口 `/api/nurse/visits/<id>/verify` 增加执行前校验（至少库存校验与状态迁移合法性）
  - [ ] 确认执行接口 `/api/nurse/visits/<id>/execute` 仍强制要求 `nurse_verified`

- [ ] Task 4: 护士端扩权：库存管理能力对齐管理员端
  - [ ] 选择实现方式：为现有 admin 库存相关接口增加 nurse 权限，或新增等价 nurse 接口（要求不重复核心逻辑）
  - [ ] 护士端提供药品/项目管理 UI（可复用/迁移 admin 现有 DrugManagement）
  - [ ] 护士端提供批量入库、模板下载、智能盘库、启停用/删除等全量能力

- [ ] Task 5: 报表导出与内容细化（后端导出 + 前端触发）
  - [ ] 增加导出接口（护士可用），导出 `.xlsx`，包含汇总 + Visit 级明细字段（含支付方式、医生/护士/患者信息、成本与利润）
  - [ ] 前端在统计页面补齐导出按钮逻辑（可复用 admin/Statistics，并在护士端提供入口）

- [ ] Task 6: 数据库（MySQL）迁移与兼容性
  - [ ] 如需新增字段/索引：补齐 Alembic 迁移脚本，并在 MySQL 连接下可执行
  - [ ] 更新相关文档：说明通过环境变量配置 MySQL（不写入任何明文账号密码）

- [ ] Task 7: 验证与回归
  - [ ] 覆盖问题 1/2：分别验证“医生端强制检查生效”和“护士未审核不可执行”
  - [ ] 覆盖问题 3：护士端可完成药品管理全流程与报表导出
  - [ ] 运行后端测试用例（若存在），并补充关键路径测试（最小集合）

# Task Dependencies

- Task 2 depends on Task 1
- Task 3 depends on Task 1
- Task 4 depends on Task 1
- Task 5 depends on Task 1
- Task 6 depends on Task 2, Task 4, Task 5
- Task 7 depends on Task 2, Task 3, Task 4, Task 5, Task 6

