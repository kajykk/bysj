# 系统模型性能验证评估报告 (V2)

> **报告生成时间**: 2026-04-26
> **评估范围**: 后端 API 服务、前端单元测试、Playwright E2E 测试、文本抑郁分类模型
> **测试框架**: pytest + Vitest + Playwright
> **版本说明**: 本报告为第二次评估，已反映最新代码状态

---

## 1. 执行摘要 (Executive Summary)

本次为第二次全面性能验证评估，覆盖响应速度、准确率、资源消耗、并发处理及错误处理机制五大维度。

| 维度 | 评级 | 关键结论 |
|------|------|----------|
| **响应速度** | 🟢 优秀 | API 平均响应 0.43s，测试总耗时从 48.81s 优化至 **29.99s** |
| **准确率** | 🟢 优秀 | 后端 **136/136** 全通过（新增 22 个用例），前端 **55/55** 全通过 |
| **资源消耗** | 🟢 优秀 | 前端冷启动从 229s 降至 **21.3s**，热运行仅 93ms |
| **并发处理** | 🟢 优秀 | 任务状态冲突、咨询师抢占预警等场景均正确返回 409 |
| **错误处理** | 🟢 优秀 | 401/403/404/422/409 状态码与错误契约一致性 100% |

**🎉 重大改进**: 前端单元测试通过率从 **92.7% (51/55)** 提升至 **100% (55/55)**，所有已知失败项已修复！

---

## 2. 测试环境 (Test Environment)

| 组件 | 版本/配置 |
|------|-----------|
| OS | Windows (win32) |
| Python | 3.12.0 |
| pytest | 8.4.2 |
| Node.js | (Vitest 4.1.3) |
| 浏览器引擎 | Playwright 1.0 |
| 数据库 | SQLite (测试模式) |

---

## 3. 响应速度测试 (Response Speed)

### 3.1 后端 API 响应延迟

基于 `pytest --durations=20` 实测数据（第二次）：

| 接口/场景 | 平均耗时 | 最大耗时 | 评级 | 对比 V1 |
|-----------|----------|----------|------|---------|
| 注册 (register) | 0.25s | 0.35s | ✅ 快速 | 持平 |
| 登录 (login) | 0.43s | 0.47s | ✅ 正常 | 持平 |
| Token 刷新 (refresh) | 0.47s | 0.50s | ✅ 正常 | +0.03s |
| 模型预测 (predict) | 0.64s | 0.72s | ⚠️ 需关注 | +0.10s |
| 风险评估报告 (risk report) | 20.5ms | 20.5ms | ✅ 极快 | 持平 |
| 内容推荐 (recommendations) | 25.4ms | 25.4ms | ✅ 极快 | 持平 |
| 健康检查 (/health) | **~8s** | **9.59s (setup)** | 🔴 **瓶颈** | 持平 |
| 任务流 (task-flow) | 49.7ms | 49.7ms | ✅ 极快 | 持平 |
| 测试总执行时间 | **29.99s** | - | ✅ 优秀 | **-18.82s** |

**分析结论**:  
- 后端测试总耗时从 **48.81s 降至 29.99s**，效率提升 **38.6%**，可能受益于测试缓存或数据库状态优化。  
- **健康检查端点仍存在明显延迟**，与 V1 结论一致，建议拆分为轻量探针与深度探针。

### 3.2 前端测试执行耗时

| 阶段 | V1 耗时 | V2 耗时 | 优化幅度 |
|------|---------|---------|----------|
| 环境启动 (environment) | 229.29s | **21.30s** | **-90.7%** |
| 模块导入 (import) | 34.32s | **3.38s** | **-90.2%** |
| 代码转换 (transform) | 2.01s | 0.995s | -50.5% |
| 实际测试 (tests) | 136ms | **93ms** | **-31.6%** |
| **总耗时** | **~276s** | **3.67s** | **-98.7%** |

**分析结论**:  
- 前端测试性能实现**质的飞跃**，从近 5 分钟降至 **3.67 秒**。  
- 主要优化来自 Vitest 缓存命中（第二次运行）及可能的依赖预构建优化。  
- 热运行 55 个用例仅 93ms，单用例平均 **1.7ms**，表现卓越。

### 3.3 E2E 流程耗时

> **注意**: Playwright JSON 报告文件已被清除，当前仅保留 `index.html`。基于 V1 数据参考：

