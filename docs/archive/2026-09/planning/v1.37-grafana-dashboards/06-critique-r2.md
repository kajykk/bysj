# v1.37 Round 2 自查 (Critique) — 架构修订

> **迭代**: v1.37-grafana-dashboards
> **日期**: 2026-06-03
> **目标**: 对 R2 Draft 架构做 4 维度自查, 准备进入 Step 3 调研

---

## 1. 架构完整性 (P0)

### 1.1 后端 patch 范围

| 变更类型 | 文件 | 风险 |
|:---|:---|:---:|
| 新增 1 路由文件 | `app/api/v1/grafana_adapter.py` | 低 |
| 新增 1 测试文件 | `tests/api/test_grafana_adapter.py` | 低 |
| 新增 1 测试文件 | `tests/api/test_grafana_auth.py` | 低 |
| 新增 1 测试文件 | `tests/api/test_v136_regression.py` | 低 |
| 修改 1 依赖文件 | `app/core/deps.py` (+30 行) | **中** |
| 修改 1 配置文件 | `app/core/config.py` (+5 行) | 低 |
| 修改 1 路由注册 | `app/api/v1/router.py` (+3 行) | 低 |

**⚠️ 发现 R2-1 (P0)**: `app/core/deps.py` 是 v1.36 全应用依赖文件, 任何变更都有连锁影响。
- 缓解: 新增的 `require_sa_or_admin()` 不修改任何现有函数, 仅追加
- 验证: 必须跑 224 个 v1.36 测试, 全部应继续通过

**⚠️ 发现 R2-2 (P1)**: `app/core/config.py` 新增字段需考虑 .env.example 是否需要更新。
- 缓解: 同步更新 .env.example 文档, 标记为可选 (默认 None 不影响)

### 1.2 Grafana Adapter 端点完整性

| 必需端点 | v1.37 实现 | v1.36 是否需要改 |
|:---|:---:|:---:|
| GET / (test) | ❌ 缺 | ❌ |
| POST /metrics | ✅ | ❌ |
| POST /metric-payload-options | ⚠️ 部分 (合并到 /metrics) | ❌ |
| POST /query | ✅ | ❌ |
| POST /variable | ✅ | ❌ |
| POST /tag-keys | ❌ 缺 | ❌ |
| POST /tag-values | ❌ 缺 | ❌ |

**⚠️ 发现 R2-3 (P0)**: JSON Datasource 文档明确要求 `GET /` 作为 "Test connection" 端点, v1.37 用 `/grafana/health` 替代, 但插件不识别。
- 缓解 A: 在 v1.37 也加一个 `GET /grafana/` 返回 200 (空路径)
- 缓解 B: 在 provisioning YAML 中跳过 test, 直接 Save & Use

**✅ 决策**: 选 A - 加 `GET /grafana/` 空路径, 工作量 +1 行

**⚠️ 发现 R2-4 (P1)**: tag-keys/tag-values 是 ad hoc filter 必需, v1.37 可选。
- 缓解: R2 标注为 P2 (可选), Round 3 决定是否包含

### 1.3 鉴权兼容性

| 场景 | v1.37 行为 | 是否兼容 v1.36 |
|:---|:---|:---:|
| SA Token 正确 | 返回 admin User | ✅ |
| SA Token 错误 | 401 | ✅ |
| 无 Authorization | 401 | ✅ |
| Admin User JWT | 返回 Admin User | ✅ |
| 普通 User JWT | 401 (需 admin role) | ✅ |

**✅ 兼容**: `require_sa_or_admin` 优先级正确, 不会破坏 v1.36 行为。

---

## 2. 可行性复查 (P0)

### 2.1 POST body 解析可行性

**问题**: Grafana JSON Datasource 发送的 body 是 JSON 字符串, FastAPI 用 Pydantic 自动解析。

```python
class GrafanaQueryRequest(BaseModel):
    metric: str
    params: dict = {}
```

**✅ 可行**: Pydantic 支持 `dict` 类型字段, 自动解析 JSON object。

**⚠️ 发现 R2-5 (P1)**: `params` 是 `dict` 没有 schema 约束, 内部字段 (start_time, end_time 等) 类型不安全。
- 缓解: 在 handler 函数内部用 `params.get("start_time")` 容错, 缺关键字段返回 400
- Round 3 决定: 是否升级为嵌套 Pydantic schema

### 2.2 时间格式兼容性

**问题**: v1.36 `_compute_trend` 接受 `datetime` 对象, Grafana 发送 ISO 8601 字符串。

**✅ 可行**: v1.37 handler 内部 `datetime.fromisoformat(params["start_time"])`, 转换后再传入 v1.36 函数。

### 2.3 Grafana dataframe 格式

**问题**: JSON Datasource 期望 `[{target, datapoints: [[val, ms], ...]}]` 格式, v1.36 返回 `{buckets: [...], total, by_X}` 格式。

**⚠️ 发现 R2-6 (P0)**: 需要写 `_format_for_grafana()` 适配函数。
- 工作量: 50-80 行 (7 个 metric 各 10-12 行转换)
- 测试: 验证 dataframe 格式正确

**✅ 决策**: Round 3 任务 T-GRAF-006 必须包含此适配函数。

### 2.4 缓存策略

**✅ 复用 v1.36**: `_compute_*` 函数本身用 `cached_or_compute`, 5min 缓存。Grafana 1m refresh 会看到 stale data, 但这是 v1.36 的设计。

