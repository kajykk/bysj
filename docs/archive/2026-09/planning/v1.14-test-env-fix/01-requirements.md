# v1.14 需求文档: 测试环境修复与基础设施

> **迭代名称**: v1.14-test-env-fix
> **迭代目标**: 解决 Windows 本地测试环境问题，使 pytest 可以正常运行
> **日期**: 2026-04-30
> **状态**: Draft (Round 1)

---

## 1. 背景与问题陈述

### 1.1 当前问题
v1.13-coverage-sprint-40to60 的 Testing Phase 因环境限制完全阻塞：
- 运行任何导入 `app` 模块的测试时，进程退出返回 exit code -1073741510
- 根本原因是 `sklearn`、`pandas` 等科学计算库在 Windows 上的 DLL 初始化/卸载问题
- 已尝试的解决方案（延迟加载 SKLEARN_VERSION）部分缓解了模块导入问题，但进程退出时仍崩溃

### 1.3 已知解决方案 (Research 发现)
根据社区经验，以下环境变量可能解决 OpenMP/MKL DLL 冲突：
- `KMP_DUPLICATE_LIB_OK=TRUE` — 允许重复的 OpenMP 运行时库
- `OMP_NUM_THREADS=1` — 限制 OpenMP 线程数，防止失控线程
- 这些变量需要在 Python 进程启动前设置

### 1.2 影响
- 无法本地运行 pytest 验证测试代码
- 无法生成覆盖率报告
- 无法执行 05-test-plan.md 中的测试计划
- 开发-测试闭环断裂

---

## 2. 需求目标

### 2.1 主要目标 (Must Have)
- [ ] 修复 Windows 本地 pytest 运行问题
- [ ] 使 `pytest tests/test_core_config.py -v` 可以正常通过
- [ ] 使 `pytest tests/test_core_deps.py -v` 可以正常通过
- [ ] 进程退出时不再返回 -1073741510

### 2.2 次要目标 (Should Have)
- [ ] 配置 Git 仓库，支持代码版本管理和 CI 触发
- [ ] 配置 Docker 测试环境，提供跨平台一致性
- [ ] 更新文档，记录环境配置步骤

### 2.3 可选目标 (Nice to Have)
- [ ] 配置 pre-commit hooks，自动化代码检查
- [ ] 配置 VS Code 调试配置，支持测试调试

---

## 3. 技术方案选项

### 方案 A: 修复 sklearn/pandas Windows DLL 问题
**思路**: 通过环境变量、依赖降级或补丁修复 DLL 初始化问题
**优点**: 最直接，保持现有开发流程
**缺点**: 可能需要降级库版本，影响功能

### 方案 B: 配置 WSL2 环境
**思路**: 在 WSL2 (Windows Subsystem for Linux) 中运行测试
**优点**: 完全绕过 Windows DLL 问题，接近生产环境
**缺点**: 需要用户配置 WSL2，增加开发复杂度

### 方案 C: 配置 Docker 测试环境
**思路**: 添加 test 服务到 docker-compose.yml，在容器中运行 pytest
**优点**: 跨平台一致，隔离性好
**缺点**: 需要 Docker 安装，运行速度较慢

### 方案 D: 配置 Git + GitHub Actions
**思路**: 初始化 git 仓库，推送代码后通过 GitHub Actions 运行测试
**优点**: 利用云端资源，不依赖本地环境
**缺点**: 反馈循环较长，需要网络连接

---

## 4. 验收标准

1. `cd backend && pytest tests/test_core_config.py -v` 返回 exit code 0
2. `cd backend && pytest tests/test_core_deps.py -v` 返回 exit code 0
3. `cd backend && pytest tests/ -m unit --cov=app --cov-report=term-missing` 可以正常生成报告
4. 所有测试通过，无 -1073741510 错误

---

> **文档版本**: v1.0-Draft
> **最后更新**: 2026-04-30
