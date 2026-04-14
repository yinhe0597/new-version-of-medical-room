# 疾病诊断检索库（ICD-10）构建与自定义诊断沉淀

目标：

- 将 `国家临床版2.0疾病诊断编码（ICD-10）.xlsx` 导入到后端 `diagnosis_dict` 表，用于医生端诊断区域的快速模糊检索（中文/拼音/编码）
- 将医生在诊断文本域（textarea）里手工输入/编辑的诊断，自动沉淀回 `diagnosis_dict`，形成长期可复用的“自定义诊断库”

## 1. 表结构

当前疾病库使用后端模型 `DiagnosisDict`：

- `code`：疾病诊断编码（ICD-10 编码；自定义诊断可为空字符串）
- `name`：疾病诊断名称
- `pinyin`：检索字段，格式为 `首字母|全拼`（例如 `gm|ganmao`）

模型位置：[models/__init__.py](file:///e:/yws2/medical-room-management-system/backend/app/models/__init__.py)

## 2. ICD-10 导入（生成疾病检索库）

导入脚本：

- [import_icd10.py](file:///e:/yws2/medical-room-management-system/backend/import_icd10.py)

特点：

- 默认读取项目根目录的 `国家临床版2.0疾病诊断编码（ICD-10）.xlsx`
- 不再清空整张表，改为按 `code` 幂等 upsert
- 保留历史/自定义诊断（`code=''`）不被覆盖

运行方式（Windows/无系统 Python 场景，使用项目内 Python）：

```powershell
cd E:\yws2\medical-room-management-system\backend
& "E:\yws2\medical-room-management-system\.tools\python\py312\python.exe" import_icd10.py
```

如果 Excel 的 sheet 不是默认第一个，可以指定：

```powershell
cd E:\yws2\medical-room-management-system\backend
& "E:\yws2\medical-room-management-system\.tools\python\py312\python.exe" import_icd10.py "E:\yws2\medical-room-management-system\国家临床版2.0疾病诊断编码（ICD-10）.xlsx" --sheet "国家临床版2.0诊断编码（ICD-10）"
```

## 3. 检索接口（供 div 诊断区域调用）

后端接口：

- `GET /api/doctor/diagnoses/search?keyword=xxx`

说明：

- `keyword` 支持：
  - 中文（按 `name` 模糊匹配）
  - 拼音/首字母（按 `pinyin` 模糊匹配）
  - ICD-10 编码（按 `code` 模糊匹配）
- 最多返回 50 条

实现位置：[doctor.py](file:///e:/yws2/medical-room-management-system/backend/app/api/doctor.py)

前端调用位置（医生开方页诊断 autocomplete）：

- [VisitForm.vue](file:///e:/yws2/medical-room-management-system/frontend/src/views/doctor/VisitForm.vue)

## 4. textarea 自定义诊断沉淀

当医生提交就诊（`POST /api/doctor/visits`）时，后端会解析 `diagnosis` 字段，把诊断文本拆成条目并写回 `diagnosis_dict`：

- 支持多行（换行分隔）
- 支持同一行多条（用 `;` 或 `；` 分隔）
- 支持 `名称 (编码)` / `名称（编码）` 的格式（会识别出编码）
- 对于无编码的自定义诊断，按 `name` 去重写入（`code=''`）

实现位置：[doctor.py](file:///e:/yws2/medical-room-management-system/backend/app/api/doctor.py)

## 5. 部署建议

- 首次部署：
  - 先初始化数据库与默认账号（如需）：运行 `backend/init_db.py`
  - 再导入 ICD-10：运行 `backend/import_icd10.py`
- 版本升级：
  - 仅更新 ICD-10 文件时，可重复执行 `import_icd10.py`（幂等 upsert）
  - 自定义诊断不应被清空；如需全量重建，建议先备份 `diagnosis_dict` 再处理

