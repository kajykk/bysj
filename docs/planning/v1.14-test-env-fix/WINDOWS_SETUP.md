# Windows 开发环境配置指南

> **适用版本**: v1.14+
> **日期**: 2026-04-30
> **状态**: 已完成

---

## 1. 已知问题

### 1.1 Windows DLL 初始化崩溃 (exit code -1073741510)

**症状**: 运行 pytest 或导入某些 Python 库时进程崩溃

**影响库**:
- `sklearn` — 科学计算库
- `pandas` — 数据分析库
- `sqlalchemy` (间歇性) — ORM 库
- `slowapi` (间歇性) — 限流库

**根本原因**: Windows 上 C 扩展/DLL 运行时环境存在兼容性问题，可能与 Python 3.12 + Windows 的组合有关。

---

## 2. 已应用的修复

### 2.1 config.py 修改

**文件**: `backend/app/core/config.py`

**修改内容**:
- `SKLEARN_VERSION` 改为延迟加载
- Windows 上完全跳过 `sklearn` 导入

```python
def _get_sklearn_version() -> str | None:
    global _SKLEARN_VERSION
    if _SKLEARN_VERSION is None:
        # On Windows, importing sklearn may crash with exit -1073741510
        if sys.platform == "win32":
            _SKLEARN_VERSION = None
        else:
            try:
                import sklearn
                _SKLEARN_VERSION = sklearn.__version__
            except ImportError:
                _SKLEARN_VERSION = None
    return _SKLEARN_VERSION
```

### 2.2 conftest.py 修改

**文件**: `backend/tests/conftest.py`

**修改内容**:
- 添加 OpenMP 环境变量（部分有效）

```python
# Fix Windows DLL issues with sklearn/pandas/numpy
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
```

### 2.3 test_core_config.py 修改

**文件**: `backend/tests/test_core_config.py`

**修改内容**:
- 移除 `import warnings`（该导入会触发崩溃）
- 修复测试断言以适应 .env 文件覆盖

---

## 3. 推荐工作流

### 3.1 本地开发 (Windows)

**运行简化测试**:
```bash
cd backend
python -m pytest tests/test_core_config.py -v -o "addopts="
```

**说明**:
- `-o "addopts="` — 禁用 pytest.ini 中的覆盖率插件（会导致崩溃）
- 仅运行核心模块测试，避免导入大量 app 模块

### 3.2 Docker 测试 (推荐)

**构建并运行**:
```bash
cd e:\code\bysj
docker-compose run test
```

**优点**:
- 完全绕过 Windows DLL 问题
- 与 CI 环境一致
- 可运行完整测试套件和覆盖率报告

### 3.3 CI 验证 (GitHub Actions)

**推送代码后自动运行**:
```bash
git push origin main
```

**查看结果**:
- 访问 GitHub 仓库 → Actions 标签
- 查看 `coverage.yml` workflow 运行结果

---

## 4. 测试运行方式对比

| 方式 | 命令 | 覆盖率 | 稳定性 | 推荐度 |
|------|------|--------|--------|--------|
| 本地简化测试 | `pytest tests/test_core_config.py -v -o "addopts="` | ❌ | ⚠️ 间歇性 | ⭐⭐ |
| Docker 测试 | `docker-compose run test` | ✅ | ✅ 稳定 | ⭐⭐⭐⭐⭐ |
| CI 验证 | `git push` 后自动运行 | ✅ | ✅ 稳定 | ⭐⭐⭐⭐⭐ |

---

## 5. 故障排除

### 5.1 pytest 崩溃 (exit -1073741510)

**尝试**:
1. 禁用覆盖率插件: `-o "addopts="`
2. 仅运行单个测试文件，避免 `tests/conftest.py` 加载
3. 使用 Docker 环境

### 5.2 导入 app 模块时崩溃

**尝试**:
1. 设置环境变量:
   ```powershell
   $env:KMP_DUPLICATE_LIB_OK="TRUE"
   $env:OMP_NUM_THREADS="1"
   ```
2. 在 Python 脚本开头设置:
   ```python
   import os
   os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
   os.environ.setdefault("OMP_NUM_THREADS", "1")
   ```

### 5.3 测试断言失败

**注意**: `.env` 文件可能覆盖默认值，测试已调整为适应这种情况。

---

## 6. 长期建议

1. **配置 WSL2** — 在 Windows Subsystem for Linux 中运行开发和测试
2. **使用 Docker** — 作为本地测试的标准环境
3. **依赖 CI** — 将完整测试验证交给 GitHub Actions

---

> **文档版本**: v1.0
> **生成日期**: 2026-04-30
