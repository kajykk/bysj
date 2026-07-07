# KPI 基线数据 (KPI Baseline)

> Phase 0 采集的当前系统基线数据，作为后续优化的对比基准。

---

## 采集元信息
- **采集时间**: 2026-06-29
- **采集方式**: 静态代码审查 + 已有测试基线 (test_qa011_resource_usage.py) + 已有性能报告 (docs/performance-evaluation-report-v2.md)
- **采集环境**: 开发环境 (静态分析推断，需运行时压测验证)
- **数据周期**: 近 30 天代码状态

---

## 1. 性能基线

### 1.1 关键接口响应时间 (静态预估)
| 接口 | P50 (ms) | P95 (ms) | P99 (ms) | 备注 |
|------|----------|----------|----------|------|
| POST /api/v1/model/predict/tabular | 80-150 | 300 | 800 | 实验性模型串行 |
| POST /api/v1/model/predict/text | 60-150 | 250 | 500 | BERT 可用时 |
| POST /api/v1/model/predict/physiological | 50-100 | 200 | 400 | - |
| POST /api/v1/model/predict/fusion | 200-500 | 1500 | 3000 | **同步等待 DB 写入** |
| GET /api/v1/user/risk/report | 20-50 | 100 | 200 | Python 内聚合 |
| GET /api/v1/user/risk/trend?days=30 | 30-80 | 150 | 300 | - |
| GET /api/v1/user/risk/trend?days=365 | 80-200 | 500 | 1000 | **全量加载** |
| GET /api/v1/alerts/observability/trend (cache hit) | 5-10 | 20 | 50 | - |
| GET /api/v1/alerts/observability/trend (cache miss) | 1-3s | 5s | 10s | **10000 条 Python 聚合** |
| POST /api/v1/reports/user-risk/pdf | 500ms-3s | 5s | 10s | 同步 reportlab |
| POST /api/v1/reports/batch-export/excel | 1-10s | 30s | 60s | **同步 openpyxl** |
| GET /api/v1/model/status | 50-100 | 200 | 500 | 无缓存 + 文件 stat |
| GET /api/v1/admin/stats | 100-300 | 800 | 1500 | 8+ count 查询 |

### 1.2 吞吐量与并发
| 指标 | 基线值 | 峰值 | 备注 |
|------|--------|------|------|
| QPS (核心接口) | 待压测 | - | 限流 60/min (生产) |
| TPS (核心交易) | 待压测 | - | - |
| 并发连接数 | 待压测 | - | WebSocket 单用户上限 5 |

### 1.3 慢接口与慢查询 Top 10
| 排名 | 接口/SQL | 平均耗时 | 调用量 | 根因 |
|------|---------|---------|--------|------|
| 1 | /reports/batch-export/excel | 1-10s | - | 同步 openpyxl 全量加载 |
| 2 | /model/experiment/evaluate | 30s-5min | - | 同步 ML 评估 |
| 3 | /alerts/observability/trend (cache miss) | 1-3s | - | 10000 条 Python 聚合 |
| 4 | /model/predict/fusion | 200-500ms | - | 同步等待 DB 写入 |
| 5 | /reports/user-risk/pdf | 500ms-3s | - | 同步 reportlab |

---

## 2. 资源利用率基线

### 2.1 CPU
| 指标 | 常态 | 峰值 | 告警阈值 |
|------|------|------|----------|
| CPU 利用率 | >80% (核心预测接口) | 待监控 | 未配置 |
| 负载均值 (1/5/15min) | 待监控 | - | - |
| 上下文切换次数 | 待监控 | - | - |
| 模型推理次数/请求 | 4 次 (应为 1 次) | - | 实验路径放大 |

### 2.2 内存
| 指标 | 常态 | 峰值 | 备注 |
|------|------|------|------|
| 内存使用率 | >2GB (模型预加载) | - | 10 模型常驻，BERT+Keras |
| GC 次数/小时 | 待监控 | - | - |
| Full GC 频率 | 待监控 | - | 需 tracemalloc 插桩 |
| ModelEngine.models 缓存 | 无界 (无 LRU) | - | RES-P0-001 |

