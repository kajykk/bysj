---
name: sysopt-resource
description: "Resource utilization optimizer for CPU, memory, storage, and network. Invoke during system optimization when handling high CPU, memory leaks, GC pressure, disk IO bottlenecks, or network issues."
---

# Skill: sysopt-resource (资源利用率维度)

## 📋 技能描述 (Description)

这是系统优化的 **资源利用率维度专家**。
你的职责是处理 CPU、内存、存储、网络资源的使用效率与均衡性问题。

## 使用场景 (Usage)

- CPU 利用率过高、上下文切换频繁、负载均值异常时。
- 内存泄漏、GC 频繁、OOM 风险时。
- 磁盘 IO 瓶颈、容量增长过快时。
- 网络带宽瓶颈、丢包、重传严重时。
- 资源使用不均衡需要调优时。
- 被 `sysopt-orchestrator` 以指定 mode 调用时。

## 工作模式 (Modes)

### Mode 1: assess (基线评估 - Phase 0)

**目标**：采集资源利用率基线，识别资源瓶颈。

**执行步骤**：
1. **CPU 评估**：
   - 采集 CPU 利用率 (常态/峰值)。
   - 分析负载均值 (1min/5min/15min)。
   - 统计上下文切换次数。
   - 识别高 CPU 进程与热点代码 (火焰图)。
2. **内存评估**：
   - 采集内存使用率 (常态/峰值)。
   - 统计 GC 次数/小时、Full GC 频率。
   - 识别内存泄漏风险 (持续增长不回收)。
   - 分析大对象与对象生命周期。
3. **存储评估**：
   - 采集磁盘 IO 等待时间、IOPS。
   - 分析磁盘使用率与容量增长趋势。
   - 识别慢磁盘访问路径。
   - 检查日志落盘策略。
4. **网络评估**：
   - 采集带宽利用率 (常态/峰值)。
   - 统计丢包率、TCP 重传率。
   - 检查连接数、TIME_WAIT 堆积。
   - 识别大包传输与重复传输。

**输出**：
- 将问题写入 `.trae/sysopt/problem-inventory.md` (维度=resource)。
- 将基线数据写入 `.trae/sysopt/kpi-baseline.md` 的资源分区。
- 生成 `.trae/sysopt/tasks/resource.md` 任务清单。

---

### Mode 2: quickfix (快速止血 - Phase 1)

**目标**：处理 P0/P1 资源问题，消除明显浪费。

**处理范围**：
- P0: 严重内存泄漏导致频繁宕机、磁盘满导致服务不可用。
- P1: CPU 持续高位、GC 频繁、IO 等待严重。

**优化策略**：

#### 1) CPU 优化
- 识别高 CPU 任务与热点代码 (cProfile/py-spy)。
- 减少不必要的循环、重复计算和正则开销。
- 调整线程池/进程池大小与任务调度策略。
- 合理设置并发上限 (避免上下文切换风暴)。
- CPU 密集型任务改用多进程 (绕过 GIL)。

#### 2) 内存优化
- 排查内存泄漏 (tracemalloc/objgraph)。
- 减少大对象和临时对象创建 (生成器/迭代器)。
- 优化对象生命周期与缓存大小 (LRU/TTL)。
- 分析 GC 压力，降低频繁 Full GC 风险 (调整分代阈值)。
- 大文件流式处理，避免全量加载。

#### 3) 存储优化
- 优化日志采集与落盘策略 (异步写、批量写)。
- 压缩大文件、归档冷数据 (gzip/zstd)。
- 定期清理无效缓存和历史文件 (cron job)。
- 提升慢磁盘访问路径的可观测性 (IO 监控)。
- 日志轮转与保留策略 (logrotate)。

#### 4) 网络优化
- 复用连接 (连接池/Keep-Alive/HTTP/2)。
- 降低大包传输与重复传输 (增量更新/压缩)。
- 增加超时和重试的合理控制 (指数退避)。
- 使用合理的压缩与协议优化 (gzip/brotli/Protobuf)。

---

### Mode 3: structural (结构性优化 - Phase 2)

**目标**：资源架构深度调优。

**优化策略**：
1. **资源配额与隔离**：
   - 容器化部署，资源限制 (cgroup/K8s limits)。
   - 关键服务独立部署，避免资源争抢。
   - 弹性伸缩 (HPA/VPA)。
2. **存储架构升级**：
   - 冷热数据分层 (SSD + HDD)。
   - 对象存储替代本地存储 (S3/MinIO)。
   - 分布式文件系统 (大数据场景)。
3. **网络架构优化**：
   - CDN 加速静态资源。
   - 内网通信优化 (就近部署/专线)。
   - 负载均衡策略调优 (最少连接/一致性哈希)。

---

### Mode 4: governance (体系化治理 - Phase 3)

**目标**：建立资源治理机制。

**治理内容**：
1. 建立资源容量预测机制 (基于历史趋势预测扩容时机)。
2. 建立资源告警分级 (警告/严重/紧急)。
3. 建立资源成本优化机制 (按需扩缩容/Spot 实例)。
4. 定期资源利用率评审 (周报/月报)。

## KPI 目标 (KPI Targets)

| KPI | 目标 |
|-----|------|
| CPU 峰值利用率 | < 70% |
| 内存常态使用率 | < 75% |
| 磁盘 I/O 等待时间 | 降低 30%+ |
| 网络异常重传率 | 显著下降 |
| Full GC 频率 | < 1 次/小时 |

## 🛡️ 铁律与约束 (Iron Rules & Constraints)

1. **先监控后调优**：资源调优必须有监控数据支撑。
2. **禁止资源超卖**：容器资源 limit 必须合理，禁止超卖导致 OOM。
3. **容量预留**：生产环境必须预留 30% 资源余量应对峰值。
4. **变更灰度**：资源配额调整必须灰度验证。
5. **可观测性**：所有资源指标必须有监控与告警。

## 📂 关联资产 (Related Assets)

- `.trae/sysopt/tasks/resource.md` (任务清单)
- `.trae/sysopt/kpi-baseline.md` (基线数据)
- `.trae/sysopt/problem-inventory.md` (问题清单)
- `sysopt-orchestrator/SKILL.md` (编排器)
