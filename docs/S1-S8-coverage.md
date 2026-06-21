# S1-S8 覆盖清单

## S1 认证与登录

### 已覆盖
- `backend/tests/api/test_auth_flow.py`
- `backend/tests/api/test_auth_p0p1.py`
- `backend/tests/api/test_auth_response_contract.py`
- `backend/tests/api/test_access_control_regression.py`
- `frontend/e2e/auth.spec.ts`
- `frontend/e2e/core-flows.spec.ts`

### 缺口
- 缺少端到端登录后 token 刷新与失效恢复的完整 UI 闭环
- 缺少后端与前端共享的统一 request_id 追踪样例

## S2 路由守卫 / 权限边界

### 已覆盖
- `backend/tests/api/test_routing_and_security_p0p1.py`
- `backend/tests/api/test_counselor_admin_invalid.py`
- `backend/tests/api/test_counselor_admin.py`
- `backend/tests/api/test_admin_counselor_writes.py`
- `frontend/e2e/auth.spec.ts`
- `frontend/e2e/core-flows.spec.ts`

### 缺口
- 管理员 / 咨询师 / 普通用户的前端权限回退页校验不足
- 缺少跨角色按钮级别权限约束检查

## S3 风险评估与风险报告

### 已覆盖
- `backend/tests/api/test_risk_export.py`
- `backend/tests/api/test_contract_and_closure.py`
- `backend/tests/api/test_p0_p1_regressions.py`
- `backend/tests/harness/scenarios/scenario_backend_smoke.py`
- `backend/tests/test_harness_integration.py`

### 缺口
- harness 中风险报告的步骤记录不足以直接定位单次失败点
- 缺少报告与真实请求标识的强关联

## S4 文本/生理数据输入与评估链路

### 已覆盖
- `backend/tests/api/test_invalid_params.py`
- `backend/tests/api/test_resilience_observability_and_security.py`
- `backend/tests/api/test_content_recommendation.py`
- `backend/tests/api/test_model_predict.py`
- `backend/tests/api/test_upload_security.py`

### 缺口
- 缺少将输入样本、模型输出、告警结果串成一个可追踪闭环的报告
- 缺少 E2E 层面对异常输入的交互反馈校验

## S5 干预计划 / 任务执行闭环

### 已覆盖
- `backend/tests/api/test_intervention_state_machine.py`
- `backend/tests/api/test_concurrency_conflicts.py`
- `backend/tests/harness/scenarios/scenario_backend_smoke.py`
- `backend/tests/harness/presets.py`
- `backend/tests/test_harness_integration.py`

### 缺口
- `task-flow` 需要在 Docker(PostgreSQL+Redis) 下稳定跑通
- 缺少 task 完成 / 跳过 / 冲突路径的步骤级快照

## S6 咨询师工作台 / 预约 / 记录

### 已覆盖
- `backend/tests/api/test_counselor_admin.py`
- `backend/tests/api/test_admin_counselor_writes.py`
- `backend/tests/api/test_websocket.py`
- `backend/tests/api/test_websocket_p0p1.py`

### 缺口
- 缺少咨询师 UI 闭环 E2E
- 缺少预约、备注、回访记录等流程的前端联动校验

## S7 管理后台 / 运维 / 配置 / 日志

### 已覆盖
- `backend/tests/api/test_health_and_admin_logs.py`
- `backend/tests/api/test_operation_logs_api.py`
- `backend/tests/api/test_resilience_observability_and_security.py`
- `backend/tests/api/test_contract_and_closure.py`

### 缺口
- 缺少管理员端完整 UI 闭环
- 缺少对后端测试报告、Playwright 报告的互链展示

## S8 贯通观测 / 审计 / 端到端闭环

### 已覆盖
- `backend/tests/api/test_request_id_audit.py`
- `backend/tests/api/test_access_control_regression.py`
- `backend/tests/api/test_resilience_observability_and_security.py`
- `frontend/e2e/harness.spec.ts`
- `frontend/e2e/core-flows.spec.ts`

### 缺口
- 需要统一 request_id 贯通到 harness、API 响应和 Markdown 报告
- 需要后端 `backend/test-artifacts` 与 `frontend/playwright-report` 的互链
- 需要把步骤记录与数据快照沉淀为稳定产物

## 结论

当前覆盖面已覆盖主要后端业务链路，但仍存在两个核心缺口：
1. `harness/task-flow` 的可执行性与可观测性不足
2. 前端三角色 E2E 闭环与后端报告互链不足

建议下一步优先保证 `task-flow` 可跑通，再补全 UI 闭环和报告互链。