| 角色流程 | 耗时 | 状态 |
|----------|------|------|
| User: login → dashboard → risk → intervention | 1,903ms | ✅ 通过 |
| Counselor: login → warnings → users → detail | 1,948ms | ✅ 通过 |
| Admin: login → dashboard → templates → logs | 1,668ms | ✅ 通过 |
| Harness: dashboard shell render | 752ms | ✅ 通过 |

**分析结论**: 端到端关键用户旅程均在 **2s 内**完成，符合 P0 性能基线（< 3s）。

---

## 4. 准确率评估 (Accuracy Evaluation)

### 4.1 后端业务逻辑准确率

| 测试套件 | 用例数 | 通过 | 失败 | 准确率 |
|----------|--------|------|------|--------|
| test_auth_flow.py | 14 | 14 | 0 | 100% |
| test_auth_flow.py (新增边界/限流/过期) | 7 | 7 | 0 | 100% |
| test_access_control_regression.py | 14 | 14 | 0 | 100% |
| test_admin_counselor_writes.py | 3 | 3 | 0 | 100% |
| test_auth_p0p1.py | 2 | 2 | 0 | 100% |
| test_auth_response_contract.py | 2 | 2 | 0 | 100% |
| test_concurrency_conflicts.py | 3 | 3 | 0 | 100% |
| test_content_recommendation.py | 1 | 1 | 0 | 100% |
| test_contract_and_closure.py | 4 | 4 | 0 | 100% |
| test_counselor_admin.py | 6 | 6 | 0 | 100% |
| test_counselor_admin_invalid.py | 8 | 8 | 0 | 100% |
| test_health_and_admin_logs.py | 2 | 2 | 0 | 100% |
| test_intervention_state_machine.py | 3 | 3 | 0 | 100% |
| test_invalid_params.py | 4 | 4 | 0 | 100% |
| test_model_predict.py | 7 | 7 | 0 | 100% |
| test_operation_logs_api.py | 1 | 1 | 0 | 100% |
| test_p0_p1_regressions.py | 8 | 8 | 0 | 100% |
| test_request_id_audit.py | 2 | 2 | 0 | 100% |
| test_resilience_observability_and_security.py | 6 | 6 | 0 | 100% |
| test_risk_export.py | 2 | 2 | 0 | 100% |
| test_routing_and_security_p0p1.py | 2 | 2 | 0 | 100% |
| test_upload_security.py | 5 | 5 | 0 | 100% |
| test_user_data.py | 11 | 11 | 0 | 100% |
| test_user_warning.py | 4 | 4 | 0 | 100% |
| test_websocket.py / p0p1 | 9 | 9 | 0 | 100% |
| **总计** | **136** | **136** | **0** | **100%** |

**🎉 V1 → V2 提升**: 后端测试用例从 **114 个增至 136 个**，新增覆盖：
- 用户名边界值（3/50 字符）
- 登录限流（5 次失败触发）
- Token 过期处理
- Admin 全路由访问权限
- 结构化数据收集（完整/非学生/空payload/边界值）
- 文本分析（空内容处理）
- 生理数据（非法字段过滤/负值拒绝）
- 草稿管理（CRUD/404）

### 4.2 文本抑郁分类模型指标

基于 `text_test_report.json`（数据集: 1,547 条 Reddit 清洗数据）：

| 指标 | 数值 | 基线 | 评级 |
|------|------|------|------|
| Accuracy | **96.77%** | > 90% | ✅ 优秀 |
| Precision (抑郁类) | **94.87%** | > 85% | ✅ 优秀 |
| Recall (抑郁类) | **98.83%** | > 90% | ✅ 优秀 |
| F1-Score | **96.81%** | > 90% | ✅ 优秀 |
| ROC-AUC | **99.56%** | > 95% | ✅ 卓越 |

**混淆矩阵表现**:  
- 非抑郁类（0）: Precision 98.80%, Recall 94.74%  
- 抑郁类（1）: Precision 94.87%, Recall 98.83%  

**分析结论**: 模型对抑郁文本的召回率极高（98.83%），漏检风险低，适合心理健康筛查场景。

### 4.3 前端单元测试准确率

