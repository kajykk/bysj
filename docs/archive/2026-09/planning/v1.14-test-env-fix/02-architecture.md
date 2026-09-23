# v1.14 架构设计: 测试环境修复与基础设施

> **迭代名称**: v1.14-test-env-fix
> **日期**: 2026-04-30
> **状态**: Draft (Round 1)

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    开发环境 (Windows)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ 本地 pytest  │  │ WSL2 pytest │  │ Docker pytest       │  │
│  │ (方案 A)     │  │ (方案 B)    │  │ (方案 C)            │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    CI 环境 (GitHub Actions)                   │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  coverage.yml (pytest --cov=app --cov-fail-under=60)   │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 方案详细设计

### 2.1 方案 A: 修复 Windows DLL 问题

**根因**: sklearn/pandas 依赖的 OpenMP/Intel MKL DLL 在 Windows 上初始化/卸载时崩溃

**修复策略**:
1. 设置环境变量 `KMP_DUPLICATE_LIB_OK=TRUE` 允许重复 OpenMP 库
2. 设置环境变量 `OMP_NUM_THREADS=1` 限制 OpenMP 线程数
3. 在 `conftest.py` 中添加进程退出清理钩子

**代码变更**:
- `backend/tests/conftest.py`: 添加 DLL 修复补丁
- `backend/pytest.ini`: 添加环境变量配置

**pytest.ini 配置示例**:
```ini
[pytest]
env =
    KMP_DUPLICATE_LIB_OK=TRUE
    OMP_NUM_THREADS=1
```

**conftest.py 补丁示例**:
```python
import os
import atexit

# Fix Windows DLL issues with sklearn/pandas
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

# Prevent aggressive cleanup that crashes on Windows
def _windows_cleanup():
    pass

atexit.register(_windows_cleanup)
```

### 2.2 方案 B: WSL2 环境

**配置步骤**:
1. 安装 WSL2 + Ubuntu
2. 在 WSL2 中安装 Python 依赖
3. 配置 VS Code Remote-WSL 扩展

**优点**: 一劳永逸，完全绕过 Windows DLL 问题

### 2.3 方案 C: Docker 测试环境

**docker-compose.yml 变更**:
```yaml
services:
  test:
    build:
      context: ./backend
      dockerfile: Dockerfile.test
    volumes:
      - ./backend:/app
    command: pytest tests/ -v --cov=app
    environment:
      - APP_ENV=test
      - DATABASE_URL=sqlite+aiosqlite:///./test.db
```

### 2.4 方案 D: Git + GitHub Actions

**配置步骤**:
1. 初始化 git 仓库: `git init`
2. 添加远程仓库: `git remote add origin <url>`
3. 配置 `.gitignore`
4. 推送代码触发 Actions

---

## 3. 推荐方案组合

**短期 (立即执行)**: 方案 A — 尝试修复 Windows DLL 问题
**中期 (本周内)**: 方案 D — 配置 Git 仓库，启用 CI 验证
**长期 (可选)**: 方案 C — 配置 Docker 测试环境

---

> **文档版本**: v1.0-Draft
> **最后更新**: 2026-04-30
