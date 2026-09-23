# v1.5 系统架构设计 (System Architecture)

> **迭代**: v1.5-performance-observability-insights
> **版本**: Final Locked
> **日期**: 2026-04-28
> **状态**: ✅ 已终定锁定，进入开发阶段

---

## 1. 技术栈 (Tech Stack)

### 1.1 前端
- **框架**: Vue 3 (Composition API)
- **构建工具**: Vite 5
- **UI 库**: Element Plus
- **状态管理**: Pinia
- **HTTP 客户端**: Axios
- **图表库**: ECharts 5
- **PDF 生成**: ReportLab (后端主方案) / html2canvas + jsPDF (前端备选)
- **Excel 导出**: openpyxl (后端) / SheetJS (前端备选)
- **路由**: Vue Router 4 (支持路由懒加载)

### 1.2 后端
- **Runtime**: Python 3.11
- **框架**: FastAPI
- **数据库**: PostgreSQL 15 (主库) + Redis 7 (缓存/队列)
- **ORM**: SQLAlchemy 2.0 (async)
- **任务队列**: Celery + Redis
- **模型服务**: scikit-learn 1.3.x / PyTorch 2.x / transformers
- **监控**: Prometheus (指标采集) + Grafana (可选)
- **日志**: structlog + 文件轮转

### 1.3 基础设施
- **容器化**: Docker + Docker Compose
- **反向代理**: Nginx (支持灰度流量分割)
- **CI/CD**: GitHub Actions
- **环境**: 开发(dev) / 测试(test) / 预发布(staging) / 生产(prod)

### 1.4 质量保障 (QA Stack)
- **后端单元测试**: pytest + pytest-asyncio + httpx
- **前端组件测试**: Vitest + Vue Test Utils
- **E2E 测试**: Playwright
- **性能测试**: locust / k6
- **契约测试**: schemathesis (OpenAPI)

---

## 2. 目录结构规范

### 2.1 后端 (backend/)
```
backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── auth.py
│   │       ├── user_risk.py
│   │       ├── model_predict.py
│   │       ├── admin.py
│   │       ├── monitoring.py          # NEW: 监控指标接口
│   │       ├── canary.py              # NEW: 灰度发布控制
│   │       ├── report.py              # NEW: 报告导出接口
│   │       └── __init__.py
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   ├── database.py
│   │   ├── model_engine.py
│   │   ├── model_registry.py
│   │   ├── model_monitor.py
│   │   ├── canary_manager.py          # NEW: 灰度管理器
│   │   ├── observability.py           # NEW: 可观测性指标收集
│   │   ├── fallback.py                # NEW: 回退策略统一入口
│   │   └── exception.py
│   ├── ml/
│   │   ├── trainer.py
│   │   ├── fusion_engine.py
│   │   ├── drift_detector.py          # EXISTING: 漂移检测
│   │   └── validators.py              # NEW: 输入验证与异常检测
│   ├── models/
│   │   ├── base.py
│   │   ├── user.py
│   │   ├── risk.py
│   │   ├── assessment.py
│   │   ├── intervention.py
│   │   ├── monitoring_log.py          # NEW: 监控日志模型
│   │   └── canary_record.py           # NEW: 灰度记录模型
│   ├── services/
│   │   ├── risk_service.py
│   │   ├── warning_service.py
│   │   ├── monitoring_service.py      # NEW: 监控服务
│   │   └── report_service.py          # NEW: 报告生成服务
│   └── main.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/                      # NEW: 契约测试
│   └── performance/                   # NEW: 性能回归测试
└── requirements.txt
```

### 2.2 前端 (frontend/)
```
frontend/
├── src/
│   ├── components/
│   │   ├── common/                    # 通用原子组件
│   │   ├── charts/                    # NEW: ECharts 图表封装
│   │   ├── virtual-list/              # NEW: 虚拟列表组件
│   │   └── skeleton/                  # NEW: 骨架屏组件
│   ├── views/
│   │   ├── dashboard/
│   │   ├── risk/                      # 风险分析页
│   │   ├── monitoring/                # NEW: 监控面板页
│   │   ├── reports/                   # NEW: 报告中心
│   │   └── admin/
│   ├── composables/
│   │   ├── useVirtualScroll.ts        # NEW: 虚拟滚动逻辑
│   │   ├── useLazyLoad.ts             # NEW: 懒加载逻辑
│   │   ├── usePerformanceMonitor.ts   # NEW: 性能监控
│   │   └── useChart.ts                # NEW: ECharts 封装
│   ├── stores/
│   │   ├── monitoringStore.ts         # NEW: 监控状态
│   │   └── reportStore.ts             # NEW: 报告状态
│   ├── api/
│   │   ├── monitoringApi.ts           # NEW: 监控 API
│   │   └── reportApi.ts               # NEW: 报告 API
│   └── router/
│       └── index.ts                   # 路由懒加载配置
├── tests/
│   ├── unit/
│   └── e2e/
└── vite.config.ts
```

