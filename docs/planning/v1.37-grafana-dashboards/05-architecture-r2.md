# v1.37 Grafana 仪表盘模板 — Round 2 架构 (Draft)

> **迭代**: v1.37-grafana-dashboards
> **日期**: 2026-06-03
> **状态**: 🔄 R2 Draft (架构修订)
> **基于**: R1 Lock (01-requirements / 02-research / 03-simulation)
> **目标**: 在 v1.36 之上最小化补丁, 增加 Grafana Adapter 路由 + SA 鉴权

---

## 1. 系统架构 (R2 修订)

### 1.1 总体架构图

```
┌──────────────────┐         ┌────────────────────────────────────────────┐
│   Grafana 11.6   │  HTTPS  │   Backend (v1.36 + v1.37 patch)            │
│                  │ ──────► │                                            │
│ ┌──────────────┐ │         │ ┌──────────────────────────────────────┐   │
│ │  Dashboard   │ │         │ │  v1.36 (existing)                    │   │
│ │  JSON Panel  │ │ Bearer  │ │  /alerts/observability/{trend, ...}  │   │
│ │  Targets     │ │ Token   │ │  require_role("admin")               │   │
│ └──────┬───────┘ │         │ │  (8 端点, 已有)                       │   │
│        │ POST    │         │ └──────────────────────────────────────┘   │
│        ▼         │         │ ┌──────────────────────────────────────┐   │
│ ┌──────────────┐ │         │ │  v1.37 patch (new)                   │   │
│ │ simpod-json- │ │         │ │  /grafana/health     (GET)            │   │
│ │ datasource   │ │         │ │  /grafana/metrics    (POST)           │   │
│ │ (plugin)     │ │         │ │  /grafana/query      (POST)           │   │
│ └──────────────┘ │         │ │  /grafana/variable   (POST)           │   │
│                  │         │ │  require_sa_or_admin()                │   │
└──────────────────┘         │ │  (4 端点 + 1 依赖, 新增)                │   │
                             │ └──────────────────────────────────────┘   │
                             └────────────────────────────────────────────┘
```

### 1.2 关键架构决策 (R2 锁定)

| 决策 | 选型 | 理由 |
|:---|:---|:---|
| **Adapter 位置** | 同进程 (FastAPI 子路由) | 低延迟, 无网络跳转, 复用 DB session |
| **鉴权依赖** | `require_sa_or_admin()` 新依赖 | 优先级: SA Token → Admin User → 401 |
| **POST body 格式** | JSON `{"metric": "trend", "params": {...}}` | 复用 JSON Datasource 插件标准 |
| **缓存策略** | 复用 v1.36 `cached_or_compute` (5min) | 仪表盘 1m refresh → 5min 缓存命中 |
| **变量端点** | `/grafana/variable` 统一返回 `{text, value}[]` | 兼容 Grafana variable query 类型 |

### 1.3 与 v1.36 的兼容性

**v1.36 minor patch 必须**:
- ✅ 不修改 v1.36 现有 8 个 REST 端点
- ✅ 不修改 v1.36 现有依赖函数
- ✅ 不修改 v1.36 数据库 schema
- ✅ 不破坏 v1.36 224 个测试

**v1.37 patch 仅新增**:
- 4 个新路由 (`/grafana/*`)
- 1 个新鉴权依赖 (`require_sa_or_admin`)
- 1 个新配置 (`GRAFANA_SERVICE_TOKEN` env var)
- 1 个新文件 (`app/api/v1/grafana_adapter.py`)
- 1 个新测试文件 (`tests/api/test_grafana_adapter.py`)

---

## 2. 文件级设计 (R2 详细)

### 2.1 新增文件 (2 个)

#### 📄 `backend/app/api/v1/grafana_adapter.py` (~150 行)