### 2.3 存储
| 指标 | 常态 | 峰值 | 备注 |
|------|------|------|------|
| 磁盘 I/O 等待 | 待监控 | - | - |
| 磁盘使用率 | 持续增长 | - | uploads/ + experiment artifacts 无清理 |
| 日志文件 | **无轮转** | - | RES-P0-002，磁盘必定写满 |
| 容量增长趋势 | 持续增长 | - | 缺少归档机制 |

### 2.4 网络
| 指标 | 常态 | 峰值 | 备注 |
|------|------|------|------|
| 带宽利用率 | 待监控 | - | - |
| TCP 连接复用率 | 0% (requests 模块级) | - | RES-P1-010，未用 Session |
| SMTP 连接 | 每次新建 (1-3s) | - | RES-P1-009 |
| async 内同步 requests | 阻塞事件循环 | - | RES-P1-008 |

---

## 3. 稳定性基线

| 指标 | 基线值 | 备注 |
|------|--------|------|
| 5xx 错误率 | 待监控 | DB 异常未分类处理 (STAB-P2-001) |
| 4xx 错误率 | 待监控 | - |
| 超时率 | 待监控 | DB 无语句超时 (STAB-P0-002) |
| 可用性 (SLA) | 未量化 | PG 单点 (STAB-P0-003) |
| MTTR | 人工记录 | 无自动统计 (STAB-P1-007) |
| 熔断覆盖率 | 仅 Redis (1 处) | DB/ML/SMTP/Celery 均无熔断 |
| 限流覆盖率 | 部分 (auth/admin/upload/predict/monitoring) | reports/validation/canary 等 0 显式限流 |
| 告警规则落地 | 0 (仅文档) | STAB-P1-014 |
| DB 连接池指标 | 未暴露 | STAB-P1-015 |
| Redis 熔断指标 | 未暴露 | STAB-P1-016 |

---

## 4. 安全基线

| 指标 | 基线值 | 备注 |
|------|--------|------|
| 高危漏洞数量 | 1 (P0) | SEC-P0-001 /uploads 无鉴权 |
| 中危漏洞数量 | 6 (P1) | JWT role/HTTP 重置链接/审计缺失/TLS 缺失 |
| 关键接口鉴权覆盖率 | ~95% | /uploads/* 静态服务未鉴权 |
| 敏感数据加密覆盖率 | ~90% | PII Fernet 加密，但 AES-128 (SEC-P2-004) |
| 日志脱敏覆盖率 | 分散实现 | 无统一 logging.Filter (SEC-P2-007) |
| 审计日志覆盖率 | ~60% | 数据导出/上传/咨询师查看未审计 |
| 依赖版本固定率 | 0% | 全部 `>=` 无上界 (SEC-P2-005) |
| TLS 配置 | 缺失 | nginx 仅监听 80 (SEC-P1-006) |

---

## 5. 可维护性基线

| 指标 | 基线值 | 备注 |
|------|--------|------|
| 核心模块单元测试覆盖率 | 46.13% (P0 子集) | 门禁 40%，目标 70-85% |
| 关键链路集成测试覆盖率 | 待运行 | integration/ 5 文件 + api/ 41 文件 |
| 代码重复率 | 未检测 (无 jscpd) | 估算 API 层样板 600-800 行 |
| 代码复杂度 (圈复杂度均值) | 未检测 (无 radon) | model_engine.py 预估高 |
| 关键模块文档覆盖率 | ~70% | architecture/runbook 优秀，deployment/api-doc 过时 |
| 循环依赖数量 | 待运行 import-linter | model_engine→ml 反向依赖已识别 |
| 后端超大文件 (>500 行) | 9 个 | 最大 2036 行 (model_engine.py) |
| 前端超大文件 (>500 行) | 11 个 | 最大 3855 行 (UserRiskPage.vue) |
| CI lint 门禁 | 缺失 | ruff/black/mypy/bandit/eslint 均未在 CI 执行 |
| pre-commit 钩子 | 不存在 | 无 .pre-commit-config.yaml |
| 后端测试文件数 | ~215 个 (576 用例) | - |
| 前端单元测试文件 | ~30 个 *.test.ts | 偏少 |
| 前端 E2E 测试文件 | 12 个 *.spec.ts | 充足 |