**⚠️ 发现 R2-7 (P2)**: Grafana 自身也有 query-level cache (默认 0s), 可独立设置。
- 缓解: 在 panel target 设置 `cacheDurationSeconds: 300` 与 v1.36 缓存对齐

---

## 3. 可测试性复查 (P0)

### 3.1 19 个测试覆盖矩阵

| 测试 | 关键场景 | 是否可自动 |
|:---|:---|:---:|
| test_health_returns_200 | 基础连通性 | ✅ |
| test_metrics_lists_7_metrics | metrics 端点完整性 | ✅ |
| test_query_trend | metric=trend 正确返回 | ✅ |
| test_query_response_time | metric=response_time 正确返回 | ✅ |
| test_query_escalation | metric=escalation | ✅ |
| test_query_channel_stats | metric=channel_stats | ✅ |
| test_query_silence_hit_rate | metric=silence_hit_rate | ✅ |
| test_query_am_sync | metric=am_sync | ✅ |
| test_query_lock_stats | metric=lock_stats | ✅ |
| test_query_unknown_metric_400 | 错误 metric 400 | ✅ |
| test_query_no_auth_401 | 无 token 401 | ✅ |
| test_query_with_sa_token_200 | SA Token 通过 | ✅ |
| test_query_with_admin_user_200 | Admin JWT 通过 | ✅ |
| test_query_with_user_jwt_403 | User JWT 拒绝 | ✅ |
| test_variable_rule_returns_top20 | 变量端点 | ✅ |
| test_variable_matcher_returns_top10 | 变量端点 | ✅ |
| test_variable_operation_returns_all | 变量端点 (静态) | ✅ |
| test_variable_channel_returns_all | 变量端点 (静态) | ✅ |
| test_v136_8_endpoints_still_work | v1.36 回归 | ✅ |

**✅ 全部可自动**: 19/19 测试可被 pytest 自动化。

### 3.2 v1.36 回归测试

**⚠️ 发现 R2-8 (P0)**: v1.36 现有 224 个测试必须继续通过。
- 验证: 跑完整测试套件 `pytest tests/ -k "not perf"` (perf 在 Windows 偶发超时)
- 关键 8 个端点测试: tests/test_observability_api.py (58 个)

**✅ 决策**: Round 3 任务 T-GRAF-011 包含 8 个 v1.36 端点 smoke test, 跑通即视为 patch 不破坏。

---

## 4. 可观测性复查 (P1)

### 4.1 仪表盘自身可观测

| 场景 | v1.37 行为 | 改进 |
|:---|:---|:---|
| 加载失败 | Grafana 显示 "No data" | (无) |
| Token 失效 | 401, 仪表盘 "No data" | (无) |
| Grafana Adapter 端点 5xx | 仪表盘 panel 显示错误 | (无) |
| 缓存 stale | 5min 内数据不变 | (无, 接受) |

**⚠️ 发现 R2-9 (P2)**: 没有 SA Token 过期指示器。R1 决定: 依赖 Grafana 自身告警。
- 缓解: README 说明 "30 天轮换 SA Token", 配合外部告警系统

### 4.2 后端可观测

**✅ 复用 v1.36**: 所有 Grafana Adapter 端点写日志到标准 FastAPI logger。
- Round 3 可选: 写 OperationLog (复用 v1.36 admin OperationLog)

---

## 5. 综合问题清单 (R2 修订)

### 5.1 P0 (R2 解决)

| # | 问题 | 解决方案 |
|:---|:---|:---|
| P0-1 | JSON Datasource `GET /` 端点缺失 | 加 `GET /grafana/` 空路由 |
| P0-2 | v1.36 patch 不破坏 224 测试 | T-GRAF-011 必跑 v1.36 端点 smoke test |

### 5.2 P1 (R2 建议解决)

| # | 问题 | 解决方案 |
|:---|:---|:---|
| P1-1 | params dict 无 schema 约束 | handler 内部 `params.get()` 容错 |
| P1-2 | tag-keys/tag-values 缺失 | Round 3 决定 P2 是否包含 |
| P1-3 | .env.example 需同步 | Round 3 任务 T-GRAF-014 包含 |

### 5.3 P2 (可选)

| # | 问题 | 解决方案 |
|:---|:---|:---|
| P2-1 | Grafana query-level cache 未对齐 v1.36 5min | panel target 加 `cacheDurationSeconds: 300` |
| P2-2 | OperationLog 写入 (admin 端点) | Round 3 决定是否包含 |
| P2-3 | Grafana 内嵌告警 (R1 已排除) | (不做) |

---

## 6. Round 3 任务修订

基于 R2 Critique, Round 3 任务列表需调整:

### 6.1 新增任务

- **T-GRAF-002.5**: 加 `GET /grafana/` 空路由 (P0-1 解决)

### 6.2 调整任务

- **T-GRAF-011**: 跑 v1.36 8 端点 smoke test (P0-2 验证)
- **T-GRAF-014**: 包含 .env.example 同步 (P1-3 解决)

### 6.3 保持不变

- 16 个原有任务继续

---

## 7. R3 决策 (待 R2 调研后定)

1. **是否包含 tag-keys/tag-values** (P1-2) → 待 R2S3 调研 JSON Datasource 实际是否必需
2. **是否升级 params 为 Pydantic schema** (P1-1) → 待 R2S4 推演决定
3. **是否写 OperationLog** (P2-2) → 待 R2S3 调研 v1.36 admin 端点

---

> **Round 2 Step 2 完成**: 进入 Step 3 (Research) - 调研 v1.36 patch 兼容性