```python
"""v1.37: Grafana JSON Datasource Adapter 路由.

4 个 RPC 端点, 复用 v1.36 _compute_* 函数:
- GET  /grafana/health         → Test connection
- POST /grafana/metrics        → 可用 metric 列表
- POST /grafana/query          → panel 数据 (主)
- POST /grafana/variable       → 变量 query 数据

鉴权: require_sa_or_admin (支持 SA Token + Admin User)
"""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.deps import require_sa_or_admin
from app.api.v1.observability import (
    _compute_trend, _compute_response_time, _compute_escalation,
    _compute_channel_stats, _compute_silence_hit_rate,
    _compute_am_sync, _compute_lock_stats,
)
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/grafana", tags=["grafana-adapter"])


# ===== Request/Response Schemas =====

class GrafanaQueryRequest(BaseModel):
    """JSON Datasource /query 端点的标准 body."""
    metric: str  # trend / response_time / escalation / channel_stats / silence_hit_rate / am_sync / lock_stats
    params: dict = {}  # start_time, end_time, severity, group_by, top_n, etc.


class GrafanaVariableRequest(BaseModel):
    """JSON Datasource /variable 端点的标准 body."""
    type: str  # rule / matcher / operation / channel


# ===== 端点 1: Health Check =====

@router.get("/health")
async def grafana_health() -> dict:
    """JSON Datasource 'Test connection' 用. 返回 200 + 元数据."""
    return {
        "status": "ok",
        "version": "v1.37",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ===== 端点 2: Metrics List =====

@router.post("/metrics")
async def grafana_metrics() -> list[dict]:
    """返回可用 metric 列表 (供 panel 配置时选择)."""
    return [
        {"value": "trend", "label": "Alert Trend", "payloads": [
            {"name": "bucket", "type": "select", "options": [
                {"label": "5min", "value": "5m"},
                {"label": "1hour", "value": "1h"},
                {"label": "6hour", "value": "6h"},
                {"label": "1day", "value": "1d"},
            ]},
            {"name": "severity", "type": "select", "options": [
                {"label": "P0", "value": "P0"}, {"label": "P1", "value": "P1"},
                {"label": "P2", "value": "P2"}, {"label": "P3", "value": "P3"},
                {"label": "all", "value": "all"},
            ]},
            {"name": "group_by", "type": "select", "options": [
                {"label": "status", "value": "status"},
                {"label": "severity", "value": "severity"},
                {"label": "rule", "value": "rule"},
            ]},
        ]},
        {"value": "response_time", "label": "Response Time", "payloads": [...]},
        # ... 其他 5 个 metric
    ]


# ===== 端点 3: Query (主端点) =====

@router.post("/query")
async def grafana_query(
    req: GrafanaQueryRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_sa_or_admin),
) -> list[dict]:
    """panel 数据查询. 根据 metric 分发到 v1.36 _compute_* 函数."""
    handler = _METRIC_HANDLERS.get(req.metric)
    if not handler:
        raise HTTPException(400, f"unknown metric: {req.metric}")
    result = await handler(db, req.params)
    return _format_for_grafana(result, req.metric, req.params)


_METRIC_HANDLERS = {
    "trend": _trend_handler,
    "response_time": _response_time_handler,
    # ... 其他 5 个
}
```

#### 📄 `backend/tests/api/test_grafana_adapter.py` (~250 行)

```python
"""v1.37 Grafana Adapter 单元测试.

测试矩阵:
- test_health_returns_200
- test_metrics_lists_7_metrics
- test_query_trend
- test_query_response_time
- test_query_escalation
- test_query_channel_stats
- test_query_silence_hit_rate
- test_query_am_sync
- test_query_lock_stats
- test_query_unknown_metric_400
- test_query_no_auth_401
- test_query_with_sa_token_200
- test_query_with_admin_user_200
- test_variable_rule_returns_top20
- test_variable_matcher_returns_top10
- test_variable_operation_returns_all
- test_v136_8_endpoints_still_work (regression)
"""
```

### 2.2 修改文件 (3 个)

#### 📝 `backend/app/core/deps.py` (+30 行)

在文件末尾新增依赖:

```python
async def require_sa_or_admin(
    token: str = Depends(oauth2_scheme),
) -> User:
    """支持 Service Account Token 或 Admin User.
    
    优先级:
    1. 如果 token == settings.GRAFANA_SERVICE_TOKEN → 返回虚拟 admin User
    2. 否则调用 get_current_user(token) → Admin User
    """
    from app.core.config import settings
    if settings.GRAFANA_SERVICE_TOKEN and token == settings.GRAFANA_SERVICE_TOKEN:
        return User(
            id=0,
            email="grafana-service-account@bysj.local",
            role="admin",
            is_active=True,
        )
    return await get_current_user(token)
```

#### 📝 `backend/app/core/config.py` (+5 行)

在 `Settings` 类中新增:

```python
class Settings(BaseSettings):
    # ... 现有字段 ...
    
    # v1.37: Grafana Service Account Token
    # 用于 Grafana JSON Datasource 调用 v1.36 后端时的鉴权
    # 留空表示禁用 (无 SA 鉴权, 走 Admin User 路径)
    grafana_service_token: str | None = None
```