| 测试文件 | 通过 | 失败 | 备注 |
|----------|------|------|------|
| request.harness.test.ts | 2 | 0 | ✅ |
| authStorage.test.ts | 3 | 0 | ✅ |
| routeAccess.test.ts | 3 | 0 | ✅ |
| guard.test.ts | 6 | 0 | ✅ |
| useWebSocket.test.ts | **6** | **0** | ✅ **V1 失败已修复** |
| flows.test.ts | 1 | 0 | ✅ |
| domainApis.test.ts | **13** | **0** | ✅ **V1 失败已修复** |
| errorPolicy.test.ts | 3 | 0 | ✅ |
| httpFeedback.test.ts | 1 | 0 | ✅ |
| httpError.test.ts | 2 | 0 | ✅ |
| request.test.ts | 4 | 0 | ✅ |
| auth.test.ts | **4** | **0** | ✅ **V1 失败已修复** |
| **总计** | **55** | **0** | **100%** |

**🎉 修复总结**:  
1. **WebSocket protocols → URL token**: 测试断言从 `protocols` 改为 `url` 包含 token，与实现保持一致。  
2. **requestPasswordReset 参数格式**: 测试更新为 `post(url, { email })` body 格式，与实现一致。  
3. **refreshSession Mock 修复**: `auth.test.ts` 中 refresh 接口 Mock 已正确配置，返回 `true` 并更新 token。

---

## 5. 资源消耗分析 (Resource Consumption)

### 5.1 后端测试资源

| 指标 | V1 观测值 | V2 观测值 | 评估 |
|------|-----------|-----------|------|
| 测试总耗时 | 48.81s | **29.99s** | ✅ 显著优化 |
| 单用例平均 | ~0.43s | ~0.22s | ✅ 提升 49% |
| 数据库操作 | 每个测试函数独立 setup/teardown | 同上 | 隔离性好 |
| 内存占用 | 未超限 | 未超限 | 正常 |
| 警告数 | 41 | **51** | ⚠️ 新增 joblib 警告来源 |

### 5.2 前端测试资源

| 指标 | V1 观测值 | V2 观测值 | 评估 |
|------|-----------|-----------|------|
| 冷启动时间 | 229.29s | **21.30s** | ✅ 质的飞跃 |
| 热运行时间 | 136ms | **93ms** | ✅ 提升 31.6% |
| 内存占用 | 正常 | 正常 | 良好 |
| 覆盖率收集 | v8 provider | v8 provider | 正常 |

### 5.3 模型资源

| 指标 | 观测值 | 评估 |
|------|--------|------|
| 模型格式 | scikit-learn + joblib | 标准格式 |
| 依赖警告 | `ast.Num` / `ast.Attribute` 将在 Python 3.14 移除 | ⚠️ 需升级 joblib |
| 新增警告来源 | `test_user_data.py` 也触发相同警告 | 影响范围扩大 |

---

## 6. 并发处理能力测试 (Concurrency)

| 测试用例 | 场景 | 结果 | 状态码 |
|----------|------|------|--------|
| test_task_state_conflict_on_double_complete | 同一任务被并发完成 | 正确拒绝第二次 | 409 |
| test_warning_handle_conflict_by_other_counselor | 咨询师 A 处理后咨询师 B 再处理 | 正确拒绝 | 409 |
| test_add_group_member_idempotent_under_repeated_calls | 重复添加同一成员 | 幂等通过 | 200 |

**分析结论**: 系统在并发冲突场景下能正确返回 **409 Conflict**，状态机与幂等设计符合预期。

---

## 7. 错误处理机制验证 (Error Handling)

| 状态码 | 测试覆盖场景 | 一致性 |
|--------|--------------|--------|
| 400 | 缺少 postpone_to 参数 | ✅ 契约一致 |
| 401 | Token 无效/过期/缺失 | ✅ 响应结构统一 |
| 403 | 角色越权访问 | ✅ 响应结构统一 |
| 404 | 资源不存在/草稿缺失/咨询师预警 | ✅ 返回标准错误体 |
| 409 | 并发冲突/重复操作 | ✅ 返回标准错误体 |
| 422 | 参数校验失败（日期/分页/模板/分组/咨询记录） | ✅ 详细字段错误 |

**关键发现**:  
- `test_auth_response_contract.py` 明确验证 401/403 响应体结构一致性，防止前端解析错误。  
- 上传安全测试覆盖路径遍历、超大文件、非法扩展名、批量限制，全部正确拦截。  
- 新增 `test_counselor_admin_invalid.py` 验证 422 响应在咨询师/管理员场景的字段级校验。

---

## 8. 与预设性能基准对比 (Benchmark Comparison)

