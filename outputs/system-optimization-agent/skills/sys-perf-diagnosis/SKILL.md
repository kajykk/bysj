---
name: sys-perf-diagnosis
description: >-
  This skill should be used when diagnosing performance and request-chain
  bottlenecks — "核心接口慢", "做性能诊断", "链路瓶颈在哪", "P95 高".
  It covers baseline measurement, slow interface/SQL location, and 5-Why
  root-cause analysis for the §2 assessment and §4.1 link optimization.
agent_created: true
---

# sys-perf-diagnosis

## 用途
定位性能瓶颈并执行 5-Why 根因分析，为后续 db/cache/reliability 等技能提供决策依据。

## 何时使用
- 用户报告接口慢、超时、峰值时延高。
- WF-0 基线评估或 WF-1/WF-2 优化前后对比。

## 执行流程
1. **界定范围**：列出核心接口与核心链路（参考架构图 / `backend/app/api/v1/`）。
2. **采集指标**：P50/P95/P99、QPS/TPS、并发、错误率；前端用 Lighthouse 取首屏与 TTI。
3. **链路切片**：前后端耗时分布、DB 耗时、外部调用耗时。
4. **瓶颈定位**：
   - 后端：开启 SQLAlchemy `echo`/慢查询日志；用 `py-spy`/`cProfile` 抓热点函数；看 Sentry 事务。
   - 前端：`lighthouse`、`performance` 面板、长任务、`any` 滥用（本工程已有 361 处）。
5. **5-Why 根因**：是哪里慢 → 为什么慢 → 为什么阻塞 → 为什么没提前发现 → 为什么没机制化。
6. **产出清单**：慢接口/慢 SQL/阻塞点，标注优先级，交给 `sys-db-optimizer` / `sys-cache-optimizer`。

## 工具与脚本
- 后端：`py-spy top`、`cProfile`、SQLAlchemy `echo=True`、Sentry 事务。
- 前端：`npx lighthouse`、`vitest`、浏览器 performance。
- 压测见 `sys-load-testing`。

## 验收与 KPI（§3）
- 关键接口 P95 ↓30–60%，P99 ↓20–50%。
- 输出「瓶颈清单 + 5-Why 结论」。

## 与本工程栈的对应
- API 路由集中在 `backend/app/api/v1/`；ML 推理路径经 `app/core/model_engine_predict`（已做延迟导入优化）。
- 前端 `any` 类型 361 处是潜在重渲染/类型风险点，纳入诊断。

## 注意事项
- 诊断先于优化，禁止凭感觉改代码。
- 结论必须可量化（带具体数字与对比）。