---

## 3. 数据模型 (Data Model)

### 3.1 监控日志 (MonitoringLog) — NEW
| 字段名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | UUID | 是 | 主键 |
| event_type | Enum | 是 | MODEL_SUCCESS, MODEL_FALLBACK, INPUT_ANOMALY, DRIFT_ALERT |
| model_version | String | 是 | 模型版本号 |
| user_id | UUID | 否 | 关联用户 |
| request_payload | JSON | 否 | 请求摘要(脱敏) |
| response_summary | JSON | 否 | 响应摘要 |
| fallback_reason | String | 否 | 回退原因 |
| latency_ms | Float | 是 | 推理延迟(ms) |
| created_at | DateTime | 是 | 记录时间 |

**索引**: (event_type, created_at), (model_version, created_at)

### 3.2 灰度记录 (CanaryRecord) — NEW
| 字段名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | UUID | 是 | 主键 |
| version | String | 是 | 目标版本 |
| traffic_percent | Float | 是 | 流量比例(0-100) |
| status | Enum | 是 | ACTIVE, PAUSED, ROLLED_BACK, COMPLETED |
| auto_rollback_thresholds | JSON | 是 | 自动回退阈值配置 |
| triggered_by | String | 是 | 触发人/系统 |
| started_at | DateTime | 是 | 开始时间 |
| ended_at | DateTime | 否 | 结束时间 |
| rollback_reason | String | 否 | 回退原因 |

### 3.3 漂移告警 (DriftAlert) — EXISTING + 增强
| 字段名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | UUID | 是 | 主键 |
| model_version | String | 是 | 模型版本 |
| metric_name | String | 是 | PSI / KS / Wasserstein |
| metric_value | Float | 是 | 指标值 |
| severity | Enum | 是 | LOW, MEDIUM, HIGH, CRITICAL |
| feature_name | String | 否 | 触发特征 |
| resolved_at | DateTime | 否 | 解决时间 |
| created_at | DateTime | 是 | 告警时间 |

### 3.4 真实样本验证结果 (ValidationResult) — NEW
| 字段名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | UUID | 是 | 主键 |
| sample_id | String | 是 | 样本标识 |
| model_version | String | 是 | 验证版本 |
| ground_truth | String | 是 | 真实标签 |
| prediction | String | 是 | 模型预测 |
| confidence | Float | 否 | 置信度 |
| is_correct | Boolean | 是 | 是否正确 |
| failure_reason | String | 否 | 失败原因 |
| created_at | DateTime | 是 | 验证时间 |

---

## 4. API 接口定义 (API Specification)

### 4.1 模块: 监控与可观测性 (Monitoring)

#### 4.1.1 接口: 获取模型成功率趋势
- **URL**: `GET /api/v1/monitoring/model-success-rate`
- **Auth**: Admin

**Query Parameters**:
```json
{
  "model_version": "v1.4.0",
  "start_time": "2026-04-01T00:00:00Z",
  "end_time": "2026-04-28T00:00:00Z",
  "granularity": "hour" // hour | day | week
}
```

**Response (200 OK)**:
```json
{
  "data": [
    { "timestamp": "2026-04-27T00:00:00Z", "success_rate": 0.982, "total_requests": 1200 },
    { "timestamp": "2026-04-27T01:00:00Z", "success_rate": 0.975, "total_requests": 980 }
  ],
  "summary": { "avg_success_rate": 0.978, "total_requests": 2180 }
}
```

#### 4.1.2 接口: 获取回退触发统计
- **URL**: `GET /api/v1/monitoring/fallback-stats`
- **Auth**: Admin

**Response (200 OK)**:
```json
{
  "data": [
    { "model_version": "v1.4.0", "fallback_count": 45, "fallback_rate": 0.02, "top_reason": "PYTORCH_LOAD_ERROR" },
    { "model_version": "v1.3.0", "fallback_count": 12, "fallback_rate": 0.01, "top_reason": "INPUT_ANOMALY" }
  ]
}
```

