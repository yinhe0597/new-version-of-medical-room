# 开发日志

## 2026/05/11

### 编译 exe 启动崩溃（AssertionError）

**问题根因**：Flask Blueprint 以函数名作为 endpoint 标识，同一 Blueprint 下存在 3 对同名视图函数导致路由注册冲突，exe 启动时抛出 `AssertionError: View function mapping is overwriting an existing endpoint function`。

**冲突清单**：

| 函数名 | 冲突文件 |
|---|---|
| `create_patient` | `doctor.py` 和 `admin.py` |
| `update_patient` | `doctor.py` 和 `admin.py` |
| `get_visit_detail` | `nurse.py` 和 `admin.py` |

**修复**：将 `admin.py` 中的三个冲突函数分别重命名为 `admin_create_patient`、`admin_update_patient`、`admin_get_visit_detail`，消除 endpoint 命名冲突。

### run_prod.py 模块级代码脆弱性

**问题根因**：`app = create_app()` 写在模块级别（不在 `if __name__ == '__main__'` 内），导入时即执行。若有任何初始化异常（如数据库问题、路由冲突等），整个进程无异常处理直接崩溃，日志瞬间截断。

**修复**：将所有执行代码移入 `if __name__ == '__main__'` 块，并添加 `try/except` 兜底异常捕获和 `input()` 暂停，确保错误信息可读。

### PyInstaller 隐式导入遗漏

**问题根因**：部分动态加载模块（alembic、openpyxl 子模块等）未在 spec 文件中列为 `hiddenimports`，可能导致运行时找不到模块。

**修复**：在 `medical_room.spec` 中补充缺失的隐式导入。
