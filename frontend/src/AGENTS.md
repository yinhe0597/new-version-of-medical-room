# frontend/src 域约定

前端核心域（Vue 3 + Vite + Element Plus + Pinia）。硬约束见根 `AGENTS.md`，本文件不重复。

## 边界

- `views/`：按角色分目录（`admin/`、`doctor/`、`nurse/`、`finance/`）。热点：`doctor/VisitForm.vue`（约 1250 行）、`nurse/Inventory.vue`（约 880 行）。
- `api/request.js`：唯一的 axios 封装与请求拦截层，新接口调用统一走它，不在组件内裸用 axios。
- `store/user.js`：Pinia 用户状态（登录态/角色），权限相关状态只放这里。
- `router/index.js`：路由与角色守卫，新增页面须在此注册。

## 验证入口

- `frontend/` 下先执行 `npm run test`（Vitest，覆盖 `utils/` 纯逻辑），再 `npm run build`。

## 风险提示

- `VisitForm.vue`、`Inventory.vue` 为大型 SFC：小步修改，避免整段重写 template/script，每次改动后跑 `npm run test` 与 `npm run build` 验证；其可测纯逻辑已提取到 `utils/prescription.js`、`utils/inventoryCalc.js`。
