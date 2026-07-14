# Phase 0 基线评估报告 (Phase 0 Baseline Report)

> **项目**: bysj (毕业设计系统) | **阶段**: PHASE_0_BASELINE | **完成时间**: 2026-06-29
> **下一步**: 等待用户确认优先级，通过 Gate 0→1 关卡后进入 PHASE_1_QUICKFIX

---

## 1. 执行摘要

Phase 0 基线评估已完成，覆盖 5 个维度（性能、资源、稳定性、安全、可维护性）。通过静态代码审查、已有测试基线与已有性能报告，共识别 **124 个问题**，按优先级分布如下：

| 优先级 | 数量 | 处理阶段 |
|--------|------|----------|
| **P0** (必须立即处理) | 11 | Phase 1 快速止血 |
| **P1** (高优先级) | 43 | Phase 1 快速止血 (部分) + Phase 2 |
| **P2** (中优先级) | 43 | Phase 2 结构性优化 |
| **P3** (低优先级) | 27 | Phase 3 体系化治理 |
| **总计** | **124** | - |

**关键风险**：PostgreSQL 单点、ModelEngine 无界缓存、predict/fusion 同步等待 DB 写入、/uploads/* 无鉴权。

**关键收益机会**：predict_structured 串行→并行可降 4 倍 CPU、observability 端点 SQL 聚合可降 90% 响应时间、LRU 缓存可释放 50%+ 内存。

---

## 2. 评估方法

| 维度 | 评估方法 |
|------|----------|
| 性能 | 静态代码审查 + docs/performance-evaluation-report-v2.md + 已有测试基线 |
| 资源 | test_qa011_resource_usage.py + 代码静态分析 (内存/CPU/I/O 路径) |
| 稳定性 | 代码审查 (熔断/限流/降级/超时覆盖) + 监控配置扫描 |
| 安全 | 代码审查 (鉴权/加密/审计/输入验证) + nginx 配置扫描 |
| 可维护性 | 测试覆盖率报告 + 文件行数扫描 + 依赖图分析 + CI 配置审查 |

**评估局限**：
- 部分指标为静态分析推断，缺运行时压测数据（标记 RISK-001）
- Phase 1 启动前需补做 Locust 压测（已有 `load_tests/locustfile.py`）

---

## 3. 关键基线数据 (KPI Snapshot)

### 3.1 性能基线 (关键接口 P95)
| 接口 | P95 | 风险 |
|------|-----|------|
| predict/fusion | 1500ms | 同步等待 DB 写入 (PERF-P0-001) |
| observability/trend (cache miss) | 5s | 10000 条 Python 聚合 (PERF-P1-001) |
| reports/batch-export/excel | 30s | 同步 openpyxl (PERF-P1-005) |
| model/experiment/evaluate | 30s-5min | 同步 ML 评估 (PERF-P1-006) |
| reports/user-risk/pdf | 5s | 同步 reportlab |

### 3.2 资源基线
- CPU: >80% (核心预测接口，实验路径放大 4 倍)
- 内存: >2GB (10 模型常驻，BERT+Keras)
- 磁盘: 持续增长 (uploads/ + artifacts 无清理)，**日志无轮转**
- 网络: requests 未用 Session，SMTP 每次新建

### 3.3 稳定性基线
- 熔断覆盖率: **1/5** (仅 Redis，DB/ML/SMTP/Celery 全无)
- 限流覆盖率: ~42% (5/12 类接口)
- 告警规则落地: **0** (仅文档)
- DB 连接池指标: **未暴露**
- 服务可用性: **未量化** (PG 单点)

### 3.4 安全基线
- 高危漏洞: **1** (SEC-P0-001 /uploads/* 无鉴权)
- 中危漏洞: 6 (JWT role/HTTP 重置/审计/TLS 等)
- 依赖版本固定率: **0%** (全部 >=)
- TLS 配置: **缺失** (nginx 仅监听 80)

### 3.5 可维护性基线
- 单元测试覆盖率: **46.13%** (门禁 40%，目标 70-85%)
- 后端超大文件 (>500 行): **9 个** (最大 2036 行 model_engine.py)
- 前端超大文件 (>500 行): **11 个** (最大 3855 行 UserRiskPage.vue)
- CI lint 门禁: **缺失**
- pre-commit 钩子: **不存在**

---

## 4. P0 问题清单 (11 个 - 必须立即处理)

| ID | 维度 | 问题描述 | 修复方案 |
|----|------|----------|----------|
| PERF-P0-001 | 性能 | predict_fusion 同步等待 save_assessment_result 阻塞响应 | 改为 fire-and-forget 异步任务 |
| PERF-P0-002 | 性能 | predict_structured 串行执行 3 个实验性模型 | asyncio.gather 并行 + 异步任务 |
| RES-P0-001 | 资源 | ModelEngine.models 无界缓存 (OOM 风险) | LRU(maxsize=20) + 空闲卸载 |
| RES-P0-002 | 资源 | 缺少日志文件轮转配置 | RotatingFileHandler |
| STAB-P0-001 | 稳定性 | 数据库无熔断器 | pybreaker 断路器 |
| STAB-P0-002 | 稳定性 | 数据库查询无语句级超时 | statement_timeout=10s |
| STAB-P0-003 | 稳定性 | PostgreSQL 单点故障 | 流复制+Patroni 或 RDS Multi-AZ (Phase 2) |
| SEC-P0-001 | 安全 | /uploads/* 静态服务无鉴权 | 移除 StaticFiles，改鉴权路由 |
| MAINT-P0-001 | 可维护性 | model_engine.py 缺少专属单元测试 | 新建 test_model_engine.py (≥80%) |
| MAINT-P0-002 | 可维护性 | 硬编码 _STR_TO_NUM/_DEFAULTS 无文档 | 抽离到 feature_maps.py |
| MAINT-P0-003 | 可维护性 | UserRiskPage.vue (3855 行) 测试碎片化 | 拆分为 5 个子组件 |

---

## 5. P1 问题概览 (43 个 - 高优先级)

按维度分布：
- **性能** (6 个): observability 聚合慢、model_status 无缓存、TTL 雪崩风险、assess_structured N+1 查询、Excel 同步导出、ML 实验同步等待
- **资源** (10 个): predict_structured 4 倍 CPU 放大、关键词扫描 O(n*k)、Celery 事件循环、ObservabilityCollector 缓冲区、TRAINING_JOBS 无清理、uploads 无清理、artifact 无清理、SMTP 阻塞、SMTP 连接、requests 无 Session
- **稳定性** (18 个): 响应体不一致、ML/SMTP/Celery 无熔断、限流盲区、健康检查不全、MTTR 无统计、金丝雀依赖 Celery、模型本地存储、Redis 单点、Celery worker 单点、CI 缺稳定性/负载测试、告警未代码化、DB 池指标缺失、Redis 熔断指标缺失、模型 fallback 告警缺失、Celery 失败告警缺失
- **安全** (6 个): JWT role 未实时校验、密码重置 HTTP、数据导出无审计、上传无审计、异常检测缺失、nginx 无 TLS
- **可维护性** (3 个): DEPLOYMENT_GUIDE 过时、API 文档不全、contracts.py 单薄

---

## 6. P2/P3 概览

### P2 (43 个)
- 性能: 9 个 (daemon Thread 训练、子查询、归档、Python 聚合、chunk 体积、brotli、推理无缓存等)
- 资源: 8 个 (celery 并发、PDF/Excel 全量加载、队列无上限、snapshot 本地、Google Fonts、nginx Brotli)
- 稳定性: 11 个 (DB 异常分类、回滚方案、模型预加载、覆盖率门禁、金丝雀覆盖、发布窗口、迁移测试、追踪导出、Sentry 采样、SLO 仪表盘)
- 安全: 10 个 (JWT HS256、token 撤销、上传扫描、PII AES-128、依赖固定、detail 截断、日志脱敏、IP 保留、CSP、X-Frame-Options)
- 可维护性: 5 个 (9 个超大文件、core→ml 反向依赖、API CRUD 重复、import 位置、services 导出)

### P3 (27 个)
- 性能: 7 个 (inflight 清理、BN 重载、celery prefetch、observability 缓冲区、/health、进度条、BERT 批处理)
- 资源: 7 个 (numpy 标量、SHAP、list/deque、WS 总用户数、.sha256、redis 客户端、nginx WS timeout)
- 稳定性: 3 个 (废弃中间件、WS 硬编码、metrics 鉴权)
- 安全: 4 个 (JWT iss/aud、requirements 混入测试依赖、npm audit、PII 轮换脚本)
- 可维护性: 6 个 (覆盖率门禁、CI fail-fast、lint 门禁、pre-commit、依赖上界、ml 模块扁平化)

---

## 7. 关卡验证 (Gate 0→1)

| 验证项 | 状态 | 证据 |
|--------|------|------|
| 5 个维度全部完成基线评估 | ✅ | tasks/{performance,resource,stability,security,maintainability}.md 已填充 |
| 问题清单已生成并按 P0~P3 排序 | ✅ | problem-inventory.md (124 个问题) |
| KPI 基线数据已采集 | ✅ | kpi-baseline.md (5 个分区) |
| 优先级列表已与用户确认 | ⏳ | **待用户确认** |

---

## 8. 风险与建议

### 风险
| ID | 描述 | 缓解措施 |
|----|------|----------|
| RISK-001 | KPI 多项为静态推断，缺运行时压测 | Phase 1 启动前补做 Locust 压测 |
| RISK-002 | PG 单点短期无法解决 | Phase 1 临时加熔断+超时，Phase 2 评估 Multi-AZ |
| RISK-003 | P0 跨 5 维度需多轮迭代 | 严格按优先级铁律 |
| RISK-004 | model_engine.py 同时存在 3 个 P0 问题 | 集中处理：LRU+测试覆盖→异步化→拆分 |

### 建议
1. **Phase 1 处理顺序** (按收益/成本比)：
   - SEC-P0-001 (/uploads 鉴权) - 安全风险最高，修复成本最低
   - RES-P0-002 (日志轮转) - 单点配置，10 分钟完成
   - STAB-P0-001/002 (DB 熔断+超时) - 一起做，防止级联失败
   - PERF-P0-001 (predict/fusion 异步) - 与 PERF-P0-002 一起做，统一异步模式
   - RES-P0-001 (ModelEngine LRU) - 与 MAINT-P0-001/002 一起做，先加测试再重构
   - MAINT-P0-003 (UserRiskPage 拆分) - 独立任务，可与后端并行
   - STAB-P0-003 (PG 高可用) - 延后到 Phase 2，需基础设施投入

2. **数据补全**：Phase 1 启动前补做 Locust 压测，将"待压测"指标填充实际值

3. **优先级铁律**：P0 未清零 (0/11) 禁止处理 P1 问题

---

## 9. 输出文件清单

| 文件 | 状态 | 说明 |
|------|------|------|
| .trae/sysopt/STATE.md | ✅ 已更新 | 主状态文件，反映 5/5 维度评估完成 |
| .trae/sysopt/problem-inventory.md | ✅ 已更新 | 124 个问题清单 |
| .trae/sysopt/kpi-baseline.md | ✅ 已更新 | 5 个分区基线数据 |
| .trae/sysopt/tasks/performance.md | ✅ 已更新 | 24 个任务 |
| .trae/sysopt/tasks/resource.md | ✅ 已更新 | 27 个任务 |
| .trae/sysopt/tasks/stability.md | ✅ 已更新 | 35 个任务 |
| .trae/sysopt/tasks/security.md | ✅ 已更新 | 21 个任务 |
| .trae/sysopt/tasks/maintainability.md | ✅ 已更新 | 17 个任务 |
| .trae/sysopt/test-plan.md | ✅ 已创建 | 4 个关卡验证测试用例 |
| .trae/sysopt/reports/phase-0-baseline.md | ✅ 本文件 | Phase 0 基线报告 |

---

## 10. 下一步行动

**等待用户确认以下事项**：

1. **优先级列表是否认可** - 124 个问题的 P0~P3 分级
2. **Phase 1 执行顺序建议是否采纳** - 第 8 节"建议"中的处理顺序
3. **RISK-001 (压测数据缺失) 处理方式** - 是否在 Phase 1 启动前补做 Locust 压测
4. **STAB-P0-003 (PG 单点) 是否延后到 Phase 2** - 需基础设施投入

**用户确认后**：
- 标记 Gate 0→1 验证通过
- 切换到 PHASE_1_QUICKFIX
- 输出 "📊 基线建立完成，进入 Phase 1: 快速止血"