#### 📝 `backend/app/api/v1/router.py` (+3 行)

注册 Grafana Adapter 路由:

```python
from app.api.v1 import grafana_adapter

# ... 现有路由注册 ...
api_router.include_router(grafana_adapter.router, prefix="/alerts/observability")
```

### 2.3 不修改文件 (R2 关键 - 不破坏 v1.36)

- ❌ `app/api/v1/observability.py` (v1.36 端点, 不变)
- ❌ `app/models/admin.py` (OperationLog schema, 不变)
- ❌ `app/monitoring/notifier.py` (v1.36 业务逻辑, 不变)
- ❌ `app/monitoring/am_sync.py` (v1.36 业务逻辑, 不变)
- ❌ `app/monitoring/dedup_lock.py` (v1.36 业务逻辑, 不变)
- ❌ `alembic/versions/*.py` (无 schema 变更)
- ❌ 224 个 v1.36 测试 (全部应继续通过)

---

## 3. Grafana Adapter 详细规范

### 3.1 端点契约

| 端点 | 方法 | 请求体 | 响应 | 用途 |
|:---|:---:|:---|:---|:---|
| `/grafana/health` | GET | - | `{status, version, timestamp}` | Test connection |
| `/grafana/metrics` | POST | `{}` | `[{value, label, payloads}, ...]` | Panel 配置时选 metric |
| `/grafana/query` | POST | `{metric, params}` | Grafana dataframe 格式 | Panel 数据查询 (主) |
| `/grafana/variable` | POST | `{type}` | `[{text, value}, ...]` | 变量 query 类型 |

### 3.2 7 个 metric 处理器

```python
async def _trend_handler(db, params):
    """分发到 v1.36 _compute_trend."""
    return await _compute_trend(
        db,
        start=params["start_time"],
        end=params["end_time"],
        bucket=params.get("bucket", "1h"),
        severity=params.get("severity"),
        status=params.get("status"),
        group_by=params.get("group_by", "status"),
    )

# 其他 6 个类似...
```

### 3.3 Grafana dataframe 格式

JSON Datasource 期望的响应格式 (简化版):

```json
[
  {
    "target": "alert_fired",
    "datapoints": [
      [123, 1622548800000],
      [456, 1622548860000]
    ]
  },
  {
    "target": "alert_resolved",
    "datapoints": [
      [10, 1622548800000]
    ]
  }
]
```

`_format_for_grafana()` 函数将 v1.36 `_compute_*` 的输出 (含 buckets) 转换为 Grafana dataframe。

### 3.4 变量端点

```python
@router.post("/variable")
async def grafana_variable(req: GrafanaVariableRequest, db, _user):
    if req.type == "rule":
        # 返回 top 20 规则
        result = await _compute_trend(
            db, start=..., end=..., bucket="1h", group_by="rule", top_n=20
        )
        return [{"text": r, "value": r} for r in result["by_rule"]]
    elif req.type == "matcher":
        # 返回 top 10 matcher
        ...
    elif req.type == "operation":
        # 静态
        return [
            {"text": "all", "value": "all"},
            {"text": "push_silence", "value": "push_silence"},
            {"text": "expire_silence", "value": "expire_silence"},
        ]
    elif req.type == "channel":
        return [
            {"text": "all", "value": "all"},
            {"text": "webhook", "value": "webhook"},
            {"text": "slack", "value": "slack"},
            {"text": "dingtalk", "value": "dingtalk"},
            {"text": "email", "value": "email"},
        ]
```

---

## 4. 部署架构 (R2 修订)

### 4.1 docker-compose.yml 增量

```yaml
services:
  # ... 现有 backend/redis/postgres ...
  
  grafana:
    image: grafana/grafana:11.6.0
    container_name: bysj-grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:-admin}
      - GF_USERS_ALLOW_SIGN_UP=false
      - GF_AUTH_ANONYMOUS_ENABLED=false
      - GF_PLUGINS_PREINSTALL=simpod-json-datasource
    volumes:
      - ./infra/grafana/provisioning:/etc/grafana/provisioning:ro
      - ./infra/grafana/dashboards:/var/lib/grafana/dashboards:ro
    depends_on:
      - backend
    networks:
      - bysj-net
```

### 4.2 Provisioning 文件 (3 个)

#### 📄 `infra/grafana/provisioning/datasources/observability-api.yaml`

```yaml
apiVersion: 1

datasources:
  - name: Observability API
    type: simpod-json-datasource
    access: proxy
    url: http://backend:8000/api/v1/alerts/observability
    isDefault: true
    jsonData:
      tlsSkipVerify: false
    secureJsonData:
      Authorization: Bearer ${GRAFANA_SA_TOKEN}
```

