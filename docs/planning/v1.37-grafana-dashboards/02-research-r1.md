# v1.37 Grafana 仪表盘模板 — Round 1 调研 (Research)

> **迭代**: v1.37-grafana-dashboards
> **日期**: 2026-06-03
> **目标**: 调研 Grafana JSON Datasource + Provisioning + Service Account 最佳实践, 解决 Critique 中发现的问题

---

## 1. 调研结论摘要

| 主题 | 关键发现 | 决策影响 |
|:---|:---|:---|
| **JSON Datasource API** | 后端需实现 `GET /` + `POST /metrics` + `POST /query` 等 4 端点 | v1.36 端点路径不直接匹配, 需前端路径适配或后端 minor patch |
| **Template Variables** | 支持 `${var}` 嵌入 URL/Params/Headers/Body/JSONPath | 满足 Round 1 变量需求 |
| **Time Macros** | 支持 `$__unixEpochFrom()` `$__isoFrom()` 等 4 种时间宏 | Grafana 自动转换 time range, 简化后端实现 |
| **Provisioning YAML** | 支持 `$ENV_VAR` 环境变量插值 (值内) | 满足 SA Token 注入需求 |
| **Service Account Token** | 格式 `glsa_...`, 通过 `Authorization: Bearer` 传递 | v1.36 JWT vs Grafana SA 兼容性需澄清 |
| **Prune 选项** | `prune: true` 自动删除已移除的 datasource | 适合 CI/CD 自动清理 |

---

## 2. JSON Datasource 后端契约 (R1 关键)

### 2.1 必需端点 (4 个)

| 端点 | 方法 | 用途 | v1.36 兼容性 |
|:---|:---:|:---|:---:|
| `/` | GET | Test connection (返回 200) | ❌ 缺 (v1.36 仅 `/alerts/observability/*` 路径) |
| `/metrics` | POST | 返回可用 metrics 列表 | ❌ 缺 |
| `/metric-payload-options` | POST | 返回 metric 的可选 payload | ❌ 缺 |
| `/query` | POST | 返回 panel data 或 annotations | ❌ 缺 (v1.36 用 GET) |

### 2.2 可选端点 (3 个)

| 端点 | 方法 | 用途 | v1.36 兼容性 |
|:---|:---:|:---|:---:|
| `/variable` | POST | 变量 query 类型数据 | ❌ 缺 |
| `/tag-keys` | POST | ad hoc filter tag keys | ❌ 缺 |
| `/tag-values` | POST | ad hoc filter tag values | ❌ 缺 |

### 2.3 兼容性结论 (P0)

**⚠️ 重大发现**: v1.36 后端是 **REST 资源风格** (GET `/alerts/observability/trend`), 而 JSON Datasource 是 **RPC 风格** (POST `/query` + path/method in body)。

两种解决方案:

**方案 A: 在 v1.36 加 Grafana Adapter 路由 (推荐, P0)**
- 在 v1.36 增加 4 个 RPC 端点 (`POST /grafana/query`, `GET /grafana/health`, `POST /grafana/metrics`, `POST /grafana/variable`)
- 每个 RPC 端点内部调用 v1.36 已有的 `_compute_*` 函数
- 不影响 v1.36 的 8 个 REST 端点
- 工作量: 2-3 小时 (复用现成逻辑)

**方案 B: 在 Grafana 端用 JSON Datasource 转 REST (不推荐)**
- 用 JSON Datasource 的 `Method: GET` + `Path: /alerts/observability/trend` 模式
- 但插件期望 POST + `/query` 路径, 不完全支持 REST 风格
- 部分 panel 可能无法工作
- 工作量: 不可预估 (插件限制)

**✅ 决策**: 选 **方案 A** - v1.37 包含 1 个后端 minor patch (Grafana Adapter), 工作量纳入 v1.37 任务清单。

---

## 3. Template Variables 与 Time Macros (R1 关键)

### 3.1 Grafana 变量语法

```json
{
  "targets": [{
    "path": "/alerts/observability/trend",
    "params": [
      {"key": "severity", "value": "$severity"},
      {"key": "channel", "value": "$channel"}
    ],
    "method": "GET"
  }]
}
```

