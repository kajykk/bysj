# Phase 2 结构性优化计划 (Phase 2 Plan)

> 阶段: PHASE_2_STRUCTURAL | 制定时间: 2026-06-30
> 关联: STATE.md / problem-inventory.md / tasks/*.md
> 关卡: 需通过 Gate 1→2 后启动

---

## 1. 目标 (Objectives)

针对瓶颈链路和架构问题进行深度治理，达成 KPI 目标 >60%。

- 拆分高耦合模块 (MAINT-P2-001/002 子组件 + model_engine.py)
- 耗时任务异步化 (PERF-P1-004/005/006, RES-P1-003)
- 数据库结构与索引优化 (PERF-P1-001, RES-P1-002)
- 服务降级与故障隔离 (STAB-P1-002/003/004/008/009/010/011)
- 资源配额与连接池策略 (RES-P1-001/004/005/006/007/008/009/010)
- 安全访问控制 (SEC-P1-001/002/003/004/005/006)
- 文档与契约层 (MAINT-P1-001/002/003)

---

## 2. P1 问题 Phase 归属 (P1 Phase Allocation)

### Phase 1 提前处理 (5 个 - 告警阈值相关, Gate 1→2 必备)

> 这些是 Gate 1→2 第 4 项 "告警阈值与通知链路已完善" 的必备前置。

| ID | 问题描述 | Phase 1 提前原因 |
|----|----------|------------------|
| STAB-P1-014 | 核心告警规则未在代码中定义 (5xx/P99/CPU 等阈值仅文档) | Gate 1→2 验证项 4 直接依赖 |
| STAB-P1-015 | DB 连接池使用率无指标，无法监控耗尽风险 | 告警阈值落地需要指标暴露 |
| STAB-P1-016 | Redis 熔断状态无指标，降级无声发生 | 告警阈值落地需要指标暴露 |
| STAB-P1-017 | 模型 fallback 率无全局告警，非金丝雀期间降级无感知 | 告警阈值落地需要告警规则 |
| STAB-P1-018 | Celery 任务失败无告警，仅记录 DLQ 日志 | 告警阈值落地需要告警规则 |

**修复方案**:
- 新增 `app/core/alert_rules.py` 集中定义告警阈值 (5xx_rate/P99/cpu/mem/db_pool/redis_state/model_fallback/celery_fail)
- 新增 `app/core/metrics.py` 暴露 `/metrics` 端点 (db_pool_*/redis_circuit_state/model_fallback_rate/celery_task_failures_total)
- 新增 `monitoring/alert_rules.yml` YAML 化告警规则 (供 Prometheus/Loki 接入)
- 新增 `tests/test_alert_rules.py` 验证阈值合规

### Phase 2 处理 (39 个)

#### 性能维度 (6 个)

| ID | 问题描述 | Phase 2 修复方案 |
|----|----------|------------------|
| PERF-P1-001 | observability API 拉取 10000 条在 Python 内聚合，P95 > 2s | 强制时间范围参数 + SQL GROUP BY 聚合 |
| PERF-P1-002 | model_status 端点无缓存，每次遍历所有模型文件 stat() | 加 30s Redis 缓存 |
| PERF-P1-003 | observability 端点 cache TTL 全部 5min 固定，雪崩风险 | TTL 加 ±60s 随机抖动 |
| PERF-P1-004 | assess_structured 单次评估触发 5-7 次 DB 查询 | warning/intervention 改为 fire-and-forget 异步 |
| PERF-P1-005 | /reports/batch-export/excel 同步等待大文件生成 30s | 添加异步版本 (复用 pdf_job_store 模式) |
| PERF-P1-006 | model/experiment 同步等待 ML 任务 30s-5min | 改为 Celery 任务，返回 job_id 轮询 |

#### 资源维度 (10 个)

