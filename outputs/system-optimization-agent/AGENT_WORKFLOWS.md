# Agent 工作流详细设计（WF-0 ~ WF-3）

> 将《系统优化总体计划》落地的 4 条可执行工作流。每条工作流含：目标、输入、任务（含调用的技能）、门禁（Gate，对应 §3 KPI / §9 验收）、交付物。
> 编排逻辑：WF-0 → WF-1 → WF-2 → WF-3 顺序推进；跨阶段支撑技能（observability / code-quality / security / load-testing）按需插入。

---

## WF-0 · 基线评估与问题诊断（计划阶段 0 / §2 / §5）

**目标**：获得可比较的基线数据，明确「问题在哪里、严重程度、优先改什么」。

**输入**：架构图、近 30 天监控/日志/告警/事故记录、`pyproject.toml`、`package.json`、数据库。

**任务**：
1. **梳理现状** — 架构图、依赖图（`import-linter`/`grimp` 已配置层级契约）、核心链路图。
   - 技能：`sys-code-quality`（架构分层）、`sys-observability`（现有埋点盘点）
2. **采集数据** — 五维度（性能/资源/稳定性/安全/可维护性）基线。
   - 技能：`sys-perf-diagnosis`、`sys-load-testing`、`sys-security-hardening`（trivy/bandit/npm audit）、`sys-code-quality`（ruff/coverage/复杂度）
3. **压测建基线** — 对核心接口做基线压测，记录 P50/P95/P99、QPS、错误率。
   - 技能：`sys-load-testing`
4. **根因分析** — 对每个主要问题执行 5-Why（是哪里慢 → 为什么慢 → 为什么阻塞 → 为什么没提前发现 → 为什么没机制化）。
   - 技能：`sys-perf-diagnosis`
5. **输出清单** — 按 §7 四维（影响面×风险×成本×收益）排序，标注 P0–P3。
   - 技能：`sys-optimization-orchestrator`（Backlog 排序）

**门禁 Gate-0**：现状评估报告 ✓、问题清单+优先级 ✓、KPI 基线数据 ✓（通过技术负责人评审）。

**交付物**：`系统现状评估报告.md`、`问题清单与优先级.csv`、`KPI-基线.json`。

---

## WF-1 · 快速止血优化（计划阶段 1 / §4 高收益项 / §5）

**目标**：优先解决影响最大、收益最高的问题，先止血。

**输入**：WF-0 的问题清单中 P0 + 高收益 P1。

**任务**：
1. **修复高频慢接口 / 慢 SQL** — 技能：`sys-db-optimizer`、`sys-perf-diagnosis`
2. **调整缓存策略** — 技能：`sys-cache-optimizer`
3. **补齐限流 / 熔断 / 超时** — 技能：`sys-reliability`
4. **处理内存泄漏 / 资源浪费** — 技能：`sys-resource-tuning`
5. **修复高危安全漏洞** — 技能：`sys-security-hardening`
6. **完善告警阈值与故障通知链路** — 技能：`sys-observability`

**门禁 Gate-1**：高危漏洞清零 ✓、P0 全部闭环 ✓、核心接口 P95 较基线下降 ≥ 20% ✓、5xx 错误率 < 1% ✓。

**交付物**：`热点问题修复清单.md`、`性能优化前后对比.md`、`稳定性改进结果.md`。

---

## WF-2 · 结构性优化（计划阶段 2 / §4 深度项 / §5）

**目标**：针对瓶颈链路与架构问题深度治理。

**输入**：WF-1 余下 P1 + P2 结构性问题。

**任务**：
1. **拆分高耦合模块** — 技能：`sys-code-quality`（降低耦合、拆大模块）、`sys-resource-tuning`
2. **耗时任务异步化** — 技能：`sys-async-decoupling`
3. **优化 DB 结构 / 索引 / 查询** — 技能：`sys-db-optimizer`
4. **引入消息队列与削峰** — 技能：`sys-async-decoupling`
5. **完善服务降级与故障隔离** — 技能：`sys-reliability`
6. **调整资源配额与线程池** — 技能：`sys-resource-tuning`

**门禁 Gate-2**：架构优化方案评审通过 ✓、新旧链路对比达标（P95 较 WF-1 再降 ≥ 15%）✓、CPU 峰值 < 70%、内存常态 < 75% ✓。

**交付物**：`架构优化方案.md`、`新旧链路对比.md`、`性能-资源-稳定性提升报告.md`。

---

## WF-3 · 体系化治理（计划阶段 3 / §4.3–4.5 / §5 / §9）

**目标**：把优化成果固化为制度与工程机制。

**输入**：WF-2 后的稳定系统 + 既有 CI/CD。

**任务**：
1. **持续性能监控 + 容量预测** — 技能：`sys-observability`
2. **安全扫描 SLA（高危 24–72h / 中危 7d）** — 技能：`sys-security-hardening`
3. **代码质量门禁 + 测试门禁** — 技能：`sys-code-quality`、`sys-test-gates`（注：测试门禁由 code-quality 内含脚本支撑）
4. **发布灰度 / 回滚标准** — 技能：`sys-release-governance`
5. **文档 / Runbook / 应急预案** — 技能：`sys-code-quality`（文档）、`sys-observability`（Runbook）
6. **定期稳定性压测与故障演练** — 技能：`sys-load-testing`、`sys-reliability`

**门禁 Gate-3**：治理机制手册 ✓、质量/测试/安全门禁在 CI 生效 ✓、至少 1 次故障演练记录 ✓、核心模块单测覆盖率 ≥ 70% ✓。

**交付物**：`运营与治理机制手册.md`、`标准化发布与回滚流程.md`、`长效优化机制.md`、`故障演练记录.md`。

---

## 跨阶段支撑技能（贯穿 WF-0~WF-3）

| 技能 | 贯穿用途 |
|---|---|
| `sys-observability` | 每个阶段都需先用它盘点/补齐埋点，并在阶段末核验指标 |
| `sys-code-quality` | WF-0 评估、WF-1/WF-2 重构、WF-3 门禁持续生效 |
| `sys-security-hardening` | WF-0 扫描、WF-1 修高危、WF-3 固化 SLA |
| `sys-load-testing` | WF-0 建基线、WF-1/2 验证、WF-3 定期回归 |

---

## 风险与回退（对应计划 §8）

- 每阶段进入前必须在**测试环境**验证；通过 Gate 才推进。
- 任一 Gate 未通过：编排 Agent 回到对应任务重做，不允许带伤进入下一阶段。
- 线上变更一律灰度 + 预置回滚（见 `sys-release-governance`）。
- 指标异常自动告警（见 `sys-observability`）。
