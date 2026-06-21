# v1.37 Round 3 Step 3 调研 (Research) — 实现细节

> **迭代**: v1.37-grafana-dashboards
> **日期**: 2026-06-03
> **目标**: 调研 v1.37 实施所需的关键实现细节 (Provisioning/Python 测试模板/simpod-json-datasource 安装)

---

## 1. simpod-json-datasource 插件 (P0)

### 1.1 安装方式

| 方式 | 命令 | 适用 |
|:---|:---|:---|
| **Provisioning (推荐)** | `GF_PLUGINS_PREINSTALL=simpod-json-datasource` 环境变量 | Docker |
| 手动 CLI | `docker exec -u root grafana grafana-cli plugins install simpod-json-datasource` | 调试 |
| 镜像预装 | `FROM grafana/grafana:11.6.0 && RUN grafana-cli plugins install simpod-json-datasource` | 自定义镜像 |

**✅ 决策**: 用 `GF_PLUGINS_PREINSTALL` (Provisioning 兼容, 容器启动时自动安装)

### 1.2 验证

```bash
docker exec grafana grafana-cli plugins ls | grep json
# 预期: simpod-json-datasource @ <version>
```

## 2. Provisioning 模板 (P0)

### 2.1 datasources 模板 (锁定)

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

### 2.2 dashboards 模板 (锁定)

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

### 2.3 dashboard JSON 路径

`/var/lib/grafana/dashboards/v1.37-alerts-overview.json`

## 3. Service Account Token 创建 (P0)

### 3.1 通过 Grafana API (CI 脚本)

```bash
# 1. 创建 SA
SA_RESPONSE=$(curl -s -u admin:${GRAFANA_ADMIN_PASSWORD} \
  -H "Content-Type: application/json" \
  -X POST http://localhost:3000/api/serviceaccounts \
  -d '{"name": "v1.37-observability", "role": "Viewer", "isDisabled": false}')
SA_ID=$(echo $SA_RESPONSE | jq -r '.id')

# 2. 创建 Token
TOKEN_RESPONSE=$(curl -s -u admin:${GRAFANA_ADMIN_PASSWORD} \
  -H "Content-Type: application/json" \
  -X POST http://localhost:3000/api/serviceaccounts/${SA_ID}/tokens \
  -d '{"name": "observability-api-token"}')
TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.key')

# 3. 写 .env
echo "GRAFANA_SA_TOKEN=${TOKEN}" >> .env
echo "GRAFANA_SERVICE_TOKEN=${TOKEN}" >> backend/.env
```

### 3.2 手动 (UI)

1. 登录 Grafana → Administration → Users and access → Service accounts
2. Add service account: name=`v1.37-observability`, role=`Viewer`
3. 在 SA 详情页 → Add token → name=`observability-api-token`
4. 复制 token (格式 `glsa_...`) → 写 .env

## 4. Python 测试模板 (P0)

### 4.1 test_grafana_auth.py 模板

```python
"""v1.37: Grafana SA 鉴权测试."""
import pytest
from app.core.config import settings


def test_auth_with_sa_token_correct(client, override_sa_token):
    """正确 SA Token 应返回 200."""
    response = client.get(
        "/api/v1/alerts/observability/grafana/health",
        headers={"Authorization": f"Bearer {settings.grafana_service_token}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_auth_with_sa_token_wrong(client):
    """错误 SA Token 应返回 401."""
    response = client.get(
        "/api/v1/alerts/observability/grafana/health",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401


def test_auth_with_no_token(client):
    """无 Authorization 头应返回 401."""
    response = client.get("/api/v1/alerts/observability/grafana/health")
    assert response.status_code == 401
```

### 4.2 test_grafana_adapter.py 模板

```python
"""v1.37: Grafana Adapter 端点测试."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


@pytest.fixture
def mock_db_with_trend():
    """Mock DB 返回 trend 数据."""
    rows = [(json.dumps({}), datetime(2026, 6, 3, tzinfo=timezone.utc))] * 100
    db = MagicMock()
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    db.execute = AsyncMock(return_value=mock_result)
    return db


def test_health_returns_200(client, as_role):
    as_role("admin", 3)
    response = client.get("/api/v1/alerts/observability/grafana/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "v1.37"


def test_query_trend_returns_dataframe(client, as_role, mock_db_with_trend):
    as_role("admin", 3)
    response = client.post(
        "/api/v1/alerts/observability/grafana/query"
        "?start_time=2026-06-03T00:00:00Z&end_time=2026-06-03T01:00:00Z&severity=all",
        json={"metric": "trend", "params": {"bucket": "1h"}},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert all("target" in s and "datapoints" in s for s in data)
```

## 5. .env.example 增量 (P0)

```bash
# v1.37 Grafana
GRAFANA_ADMIN_PASSWORD=changeme
GRAFANA_SA_TOKEN=
# 后端 .env 同步:
GRAFANA_SERVICE_TOKEN=
```

## 6. README 模板 (P0)

### 6.1 章节结构

1. 概述
2. 架构图
3. 部署方式 (手动 / Provisioning)
4. SA Token 创建
5. 仪表盘导入
6. 24 panels 介绍
7. 变量使用
8. 故障排查
9. 性能基线
10. 安全注意事项

### 6.2 故障排查常见问题

| 问题 | 原因 | 解决 |
|:---|:---|:---|
| "No data" 全部 panel | 后端 unreachable | 检查 `docker network`, backend:8000 端口 |
| "401 Unauthorized" | SA Token 错 | 检查 .env 同步, Grafana restart |
| "Data source not found" | simpod-json-datasource 未装 | 检查 `GF_PLUGINS_PREINSTALL` |
| 数据 stale 5min | v1.36 5min 缓存 | (正常, 文档说明) |
| 仪表盘找不到 | provisioning 路径错 | 检查 volumes 挂载 |

---

## 7. R3 决策 (R3S3 锁定)

| 决策 | 选定 | 备注 |
|:---|:---:|:---|
| 插件安装方式 | `GF_PLUGINS_PREINSTALL` | 容器启动时自动装 |
| SA Token 创建 | API 脚本 (CI) + UI 手动 | 两种都支持 |
| 测试 fixture | mock DB + real client + as_role | 复用 v1.36 模式 |
| .env 同步 | backend + root 各一份 | 文档明确 |
| README 结构 | 10 章节 | ~200 行 |

---

> **R3 Step 3 完成**: 进入 R3 Step 4 (Simulation) - 推演任务时间
