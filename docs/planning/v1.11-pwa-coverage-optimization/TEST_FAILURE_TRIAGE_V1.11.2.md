# Test Failure Triage v1.11.2

> **迭代**: v1.11.2-security-test-closure
> **日期**: 2026-04-30
> **基线**: v1.11.1 验证报告 (1397 测试 collected, 214 failed)
> **目标**: 对 214 个失败测试进行分类，明确处理策略

---

## 1. 分类方法论

### 1.1 分类维度

| 分类代码 | 说明 | 是否阻塞 | 处理策略 |
|---|---|---|---|
| ENV | 环境依赖缺失 (Redis/Postgres/Celery) | 否 | mock/配置文档 |
| DATA | 测试数据/fixture 问题 | 是 | 修复 fixture |
| LOGIC | 业务逻辑变更导致 | 是 | 修复测试或代码 |
| OUTDATED | 历史过期测试 | 否 | 标记跳过或删除 |
| FLAKY | 不稳定/时序相关 | 否 | 重试机制或重构 |
| IMPORT | 导入错误/循环依赖 | 是 | 修复导入路径 |
| CONFIG | 配置缺失或不匹配 | 是 | 更新配置 |
| SECURITY | 安全相关测试失败 | 是 | 优先修复 |

---

## 2. 失败测试分类结果

### 2.1 ENV (环境依赖) - 预估 ~120 个 (56%)

**特征**:
- 错误信息包含 `Connection refused`, `Cannot connect`, `No such host`
- 涉及 Redis、Postgres、Celery、外部 API

**典型错误**:
```
redis.exceptions.ConnectionError: Error connecting to localhost:6379
asyncpg.exceptions.CannotConnectError: connection refused
```

**处理策略**:
- [x] conftest.py 已配置 rate_limiter.enabled = False
- [x] health 测试已通过 mock 处理 Redis/Celery
- [ ] 部分服务测试仍需外部服务，建议标记 `pytest.mark.skipif`

---

### 2.2 DATA (测试数据) - 预估 ~40 个 (19%)

**特征**:
- 错误信息包含 `assert expected == actual`, `KeyError`, `AttributeError`
- 数据库状态不一致

**典型错误**:
```
AssertionError: assert 3 == 4
KeyError: 'risk_score'
```

**处理策略**:
- [ ] 检查 fixture 数据一致性
- [ ] 确保测试隔离性（事务回滚）
- [ ] 更新过期的测试数据期望

---

### 2.3 IMPORT (导入错误) - 预估 ~25 个 (12%)

**特征**:
- 错误信息包含 `ModuleNotFoundError`, `ImportError`
- 循环导入或路径问题

**典型错误**:
```
ModuleNotFoundError: No module named 'app.ml.bert'
ImportError: cannot import name 'X' from 'app.models'
```

**处理策略**:
- [x] conftest.py 已配置 sys.path
- [ ] 检查模型层导入顺序
- [ ] 使用 TYPE_CHECKING 避免循环导入

---

### 2.4 LOGIC (业务逻辑) - 预估 ~15 个 (7%)

**特征**:
- 代码变更导致测试期望不匹配
- 边界条件处理变化

**处理策略**:
- [ ] 审查相关代码变更
- [ ] 更新测试期望或修复代码

---

### 2.5 OUTDATED (历史过期) - 预估 ~10 个 (5%)

**特征**:
- 测试的功能已删除或重构
- 测试文件长期未更新

**处理策略**:
- [ ] 标记 `pytest.mark.skip` 并注明原因
- [ ] 或删除过期测试

---

### 2.6 FLAKY (不稳定) - 预估 ~4 个 (2%)

**特征**:
- 时序相关、异步竞争条件
- 随机失败

**处理策略**:
- [ ] 增加等待时间或重试机制
- [ ] 使用 asyncio 同步原语

---

## 3. Release Gate 测试集

### 3.1 核心测试 (不依赖外部服务)

以下测试文件**不依赖** Redis/Postgres/Celery/BERT，可作为 release gate：

| 测试文件 | 测试数 | 依赖 | 状态 |
|---|---|---|---|
| tests/test_core_health.py | 3 | 无 | ✅ 通过 |
| tests/test_core_modules.py | 32 | 无 | ✅ 通过 |
| tests/test_core_security.py | 14 | 无 | ✅ 通过 |
| tests/test_core_*_extended.py | 78 | mock | ✅ 通过 |
| tests/api/test_csp_report.py | 13 | 无 | ✅ 通过 |
| tests/api/test_auth_flow.py | 8 | SQLite | ✅ 通过 |

**Release Gate 总计**: ~148 个测试

### 3.2 排除的测试

以下测试需要外部服务，**不纳入** release gate：

| 测试文件 | 原因 |
|---|---|
| tests/ml/* | 需要 BERT/PyTorch |
| tests/integration/* | 需要完整服务栈 |
| tests/performance/* | 需要性能基准环境 |
| tests/degradation/* | 需要模型加载 |

---

## 4. 处理优先级

### P0 (立即处理)
1. [ ] DATA 类错误修复 (影响 release gate)
2. [ ] IMPORT 类错误修复 (阻塞测试收集)
3. [ ] LOGIC 类错误修复 (业务逻辑问题)

### P1 (本周处理)
4. [ ] ENV 类测试添加 skipif 标记
5. [ ] OUTDATED 测试清理

### P2 (后续迭代)
6. [ ] FLAKY 测试重构
7. [ ] 覆盖率提升到 40%

---

## 5. 结论

| 指标 | 数值 |
|---|---|
| 总失败测试 | 214 |
| ENV (环境依赖) | ~120 (56%) |
| DATA (测试数据) | ~40 (19%) |
| IMPORT (导入错误) | ~25 (12%) |
| LOGIC (业务逻辑) | ~15 (7%) |
| OUTDATED (历史过期) | ~10 (5%) |
| FLAKY (不稳定) | ~4 (2%) |
| Release Gate 可用测试 | ~148 |

**关键结论**:
1. 56% 的失败是环境依赖问题，可通过 mock/skipif 解决
2. Release gate 测试集 (~148 个) 可作为最小生产放行门槛
3. 19% 的数据问题需要修复 fixture
4. 12% 的导入错误需要梳理模块依赖

---

> **产出日期**: 2026-04-30
> **报告状态**: 已归档
> **下一步**: 按优先级修复 P0 问题，验证 release gate 通过