| ID | 问题描述 | Phase 2 修复方案 |
|----|----------|------------------|
| RES-P1-001 | predict_structured 每次执行 3 路实验性推理 CPU 放大 4 倍 | 引入实验开关，仅 A/B 流量走实验路径 |
| RES-P1-002 | LiteFeatureExtractor 嵌套关键词扫描 O(n*k) | 改用 Aho-Corasick 或单次正则扫描 |
| RES-P1-003 | Celery 任务每次创建/复用事件循环 | 评估 celery[asyncio] 或高频任务改 FastAPI asyncio.Task |
| RES-P1-004 | ObservabilityCollector 缓冲区上限 10000 条占数百 MB | 确认消费者接入，无消费者则改 1000 或 DB flush |
| RES-P1-005 | TRAINING_JOBS 全局字典无清理机制 | 添加 cleanup_old_jobs + OrderedDict LRU 上限 100 |
| RES-P1-006 | uploads/ 目录无自动清理机制 | 添加 cleanup_uploads.py + Celery 每日清理 |
| RES-P1-007 | experiment_trainer 写入多个 artifact 文件无清理 | 保留最近 10 次，更旧压缩归档 |
| RES-P1-008 | notifier/am_sync 在 async 函数中调用同步 requests 阻塞事件循环 | 替换为 httpx.AsyncClient 或 asyncio.to_thread 包装 |
| RES-P1-009 | email_service SMTP 连接未复用，每次新建 1-3s | 实现模块级 SMTP 连接池 |
| RES-P1-010 | requests 库未使用 Session 复用 TCP 连接 | 模块级创建 requests.Session() |

#### 稳定性维度 (14 个 - 剩余)

| ID | 问题描述 | Phase 2 修复方案 |
|----|----------|------------------|
| STAB-P1-001 (降级) | PostgreSQL 单点故障，无高可用方案 | 引入流复制+Patroni 或 RDS Multi-AZ (评估) |
| STAB-P1-001 (原) | 成功响应与错误响应体结构不一致 | 统一为 {code,message,data,error} 结构 |
| STAB-P1-002 | ML 模型推理无熔断器与超时 | predict_* 包装 asyncio.wait_for(timeout=5) + 模型熔断 |
| STAB-P1-003 | Email/SMTP 无熔断器 | 引入 SMTP 熔断器 |
| STAB-P1-004 | Celery broker 无熔断与快速失败 | 监控 broker 连通性 + 告警 |
| STAB-P1-005 | 限流覆盖盲区 (reports/validation/canary 等) | 计算密集接口 5/min，敏感操作 10/min |
| STAB-P1-006 | 健康检查未覆盖 ML 模型可用性 | HealthSnapshot 增加 models 字段 |
| STAB-P1-007 | 无 MTTR 自动统计与监控 | 基于 OperationLog 时间差计算 MTTR |
| STAB-P1-008 | 金丝雀自动回滚强依赖 Celery | 增加备用定时任务 (asyncio.create_task) |
| STAB-P1-009 | ML 模型文件依赖本地文件系统 | 模型存储到对象存储 + SHA256 校验 |
| STAB-P1-010 | Redis 单实例无 Sentinel/Cluster | 部署 Redis Sentinel (3 节点) |
| STAB-P1-011 | Celery worker 单点 | 部署至少 2 个 worker 实例 |
| STAB-P1-012 | CI 未运行稳定性与故障注入测试 | CI 增加 stability-tests job |
| STAB-P1-013 | CI 未运行负载测试 | 增加 nightly 负载测试 job |

#### 安全维度 (6 个)

| ID | 问题描述 | Phase 2 修复方案 |
|----|----------|------------------|
| SEC-P1-001 | JWT role 未与 DB 实时校验 | get_current_user 增加 role 对比 + token blocklist |
| SEC-P1-002 | 密码重置链接默认 HTTP 明文传输 | 生产环境强制 HTTPS 校验 |
| SEC-P1-003 | 数据导出端点无审计日志 | 每个导出端点 _log_auth_operation |
| SEC-P1-004 | 文件上传与咨询师查看未记录审计日志 | upload_file + counselor 查看增加审计 |
| SEC-P1-005 | 异常访问检测能力缺失 | Celery 周期扫描 + alerts anomaly rule |
| SEC-P1-006 | nginx 仅监听 80 端口无 TLS | 增加 443 ssl 配置 + 80→443 跳转 |

#### 可维护性维度 (3 个)