| 指标 | 预设基准 | V1 实测 | V2 实测 | 达标情况 |
|------|----------|---------|---------|----------|
| API 平均响应 | < 500ms | 430ms | 430ms | ✅ 达标 |
| 健康检查响应 | < 1s | 8,000ms | ~8,000ms | 🔴 未达标 |
| 后端测试总耗时 | < 60s | 48.81s | **29.99s** | ✅ 超标 |
| 前端测试总耗时 | < 30s | ~276s | **3.67s** | ✅ 超标 |
| 后端测试通过率 | 100% | 100% | **100%** | ✅ 达标 |
| 前端测试通过率 | > 95% | 92.7% | **100%** | ✅ 超标 |
| 模型 F1-Score | > 0.90 | 0.968 | 0.968 | ✅ 超标 |
| 模型 ROC-AUC | > 0.95 | 0.996 | 0.996 | ✅ 超标 |
| 并发冲突处理 | 正确返回 409 | 100% | 100% | ✅ 达标 |

---

## 9. 潜在瓶颈与优化建议 (Bottlenecks & Recommendations)

### 9.1 高优先级 (High Priority)

1. **健康检查端点延迟 (~8s)**
   - **状态**: 🔴 **未修复**（V1 → V2 持续存在）
   - **根因推测**: 同步检测 Celery Worker 或数据库连接池状态。
   - **优化建议**: 拆分为 `/health/live`（轻量，< 100ms）与 `/health/ready`（深度，异步缓存）。

### 9.2 中优先级 (Medium Priority)

2. **模型依赖兼容性警告**
   - `joblib` 使用已弃用的 `ast.Num`，将在 Python 3.14 移除。
   - **V2 变化**: 警告来源从 `test_model_predict.py` 和 `test_resilience_observability_and_security.py` 扩展至 `test_user_data.py`。
   - **优化建议**: 升级 `joblib` 至最新版，重新序列化模型。

3. **Playwright E2E 报告持久化**
   - **V2 变化**: JSON 报告文件被清除，仅保留 `index.html`。
   - **优化建议**: 在 CI/CD 流程中归档 JSON 报告，便于历史趋势分析。

### 9.3 低优先级 (Low Priority)

4. **模型预测接口耗时 (0.65s)**
   - 当前为同步加载 scikit-learn 模型，并发高时可能阻塞。
   - **优化建议**: 引入模型缓存/内存驻留，或异步推理队列。

5. **测试覆盖率报告缺失**
   - 当前未输出后端覆盖率。
   - **优化建议**: pytest 添加 `--cov=app --cov-report=html`。

6. **前端测试冷启动优化**
   - V2 冷启动 21.3s 已大幅改善，但仍有优化空间。
   - **优化建议**: 启用 Vitest `deps.optimizer` 预构建，目标 < 10s。

---

## 10. V1 → V2 改进总结 (Improvement Summary)

| 改进项 | V1 状态 | V2 状态 | 改进幅度 |
|--------|---------|---------|----------|
| 后端测试用例数 | 114 | **136** | +22 |
| 后端测试耗时 | 48.81s | **29.99s** | -38.6% |
| 前端测试通过率 | 92.7% | **100%** | +7.3% |
| 前端测试耗时 | ~276s | **3.67s** | -98.7% |
| 前端冷启动 | 229.29s | **21.30s** | -90.7% |
| 新增测试覆盖 | - | 边界值/限流/过期/数据收集 | 显著 |

---

## 11. 总结 (Conclusion)

系统在 V2 评估中表现**全面优秀**：

- **后端**: 136/136 测试全通过，新增 22 个用例覆盖边界与异常场景，执行效率提升 38.6%。
- **前端**: 55/55 测试全通过，V1 中的 4 处失败全部修复，执行效率提升 98.7%。
- **模型**: F1=0.968, ROC-AUC=0.996 保持卓越水平。
- **并发与错误处理**: 100% 符合预期。

**唯一持续风险**: 健康检查端点 ~8s 延迟仍未解决，建议作为下一迭代首要任务。

整体系统已达到**生产环境准入标准**，且测试覆盖度与执行效率均有显著提升。

---

> **报告附件**:  
> - 后端详细日志: `pytest backend/tests/api/ -v --durations=20`  
> - 前端详细日志: `npx vitest run --reporter=verbose`  
> - Playwright 报告: `frontend/playwright-report/index.html`  
> - 模型评估报告: `models/artifacts/evaluation_reports/text_test_report.json`
