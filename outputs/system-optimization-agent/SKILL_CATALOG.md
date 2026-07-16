# 技能注册表（Skill Catalog）

> 12 个 CodeBuddy 技能，覆盖《系统优化总体计划》全部优化手段。每个技能对应一个 `skills/<name>/SKILL.md`。
> 触发条件（description）采用第三人称描述，供 CodeBuddy 自动匹配；KPI 取自计划 §3；工具取自本工程真实技术栈。

| # | 技能名 | 对应计划 | 触发场景（示例用户表述） | 关键 KPI（§3） | 本工程可用工具 |
|---|---|---|---|---|---|
| 1 | `sys-optimization-orchestrator` | 全局 | “按优化计划推进”“开始系统优化” | 四阶段全部 Gate 通过 | 本目录 workflows.json、各技能 |
| 2 | `sys-perf-diagnosis` | §2, §4.1 | “核心接口慢”“做性能诊断”“链路瓶颈” | P95↓30–60%、P99↓20–50% | FastAPI route timing、SQLAlchemy echo、py-spy、cProfile、Sentry、Lighthouse |
| 3 | `sys-db-optimizer` | §4.1.2 | “慢 SQL”“建索引”“长事务” | 慢查询清零、全表扫描↓ | SQLAlchemy、Alembic、EXPLAIN/ANALYZE、SQLite/Postgres |
| 4 | `sys-cache-optimizer` | §4.1.3 | “加缓存”“缓存击穿”“命中率低” | 缓存命中率↑、穿透/雪崩防护 | Redis / cachetools、FastAPI 依赖缓存 |
| 5 | `sys-async-decoupling` | §4.1.4 | “异步化”“削峰”“消息队列” | 非关键路径异步率↑、峰值承载↑30–80% | Celery/ARQ、FastAPI BackgroundTasks、Redis Stream |
| 6 | `sys-resource-tuning` | §4.2 | “CPU 高”“内存泄漏”“GC 频繁” | CPU 峰值<70%、内存<75%、IO wait↓30% | py-spy、tracemalloc、objgraph、gc 日志 |
| 7 | `sys-reliability` | §4.3 | “熔断”“限流”“降级”“超时”“高可用” | 5xx<0.1%、可用性 99.9%、MTTR↓50% | slowapi/limits、tenacity、CircuitBreaker、健康检查 |
| 8 | `sys-security-hardening` | §4.4 | “漏洞扫描”“权限审计”“数据脱敏” | 高危 24–72h 清零、鉴权 100%、加密 100% | trivy、bandit、npm audit、Sentry、日志脱敏 |
| 9 | `sys-code-quality` | §4.5 | “降低耦合”“清重复”“补文档”“质量门禁” | 单测 70–85%、重复率↓20%、文档 100% | ruff、import-linter/grimp、radon、vulture、pytest |
| 10 | `sys-observability` | §4.3.3 | “监控告警”“链路追踪”“告警噪音” | 分层监控覆盖、告警分级、异常自动发现 | Sentry、Prometheus/Grafana、OpenTelemetry、logging |
| 11 | `sys-load-testing` | §2.1, §5 | “压测”“建基线”“峰值压测” | QPS/TPS 提升 50–100%、并发↑30–80% | locust / k6、Lighthouse CI、pytest-benchmark |
| 12 | `sys-release-governance` | §4.3.4, §9 | “灰度发布”“金丝雀”“回滚”“发布评审” | 灰度+回滚 100% 覆盖、发布风险↓ | GitHub Actions、feature flag、DB 迁移向后兼容 |

---

## 技能间依赖（编排参考）

```
sys-optimization-orchestrator
   ├─> sys-perf-diagnosis ──> sys-db-optimizer
   │                     └─> sys-cache-optimizer
   ├─> sys-load-testing ────> (基线 / 回归)
   ├─> sys-security-hardening
   ├─> sys-code-quality ────> sys-observability
   ├─> sys-resource-tuning
   ├─> sys-reliable-architecture (sys-reliability)
   ├─> sys-async-decoupling
   └─> sys-release-governance
```

> 编排 Agent 在 WF-0 先调用 diagnosis/load-testing/security/code-quality 建立基线；
> WF-1 调用 db/cache/reliability/resource/security 止血；
> WF-2 调用 async/decoupling/db/cache/reliability/resource 深治；
> WF-3 调用 observability/release-governance/code-quality/security 固化。
