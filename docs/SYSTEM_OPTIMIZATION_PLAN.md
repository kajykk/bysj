# 系统优化计划 (System Optimization Plan)

> **项目名称**: 基于多模态融合的大学生抑郁症预警与干预系统
> **文档版本**: v1.0
> **编制日期**: 2026-06-01
> **当前基线**: v1.28-final-delivery (FINAL-GO)
> **规划周期**: 2026-06-01 ~ 2026-08-31 (12 周)
> **适用范围**: 后端 (FastAPI + ML) / 前端 (Vue 3 + Vite) / 数据库 / 部署运维 / 安全合规

---

## 目录 (Table of Contents)

1. [系统现状评估与问题诊断](#1-系统现状评估与问题诊断)
2. [优化目标与关键绩效指标 (KPIs)](#2-优化目标与关键绩效指标-kpis)
3. [优化策略与技术方案](#3-优化策略与技术方案)
4. [实施步骤与时间规划](#4-实施步骤与时间规划)
5. [资源需求与分配方案](#5-资源需求与分配方案)
6. [风险评估与应对措施](#6-风险评估与应对措施)
7. [质量保障与验收标准](#7-质量保障与验收标准)
8. [预期效果评估](#8-预期效果评估)
9. [附录](#9-附录)

---

## 1. 系统现状评估与问题诊断

### 1.1 系统架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                    客户端 (Browser / PWA)                     │
│  Vue 3 + Vite + Element Plus + ECharts + Pinia + Workbox   │
└────────────┬────────────────────────────────────────────────┘
             │ HTTPS / WSS
┌────────────▼────────────────────────────────────────────────┐
│                Nginx 反向代理 + 负载均衡                       │
└────────────┬────────────────────────────────────────────────┘
             │
┌────────────▼────────────────────────────────────────────────┐
│        FastAPI 应用层 (Uvicorn + Gunicorn Workers)            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  API v1: auth/user/counselor/admin/model/warning/... │  │
│  │  中间件: CORS / RateLimit / Security Headers / Sentry│  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │  Model Engine  │  │  Risk Service  │  │  WebSocket   │  │
│  │  (PyTorch MLP) │  │  (多模态融合)   │  │  Real-time   │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
└────────────┬────────────────────────────────────────────────┘
             │
   ┌─────────┼──────────┬──────────────┐
   ▼         ▼          ▼              ▼
┌──────┐ ┌──────┐  ┌──────────┐  ┌──────────┐
│ PG   │ │Redis │  │  Celery  │  │  MLflow  │
│ 14+  │ │ 6+   │  │  Worker  │  │  (模型)  │
└──────┘ └──────┘  └──────────┘  └──────────┘
```

### 1.2 现状基线指标 (Baseline Metrics, 2026-04-26 评估)

| 维度 | 指标 | 当前值 | 评级 | 数据来源 |
|------|------|--------|------|----------|
| **性能** | API 平均响应时间 | 430ms | ✅ 良好 | pytest --durations |
| **性能** | 健康检查端点响应 | **8000ms** | 🔴 瓶颈 | 性能报告 §3.1 |
| **性能** | 模型预测接口耗时 | 540~650ms | ⚠️ 需关注 | 性能报告 §3.1 |
| **性能** | E2E 关键流程耗时 | 1.7~1.9s | ✅ 达标 | Playwright |
| **性能** | 前端冷启动 | 229s | ⚠️ 偏高 | Vitest 报告 |
| **资源** | CPU 峰值 (单容器) | 65% | ✅ 正常 | docker stats |
| **资源** | 内存占用 (后端) | ~480MB | ✅ 合理 | 性能测试 |
| **资源** | 镜像体积 (后端) | **2.8GB** | 🔴 过大 | Docker layers |
| **资源** | 前端 chunk 总数 | 12 | ✅ 合理 | Vite build |
| **稳定性** | 后端测试通过率 | 114/114 (100%) | 🟢 优秀 | pytest |
| **稳定性** | 前端测试通过率 | 51/55 (92.7%) | ⚠️ 接近达标 | Vitest |
| **稳定性** | 错误码契约一致性 | 100% (401/403/404/409/422) | 🟢 优秀 | 契约测试 |
| **稳定性** | 并发冲突处理 | 100% 返回 409 | 🟢 优秀 | 并发测试 |
| **安全** | OWASP Top 10 覆盖 | 7/10 | 🟡 需加强 | 安全审查 |
| **安全** | 依赖漏洞 (Critical) | 0 | ✅ 无 | npm audit |
| **安全** | 依赖漏洞 (High) | 3 | ⚠️ 待修复 | npm audit |
| **可维护** | 后端代码行数 | ~28,000 | 良好 | cloc |
| **可维护** | 前端代码行数 | ~12,000 | 良好 | cloc |
| **可维护** | API 文档覆盖率 | 100% | ✅ 完整 | OpenAPI |
| **可维护** | 类型安全 (TS) | strict | ✅ 优秀 | tsconfig |

### 1.3 问题诊断 (Problem Diagnosis)

#### 1.3.1 🔴 P0 - 紧急问题 (Critical)

| ID | 问题 | 根因 | 业务影响 |
|----|------|------|----------|
| **P0-01** | 健康检查端点延迟 8s | `get_health_snapshot` 同步检测 Celery Worker + DB Pool + Redis，串行等待 | K8s Liveness 探针误判 → Pod 被杀 → 服务抖动 |
| **P0-02** | 后端 Docker 镜像 2.8GB | 同时打包 PyTorch (~900MB) + TensorFlow (~1.5GB) + Transformers (~250MB) | 部署慢、CI 缓存低效、冷启动耗时长 |
| **P0-03** | 前端单元测试 4 处失败 | (a) useWebSocket protocols 传递不一致；(b) requestPasswordReset 参数格式不统一；(c) refreshSession mock 失败 | CI 流水线阻塞，无法保证 PR 合并质量 |

#### 1.3.2 🟡 P1 - 重要问题 (Important)

| ID | 问题 | 根因 | 业务影响 |
|----|------|------|----------|
| **P1-01** | 模型预测耗时 0.65s | sklearn 模型按需加载、无 LRU 缓存，并发请求竞争 GIL | 用户感知卡顿，高峰期 P95 突破 1s |
| **P1-02** | joblib Python 3.14 兼容性 | 使用已弃用 `ast.Num` / `ast.Attribute` 语法 | 未来 Python 升级时模型加载失败 |
| **P1-03** | 前端冷启动 229s | jsdom 环境初始化 + 完整 Element Plus 解析 | CI 反馈周期长，开发者体验差 |
| **P1-04** | 高危 npm 漏洞 ×3 | `serialize-javascript` 旧版本注入风险 | 安全扫描告警，XSS 风险 |
| **P1-05** | 测试覆盖率报告缺失 | 后端未启用 pytest-cov，前端覆盖率未定期采集 | 难以量化回归保护程度 |
| **P1-06** | 监控告警规则不完整 | alerting-rules.yml 仅覆盖 CPU/内存，无业务指标 (QPS/P99/错误率) | 故障发现滞后 |

#### 1.3.3 🟢 P2 - 一般问题 (Minor)

| ID | 问题 | 根因 | 业务影响 |
|----|------|------|----------|
| **P2-01** | 模型预测无异步队列 | CPU 密集型任务同步执行 | 高并发下阻塞事件循环 |
| **P2-02** | 数据库连接池未显式调优 | 使用 SQLAlchemy 默认配置 (5+10) | 突发流量下连接耗尽 |
| **P2-03** | 前端 ECharts 全量引入 | `import 'echarts'` 未按需引入 | 初始包体积偏大 |
| **P2-04** | 缺少 API 限流分级 | slowapi 统一配置 | 关键接口与公开接口无差异化保护 |
| **P2-05** | 文档国际化不完整 | zh-CN 完整，en-US 覆盖率 ~70% | 国际化用户体验下降 |

### 1.4 优化必要性分析

- **业务驱动**: 系统已具备生产条件 (v1.28 FINAL-GO)，但性能瓶颈与可维护性短板会影响用户留存与运维效率
- **技术驱动**: 双深度学习框架冗余、监控盲区、测试失败等问题如不治理将逐步累积
- **学术价值**: 本科毕业设计若能附上"上线后优化迭代"案例，可显著提升论文说服力

---

## 2. 优化目标与关键绩效指标 (KPIs)

### 2.1 总体目标 (SMART Goals)

> **在 12 周内，将系统的"性能-资源-稳定性-安全性-可维护性"五大维度分别提升至生产级优秀水平，所有指标可量化、可验证、可监控。**

### 2.2 关键绩效指标体系 (KPI Tree)

#### 2.2.1 性能维度 (Performance KPIs)

| KPI ID | 指标名称 | 当前基线 | 目标值 | 测量方法 | 优先级 |
|--------|----------|----------|--------|----------|--------|
| **PF-01** | API 平均响应时间 (P50) | 430ms | **< 200ms** | Prometheus histogram | P0 |
| **PF-02** | API P95 响应时间 | ~800ms (估) | **< 500ms** | Prometheus histogram | P0 |
| **PF-03** | API P99 响应时间 | ~1500ms (估) | **< 1000ms** | Prometheus histogram | P1 |
| **PF-04** | 健康检查端点 (/health) | 8000ms | **< 100ms** | pytest benchmark | P0 |
| **PF-05** | 模型预测接口耗时 | 540ms | **< 300ms** | pytest benchmark | P0 |
| **PF-06** | 端到端关键流程 (User) | 1.9s | **< 1.5s** | Playwright trace | P1 |
| **PF-07** | 首屏渲染 (FCP) | ~1.2s (估) | **< 0.8s** | Lighthouse CI | P1 |
| **PF-08** | 可交互时间 (TTI) | ~2.5s (估) | **< 1.5s** | Lighthouse CI | P1 |

#### 2.2.2 资源利用率维度 (Resource KPIs)

| KPI ID | 指标名称 | 当前基线 | 目标值 | 测量方法 | 优先级 |
|--------|----------|----------|--------|----------|--------|
| **RS-01** | 后端 Docker 镜像体积 | 2.8GB | **< 1.2GB** | docker images | P0 |
| **RS-02** | 容器空闲内存 | 480MB | **< 350MB** | docker stats | P1 |
| **RS-03** | CPU 平均利用率 | 35% | 40-60% (健康区间) | Prometheus node | P2 |
| **RS-04** | 数据库连接池使用率 | 未监控 | **< 70%** | PG `pg_stat_activity` | P1 |
| **RS-05** | Redis 内存使用 | ~120MB | **< 200MB** (稳定) | redis-cli INFO | P2 |
| **RS-06** | 前端主 chunk gzipped | ~280KB | **< 200KB** | Vite build report | P1 |
| **RS-07** | 模型加载内存峰值 | ~600MB | **< 400MB** | tracemalloc | P1 |

#### 2.2.3 稳定性与可靠性维度 (Stability KPIs)

| KPI ID | 指标名称 | 当前基线 | 目标值 | 测量方法 | 优先级 |
|--------|----------|----------|--------|----------|--------|
| **ST-01** | 后端测试通过率 | 100% (114/114) | **维持 100%** | pytest | P0 |
| **ST-02** | 前端单元测试通过率 | 92.7% (51/55) | **> 98%** | Vitest | P0 |
| **ST-03** | E2E 测试通过率 | 100% (3/3 角色) | **维持 100%** | Playwright | P0 |
| **ST-04** | 服务可用性 (SLA) | 未度量 | **> 99.5%** (月度) | Prometheus uptime | P1 |
| **ST-05** | 错误率 (5xx) | < 0.1% (估) | **< 0.05%** | Sentry | P1 |
| **ST-06** | 平均恢复时间 (MTTR) | 未度量 | **< 15min** | 故障演练 | P2 |
| **ST-07** | 健康检查准确率 | 100% | 维持 100% | K8s probe | P0 |
| **ST-08** | 灰度回滚响应时间 | 未度量 | **< 5min** | canary 测试 | P2 |

#### 2.2.4 安全性维度 (Security KPIs)

| KPI ID | 指标名称 | 当前基线 | 目标值 | 测量方法 | 优先级 |
|--------|----------|----------|--------|----------|--------|
| **SC-01** | Critical 依赖漏洞 | 0 | 维持 0 | npm audit / pip-audit | P0 |
| **SC-02** | High 依赖漏洞 | 3 | **0** | npm audit / pip-audit | P0 |
| **SC-03** | OWASP Top 10 覆盖 | 7/10 | **10/10** | 安全审查清单 | P1 |
| **SC-04** | 密钥泄漏扫描 | 未配置 | **CI 强制阻断** | git-secrets / TruffleHog | P1 |
| **SC-05** | CSP 违规事件 | 未监控 | **< 5/日** | CSP report endpoint | P2 |
| **SC-06** | RBAC 越权测试覆盖 | ~80% | **100%** | 自动化测试 | P1 |
| **SC-07** | 审计日志完整性 | 100% | 维持 100% | pytest audit | P0 |
| **SC-08** | 数据脱敏覆盖率 | 100% (PII) | 维持 100% | 静态扫描 | P0 |

#### 2.2.5 可维护性维度 (Maintainability KPIs)

| KPI ID | 指标名称 | 当前基线 | 目标值 | 测量方法 | 优先级 |
|--------|----------|----------|--------|----------|--------|
| **MN-01** | 后端测试覆盖率 | 未采集 | **> 70%** (核心模块 > 85%) | pytest-cov | P1 |
| **MN-02** | 前端测试覆盖率 | 未采集 | **> 60%** (组件 > 75%) | vitest --coverage | P1 |
| **MN-03** | TypeScript strict 模式 | 开启 | 维持 strict | tsc --noEmit | P0 |
| **MN-04** | ESLint 错误数 | 0 | 维持 0 | eslint . | P0 |
| **MN-05** | API 文档与实现一致 | 100% | 维持 100% | contract test | P0 |
| **MN-06** | 关键路径注释覆盖 | ~80% (估) | **> 90%** | 人工审查 + linter | P2 |
| **MN-07** | 模块循环依赖 | 0 | 维持 0 | madge / pydeps | P1 |
| **MN-08** | Docker 多阶段构建 | 未启用 | **启用** | Dockerfile 审查 | P1 |
| **MN-09** | CHANGELOG 更新及时性 | 良好 | 维持 | git log 审查 | P2 |

### 2.3 KPI 优先级矩阵

```
        紧急性 (Urgency)
        高              低
  ┌─────────────────┬─────────────────┐
高│  P0 关键        │  P1 重要        │ 影
  │  • 健康检查修复  │  • 监控完善      │ 响
  │  • 测试全绿     │  • 覆盖率采集    │ 程
  │  • 镜像瘦身     │  • 漏洞修复      │ 度
  │  • 预测加速     │  • API 限流分级  │
  │                 │                 │
  ├─────────────────┼─────────────────┤
低│  P1 重要        │  P2 一般        │
  │  • ECharts 按需  │  • 文档国际化    │
  │  • 异步队列     │  • CHANGELOG     │
  │  • 告警规则扩展 │  • 性能调优      │
  │                 │                 │
  └─────────────────┴─────────────────┘
```

---

## 3. 优化策略与技术方案

### 3.1 性能优化策略 (Performance)

#### 3.1.1 健康检查端点拆分 (P0-01)

**问题**: `/health` 端点 8s 延迟，影响 K8s 探针。

**方案**: 实施 "Live/Ready" 双探针模式。

```python
# backend/app/main.py
@app.get("/health/live")
@limiter.exempt
async def liveness() -> dict:
    """Kubernetes liveness probe - 必须在 100ms 内返回."""
    return {"status": "alive"}

@app.get("/health/ready")
@limiter.exempt
async def readiness(response: Response) -> dict:
    """Kubernetes readiness probe - 深度健康检查 (缓存 5s)."""
    snapshot = await get_health_snapshot(engine, settings.redis_url)
    if not snapshot.database:
        response.status_code = 503
    return {
        "status": "ready" if snapshot.database else "not_ready",
        "checks": {
            "database": snapshot.database,
            "redis": snapshot.redis,
            "celery": snapshot.celery_worker,
        }
    }
```

**K8s 探针配置**:
```yaml
livenessProbe:
  httpGet: { path: /health/live, port: 8000 }
  periodSeconds: 10
  timeoutSeconds: 1
  failureThreshold: 3
readinessProbe:
  httpGet: { path: /health/ready, port: 8000 }
  periodSeconds: 30
  timeoutSeconds: 5
  failureThreshold: 2
```

**预期效果**: 8s → < 100ms (PF-04)

#### 3.1.2 模型推理加速 (P1-01)

**方案 A - 模型驻留 + LRU 缓存**:
```python
# backend/app/core/model_engine.py
from functools import lru_cache
import asyncio
from concurrent.futures import ThreadPoolExecutor

class ModelEngine:
    def __init__(self):
        self._models = {}  # 驻留内存
        self._lock = asyncio.Lock()
        self._executor = ThreadPoolExecutor(max_workers=4)
    
    def preload(self):
        """应用启动时一次性加载所有模型."""
        self._models['structured'] = joblib.load(MODELS_DIR / 'structured.pkl')
        self._models['physiological'] = joblib.load(MODELS_DIR / 'physiological.pkl')
        # 文本模型按需懒加载
        logger.info("models.preloaded", extra={"count": len(self._models)})
    
    async def predict_async(self, features):
        """异步推理 - 释放事件循环."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self._predict_sync, features
        )
```

**方案 B - 推理结果缓存 (Redis)**:
```python
import hashlib
import json
from redis.asyncio import Redis

async def predict_with_cache(features, ttl=300):
    cache_key = "pred:" + hashlib.sha256(
        json.dumps(features, sort_keys=True).encode()
    ).hexdigest()[:16]
    
    if cached := await redis.get(cache_key):
        return json.loads(cached)
    
    result = await model_engine.predict_async(features)
    await redis.setex(cache_key, ttl, json.dumps(result))
    return result
```

**预期效果**: 540ms → < 300ms (PF-05)；高频请求命中率 > 30%

#### 3.1.3 数据库查询优化

**索引补全审查**:
```python
# backend/alembic/versions/xxxxx_add_performance_indexes.py
def upgrade():
    # 高频查询路径索引
    op.create_index('idx_warning_user_status', 'warnings', ['user_id', 'status'])
    op.create_index('idx_risk_assessment_user_time', 'risk_assessments', ['user_id', 'created_at'])
    op.create_index('idx_intervention_counselor_status', 'interventions', ['counselor_id', 'status'])
    op.create_index('idx_audit_log_time', 'audit_logs', ['created_at'])
```

**连接池调优**:
```python
# backend/app/core/database.py
engine = create_async_engine(
    settings.database_url,
    pool_size=20,          # 默认 5
    max_overflow=10,       # 默认 10
    pool_pre_ping=True,    # 防止 stale connection
    pool_recycle=3600,     # 1 小时回收
)
```

#### 3.1.4 前端性能优化

**ECharts 按需引入** (P2-03):
```typescript
// frontend/src/composables/useECharts.ts
import * as echarts from 'echarts/core'
import { LineChart, BarChart, PieChart, RadarChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent,
  TitleComponent, DataZoomComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart, BarChart, PieChart, RadarChart,
  GridComponent, TooltipComponent, LegendComponent,
  TitleComponent, DataZoomComponent, CanvasRenderer,
])

export { echarts }
```

**路由级代码分割 + 预加载**:
```typescript
// frontend/src/router/index.ts
const routes = [
  {
    path: '/user/dashboard',
    component: () => import(/* webpackChunkName: "user-dashboard" */ '@/views/user/UserDashboard.vue'),
    meta: { preload: 'visible' },  // 视口内时预加载
  }
]
```

**Web Vitals 监控集成**:
```typescript
// frontend/src/utils/web-vitals.ts (已存在，需扩展)
import { onLCP, onFID, onCLS, onFCP, onTTFB } from 'web-vitals'

export function reportWebVitals() {
  onLCP(metric => sendToAnalytics('LCP', metric))
  onFCP(metric => sendToAnalytics('FCP', metric))
  // ... 上报到 Sentry breadcrumbs
}
```

### 3.2 资源优化策略 (Resource)

#### 3.2.1 Docker 镜像瘦身 (P0-02)

**多阶段构建**:
```dockerfile
# backend/Dockerfile
# ---- Stage 1: Builder ----
FROM python:3.12-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ---- Stage 2: Runtime - 轻量化镜像 ----
FROM python:3.12-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 libmagic1 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
# 健康检查使用新端点
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD curl -f http://localhost:8000/health/live || exit 1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

**依赖精简策略**:
```toml
# pyproject.toml (新增)
[project.optional-dependencies]
ml-lite = ["torch>=2.2.0", "scikit-learn>=1.3.2"]
ml-full = ["torch>=2.2.0", "tensorflow>=2.20.0", "transformers>=4.36.2"]
ml-minimal = ["scikit-learn>=1.3.2"]  # 仅结构化模型
```

**效果预估**: 2.8GB → ~1.0GB (RS-01)

#### 3.2.2 joblib 升级 (P1-02)

```bash
pip install --upgrade joblib
python -c "
import joblib
from pathlib import Path
for pkl in Path('models/artifacts').rglob('*.pkl'):
    model = joblib.load(pkl)
    joblib.dump(model, pkl, compress=3)
    print(f'Re-serialized: {pkl}')
"
```

**CI 中增加兼容性检查**:
```yaml
# .github/workflows/ml-compat.yml
- name: Python 3.14 compatibility check
  run: |
    python -c "import joblib; joblib.load('models/artifacts/physiological/model.pkl')"
    ! python -c "import ast; ast.parse('models/...')" | grep -E "(Num|Attribute).*deprecated"
```

### 3.3 稳定性优化策略 (Stability)

#### 3.3.1 前端测试失败修复 (P0-03)

**问题 1: useWebSocket protocols 传递**
```typescript
// frontend/src/composables/useWebSocket.ts (修复)
const protocols = token ? ['bearer', token] : []  // ← 修复
const ws = new WebSocket(url, protocols)
```

**问题 2: requestPasswordReset 参数格式统一**
```typescript
// frontend/src/api/auth.ts
async function requestPasswordReset(email: string) {
  return post('/api/v1/auth/password-reset/request', { email })
  // 统一为单一参数对象
}
```

**问题 3: refreshSession mock 修复**
```typescript
// frontend/src/stores/auth.ts
async function refreshSession(): Promise<boolean> {
  try {
    const res = await post('/api/v1/auth/refresh', null, { skipAuth: true })
    token.value = res.access_token
    return true
  } catch {
    return false  // ← 保证返回 boolean
  }
}
```

#### 3.3.2 监控告警规则完善 (P1-06)

```yaml
# backend/app/monitoring/alerting-rules.yml
groups:
  - name: business_slo
    rules:
      - alert: HighErrorRate
        expr: |
          (
            sum(rate(http_requests_total{status=~"5.."}[5m]))
            / sum(rate(http_requests_total[5m]))
          ) > 0.01
        for: 5m
        labels: { severity: critical }
        annotations:
          summary: "5xx 错误率超过 1% (持续 5min)"
      
      - alert: SlowAPI
        expr: |
          histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 1
        for: 10m
        labels: { severity: warning }
      
      - alert: ModelInferenceBacklog
        expr: celery_queue_length{queue="model_inference"} > 100
        for: 3m
        labels: { severity: warning }
      
      - alert: DatabaseConnectionsHigh
        expr: pg_stat_activity_count > 0.8 * pg_settings_max_connections
        for: 2m
        labels: { severity: critical }
```

### 3.4 安全优化策略 (Security)

#### 3.4.1 依赖漏洞修复 (P1-04)

```bash
# 前端
cd frontend
npm audit fix --production
npm audit  # 确认 High = 0

# 后端
pip install --upgrade \
  "fastapi>=0.115.0" \
  "pydantic>=2.9.0" \
  "sqlalchemy>=2.0.36"
pip-audit  # 确认无 Critical
```

**CI 强制门禁**:
```yaml
# .github/workflows/security-audit.yml
- name: Security audit
  run: |
    if [ "$(npm audit --audit-level=high --json | jq '.metadata.vulnerabilities.high')" -gt "0" ]; then
      echo "::error::发现 High 级别依赖漏洞"
      exit 1
    fi
```

#### 3.4.2 OWASP Top 10 全面覆盖 (SC-03)

| 风险 | 现状 | 补充措施 |
|------|------|----------|
| A01 访问控制 | RBAC 已实现 | 添加 ABAC 测试 + 越权矩阵 |
| A02 加密失败 | JWT + bcrypt | 增加密钥轮转机制 |
| A03 注入 | Pydantic 校验 | 增加 SQL 注入扫描 (sqlmap) |
| A04 不安全设计 | 状态机 + 审计日志 | 完善威胁建模文档 |
| A05 配置错误 | secrets 集中 | 集成 git-secrets pre-commit |
| A06 易受攻击组件 | 部分修复 | npm audit + Snyk 持续监控 |
| A07 身份认证 | JWT + Refresh | 增加 MFA (TOTP) 选项 |
| A08 软件数据完整性 | Sentry + checksum | 依赖签名验证 |
| A09 日志失败 | Sentry 已集成 | 完善告警 SOP |
| A10 SSRF | URL 白名单 | 加强对外部资源限制 |

#### 3.4.3 密钥泄漏防护 (SC-04)

```yaml
# .pre-commit-config.yaml (新增)
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
        exclude: '\.md$|outputs/thesis/'

# .github/workflows/secrets-scan.yml
- name: TruffleHog scan
  uses: trufflesecurity/trufflehog@main
  with:
    extraArgs: --only-verified
```

### 3.5 可维护性优化策略 (Maintainability)

#### 3.5.1 测试覆盖率采集 (P1-05 / MN-01 / MN-02)

**后端 pytest 配置**:
```ini
# backend/pytest.ini
[pytest]
addopts =
    --cov=app
    --cov-report=term-missing
    --cov-report=html:htmlcov
    --cov-report=xml:coverage.xml
    --cov-fail-under=70
    --strict-markers
    --durations=10
```

**前端 vitest 配置**:
```typescript
// frontend/vitest.config.ts
export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'json', 'lcov'],
      include: ['src/**/*.{ts,vue}'],
      exclude: [
        'src/**/*.test.ts',
        'src/main.ts',
        'src/router/index.ts',
      ],
      thresholds: {
        lines: 60,
        functions: 60,
        branches: 55,
        statements: 60,
      },
    },
  },
})
```

**CI 集成**:
```yaml
- name: Coverage gate
  run: |
    coverage=$(python -c "import xml.etree.ElementTree as ET; print(ET.parse('coverage.xml').getroot().attrib['line-rate'])")
    if (( $(echo "$coverage < 0.70" | bc -l) )); then
      exit 1
    fi
- uses: codecov/codecov-action@v4
  with: { file: coverage.xml, fail_ci_if_error: true }
```

#### 3.5.2 模块解耦与依赖治理 (MN-07)

```bash
# 前端模块循环依赖检测
npx madge --circular --extensions ts,vue src/

# 后端 Python 依赖
pip install pydeps
pydeps app --max-depth=3 --show-deps
```

**API 限流分级** (P2-04):
```python
# backend/app/core/rate_limit.py
LIMIT_RULES = {
    "/api/v1/auth/login": "5/minute",          # 登录防爆破
    "/api/v1/auth/register": "3/hour",          # 注册防滥用
    "/api/v1/model_predict": "30/minute",       # 预测成本高
    "/api/v1/user/upload": "10/hour",           # 上传限流
    "/api/v1/admin/*": "60/minute",             # 管理类
    "default": "120/minute",                    # 公开接口
}
```

---

## 4. 实施步骤与时间规划

### 4.1 总体里程碑 (Milestones)

```
Week:  1   2   3   4   5   6   7   8   9   10  11  12
       ├───┴───┤   ├───┴───┤   ├───┴───┤   ├───┴───┤
       M1 准备 │   M2 攻坚 │   M3 提升 │   M4 沉淀 │
       环境基线  │   P0修复  │   性能冲刺│   验收交付│
```

### 4.2 阶段化目标 (Phased Goals)

#### **阶段 1: 准备与基线 (Week 1-2) - "知己"**

| 时间 | 任务 ID | 任务内容 | 交付物 | 负责人 |
|------|---------|----------|--------|--------|
| W1 D1-2 | T-001 | 搭建性能基线测试框架 (Locust + k6) | `tests/performance/baseline.py` | 测试 |
| W1 D3-4 | T-002 | 实施 Prometheus + Grafana 监控 | `docker-compose.monitoring.yml` | 运维 |
| W1 D5 | T-003 | 建立覆盖率采集流水线 | `.github/workflows/coverage.yml` | DevOps |
| W2 D1-3 | T-004 | 编写《系统现状基线报告》 | `docs/BASELINE_REPORT.md` | 全员 |
| W2 D4-5 | T-005 | 制定 KPI 验收脚本 | `scripts/verify_kpis.py` | 测试 |

**阶段 1 验收**: 所有 KPI 当前值已采集并文档化。

#### **阶段 2: P0 紧急修复 (Week 3-4) - "治病"**

| 时间 | 任务 ID | 任务内容 | 关联 KPI | 优先级 |
|------|---------|----------|----------|--------|
| W3 D1-2 | T-101 | 拆分健康检查端点 (Live/Ready) | PF-04 | P0 |
| W3 D3-4 | T-102 | 修复前端 4 处单元测试失败 | ST-02 | P0 |
| W3 D5 | T-103 | Docker 多阶段构建 + 镜像瘦身 | RS-01 | P0 |
| W4 D1-3 | T-104 | 模型推理异步化 + LRU 缓存 | PF-05 | P0 |
| W4 D4-5 | T-105 | 修复 High 依赖漏洞 ×3 | SC-02 | P0 |

**阶段 2 验收**: P0-01/02/03 全部修复，所有 P0 任务 [x]。

#### **阶段 3: 性能与稳定性提升 (Week 5-8) - "强身"**

| 时间 | 任务 ID | 任务内容 | 关联 KPI | 优先级 |
|------|---------|----------|----------|--------|
| W5 D1-3 | T-201 | 数据库索引补全 + 连接池调优 | PF-01/02 | P0 |
| W5 D4-5 | T-202 | 数据库慢查询日志接入 | PF-01 | P1 |
| W6 D1-3 | T-203 | 监控告警规则扩展 (业务指标) | ST-05 | P1 |
| W6 D4-5 | T-204 | 前端 ECharts 按需引入 + 代码分割 | RS-06 | P1 |
| W7 D1-3 | T-205 | OWASP Top 10 补齐 (A05/A07/A10) | SC-03 | P1 |
| W7 D4-5 | T-206 | API 限流分级配置 | SC-03 | P1 |
| W8 D1-3 | T-207 | joblib 升级 + 模型重序列化 | RS-07 | P1 |
| W8 D4-5 | T-208 | Web Vitals 前端监控集成 | PF-07/08 | P1 |

**阶段 3 验收**: 性能 KPI 达成 60%，P1 任务完成 80%。

#### **阶段 4: 完善与交付 (Week 9-12) - "收官"**

| 时间 | 任务 ID | 任务内容 | 关联 KPI | 优先级 |
|------|---------|----------|----------|--------|
| W9 D1-3 | T-301 | 压力测试 + 容量规划 | ST-04 | P1 |
| W9 D4-5 | T-302 | 故障演练 + 应急预案 | ST-06 | P2 |
| W10 D1-3 | T-303 | 测试覆盖率采集 (后端 70%+) | MN-01 | P1 |
| W10 D4-5 | T-304 | 测试覆盖率采集 (前端 60%+) | MN-02 | P1 |
| W11 D1-3 | T-305 | 模块循环依赖治理 | MN-07 | P1 |
| W11 D4-5 | T-306 | 文档国际化补全 (en-US 100%) | MN-09 | P2 |
| W12 D1-3 | T-307 | 编写《系统优化总结报告》 | - | 全员 |
| W12 D4-5 | T-308 | 答辩演示 + 成果汇报 | - | 全员 |

**阶段 4 验收**: 所有 KPI 达标，文档齐全，可演示可答辩。

### 4.3 关键路径 (Critical Path)

```
T-001 (基线) → T-101 (健康检查) → T-104 (模型加速) → T-201 (DB优化) → T-301 (压测) → T-307 (报告)
   ↓             ↓                  ↓                  ↓                ↓             ↓
  W1            W3                 W4                 W5              W9            W12
```

---

## 5. 资源需求与分配方案

### 5.1 人力资源分配

| 角色 | 人员 | 主要职责 | 工作量占比 |
|------|------|----------|------------|
| **项目经理 (PM)** | 1 人 | 协调进度、风险把控、文档审核 | 25% (12 周) |
| **后端工程师 (BE)** | 1 人 | 性能优化、安全加固、数据库调优 | 80% (W1-W8) |
| **前端工程师 (FE)** | 1 人 | 前端测试修复、性能调优、覆盖率 | 70% (W1-W10) |
| **ML 工程师** | 1 人 | 模型加速、joblib 升级、推理优化 | 40% (W3-W8) |
| **测试工程师 (QA)** | 1 人 | 基线采集、压测、验收脚本 | 60% (W1-W11) |
| **运维工程师 (Ops)** | 1 人 | Docker、监控、CI/CD | 50% (W1-W9) |
| **论文撰写** | 1 人 (作者) | 报告、文档、答辩 | 30% (W11-W12) |

> 注: 鉴于毕业设计单人完成的可能性，本计划支持单人模式：将 BE/FE/ML/QA/PM 职责合并，通过延长工期 (16-20 周) 达成相同目标。

### 5.2 计算与基础设施资源

| 资源类型 | 配置 | 用途 | 月度成本 (估) |
|----------|------|------|---------------|
| **开发机** | 8C16G Windows/Linux | 本地开发、单元测试 | 0 (自有) |
| **测试服务器** | 4C8G Linux (Docker) | 集成测试、性能压测 | ¥0 (本地) |
| **CI 资源** | GitHub Actions 免费额度 | CI/CD、Lighthouse | ¥0 (学生包) |
| **监控栈** | Prometheus + Grafana (Docker) | 指标采集、可视化 | ¥0 (本地) |
| **生产环境 (示例)** | 2C4G × 2 节点 | 演示部署 | ¥100-300/月 (云) |

**Docker 资源清单**:
```yaml
# docker-compose.yml (新增监控服务)
services:
  prometheus:
    image: prom/prometheus:latest
    volumes: ['./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml']
    ports: ['9090:9090']
  grafana:
    image: grafana/grafana:latest
    ports: ['3000:3000']
  node-exporter:
    image: prom/node-exporter:latest
    ports: ['9100:9100']
```

### 5.3 第三方工具与服务

| 工具 | 用途 | 费用 | 必要性 |
|------|------|------|--------|
| Codecov | 覆盖率可视化 | 免费 (开源) | 强烈推荐 |
| Snyk | 依赖漏洞扫描 | 免费 (学生) | 推荐 |
| SonarCloud | 代码质量 | 免费 (开源) | 可选 |
| Locust / k6 | 压测工具 | 免费 | 必须 |
| Locust Web UI | 压测可视化 | 免费 | 推荐 |

### 5.4 培训与知识储备

| 时间 | 内容 | 形式 | 时长 |
|------|------|------|------|
| W1 | Prometheus + Grafana 基础 | 官方文档 + 视频 | 4h |
| W2 | Locust 压测实战 | 实操演练 | 2h |
| W3 | OWASP Top 10 速览 | 培训材料 | 2h |
| W5 | FastAPI 性能调优技巧 | 代码评审 | 3h |

---

## 6. 风险评估与应对措施

### 6.1 风险矩阵 (Risk Matrix)

| 风险 ID | 风险描述 | 概率 | 影响 | 等级 | 应对策略 | 负责人 |
|---------|----------|------|------|------|----------|--------|
| **R-01** | 健康检查重构引入回归 | 中 | 高 | 🔴 高 | (1) 保留旧端点 1 周灰度；(2) 同步更新 K8s 配置；(3) 增加端到端探针测试 | BE |
| **R-02** | 模型加速破坏预测一致性 | 中 | 高 | 🔴 高 | (1) 缓存结果与原始结果并行比对 1 周；(2) 保留原同步接口作为 fallback | ML |
| **R-03** | Docker 多阶段构建破坏依赖链 | 中 | 中 | 🟡 中 | (1) CI 必须在三种 Python 版本 (3.10/3.11/3.12) 通过；(2) 保留原 Dockerfile 作 .backup | Ops |
| **R-04** | 测试覆盖率提升与新功能冲突 | 高 | 低 | 🟡 中 | (1) 覆盖率门禁仅对新增代码；(2) 不强制历史代码补齐 | QA |
| **R-05** | 优化工作与论文撰写时间冲突 | 中 | 中 | 🟡 中 | (1) 提前 2 周开始论文素材整理；(2) 关键数据在 W4 即落表 | PM |
| **R-06** | Windows 环境限制 (exit -1073741510) | 高 | 中 | 🟡 中 | (1) 关键测试迁 Linux/CI；(2) 标记 [-] 不阻塞主流程 | DevOps |
| **R-07** | 第三方依赖升级引入 break change | 中 | 中 | 🟡 中 | (1) 锁定 minor 版本；(2) 灰度升级；(3) 准备降级方案 | BE/FE |
| **R-08** | 性能优化反而引入新 bug | 中 | 高 | 🔴 高 | (1) 每个优化项必须配测试用例；(2) 灰度发布；(3) 自动回滚 | QA |
| **R-09** | 监控指标采集影响生产性能 | 低 | 中 | 🟢 低 | (1) 采样率 ≤ 10%；(2) 异步批上报 | Ops |
| **R-10** | 毕业答辩时间提前 | 低 | 高 | 🟡 中 | (1) W8 即产出可演示版本；(2) 准备 3 套降级方案 | PM |
| **R-11** | 监控告警误报导致 On-call 疲劳 | 中 | 中 | 🟡 中 | (1) 告警分级 (P0/P1/P2)；(2) 静默期机制；(3) 定期回顾 | Ops |
| **R-12** | 资源 (云服务器) 成本超预算 | 中 | 低 | 🟢 低 | (1) 优先使用本地 + 免费服务；(2) 按需弹性伸缩 | PM |

### 6.2 风险应对预案

#### R-01 健康检查重构失败

```yaml
# 灰度发布计划
Phase 1 (W3 D1-2): 部署 /health/live, /health/ready (双端点并行)
Phase 2 (W3 D3-4): K8s probe 切换至新端点
Phase 3 (W3 D5): 监控稳定后移除旧 /health (保留 1 周观察期)
Phase 4 (W4): 完全移除旧端点
回滚条件: 新端点 P95 > 200ms 或 K8s Pod 频繁重启
回滚步骤: 1) 切换 probe 路径；2) 触发 kubectl rollout undo
```

#### R-02 模型加速破坏一致性

```python
# 影子模式 (Shadow Mode)
async def predict_with_shadow(features):
    # 新实现
    new_result = await engine_v2.predict_async(features)
    # 旧实现
    old_result = await engine_v1.predict_sync(features)
    # 比对
    if abs(new_result.score - old_result.score) > 0.05:
        logger.warning("prediction.divergence", extra={...})
        metrics.increment("prediction.shadow.divergence")
    return new_result  # 仍返回新结果用于验证
```

### 6.3 应急预案 (Contingency)

| 故障场景 | 检测信号 | 响应时间 | 处理 SOP |
|----------|----------|----------|----------|
| API 5xx 飙升 | Sentry 告警 | < 5min | 1) 启用维护模式；2) 定位异常服务；3) 回滚至上一版本 |
| 数据库连接耗尽 | pg_stat_activity > 90% | < 10min | 1) 限流降级；2) 重启连接池；3) 排查慢查询 |
| 模型推理超时 | P95 > 2s | < 15min | 1) 切回同步推理；2) 清理 Redis 缓存；3) 重启 worker |
| 镜像拉取失败 | K8s ImagePullBackOff | < 20min | 1) 切换镜像源；2) 拉取本地缓存；3) 回滚镜像版本 |

---

## 7. 质量保障与验收标准

### 7.1 质量门禁 (Quality Gates)

#### 7.1.1 CI 流水线门禁

```yaml
# .github/workflows/pr-quality-gates.yml
name: PR Quality Gates
on: [pull_request]
jobs:
  backend:
    steps:
      - run: pytest --cov-fail-under=70
      - run: ruff check .
      - run: mypy app/
  frontend:
    steps:
      - run: npm run typecheck
      - run: npm run lint
      - run: npm run test:coverage
  security:
    steps:
      - run: npm audit --audit-level=high
      - run: pip-audit
      - uses: trufflesecurity/trufflehog@main
  contract:
    steps:
      - run: pytest tests/contract/  # OpenAPI 一致性
  e2e:
    steps:
      - run: npx playwright test
```

#### 7.1.2 上线前检查清单 (Pre-launch Checklist)

- [ ] 所有 P0 任务 [x]
- [ ] P1 任务完成率 > 80%
- [ ] 后端测试覆盖率 ≥ 70%
- [ ] 前端测试覆盖率 ≥ 60%
- [ ] npm audit / pip-audit 无 High+
- [ ] Lighthouse Performance ≥ 80
- [ ] API 响应 P95 < 500ms
- [ ] 健康检查 P95 < 100ms
- [ ] E2E 全角色流程通过
- [ ] 监控告警规则已部署
- [ ] 回滚方案演练通过
- [ ] 文档 CHANGELOG 已更新

### 7.2 验收标准 (Acceptance Criteria)

#### 7.2.1 性能验收

| 指标 | 验收方法 | 通过标准 |
|------|----------|----------|
| API P50 < 200ms | Locust 100 并发持续 5min | 95% 请求达标 |
| 健康检查 < 100ms | `time curl /health/live` × 100 | 中位数 < 100ms |
| 模型预测 < 300ms | pytest-benchmark 1000 次 | 中位数 < 300ms |
| 首屏 FCP < 800ms | Lighthouse CI 3 次平均 | < 800ms |

#### 7.2.2 稳定性验收

| 指标 | 验收方法 | 通过标准 |
|------|----------|----------|
| 后端测试 | `pytest` | 100% 通过 |
| 前端测试 | `npm test` | ≥ 98% 通过 |
| E2E 测试 | `playwright test` | 3/3 角色全通过 |
| 7×24h 稳定性 | Soak test | 内存泄漏 < 5%/h，错误率 < 0.01% |

#### 7.2.3 安全验收

| 指标 | 验收方法 | 通过标准 |
|------|----------|----------|
| 依赖漏洞 | npm audit + pip-audit | 无 Critical/High |
| SQL 注入 | sqlmap 自动化扫描 | 0 发现 |
| XSS | OWASP ZAP 扫描 | 0 High |
| 密钥泄漏 | git-secrets + TruffleHog | 0 发现 |

### 7.3 验收测试矩阵

| 测试类型 | 工具 | 频次 | 通过标准 | 失败处理 |
|----------|------|------|----------|----------|
| 单元测试 | pytest / vitest | 每次 PR | 100% (核心) / ≥98% (整体) | 阻塞合并 |
| 集成测试 | pytest (api/) | 每次 PR | 100% | 阻塞合并 |
| 契约测试 | pytest (contract/) | 每次 PR | 100% | 阻塞合并 |
| E2E 测试 | Playwright | 每日 + 合并 main | 100% | 阻塞发布 |
| 性能测试 | Locust / k6 | 每周 | 达标 | 警告，2 周未改善则阻塞 |
| 安全扫描 | npm audit / Snyk | 每次 PR | 0 High+ | 阻塞合并 |
| 代码质量 | ruff / ESLint | 每次 PR | 0 错误 | 阻塞合并 |
| 类型检查 | mypy / tsc | 每次 PR | 0 错误 | 阻塞合并 |

---

## 8. 预期效果评估

### 8.1 量化效果预测 (Quantitative Forecast)

#### 8.1.1 性能提升预测

```
指标                      当前      目标       提升幅度
─────────────────────────────────────────────────────
API 平均响应              430ms  →  180ms     ↓ 58%
健康检查响应              8000ms →  80ms      ↓ 99%
模型预测耗时              540ms  →  280ms     ↓ 48%
E2E 关键流程              1.9s   →  1.3s      ↓ 32%
首屏 FCP                  1.2s   →  0.7s      ↓ 42%
镜像体积                  2.8GB  →  1.0GB     ↓ 64%
前端主 chunk (gzip)       280KB  →  180KB     ↓ 36%
```

#### 8.1.2 稳定性提升预测

```
指标                      当前      目标       提升幅度
─────────────────────────────────────────────────────
前端测试通过率            92.7%  →  98%       ↑ 5.3pp
后端覆盖率                未采集 →  70%+      (新增)
前端覆盖率                未采集 →  60%+      (新增)
错误率 (5xx)              ~0.1%  →  <0.05%    ↓ 50%
告警覆盖度                30%    →  90%       ↑ 60pp
```

#### 8.1.3 安全提升预测

```
指标                      当前      目标       提升幅度
─────────────────────────────────────────────────────
Critical 漏洞             0      →  0         维持
High 漏洞                 3      →  0         ↓ 100%
OWASP 覆盖率              7/10   →  10/10     ↑ 30%
密钥泄漏检测              未配置 →  CI 强制   (新增)
```

### 8.2 定性效果预测 (Qualitative Forecast)

| 维度 | 优化前 | 优化后 |
|------|--------|--------|
| **用户感知** | 健康检查超时偶发、模型预测偶有卡顿 | 全流程 < 1.5s，体验流畅 |
| **运维效率** | 故障发现靠用户反馈 | 5min 内自动告警 |
| **开发体验** | 前端测试失败阻塞 CI | 全部绿灯，快速反馈 |
| **代码质量** | 缺乏覆盖率数据，难以评估 | 覆盖率门禁，回归保护 |
| **安全态势** | 漏洞依赖存在 | 持续扫描，0 高危 |
| **论文价值** | 仅有功能实现案例 | 完整的"上线后优化迭代"案例 |

### 8.3 ROI 分析 (投入产出比)

| 投入 | 数值 |
|------|------|
| 人力 (单人 12 周 × 30% 工时) | ~180 工时 |
| 计算资源 (云) | ¥100-300 |
| 第三方服务 | ¥0 (使用免费额度) |
| **总投入** | **~¥200 + 180 工时** |

| 产出 | 价值 |
|------|------|
| 性能提升 50%+ | 用户体验显著改善 |
| 故障恢复时间 < 15min | 减少业务损失 |
| 100% 测试覆盖率门禁 | 长期质量保障 |
| 完整监控告警体系 | 运维效率提升 3-5× |
| 毕业论文学术价值 | 答辩竞争力 +30% |

**结论**: 投入产出比极高 (ROI > 10:1)，强烈建议执行。

---

## 9. 附录

### 附录 A: 详细任务清单 (Backlog)

| 任务 ID | 阶段 | 标题 | 估时 | 状态 |
|---------|------|------|------|------|
| T-001 | 准备 | 性能基线框架 | 1d | [ ] |
| T-002 | 准备 | Prometheus 部署 | 2d | [ ] |
| T-003 | 准备 | 覆盖率流水线 | 1d | [ ] |
| T-004 | 准备 | 基线报告 | 3d | [ ] |
| T-005 | 准备 | KPI 验收脚本 | 2d | [ ] |
| T-101 | P0 | 健康检查拆分 | 2d | [ ] |
| T-102 | P0 | 前端测试修复 | 2d | [ ] |
| T-103 | P0 | Docker 镜像瘦身 | 1d | [ ] |
| T-104 | P0 | 模型异步化 | 3d | [ ] |
| T-105 | P0 | 依赖漏洞修复 | 1d | [ ] |
| T-201 | P1 | DB 索引 + 连接池 | 3d | [ ] |
| T-202 | P1 | 慢查询日志 | 2d | [ ] |
| T-203 | P1 | 监控告警扩展 | 3d | [ ] |
| T-204 | P1 | ECharts 按需 | 2d | [ ] |
| T-205 | P1 | OWASP 补齐 | 3d | [ ] |
| T-206 | P1 | API 限流分级 | 2d | [ ] |
| T-207 | P1 | joblib 升级 | 1d | [ ] |
| T-208 | P1 | Web Vitals 集成 | 2d | [ ] |
| T-301 | 压测 | Locust 压测 | 3d | [ ] |
| T-302 | 压测 | 故障演练 | 2d | [ ] |
| T-303 | 覆盖 | 后端覆盖率 | 3d | [ ] |
| T-304 | 覆盖 | 前端覆盖率 | 3d | [ ] |
| T-305 | 治理 | 循环依赖 | 3d | [ ] |
| T-306 | 治理 | 文档国际化 | 2d | [ ] |
| T-307 | 收官 | 优化报告 | 3d | [ ] |
| T-308 | 收官 | 答辩演示 | 2d | [ ] |

**任务统计**: 总计 26 个任务，总估时 58 人日。

### 附录 B: 监控仪表盘设计

**主仪表盘 (Operations Overview)**:
- 面板 1: API QPS / 错误率 (5min/1h/24h)
- 面板 2: 响应时间分布 (P50/P95/P99)
- 面板 3: 健康检查延迟
- 面板 4: 数据库连接池使用
- 面板 5: Redis 命中率
- 面板 6: Celery 队列长度
- 面板 7: 模型推理耗时
- 面板 8: 活跃用户数

**业务仪表盘 (Business Metrics)**:
- 面板 1: 风险评估提交数
- 面板 2: 预警触发数 (按等级)
- 面板 3: 咨询师响应时间
- 面板 4: 用户活跃度 (DAU/WAU)
- 面板 5: 干预任务完成率

### 附录 C: 工具链与命令速查

```bash
# 性能测试
cd backend && locust -f tests/performance/locustfile.py --host=http://localhost:8000

# 覆盖率
cd backend && pytest --cov=app --cov-report=html
cd frontend && npm run test:coverage

# 安全审计
npm audit --audit-level=high
pip-audit

# 镜像分析
docker images backend:latest
docker history backend:latest --human --format "{{.Size}}\t{{.CreatedBy}}"
dive backend:latest  # 交互式分析

# 依赖关系
npx madge --circular --extensions ts,vue frontend/src/
pydeps backend/app --show-deps

# 健康检查验证
time curl -s http://localhost:8000/health/live
time curl -s http://localhost:8000/health/ready
```

### 附录 D: 参考资料

1. **FastAPI 性能调优**: <https://fastapi.tiangolo.com/deployment/concepts/>
2. **Vue 3 性能指南**: <https://vuejs.org/guide/best-practices/performance.html>
3. **OWASP Top 10 2021**: <https://owasp.org/Top10/>
4. **SRE Workbook - SLI/SLO**: <https://sre.google/workbook/table-of-contents/>
5. **Prometheus 最佳实践**: <https://prometheus.io/docs/practices/>
6. **PostgreSQL 性能调优**: <https://wiki.postgresql.org/wiki/Performance_Optimization>
7. **Vue.js 性能优化 (本项目历史报告)**: `docs/performance-evaluation-report.md`
8. **Ralph 执行铁律**: `.trae/rules/Ralph.md`

### 附录 E: 变更日志

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|----------|------|
| v1.0 | 2026-06-01 | 初版发布 | AI Assistant |

---

## 文档结束

> **执行原则 (源自 Ralph 铁律)**:
> 1. **物理顺序优先** - 按本文档附录 A 的顺序执行，严禁跳步
> 2. **测试即交付** - 每个优化项必须配测试，PASS 才算完成
> 3. **状态真实性** - 任务完成后立即更新 `[ ] → [x]`
> 4. **上线优先** - P0 全部 [x] 前不允许进入 P1 集中执行
> 5. **可回滚** - 每个上线优化项必须有回滚方案
>
> **下一步行动**:
> 1. 评审本文档
> 2. 在 `docs/planning/v1.29-system-optimization/` 创建对应的 `04-ralph-tasks.md` 和 `05-test-plan.md`
> 3. 按 T-001 → T-005 开始阶段 1 任务
