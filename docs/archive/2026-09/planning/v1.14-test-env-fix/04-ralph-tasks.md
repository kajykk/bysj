# 04-Ralph 任务列表 (Ralph Tasks)

> **迭代名称**: v1.14-test-env-fix
> **迭代目标**: 解决 Windows 本地测试环境问题，使 pytest 可以正常运行
> **日期**: 2026-04-30
> **状态**: Draft (Round 1)

---

## Phase 1: Windows DLL 问题修复 (方案 A)

### 1.1 环境变量修复
- [ ] **1.1.1 设置 OpenMP 环境变量**
    - [ ] 设置 `KMP_DUPLICATE_LIB_OK=TRUE`
    - [ ] 设置 `OMP_NUM_THREADS=1`
    - [ ] 验证 pytest 是否仍崩溃

### 1.2 conftest.py 补丁
- [ ] **1.2.1 添加进程退出清理钩子**
    - [ ] 在 `backend/tests/conftest.py` 中添加 `atexit` 清理
    - [ ] 禁用 sklearn/pandas 的激进清理行为
    - [ ] 验证 pytest 是否仍崩溃

### 1.3 pytest.ini 配置
- [ ] **1.3.1 添加 pytest 环境配置**
    - [ ] 配置 `env` 插件环境变量
    - [ ] 配置 `-p no:cacheprovider` 避免缓存问题
    - [ ] 验证 pytest 是否仍崩溃

---

## Phase 2: Git 仓库配置 (方案 D)

### 2.1 Git 初始化
- [ ] **2.1.1 初始化本地仓库**
    - [ ] `git init`
    - [ ] 配置 `.gitignore` (排除 .venv, __pycache__, 上传文件等)
    - [ ] 配置 `README.md`

### 2.2 首次提交
- [ ] **2.2.1 提交 v1.13 交付物**
    - [ ] `git add backend/tests/test_core_config.py`
    - [ ] `git add backend/tests/test_core_deps.py`
    - [ ] `git add .github/workflows/coverage.yml`
    - [ ] `git add backend/app/core/config.py` (SKLEARN_VERSION 修复)
    - [ ] `git commit -m "test(v1.13): add core tests and raise coverage threshold"`

### 2.3 远程仓库配置 (如适用)
- [ ] **2.3.1 关联远程仓库**
    - [ ] `git remote add origin <user-repo-url>`
    - [ ] `git push origin main`
    - [ ] 验证 GitHub Actions 是否触发

---

## Phase 3: Docker 测试环境 (方案 C, 可选)

### 3.1 Dockerfile.test
- [ ] **3.1.1 创建测试 Dockerfile**
    - [ ] 基于 `python:3.12-slim`
    - [ ] 安装系统依赖 (gcc, libpq-dev)
    - [ ] 安装 Python 依赖
    - [ ] 配置测试入口点

### 3.2 docker-compose.yml 更新
- [ ] **3.2.1 添加 test 服务**
    - [ ] 配置 test 服务
    - [ ] 配置 volume 挂载
    - [ ] 验证 `docker-compose run test` 可以运行 pytest

---

## Phase 4: 验证与文档

### 4.1 测试验证
- [ ] **4.1.1 运行核心测试**
    - [ ] `pytest tests/test_core_config.py -v` 通过
    - [ ] `pytest tests/test_core_deps.py -v` 通过
    - [ ] `pytest tests/ -m unit --cov=app --cov-report=term` 通过

### 4.2 文档更新
- [ ] **4.2.1 更新环境配置文档**
    - [ ] 记录 Windows 开发环境配置步骤
    - [ ] 记录已知问题和解决方案
    - [ ] 更新 `docs/planning/v1.14-test-env-fix/DELIVERY_REPORT.md`

---

> **文档版本**: v1.0-Draft
> **最后更新**: 2026-04-30
