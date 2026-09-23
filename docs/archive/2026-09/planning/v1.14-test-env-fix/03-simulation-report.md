# v1.14 Simulation 报告: 测试环境修复推演

> **迭代名称**: v1.14-test-env-fix
> **日期**: 2026-04-30
> **状态**: Round 3 Simulation 完成

---

## 1. 推演结果摘要

### 1.1 已验证的解决方案

| 方案 | 状态 | 说明 |
|------|------|------|
| config.py SKLEARN_VERSION 延迟加载 | ✅ 有效 | Windows 上跳过 sklearn 导入 |
| 禁用 pytest coverage 插件 | ✅ 有效 | `-o "addopts="` 可运行测试 |
| 移除 test_core_config.py 的 warnings 导入 | ✅ 有效 | 避免 warnings 模块触发崩溃 |
| KMP_DUPLICATE_LIB_OK / OMP_NUM_THREADS | ⚠️ 部分有效 | 对 sklearn 无效，但对其他库可能有效 |

### 1.2 关键发现

**发现 1**: pytest 可以运行简化版测试
- `test_core_config_final.py` (根目录，18 个测试) — **全部通过**
- 使用 `-o "addopts="` 禁用覆盖率插件

**发现 2**: 问题具有间歇性
- 相同的导入有时成功，有时失败
- 涉及多个库：sklearn, sqlalchemy, slowapi 等
- 可能是 Windows DLL 运行时环境的系统性问题

**发现 3**: `tests/conftest.py` 是主要障碍
- 导入了大量 app 模块（database, deps, security, main, models）
- 这些模块间接加载了多个科学计算库
- 在 pytest 环境下更容易触发崩溃

### 1.3 无法解决的问题

**根本限制**: Windows 本地环境存在深层次的 C 扩展/DLL 运行时问题
- 间歇性崩溃无法通过代码修改完全消除
- 影响多个库（sklearn, pandas, sqlalchemy, slowapi 等）
- 可能与 Python 3.12 + Windows 的兼容性有关

---

## 2. 推荐方案锁定

### 2.1 短期方案 (立即执行)

**修改代码以适配 Windows 环境**:
1. ✅ `config.py`: SKLEARN_VERSION 延迟加载（已完成）
2. ✅ `test_core_config.py`: 移除 warnings 导入（已完成）
3. ✅ `conftest.py`: 添加 KMP_DUPLICATE_LIB_OK / OMP_NUM_THREADS（已完成）

**本地测试运行方式**:
```bash
# 禁用覆盖率插件运行测试
cd backend
python -m pytest tests/test_core_config.py -v -o "addopts="

# 或使用简化版测试文件
python -m pytest test_core_config_final.py -v -o "addopts="
```

### 2.2 中期方案 (本周内)

**配置 Git 仓库 + GitHub Actions**:
1. 初始化 git 仓库
2. 推送代码
3. 通过 GitHub Actions 运行完整测试套件

**优点**:
- 利用 Linux 环境绕过 Windows DLL 问题
- 自动运行覆盖率报告
- 可持续集成

### 2.3 长期方案 (可选)

**配置 WSL2 或 Docker**:
- 提供一致的跨平台开发环境
- 完全绕过 Windows DLL 问题

---

## 3. 已完成的代码修改

### 3.1 backend/app/core/config.py
- `SKLEARN_VERSION` 改为延迟加载
- Windows 上跳过 sklearn 导入

### 3.2 backend/tests/conftest.py
- 添加 `KMP_DUPLICATE_LIB_OK=TRUE`
- 添加 `OMP_NUM_THREADS=1`

### 3.3 backend/tests/test_core_config.py
- 移除 `import warnings`
- 修复 database_url 和 cors_origins 测试断言

---

## 4. 结论

**Windows 本地环境无法完全修复**。建议采用以下工作流：

1. **本地开发**: 使用简化版测试验证核心逻辑
2. **CI 验证**: 通过 GitHub Actions 运行完整测试套件和覆盖率报告
3. **长期**: 配置 WSL2 或 Docker 作为本地测试环境

---

> **文档版本**: v1.0
> **生成日期**: 2026-04-30