| 语法 | 含义 | v1.37 用例 |
|:---|:---|:---|
| `${var}` | 变量值插入 | `severity=$severity` |
| `${var:csv}` | 多选以 CSV 拼接 | `severity=$severity` (multi-select) |
| `${var:pipe}` | 多选以 \| 拼接 | (无) |
| `${var:regex}` | 正则转换 | (无) |
| `$__from` / `$__to` | 时间范围 (ms) | (无, 用 `__isoFrom` 更友好) |

### 3.2 Time Macros (4 个)

| 宏 | 输出 | v1.36 后端参数 |
|:---|:---|:---|
| `$__unixEpochFrom()` | 1749000000 | `start_time=1749000000` |
| `$__unixEpochTo()` | 1749086400 | `end_time=1749086400` |
| `$__isoFrom()` | 2026-06-03T00:00:00Z | `start_time=2026-06-03T00:00:00Z` |
| `$__isoTo()` | 2026-06-03T01:00:00Z | `end_time=2026-06-03T01:00:00Z` |

**✅ 决策**: v1.37 优先用 `__isoFrom` / `__isoTo` (v1.36 后端接受 ISO 8601)。

### 3.3 rule 变量提取

Critique 中 P1-3 发现 "rule 变量需 JSON path 表达式"。

**问题**: v1.36 `/trend?group_by=rule` 返回 `data.buckets[*].by_rule[*]`, 不是直接的 `{label, value}` 列表。

**解决方案**: 在 v1.36 Grafana Adapter 中增加 `/grafana/variable` 端点, 返回:
```json
[
  {"text": "HighErrorRate", "value": "HighErrorRate"},
  {"text": "DiskSpaceLow", "value": "DiskSpaceLow"}
]
```

**✅ 决策**: 纳入 v1.37 后端 minor patch。

---

## 4. Service Account 与 v1.36 JWT 兼容性 (R1 关键)

### 4.1 鉴权链路分析

```
[Grafana 浏览器] → 登录 → Grafana 会话
[Grafana JSON Datasource] → 调用 v1.36 后端
  → Header: Authorization: Bearer <SERVICE_ACCOUNT_TOKEN>
  → v1.36 get_current_user() → oauth2_scheme → JWT 解码 → user 查询
```

### 4.2 不兼容点

**⚠️ 严重问题**: v1.36 的 `oauth2_scheme` 是 `OAuth2PasswordBearer(tokenUrl="auth/login")`, 它**期望 JWT** (有签名 + 过期时间), **不接受任意字符串**。

Grafana 的 Service Account Token 格式是 `glsa_<random_string>`, 没有 JWT 签名。

### 4.3 解决方案

**方案 A: 在 v1.36 增加"Service Account"鉴权路径 (推荐)**
- v1.36 新增 `get_current_user_or_service_account()` 依赖
- 检查 `Authorization: Bearer <token>` 是否在 `GRAFANA_SERVICE_TOKEN` 环境变量中
- 匹配成功 → 返回一个虚拟 admin user (绕过 DB 查询)
- 工作量: 30 分钟 (一个文件, 一个函数)

**方案 B: 用 v1.36 的"grafana"普通用户 + JWT**
- v1.36 创建 `grafana@bysj.local` 用户 (role=admin)
- v1.36 调用 `/api/v1/auth/login` 获取 JWT
- Grafana 每次启动用这个 JWT
- 工作量: 1 小时 (需用户创建脚本 + JWT 续期)
- 风险: JWT 默认 60 分钟过期, 需定时刷新

**✅ 决策**: 选 **方案 A** - 单 env var 配置, 简单且无续期问题。

### 4.4 实现细节

```python
# app/api/v1/deps.py 增加
async def get_current_user_or_service_account(
    token: str = Depends(oauth2_scheme),
) -> User:
    """支持 Service Account Token 鉴权 (用于 Grafana 等)."""
    if token == settings.GRAFANA_SERVICE_TOKEN:
        return User(id=0, email="grafana@bysj.local", role="admin", ...)
    return await get_current_user(token)
```

