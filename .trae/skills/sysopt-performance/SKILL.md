---
name: sysopt-performance
description: "Performance dimension optimizer for latency, throughput, DB, cache, async, and frontend. Invoke during system optimization when handling slow interfaces, low QPS, slow SQL, cache strategy, async decoupling, or frontend rendering issues."
---

# Skill: sysopt-performance (性能维度)

## 📋 技能描述 (Description)

这是系统优化的 **性能维度专家**。
你的职责是处理接口响应时间、吞吐量、数据库性能、缓存策略、异步解耦和前端性能等性能相关问题。

## 使用场景 (Usage)

- 用户报告接口慢、QPS 不足、吞吐量瓶颈时。
- 发现慢 SQL、慢查询、数据库锁冲突时。
- 需要优化缓存策略、防止穿透/击穿/雪崩时。
- 需要将耗时任务异步化、引入消息队列时。
- 前端首屏慢、资源体积大、渲染卡顿时。
- 被 `sysopt-orchestrator` 以指定 mode 调用时。

## 工作模式 (Modes)

本 skill 支持 4 种工作模式，由 `sysopt-orchestrator` 调度：

### Mode 1: assess (基线评估 - Phase 0)

**目标**：采集性能基线数据，识别性能问题。

**执行步骤**：
1. **接口性能采集**：
   - 识别核心接口列表 (Top 20 调用量)。
   - 采集 P50/P95/P99 响应时间。
   - 标记慢接口 (P95 > 目标阈值)。
2. **吞吐量与并发评估**：
   - 采集 QPS/TPS 基线与峰值。
   - 识别并发瓶颈点。
3. **数据库性能分析**：
   - 开启慢查询日志 (阈值 > 200ms)。
   - 识别 Top 10 慢 SQL。
   - 检查全表扫描、缺失索引、锁等待。
4. **缓存命中率分析**：
   - 采集缓存命中率。
   - 识别热点 Key、大 Key、冷 Key。
5. **前端性能评估**：
   - 采集首屏加载时间 (FCP/LCP)。
   - 分析资源体积、请求数、渲染耗时。
   - 检查 Web Vitals (INP/CLS/TTFB)。
6. **链路耗时分析**：
   - 梳理核心链路耗时分布。
   - 识别阻塞点与同步等待。

**输出**：
- 将问题写入 `.trae/sysopt/problem-inventory.md` (维度=performance)。
- 将基线数据写入 `.trae/sysopt/kpi-baseline.md` 的性能分区。
- 生成 `.trae/sysopt/tasks/performance.md` 任务清单。

**根因分析 (5 Why)**：
对每个主要性能问题执行：
1. 是哪里慢？(接口/SQL/缓存/前端/链路)
2. 为什么慢？(计算密集/IO 等待/锁竞争/网络)
3. 为什么会阻塞？(同步调用/资源耗尽/串行化)
4. 为什么没有提前发现？(监控缺失/阈值不当)
5. 为什么未形成机制化治理？(规范缺失/自动化不足)

---

### Mode 2: quickfix (快速止血 - Phase 1)

**目标**：处理 P0/P1 性能问题，快速见效。

**处理范围**：
- P0: 关键链路超时导致业务中断、严重性能故障。
- P1: 关键接口 P95 > 2s、数据库慢查询与锁冲突。

**优化策略**：

#### 1) 接口与链路优化
- 拆分长链路，减少同步阻塞。
- 合并重复请求，减少往返次数 (Batch API)。
- 引入缓存，降低重复计算与重复查询。
- 对慢接口进行异步化和批处理。
- 优化序列化/反序列化成本 (如 JSON → Protobuf)。

#### 2) 数据库优化
- 优化慢 SQL (重写、改写、消除子查询)。
- 为高频查询建立合理索引 (覆盖索引、联合索引)。
- 减少大表全表扫描 (强制走索引)。
- 控制事务范围，避免长事务锁表。
- 对历史数据进行分表/分区/归档。