| ID | 问题描述 | Phase 2 修复方案 |
|----|----------|------------------|
| MAINT-P1-001 | DEPLOYMENT_GUIDE.md 严重过时 (v1.5 vs v1.39) | 重写对齐 v1.39 架构 |
| MAINT-P1-002 | v1.5-api-documentation.md 仅覆盖 v1.5 | 导出 openapi.json + 补齐 23 个 router 文档 |
| MAINT-P1-003 | contracts.py 职责单薄 (50 行) | 升级为契约聚合层 re-export 关键常量 |

### Phase 3 处理 (0 个)

> 所有 P1 均在 Phase 1 提前 (5) 或 Phase 2 (39) 处理。

---

## 3. Phase 2 任务清单 (Task Breakdown)

### 3.1 高耦合模块拆分 (5 任务)

- [ ] T-P2-001: model_engine.py (2036 行) 拆分为 model_engine_core + model_engine_predict + model_engine_fallback
- [ ] T-P2-002: StructuredAssessTab.vue (1181 行) 拆分为 4 个 step 子组件 (基本信息/学业工作/生活状态/心理状况)
- [ ] T-P2-003: ExperimentTab.vue (921 行) 拆分为 4 个 chart 子组件
- [ ] T-P2-004: model_predict.py 拆分为 predict_structured + predict_text + predict_fusion 路由
- [ ] T-P2-005: observability.py 拆分为 observability_query + observability_aggregate

### 3.2 耗时任务异步化 (4 任务)

- [ ] T-P2-006: assess_structured 的 warning/intervention 改为 fire-and-forget 异步 (PERF-P1-004)
- [ ] T-P2-007: /reports/batch-export/excel 异步化 (PERF-P1-005)
- [ ] T-P2-008: model/experiment 改为 Celery 任务 (PERF-P1-006)
- [ ] T-P2-009: notifier/am_sync 改用 httpx.AsyncClient (RES-P1-008)

### 3.3 数据库与查询优化 (4 任务)

- [ ] T-P2-010: observability API SQL GROUP BY 聚合改造 (PERF-P1-001)
- [ ] T-P2-011: model_status 加 30s Redis 缓存 (PERF-P1-002)
- [ ] T-P2-012: observability cache TTL 加 ±60s 随机抖动 (PERF-P1-003)
- [ ] T-P2-013: LiteFeatureExtractor 改用 Aho-Corasick (RES-P1-002)

### 3.4 资源配额与清理 (8 任务)

- [ ] T-P2-014: predict_structured 实验开关 (RES-P1-001)
- [ ] T-P2-015: Celery 事件循环复用 (RES-P1-003)
- [ ] T-P2-016: ObservabilityCollector 缓冲区上限调整 (RES-P1-004)
- [ ] T-P2-017: TRAINING_JOBS cleanup_old_jobs + LRU 100 (RES-P1-005)
- [ ] T-P2-018: uploads/ Celery 每日清理 (RES-P1-006)
- [ ] T-P2-019: experiment_trainer artifact 压缩归档 (RES-P1-007)
- [ ] T-P2-020: email_service SMTP 连接池 (RES-P1-009)
- [ ] T-P2-021: requests.Session() 复用 (RES-P1-010)

### 3.5 服务降级与故障隔离 (8 任务)

- [ ] T-P2-022: ML 模型推理熔断器 + asyncio.wait_for (STAB-P1-002)
- [ ] T-P2-023: SMTP 熔断器 (STAB-P1-003)
- [ ] T-P2-024: Celery broker 熔断 + 快速失败 (STAB-P1-004)
- [ ] T-P2-025: 限流覆盖补齐 (reports/validation/canary/experiment/observability) (STAB-P1-005)
- [ ] T-P2-026: HealthSnapshot 增加 models 字段 (STAB-P1-006)
- [ ] T-P2-027: MTTR 自动统计 (STAB-P1-007)
- [ ] T-P2-028: 金丝雀备用定时任务 (STAB-P1-008)
- [ ] T-P2-029: 模型文件对象存储 + SHA256 校验 (STAB-P1-009)

### 3.6 安全访问控制 (6 任务)