然后在 `/grafana/*` 路由上用 `get_current_user_or_service_account` 替代 `get_current_user`。

---

## 5. Provisioning 路径 (R1 验证)

### 5.1 文件结构 (推荐)

```
infra/grafana/
├── dashboards/
│   └── v1.37-alerts-overview.json     # 主仪表盘
├── provisioning/
│   ├── datasources/
│   │   └── observability-api.yaml     # JSON Datasource 配置
│   └── dashboards/
│       └── v1.37-alerts.yaml          # Dashboard provisioning
└── README.md
```

### 5.2 datasource YAML

```yaml
apiVersion: 1

datasources:
  - name: Observability API
    type: simpod-json-datasource
    access: proxy  # 让 Grafana 代理, 安全
    url: http://backend:8000/grafana
    isDefault: true
    jsonData:
      tlsSkipVerify: false
    secureJsonData:
      Authorization: Bearer ${GRAFANA_SA_TOKEN}
```

**关键**: `secureJsonData` 而非 `jsonData`, 加密存储。

### 5.3 dashboard provisioning YAML

```yaml
apiVersion: 1

providers:
  - name: 'v1.37 Alerts Overview'
    orgId: 1
    folder: 'Observability'
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: false  # 防止手动编辑被覆盖
    options:
      path: /var/lib/grafana/dashboards
      foldersFromFilesStructure: true
```

---

## 6. Grafana 容器化配置 (R1 验证)

### 6.1 docker-compose.yml 片段

```yaml
services:
  grafana:
    image: grafana/grafana:11.6.0
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}
      - GF_USERS_ALLOW_SIGN_UP=false
      - GF_AUTH_ANONYMOUS_ENABLED=false
    volumes:
      - ./infra/grafana/provisioning:/etc/grafana/provisioning:ro
      - ./infra/grafana/dashboards:/var/lib/grafana/dashboards:ro
    depends_on:
      - backend
```

### 6.2 SA Token 创建脚本

```bash
# 创建 SA + Token (Provisioning 完成后用 Grafana API 一次性创建)
curl -X POST http://admin:${GRAFANA_ADMIN_PASSWORD}@localhost:3000/api/serviceaccounts \
  -H "Content-Type: application/json" \
  -d '{"name": "v1.37-observability", "role": "Viewer", "isDisabled": false}'

curl -X POST http://admin:${GRAFANA_ADMIN_PASSWORD}@localhost:3000/api/serviceaccounts/${SA_ID}/tokens \
  -H "Content-Type: application/json" \
  -d '{"name": "observability-api-token"}'
```

---

## 7. 关键风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|:---|:---:|:---:|:---|
| **v1.36 后端 RPC 端点不匹配 JSON Datasource** | 高 | 高 | 方案 A - 后端 minor patch (Grafana Adapter) |
| **Bearer Token 不被 v1.36 接受** | 高 | 高 | 方案 A - Service Account 鉴权路径 |
| **Provisioning 文件挂载路径错误** | 中 | 中 | README 明确说明 docker-compose volumes |
| **Grafana 版本差异 (10 vs 11)** | 中 | 中 | 优先支持 11.6, README 注明 10.x 也兼容 |
| **5min 缓存导致 panel stale** | 高 | 低 | 文档说明, 不在 panel 内显式标注 |

---

## 8. Round 2 待办 (修订)

完成 Research 后, 进入 Round 2 修订, 重点:

1. **R2-D1**: 在 v1.37 后端 minor patch 中增加 Grafana Adapter 路由
2. **R2-D2**: 在 v1.37 后端增加 Service Account 鉴权路径
3. **R2-D3**: 明确 time_range → start_time/end_time 转换 (用 `__isoFrom` / `__isoTo`)
4. **R2-D4**: instance_id 简化为 static 文本 (单实例场景)
5. **R2-D5**: rule 变量通过 `/grafana/variable` 端点返回标准化列表

---

> **Round 1 Step 3 完成**: 进入 Step 4 (Simulation) - 推演仪表盘 JSON 样例