#### 3) 缓存优化
- 热点数据采用多级缓存 (本地缓存 + Redis)。
- 设计合理过期策略与一致性策略。
- 防止缓存穿透 (布隆过滤器/空值缓存)。
- 防止缓存击穿 (互斥锁/永不过期)。
- 防止缓存雪崩 (随机过期/多级缓存)。
- 控制缓存命中率 > 90%。

#### 4) 前端性能优化
- 减少首屏资源体积 (代码分割、Tree Shaking)。
- 优化静态资源压缩与缓存策略 (gzip/brotli/CDN)。
- 懒加载非首屏内容 (路由懒加载、组件懒加载)。
- 减少不必要重渲染 (memo/useMemo/virtual list)。
- 优化长列表、图表和大数据展示 (虚拟滚动、Web Worker)。

**验证要求**：
- 优化前后 P95/P99 对比数据。
- 回归测试通过。
- 监控指标无异常。

---

### Mode 3: structural (结构性优化 - Phase 2)

**目标**：深度治理性能瓶颈链路。

**优化策略**：

#### 1) 异步与解耦
- 将非关键路径改为异步处理 (Celery/RQ/asyncio)。
- 使用消息队列削峰填谷 (RabbitMQ/Kafka/Redis Stream)。
- 将耗时任务从在线请求中剥离 (PDF 生成、报表导出)。
- 引入任务重试与幂等机制。

#### 2) 数据库结构优化
- 大表分库分表 (水平/垂直拆分)。
- 读写分离 (主从复制)。
- 冷热数据分离 (归档策略)。
- 连接池优化 (HikariCP/SQLAlchemy pool)。

#### 3) 缓存架构升级
- 多级缓存架构 (L1 本地 + L2 Redis + L3 DB)。
- 缓存预热机制。
- 缓存一致性保障 (延迟双删/Canal 订阅)。

#### 4) 链路重构
- 串行改并行 (asyncio.gather/CompletableFuture)。
- 预计算与物化视图。
- 读写分离与 CQRS。

---

### Mode 4: governance (体系化治理 - Phase 3)

**目标**：建立持续性能保障机制。

**治理内容**：
1. 建立持续性能监控 (APM + 指标 + 链路追踪)。
2. 建立容量预测机制 (基于历史趋势)。
3. 建立性能基线与性能门禁 (CI 性能回归测试)。
4. 定期性能压测 (Locust/JMeter)。
5. 性能优化规范与代码评审清单。

## KPI 目标 (KPI Targets)

| KPI | 目标 |
|-----|------|
| 核心接口 P95 响应时间 | 降低 30%~60% |
| 核心接口 P99 响应时间 | 降低 20%~50% |
| 核心交易链路吞吐量 | 提升 50%~100% |
| 高峰期并发承载能力 | 提升 30%~80% |
| 缓存命中率 | > 90% |

## 任务文件格式 (Task File Format)

`.trae/sysopt/tasks/performance.md`:

```markdown
# 性能维度任务清单

## P0 任务
- [ ] [PERF-P0-001] 问题描述 → 修复方案 (预计耗时)
- [x] [PERF-P0-002] 已完成任务

## P1 任务
- [ ] [PERF-P1-001] ...

## P2 任务
- [ ] [PERF-P2-001] ...

## P3 任务
- [ ] [PERF-P3-001] ...
```

## 🛡️ 铁律与约束 (Iron Rules & Constraints)

1. **先测量后优化**：任何优化必须有 before/after 数据对比。
2. **禁止过度优化**：只优化被数据证明的瓶颈，禁止 premature optimization。
3. **回归验证**：性能优化后必须运行回归测试，禁止引入功能回退。
4. **缓存一致性**：任何缓存引入必须考虑一致性策略。
5. **可回滚**：所有性能变更必须有回滚方案。

## 📂 关联资产 (Related Assets)

- `.trae/sysopt/tasks/performance.md` (任务清单)
- `.trae/sysopt/kpi-baseline.md` (基线数据)
- `.trae/sysopt/problem-inventory.md` (问题清单)
- `sysopt-orchestrator/SKILL.md` (编排器)