#### 4.1.3 接口: 获取漂移告警列表
- **URL**: `GET /api/v1/monitoring/drift-alerts`
- **Auth**: Admin

**Query Parameters**:
```json
{
  "severity": "HIGH",
  "resolved": false,
  "limit": 50,
  "offset": 0
}
```

**Response (200 OK)**:
```json
{
  "data": [
    {
      "id": "uuid-...",
      "model_version": "v1.4.0",
      "metric_name": "PSI",
      "metric_value": 0.35,
      "severity": "HIGH",
      "feature_name": "heart_rate_variability",
      "created_at": "2026-04-27T10:00:00Z"
    }
  ],
  "total": 12
}
```

### 4.2 模块: 灰度发布 (Canary)

#### 4.2.1 接口: 创建灰度发布
- **URL**: `POST /api/v1/canary/deployments`
- **Auth**: Admin

**Request Body**:
```json
{
  "version": "v1.5.0",
  "traffic_percent": 5.0,
  "auto_rollback": {
    "max_fallback_rate": 0.05,
    "max_drift_alerts_per_hour": 10,
    "max_avg_latency_ms": 500
  },
  "step_plan": [5, 25, 50, 100]
}
```

**Response (201 Created)**:
```json
{
  "deployment_id": "uuid-...",
  "version": "v1.5.0",
  "status": "ACTIVE",
  "current_traffic": 5.0,
  "started_at": "2026-04-28T08:00:00Z"
}
```

#### 4.2.2 接口: 调整灰度流量
- **URL**: `PATCH /api/v1/canary/deployments/{id}/traffic`
- **Auth**: Admin

**Request Body**:
```json
{
  "traffic_percent": 25.0,
  "reason": "监控指标正常，扩大灰度"
}
```

#### 4.2.3 接口: 回滚灰度发布
- **URL**: `POST /api/v1/canary/deployments/{id}/rollback`
- **Auth**: Admin

**Request Body**:
```json
{
  "reason": "漂移告警超过阈值，触发自动回滚",
  "triggered_by": "system"
}
```

**Response (200 OK)**:
```json
{
  "deployment_id": "uuid-...",
  "previous_version": "v1.4.0",
  "status": "ROLLED_BACK",
  "rolled_back_at": "2026-04-28T09:30:00Z"
}
```

### 4.3 模块: 报告导出 (Report)

#### 4.3.1 接口: 导出用户风险报告 (PDF)
- **URL**: `POST /api/v1/reports/user-risk/pdf`
- **Auth**: Authenticated

**Request Body**:
```json
{
  "user_id": "uuid-...",
  "start_date": "2026-01-01",
  "end_date": "2026-04-28",
  "include_trend_chart": true,
  "include_recommendations": true
}
```

**Response (200 OK)**:
```
Content-Type: application/pdf
Content-Disposition: attachment; filename="user_risk_report_20260428.pdf"
```

#### 4.3.2 接口: 导出批量数据 (Excel)
- **URL**: `POST /api/v1/reports/batch-export/excel`
- **Auth**: Admin

**Request Body**:
```json
{
  "data_type": "risk_records",
  "filters": { "risk_level": ["HIGH", "CRITICAL"], "date_range": ["2026-01-01", "2026-04-28"] },
  "columns": ["user_id", "risk_level", "confidence", "assessed_at"]
}
```

**Response (200 OK)**:
```
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="risk_export_20260428.xlsx"
```

### 4.4 模块: 真实样本验证 (Validation)

#### 4.4.1 接口: 执行离线验证
- **URL**: `POST /api/v1/validation/run`
- **Auth**: Admin

**Request Body**:
```json
{
  "model_version": "v1.5.0",
  "baseline_version": "v1.4.0",
  "dataset_path": "s3://datasets/validation_v1.5.csv",
  "metrics": ["accuracy", "precision", "recall", "f1", "auc", "mae", "rmse"]
}
```

**Response (202 Accepted)**:
```json
{
  "validation_id": "uuid-...",
  "status": "RUNNING",
  "estimated_completion": "2026-04-28T10:00:00Z"
}
```

#### 4.4.2 接口: 获取验证结果
- **URL**: `GET /api/v1/validation/{id}/results`
- **Auth**: Admin

