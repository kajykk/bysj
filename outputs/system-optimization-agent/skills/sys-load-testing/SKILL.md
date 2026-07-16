---
name: sys-load-testing
description: >-
  This skill should be used when running load/performance tests — "压测",
  "建性能基线", "峰值压测", "稳定性压测", "容量评估". It implements §2.1
  and §5 of the optimization plan and feeds KPI baselines to other skills.
agent_created: true
---

# sys-load-testing

## 用途
通过压测建立/复测性能基线，量化吞吐、并发、响应时间与错误率，支撑优化前后对比。

## 何时使用
- WF-0 建基线、WF-1/2 验证优化、WF-3 定期回归。
- 用户要求「对核心接口压测」「出压测报告」。

## 执行流程
1. **定场景**：选取核心接口/链路，明确目标 KPI（P95/P99、QPS、并发、错误率）。
2. **基线压测**：稳态负载记录基线（`KPI-基线.json`）。
3. **峰值压测**：阶梯加压至拐点，找容量上限与瓶颈点。
4. **稳定性压测**：长时间中高负载，观察内存泄漏/资源漂移。
5. **前端压测**：`lighthouse` CI 取首屏/TTI/LCP；`vitest` 测渲染开销。
6. **产出报告**：优化前后对比、瓶颈点、是否达 §3 KPI。

## 工具与脚本
- 后端：`locust` / `k6` / `pytest-benchmark`。
- 前端：`lighthouse`（frontend 已有 `lighthouserc.json` 与基线 JSON）、`vitest`。
- 基线数据落 `outputs/` 或 `KPI-基线.json`。

## 验收与 KPI（§3）
- 核心链路吞吐 ↑50–100%，并发 ↑30–80%。
- 输出可比对的压测报告与趋势图。

## 与本工程栈的对应
- 前端已有 `lighthouse-baseline.json` / `lighthouse-prod.json` 可直接复用为基准。
- 后端压测需起服务（FastAPI `backend/app/main.py`）后施压。

## 注意事项
- 压测环境尽量贴近生产配置，否则数字失真。
- 峰值压测可能触发限流/熔断（见 `sys-reliability`），属预期行为。
