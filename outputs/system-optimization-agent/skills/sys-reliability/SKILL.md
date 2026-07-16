---
name: sys-reliability
description: >-
  This skill should be used when hardening service stability and fault
  tolerance — "熔断", "限流", "降级", "超时", "高可用", "消除单点".
  It implements §4.3 of the optimization plan.
agent_created: true
---

# sys-reliability

## 用途
引入容错设计、消除单点、提升可用性与故障恢复能力（MTTR↓）。

## 何时使用
- 用户要求「加限流/熔断/降级」「做超时控制」「高可用架构」。
- WF-1 止血、WF-2 故障隔离。

## 执行流程
1. **超时控制**：为所有外部/DB 调用设合理超时，快速失败（fail-fast）。
2. **限流**：入口限流（令牌桶/漏桶），保护核心资源（slowapi / limits）。
3. **熔断**：依赖不稳定时熔断，避免雪崩（CircuitBreaker 模式）。
4. **降级**：非核心功能降级返回兜底，保证核心链路可用。
5. **重试退避**：外部调用加指数退避 + 抖动，防止重试风暴。
6. **依赖隔离**：关键依赖线程池/连接隔离，单依赖故障不拖垮全局。
7. **高可用**：多实例 + 健康检查 + 负载均衡 + 故障切换；核心数据备份与恢复演练。
8. **验证**：用 `sys-load-testing` + 故障注入验证降级/恢复，MTTR↓50%。

## 工具与脚本
- 限流：`slowapi` / `limits`。
- 重试：`tenacity`。
- 熔断：`pybreaker` / 自实现 CircuitBreaker。
- 健康检查：FastAPI `/healthz`、`/readyz`；k8s 探针。

## 验收与 KPI（§3）
- 5xx 错误率 <0.1%，可用性 ≥99.9%（核心 ≥99.95%）。
- MTTR ↓50%；关键依赖故障可自动降级/隔离。

## 与本工程栈的对应
- 中间件在 `backend/app/middleware`；路由在 `backend/app/api/v1/`。
- 外部依赖（ML 推理、第三方）是熔断/隔离重点。

## 注意事项
- 限流/熔断阈值须压测校准，避免误杀正常流量。
- 降级兜底须保证数据一致性可接受，关键写操作慎用降级。