**Response (200 OK)**:
```json
{
  "validation_id": "uuid-...",
  "status": "COMPLETED",
  "model_version": "v1.5.0",
  "baseline_version": "v1.4.0",
  "metrics": {
    "accuracy": 0.852,
    "precision": 0.841,
    "recall": 0.798,
    "f1": 0.819,
    "auc": 0.901,
    "mae": 0.12,
    "rmse": 0.18
  },
  "comparison": {
    "f1_delta": 0.03,
    "regression_samples": 23,
    "improvement_samples": 67
  },
  "anomaly_samples": [
    { "sample_id": "S-1001", "reason": "NaN_in_feature_hrv", "prediction": null }
  ],
  "canary_recommendation": "F1 >= 0.78, 建议灰度"
}
```

---

## 5. 关键流程设计

### 5.1 灰度发布与自动回滚流程
```
1. Admin 调用 POST /canary/deployments 创建灰度 (1% 流量)
2. CanaryManager 基于 md5(user_id)[0:8] % 100 < traffic_percent 分配流量
3. Nginx 根据 Header (X-Model-Version) 将请求路由到对应版本
4. CanaryManager 持续监控 (Celery beat 每 30s 检查):
   - 回退率 > 阈值? -> 触发自动回滚
   - 漂移告警/小时 > 阈值? -> 触发自动回滚
   - 平均延迟 > 阈值? -> 触发自动回滚
5. 自动回滚触发时:
   a. 流量立即切回基线版本
   b. 发送通知到 Admin (站内信 + 邮件)
   c. 记录回滚原因到 CanaryRecord
6. 若监控正常，Admin 手动 PATCH /traffic 扩大灰度 (5% -> 25% -> 50% -> 100%)
7. 若需人工回滚，调用 POST /rollback (可覆盖自动回滚)
8. 所有切换记录写入 CanaryRecord 表
```

### 5.2 模型推理与监控闭环
```
1. 用户请求 -> API Gateway
2. CanaryManager 决定路由到哪个模型版本
3. ModelEngine 加载对应版本模型
4. InputValidator 检查输入异常 (NaN/Inf/缺字段/空文本)
   - 异常 -> 记录 MonitoringLog(INPUT_ANOMALY) -> 触发回退
5. 模型推理 -> 获取预测结果
6. DriftDetector 检测输入/输出分布漂移
   - 漂移 -> 记录 DriftAlert -> 若严重则触发回退
7. 记录 MonitoringLog(MODEL_SUCCESS 或 MODEL_FALLBACK)
8. 返回结果给用户
```

### 5.3 前端性能优化策略
```
1. 路由懒加载: Vue Router 动态 import() 按需加载页面组件
2. 虚拟列表: 大数据列表使用虚拟滚动，仅渲染可视区域 DOM
3. 图片懒加载: 使用 IntersectionObserver 按需加载内容区图片
4. 组件缓存: 使用 <keep-alive> 缓存高频切换页面状态
5. 骨架屏: 页面加载时显示骨架屏提升感知体验
6. 性能监控: 使用 Performance API 采集 FCP/LCP/FID/CLS 等指标
```

### 5.4 报告生成流程
```
1. 用户选择报告类型 (PDF/Excel) 和参数
2. ReportService 查询数据库获取原始数据
3. 若数据量 < 1000 条:
   a. 同步生成 PDF (ReportLab) / Excel (openpyxl)
   b. 生成后进行基础校验 (文件大小 > 0 / 页数 > 0 / 图表存在)
   c. 返回文件流
4. 若数据量 >= 1000 条:
   a. 提交 Celery 异步任务生成报告
   b. 返回任务 ID，用户可轮询状态
   c. 生成完成后通知用户 (站内信)
   d. 用户点击下载获取文件
5. 记录下载日志
6. 若生成失败，返回友好错误提示 (含失败原因)
```

---

## 6. 监控指标字典

| 指标名 | 类型 | 计算口径 | 告警阈值 | 用途 |
|---|---|---|---|---|
| model_success_rate | Gauge | 成功推理数 / 总请求数 | < 0.95 | 模型服务健康 |
| fallback_rate | Gauge | 回退次数 / 总请求数 | > 0.05 | 模型稳定性 |
| inference_latency_p99 | Histogram | 推理延迟 99 分位 | > 500ms | 服务性能 |
| drift_alert_count | Counter | 漂移告警次数/小时 | > 10 | 数据质量 |
| input_anomaly_rate | Gauge | 异常输入数 / 总请求数 | > 0.02 | 输入质量 |
| canary_traffic_percent | Gauge | 当前灰度流量比例 | - | 发布进度 |
| frontend_fcp | Gauge | 首屏内容绘制时间 | > 2.5s | 前端性能 |
| frontend_lcp | Gauge | 最大内容绘制时间 | > 4.0s | 前端性能 |

