# 05-测试计划 (Test Plan)

> **迭代名称**: v1.14-test-env-fix
> **迭代目标**: 解决 Windows 本地测试环境问题
> **日期**: 2026-04-30
> **状态**: Draft (Round 1)

---

## 测试策略

本次迭代的测试目标不是测试业务功能，而是**验证测试环境本身**是否正常工作。

---

## 测试用例

### TC-ENV-001: pytest 基本功能
- **目标**: 验证 pytest 可以正常运行
- **步骤**:
  1. `cd backend`
  2. `python -m pytest --version`
- **预期**: 显示 pytest 版本，exit code 0

### TC-ENV-002: 空测试通过
- **目标**: 验证 pytest 可以运行空测试
- **步骤**:
  1. `cd backend`
  2. `python -m pytest tests/test_core_config.py::TestSettingsDefaults::test_default_app_name -v`
- **预期**: 测试通过，exit code 0

### TC-ENV-003: config 模块导入
- **目标**: 验证 app.core.config 可以正常导入
- **步骤**:
  1. `cd backend`
  2. `python -c "from app.core.config import Settings; s = Settings(); print(s.app_name)"`
- **预期**: 输出 "Depression Warning System"，exit code 0

### TC-ENV-004: 完整测试套件
- **目标**: 验证所有核心测试可以通过
- **步骤**:
  1. `cd backend`
  2. `python -m pytest tests/test_core_config.py tests/test_core_deps.py -v`
- **预期**: 所有测试通过，exit code 0

### TC-ENV-005: 覆盖率报告生成
- **目标**: 验证覆盖率报告可以正常生成
- **步骤**:
  1. `cd backend`
  2. `python -m pytest tests/test_core_config.py --cov=app.core.config --cov-report=term-missing`
- **预期**: 生成覆盖率报告，exit code 0

### TC-ENV-006: 进程退出码
- **目标**: 验证进程退出码正常
- **步骤**:
  1. `cd backend`
  2. `python -m pytest tests/test_core_config.py -q`
  3. `echo %ERRORLEVEL%`
- **预期**: ERRORLEVEL 为 0，不是 -1073741510

---

## 验收标准

- [ ] TC-ENV-001 通过
- [ ] TC-ENV-002 通过
- [ ] TC-ENV-003 通过
- [ ] TC-ENV-004 通过
- [ ] TC-ENV-005 通过
- [ ] TC-ENV-006 通过

---

> **文档版本**: v1.0-Draft
> **最后更新**: 2026-04-30
