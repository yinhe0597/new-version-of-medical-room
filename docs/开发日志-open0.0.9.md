# 开发日志 - open0.0.9（2026-05-20）

## 本次变更

### 🖨️ 修复护士端打印小票重复问题

**涉及文件：**
- `frontend/src/views/nurse/HistoryList.vue`

**问题：** 点击打印小票时，系统连续打印7张完全相同的票据。

**根因：** `window.print()` 打印整个页面内容，历史记录表格中有多条数据，但没有 `@media print` 样式限定打印区域，导致表格所有行逐页打印。

**修复：** 添加全局 `@media print` 样式：
```css
@media print {
  body * { visibility: hidden !important; }
  #receipt-print-area, #receipt-print-area * { visibility: visible !important; }
  #receipt-print-area { position: absolute !important; left: 0; top: 0; width: 100%; }
}
```
打印时仅显示 `#receipt-print-area` 票据区域，隐藏页面其余内容。

---

### 🔄 医生端刷新库存按钮

**涉及文件：**
- `frontend/src/views/doctor/VisitForm.vue`

**背景：** 药品库存不足时报错无法开方，护士补充库存后前端不会自动更新，医生无法及时看到库存变化。

**实现：**
- 药品搜索框右侧新增"刷新库存"按钮（带 Refresh 图标，`title="刷新库存"`）
- 点击调用 `searchDrugs('')` 重新获取最新药品列表和库存数据
- 带 `refreshingStock` loading 状态和"库存已刷新"成功提示

---

### 📱 手机号格式校验

**涉及文件：**
- `frontend/src/views/doctor/PatientSearch.vue`

**背景：** 医生初次接诊输入手机号时，学生可能少输或多输数字位数，缺少格式校验。

**实现：**
- 补充手机号弹窗的 `submitPhone` 函数增加 `/^1\d{10}$/` 格式校验
- 不符合时提示"手机号码格式不正确，应为1开头的11位数字"并阻止提交
- 建档表单中原有的校验规则保持不变（临时人员必填且格式校验，非临时选填但有值时校验）