---

## 7. 数据保留策略 (Data Retention)

| 数据类型 | 保留期限 | 存储位置 | 清理策略 |
|---|---|---|---|
| MonitoringLog (原始) | 90 天 | PostgreSQL | 定时任务删除过期数据 |
| MonitoringLog (聚合) | 1 年 | PostgreSQL | 按天/周聚合后归档 |
| CanaryRecord | 永久 | PostgreSQL | 标记删除，物理保留 |
| DriftAlert | 1 年 | PostgreSQL | 软删除，保留审计链 |
| ValidationResult | 永久 | PostgreSQL / S3 | 大样本数据存 S3 |
| 报告文件 | 30 天 | 本地磁盘 / S3 | 定时清理过期文件 |
| 回滚通知日志 | 1 年 | PostgreSQL | 审计需要，长期保留 |

---

## 8. 新增 API 规范 (Round 3 补充)

### 8.1 监控下钻接口

#### 8.1.1 获取请求明细列表
- **URL**: `GET /api/v1/monitoring/request-details`
- **Auth**: Admin

**Query Parameters**:
```json
{
  "alert_id": "uuid-...",
  "event_type": "MODEL_FALLBACK",
  "start_time": "2026-04-27T00:00:00Z",
  "end_time": "2026-04-28T00:00:00Z",
  "limit": 50,
  "offset": 0
}
```

**Response (200 OK)**:
```json
{
  "data": [
    {
      "request_id": "req-001",
      "user_id": "uuid-...",
      "timestamp": "2026-04-27T10:00:00Z",
      "model_version": "v1.5.0",
      "input_summary": { "features_count": 24, "has_nan": true },
      "output_summary": { "prediction": null, "fallback_reason": "INPUT_ANOMALY" },
      "latency_ms": 45
    }
  ],
  "total": 128
}
```

### 8.2 异步任务接口

#### 8.2.1 查询任务状态
- **URL**: `GET /api/v1/tasks/{task_id}/status`
- **Auth**: Authenticated

**Response (200 OK)**:
```json
{
  "task_id": "uuid-...",
  "status": "SUCCESS", // PENDING / RUNNING / SUCCESS / FAILED
  "progress": 100,
  "created_at": "2026-04-28T08:00:00Z",
  "completed_at": "2026-04-28T08:15:00Z",
  "download_url": "/api/v1/tasks/{task_id}/download",
  "expires_at": "2026-04-29T08:15:00Z"
}
```

#### 8.2.2 下载任务结果
- **URL**: `GET /api/v1/tasks/{task_id}/download`
- **Auth**: Authenticated

**Response (200 OK)**:
```
Content-Type: application/pdf
Content-Disposition: attachment; filename="report_20260428.pdf"
```

### 8.3 告警复盘接口

#### 8.3.1 获取告警复盘报告
- **URL**: `GET /api/v1/monitoring/alerts/{alert_id}/postmortem`
- **Auth**: Admin

**Response (200 OK)**:
```json
{
  "alert_id": "uuid-...",
  "alert_summary": {
    "metric_name": "PSI",
    "metric_value": 0.35,
    "severity": "HIGH",
    "triggered_at": "2026-04-27T10:00:00Z",
    "resolved_at": "2026-04-27T11:30:00Z"
  },
  "root_cause": "数据源 heart_rate_variability 字段格式变更",
  "impact_analysis": {
    "affected_requests": 128,
    "affected_users": 45,
    "fallback_rate_during_alert": 0.08
  },
  "resolution_steps": [
    "10:05 收到告警通知",
    "10:15 运维确认数据源异常",
    "10:30 触发自动回滚到 v1.4.0",
    "11:00 数据源修复完成",
    "11:30 告警标记为已解决"
  ],
  "improvement_actions": [
    "增加 heart_rate_variability 字段格式校验",
    "优化数据源变更通知机制"
  ],
  "generated_at": "2026-04-28T10:00:00Z"
}
```
