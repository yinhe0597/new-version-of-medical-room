# 接口文档（节选）

本文件仅覆盖本次缺陷修复涉及的接口。基础前缀为 `/api`。

## 医生端

### 文本模板（主诉/体格检查/医生贴士）
- 路径：`GET /doctor/templates`
- 参数：
  - `category`（必填）：`chief_complaint` | `physical_exam` | `doctor_advice`
  - `q`（可选）：关键字，匹配 title/content
- 响应：`{ "data": [{ "id": number, "category": string, "title": string, "content": string, "created_at": string, "updated_at": string }] }`

- 路径：`POST /doctor/templates`
- Body：`{ category, title, content }`
- 响应：`{ "data": { "id": number } }`

- 路径：`PUT /doctor/templates/<id>`
- Body：`{ title, content }`
- 响应：`{ "msg": "Template updated successfully" }`

- 路径：`DELETE /doctor/templates/<id>`
- 响应：`{ "msg": "Template deleted successfully" }`

### 诊断搜索
- 路径：`GET /doctor/diagnoses/search`
- 参数：
  - `keyword`（必填）：支持汉字、ICD 编码、拼音首字母、全拼
- 响应：`{ "data": [{ "id": number, "code": string, "name": string, "pinyin": string }] }`

### 药品/项目搜索
- 路径：`GET /doctor/drugs/search`
- 参数：
  - `keyword`（可选）：匹配 `name/specification`
- 响应：`{ "data": [{ "id": number, "name": string, "type": number, "specification": string, "unit": string, "price": number, "has_scattered": boolean, "scattered_price": number|null, "conversion_rate": number|null, "stock": number }] }`

### 学生（患者）搜索
- 路径：`GET /doctor/patient/search`
- 参数：
  - `student_id` 或 `keyword`（二选一必填）：支持学号中间片段、姓名汉字、姓名拼音首字母/全拼
- 响应：
  - `data` 为数组；每项包含 `student_id/name/gender/grade/college/major/class_name/phone`
  - 响应头：`X-Response-Time-ms`（毫秒）
- 限流：
  - 同一用户 10 秒内最多 30 次请求；超过返回 `429`

### 医生就诊历史/详情（用于“病例复盘/重新开方”）
- 路径：`GET /doctor/visits/history`
- 参数（均可选）：
  - `page`（默认 1）
  - `size`（默认 20）
  - `start_date`（格式 `YYYY-MM-DD`）
- 响应：`{ data: [{ id, patient_id, patient_name, student_id, date, diagnosis, status, total_amount }], meta: { page, per_page, total, pages } }`

- 路径：`GET /doctor/visits/<visit_id>`
- 响应（节选）：
  - `data.items[]` 包含 `drug_id/drug_type/drug_name/specification/usage/dosage/frequency/timing/days/quantity/price_at_visit/amount/is_scattered`

## 护士端

### 药品列表（库存盘点）
- 路径：`GET /nurse/drugs`
- 参数（均可选）：
  - `name`：药品名称包含匹配
  - `specification`：规格包含匹配
  - `batch_no`：批号包含匹配
  - `inbound_start`：入库时间起（ISO 格式，如 `2026-03-01 10:30:00`）
  - `inbound_end`：入库时间止（ISO 格式）
  - `pack`：`all` / `scattered` / `packed`
  - `keyword`：兼容旧参数（匹配 name/specification）
- 响应：`{ "data": [{ "id": number, "name": string, "type": number, "specification": string, "unit": string, "price": number, "stock": number, "has_scattered": boolean, "scattered_price": number|null, "conversion_rate": number|null, "batch_no": string|null, "inbound_at": string|null }] }`

## 管理端

### 药品导入模板
- 路径：`GET /admin/drugs/template`
- 文件：CSV
- 列：`name,specification,unit,purchase_price,price,has_scattered,scattered_price,conversion_rate,stock,batch_no,inbound_at`

### CSV 导入
- 路径：`POST /admin/drugs/import`
- 说明：
  - 按 `name + specification` 合并
  - `has_scattered=1` 表示支持零卖；`scattered_price` 为零卖单价；`conversion_rate` 为整装到零散转换率

### Excel 导入
- 路径：`POST /admin/drugs/import_xls`
- 说明：
  - 按 `序号` 分组
  - 若存在列 `库存/批号/入库时间` 会写入对应字段
