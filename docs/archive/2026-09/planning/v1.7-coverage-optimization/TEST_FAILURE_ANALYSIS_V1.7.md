# v1.7 失败测试分析报告

> **迭代**: v1.7-backend-contract-coverage-hardening
> **日期**: 2026-04-29
> **状态**: 分析完成
> **来源**: v1.6 最终报告 + 代码扫描分析

---

## 1. 失败测试概览

| 指标 | 数值 |
|------|------|
| 总测试文件 | ~100 |
| 总测试函数 | ~300+ |
| 通过 (v1.6) | 161 |
| **失败 (v1.6)** | **30** |
| xfail 标记 | 0 |
| skip 标记 | 0 |

---

## 2. 失败测试分类

### 2.1 外部依赖类 (预计 ~12 个)

| 问题 | 影响文件 | 原因 |
|------|----------|------|
| Redis 未运行 | test_core_health.py, test_resilience_*.py | check_redis 连接失败 |
| Celery 未运行 | test_core_health.py, test_alert_*.py | check_celery_worker 连接失败 |
| SMTP/邮件服务 | test_auth_flow.py, test_auth_p0p1.py | request-reset 需要邮件服务 |
| PostgreSQL 特定 | smoke_real_postgres.py | 需要真实 PostgreSQL |
| PyTorch 模型加载 | test_train_*.py, test_pytorch_*.py | 模型文件/依赖缺失 |

**处理策略**: 
- 使用 mock/patch 替代真实连接
- 对无法 mock 的添加 `pytest.mark.skip(reason="...")`

### 2.2 Fixture/Mock 类 (预计 ~8 个)

| 问题 | 影响文件 | 原因 |
|------|----------|------|
| 异步 fixture 兼容 | test_auth_service.py | async db_session 与 sync 测试混用 |
| 依赖覆盖冲突 | test_auth_p0p1.py | app.dependency_overrides 未清理 |
| 密码哈希不匹配 | test_auth_service.py | seed 用户 password_hash='x' |
| 状态码不一致 | test_auth_flow.py | 实现返回 400 vs 测试期望 409 |

**处理策略**:
- 修复 fixture 作用域和清理逻辑
- 统一状态码预期

### 2.3 真实业务缺陷类 (预计 ~6 个)

| 问题 | 影响文件 | 原因 |
|------|----------|------|
| 响应结构不一致 | test_auth_flow.py | code 字段位置变化 |
| 端点路径变更 | test_user_warning.py | API 路径调整 |
| 权限检查缺失 | test_counselor_admin.py | admin 接口未正确鉴权 |

**处理策略**:
- 修复后端实现
- 或更新测试预期（如设计变更）

### 2.4 环境问题类 (预计 ~4 个)

| 问题 | 影响文件 | 原因 |
|------|----------|------|
| 文件路径问题 | test_excel_export_service.py | Windows/Linux 路径差异 |
| 时区问题 | test_model_monitor.py | 时间比较精度 |
| 并发问题 | test_canary_*.py | 测试间状态污染 |

**处理策略**:
- 使用 `xfail` 标记并记录原因

---

## 3. 修复优先级

| 优先级 | 类别 | 数量 | 处理方式 |
|--------|------|------|----------|
| P0 | Fixture/Mock | ~8 | 立即修复 |
| P0 | 外部依赖 (主路径) | ~5 | mock 或 skip |
| P1 | 真实业务缺陷 | ~6 | 修复实现或更新测试 |
| P1 | 外部依赖 (边缘) | ~7 | xfail 或 skip |
| P2 | 环境问题 | ~4 | xfail |

---

## 4. 具体处理计划

### T-FIX-002: 修复环境/fixture/mock 问题

- [ ] 修复 test_auth_service.py: async db_session 兼容
- [ ] 修复 test_auth_p0p1.py: dependency_overrides 清理
- [ ] 修复 test_auth_flow.py: 状态码统一 (400 vs 409)
- [ ] mock Redis/Celery/SMTP 在主路径测试中

### T-FIX-003: 修复真实业务缺陷

- [ ] 检查 auth 响应结构一致性
- [ ] 检查 admin 接口鉴权
- [ ] 检查 user_warning 端点路径

### T-FIX-004: 隔离短期无法修复的测试

- [ ] 对 PyTorch 模型训练测试添加 skip
- [ ] 对真实 PostgreSQL 测试添加 skip
- [ ] 对并发/时区问题添加 xfail

---

## 5. 关键发现

### 5.1 conftest.py 现状

- 使用 SQLite + aiosqlite 作为测试数据库
- 已配置 `override_db_dependency` 和 `override_user_dependency`
- `rate_limiter.enabled = False` 已禁用
- **问题**: `asyncio.run()` 在 fixture 中混用可能导致事件循环冲突

### 5.2 测试模式问题

- 部分测试使用 sync `TestClient` 调用 async 端点（正确）
- 部分测试直接调用 async service 函数但缺少 `@pytest.mark.asyncio`（可能失败）
- `app.dependency_overrides` 在测试中手动修改但未在 finally 中清理（test_auth_p0p1.py 已处理，但其他文件可能未处理）

### 5.3 外部服务依赖

- **Redis**: tests/test_core_health.py, tests/test_resilience_*.py
- **Celery**: tests/test_core_health.py, tests/test_alert_*.py
- **SMTP**: tests/api/test_auth_flow.py (request-reset)
- **PostgreSQL**: tests/smoke_real_postgres.py

---

> **文档状态**: 已产出
> **下一步**: T-FIX-002 (修复环境/fixture/mock 问题)