- [ ] T-P2-030: JWT role 实时校验 + token blocklist (SEC-P1-001)
- [ ] T-P2-031: 密码重置链接强制 HTTPS (SEC-P1-002)
- [ ] T-P2-032: 数据导出审计日志 (SEC-P1-003)
- [ ] T-P2-033: 文件上传审计日志 (SEC-P1-004)
- [ ] T-P2-034: 异常访问检测 (SEC-P1-005)
- [ ] T-P2-035: nginx TLS 配置 (SEC-P1-006)

### 3.7 文档与契约 (3 任务)

- [ ] T-P2-036: DEPLOYMENT_GUIDE.md 重写 (MAINT-P1-001)
- [ ] T-P2-037: API 文档补齐 23 个 router (MAINT-P1-002)
- [ ] T-P2-038: contracts.py 升级契约聚合层 (MAINT-P1-003)

### 3.8 高可用部署 (3 任务 - 评估类)

- [ ] T-P2-039: PostgreSQL Multi-AZ 评估 (STAB-P1-001 降级)
- [ ] T-P2-040: Redis Sentinel 部署 (STAB-P1-010)
- [ ] T-P2-041: Celery worker 多实例部署 (STAB-P1-011)

### 3.9 CI 测试体系 (2 任务)

- [ ] T-P2-042: CI stability-tests job (STAB-P1-012)
- [ ] T-P2-043: nightly 负载测试 job (STAB-P1-013)

### 3.10 统一响应体 (1 任务)

- [ ] T-P2-044: 统一 {code,message,data,error} 响应结构 (STAB-P1-001 原)

**Phase 2 任务总计**: 44 个 (含 5 个 Phase 1 提前 + 39 个 Phase 2 本体 + 3 个评估类 + 2 个 CI + 1 统一响应)

---

## 4. KPI 目标 (Phase 2 完成后)

| KPI | Phase 1 当前 | Phase 2 目标 | 关联任务 |
|-----|-------------|-------------|----------|
| 核心接口 P95 响应时间 | 1500ms | 600-900ms (-40~60%) | T-P2-006/007/010/011/012 |
| 观测端点 cache miss P95 | 5s | <500ms (-90%) | T-P2-010/011/012 |
| 5xx 错误率 | 待监控 | <0.1% | T-P2-022/023/024/025 |
| 熔断覆盖率 | 2/5 (Redis+DB) | 5/5 全覆盖 | T-P2-022/023/024 |
| 限流覆盖率 | ~42% | 100% | T-P2-025 |
| 告警规则落地 | 0 (代码化) | 全部代码化 | Phase 1 提前 (STAB-P1-014) |
| DB 连接池指标 | 未暴露 | /metrics 暴露 | Phase 1 提前 (STAB-P1-015) |
| 后端超大文件 (>500 行) | 9 个 | 0 个 | T-P2-001/004/005 |
| 前端超大文件 (>500 行) | 8 个 | 0 个 | T-P2-002/003 |
| 代码重复率 | 未检测 | -20% | T-P2-038 契约层 |

---

## 5. 验收标准 (Acceptance Criteria)

- [ ] 39 个 Phase 2 P1 问题已修复并测试通过
- [ ] KPI 目标达成率 >60%
- [ ] 高耦合模块拆分完成 (model_engine.py / StructuredAssessTab.vue / ExperimentTab.vue)
- [ ] 耗时任务异步化完成 (assess_structured / batch-export / model experiment)
- [ ] 数据库结构与索引优化完成 (SQL GROUP BY / Redis 缓存)
- [ ] 服务降级与故障隔离就位 (ML/SMTP/Celery 熔断器)
- [ ] Gate 2→3 验证通过

---

## 6. 风险与依赖 (Risks & Dependencies)

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| PostgreSQL Multi-AZ 部署成本 | 高 | Phase 2 仅评估，实际部署推迟到 Phase 3 |
| ML 模型文件对象存储改造涉及训练脚本 | 中 | 双写过渡，保留本地 fallback |
| 文档重写工作量大 | 中 | 优先 API 文档，部署指南次之 |
| 熔断器误触发 | 中 | 阈值保守起步，灰度观察 1 周 |