#### 📄 `infra/grafana/provisioning/dashboards/v1.37-alerts.yaml`

```yaml
apiVersion: 1

providers:
  - name: 'v1.37 Alerts Overview'
    orgId: 1
    folder: 'Observability'
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
      foldersFromFilesStructure: true
```

#### 📄 `infra/grafana/dashboards/v1.37-alerts-overview.json`

主仪表盘 JSON, 由 `03-simulation-r1.py` 生成的样例基础上扩展。

### 4.3 .env 增量

```bash
# v1.37: Grafana 配置
GRAFANA_ADMIN_PASSWORD=changeme
GRAFANA_SA_TOKEN=<32-char random string>
# 后端 .env 需同步:
GRAFANA_SERVICE_TOKEN=<same 32-char string>
```

---

## 5. 测试架构 (R2 修订)

### 5.1 单元测试 (P0)

| 测试 | 数量 | 文件 |
|:---|:---:|:---|
| Grafana Adapter 端点测试 | 8 | `tests/api/test_grafana_adapter.py` |
| SA 鉴权路径测试 | 3 | `tests/api/test_grafana_auth.py` |
| v1.36 8 端点回归 | 8 | `tests/api/test_v136_regression.py` |
| **合计** | **19** | — |

### 5.2 集成测试 (P1, CI 专项)

| 测试 | 方式 | 触发 |
|:---|:---|:---|
| Grafana 容器启动 | `docker-compose up -d grafana` | CI step 1 |
| 仪表盘自动加载 | `curl /api/dashboards/uid/v137-alerts-overview` | CI step 2 |
| 21 panels 数据返回 | `for panel in 0..23; do curl ...` | CI step 3 |
| Provisioning 删除清理 | `rm *.yaml; docker restart` | CI step 4 |

### 5.3 性能测试 (P1)

| 测试 | 阈值 | 工具 |
|:---|:---:|:---|
| 首次加载 24 panels | < 3s | Grafana timing |
| 手动 refresh | < 2s | Grafana timing |
| 单 panel < 500ms | (v1.36 已验证) | 复用 v1.36 T3.2 |

---

## 6. 风险与缓解 (R2 修订)

| 风险 | 概率 | 影响 | 缓解 |
|:---|:---:|:---:|:---|
| v1.36 `_compute_*` 函数不返回 Grafana dataframe 格式 | 中 | 高 | 写适配器 `_format_for_grafana()` 转换 |
| SA Token 配置错误导致鉴权失败 | 中 | 高 | 测试覆盖 3 个鉴权场景 (有 token / 无 token / 错 token) |
| v1.36 patch 破坏现有测试 | 低 | 高 | 24 个 v1.36 关键测试加 CI 必跑 |
| Grafana 插件 `simpod-json-datasource` 安装失败 | 低 | 中 | 文档明确 `GF_PLUGINS_PREINSTALL` 环境变量 |
| 5min 缓存导致 panel stale | 中 | 低 | README 说明, 不在 panel 显示 |

---

## 7. Round 3 任务依赖图 (R2 草拟)

```
T-GRAF-001: 新增 deps.py::require_sa_or_admin
   ↓
T-GRAF-002: 新增 config.py::Settings.grafana_service_token
   ↓
T-GRAF-003: 新增 grafana_adapter.py 骨架 (4 路由)
   ↓
T-GRAF-004: 实现 /grafana/health
   ↓
T-GRAF-005: 实现 /grafana/metrics
   ↓
T-GRAF-006: 实现 /grafana/query (主, 7 metric 处理器)
   ↓
T-GRAF-007: 实现 /grafana/variable
   ↓
T-GRAF-008: 注册到 router.py
   ↓
T-GRAF-009: test_grafana_adapter.py (8 测试)
   ↓
T-GRAF-010: test_grafana_auth.py (3 测试)
   ↓
T-GRAF-011: test_v136_regression.py (8 测试)
   ↓
T-GRAF-012: provisioning YAML × 2
   ↓
T-GRAF-013: docker-compose 增量
   ↓
T-GRAF-014: .env 文档
   ↓
T-GRAF-015: README 编写
   ↓
T-GRAF-016: 端到端 docker 测试
```

**总计 16 任务**, 估时 6-8 小时。

---

> **Round 2 Step 1 完成**: 进入 Step 2 (Critique) - 自查架构合理性
