# v1.37 Round 2 调研 (Research) — v1.36 patch 兼容性

> **迭代**: v1.37-grafana-dashboards
> **日期**: 2026-06-03
> **目标**: 验证 v1.37 minor patch 不破坏 v1.36 现有 224 个测试

---

## 1. v1.36 现有架构分析

### 1.1 deps.py 结构 (R2 关键)

**文件**: `backend/app/core/deps.py` (~140 行)

| 函数 | 作用 | v1.37 是否修改 |
|:---|:---|:---:|
| `oauth2_scheme` | OAuth2PasswordBearer, auto_error=False | ❌ |
| `ROLE_HIERARCHY` | 角色继承字典 | ❌ |
| `PERMISSION_MATRIX` | 角色权限矩阵 | ❌ |
| `get_current_user()` | JWT 解码 + DB 查询 | ❌ |
| `_role_for_request()` | 提取 JWT 角色 | ❌ |
| `require_role(*roles)` | 工厂函数, 返回依赖 | ❌ |
| `require_permission(perm)` | 工厂函数, 返回依赖 | ❌ |
| **新增** `require_sa_or_admin()` | SA Token 或 Admin | ✅ (R2 新增) |

**R2 兼容性结论**: 所有现有函数零修改, 仅追加 1 个新函数。

### 1.2 config.py 结构 (R2 关键)

**文件**: `backend/app/core/config.py` (~190 行)

| 字段 | 类型 | 默认 | 用途 |
|:---|:---|:---|:---|
| `jwt_secret_key` | str | `""` | JWT 签名 |
| `jwt_algorithm` | str | `"HS256"` | JWT 算法 |
| ... | ... | ... | (现有 30+ 字段) |
| **新增** `grafana_service_token` | str \| None | `None` | Grafana SA Token |

**R2 兼容性结论**: pydantic-settings 自动处理新字段, 默认 None 表示禁用, 完全向后兼容。

### 1.3 v1.36 测试套件 (P0 验证)

| 文件 | 测试数 | 状态 |
|:---|:---:|:---:|
| tests/test_observability_api.py | 58 | ✅ (T2.x 验证) |
| tests/test_observability_e2e.py | 6 | ✅ (T3.1 验证) |
| tests/performance/test_observability_perf.py | 8 | ✅ (T3.2 验证) |
| tests/test_cache.py | 23 | ✅ (T0.1 验证) |
| tests/test_instance.py | 6 | ✅ (T0.2 验证) |
| tests/test_dedup.py | 7 | ✅ (T4.1 验证) |
| tests/test_dedup_lock.py | 20 | ✅ (T4.1 验证) |
| tests/test_am_sync.py | 19 | ✅ (T4.1 验证) |
| tests/test_alert_tasks.py | 9 | ✅ (T4.1 验证) |
| tests/api/test_silences_api.py | 8 | ✅ (T4.1 验证) |
| tests/api/test_alerts_webhook.py | 11 | ✅ (T4.1 验证) |
| tests/test_silence.py | 11 | ✅ (T4.1 验证) |
| tests/test_escalation.py | 9 | ✅ (T4.1 验证) |
| tests/test_notifier.py | 26 | ✅ (T4.1 验证) |
| tests/api/test_alert_archive_api.py | 6 | ✅ (T4.1 验证) |
| **合计** | **227** | **✅** |

**R2 兼容性结论**: v1.37 patch 实施后必须跑这 227 测试, 全部应继续通过。

---

## 2. JSON Datasource 关键端点验证 (R2 调研)

### 2.1 `GET /` Test connection 端点

**官方文档明确要求**:
> `GET /` with 200 status code response. Used for "Test connection" on the datasource config page.

**R2S1 设计**:
- 使用 `/grafana/health` 返回 200 + metadata

**R2 发现**:
- 插件明确要求根路径 `/`, 不是 `/health`
- 但 Grafana 也允许"Test connection"失败时仍保存 datasource (UI 有 toggle)

**✅ 决策**: Round 3 任务 T-GRAF-002.5 加 `GET /grafana/` 空路由, 返回 200

### 2.2 tag-keys / tag-values 端点 (R2 调研)

**官方文档**:
> - `POST /tag-keys` returning tag keys for ad hoc filters.
> - `POST /tag-values` returning tag values for ad hoc filters.

**R2 发现**:
- 这两个端点仅在 panel 使用 "Ad hoc filters" 功能时必需
- v1.37 R1 Draft 明确不使用 ad hoc filters (用静态变量代替)
- 因此这 2 个端点 P2 可选

**✅ 决策**: Round 3 不包含 tag-keys/tag-values, R2S2 P1-2 标记为 (P2, 不做)

### 2.3 Time Macros 行为验证

**官方文档**:
> `$__unixEpochFrom()` - Start time as Unix timestamp
> `$__isoFrom()` - Start time in ISO 8601 format

**R2 发现**:
- 这 4 个宏只在"Path"或"Params"中作为值使用时被替换
- 在 POST body JSON 中, 字符串内嵌的 `$__isoFrom()` **不会被替换**!

**⚠️ 重大发现 (P0)**: R2S1 设计中, panel target body 用了:
```json
"body": json.dumps({
    "params": {
        "start_time": "$__isoFrom()",  ← 不会被替换!
        "end_time": "$__isoTo()",        ← 不会被替换!
    }
})
```

**这是错误的!**

**✅ 正确做法**: 时间范围必须作为 **Path 参数或 Query 参数** 传递, 而非 POST body 内嵌字符串。

```python
@router.post("/query")
async def grafana_query(
    metric: str,  # ← 作为 path param
    start_time: str,  # ← 作为 query param
    end_time: str,
    # ...
    req: GrafanaQueryRequest,  # 仅包含 metric 内部子参数
    ...
):
    ...
```

**或者**: 在 panel target 中, 把 start_time/end_time 作为 params (query string) 而不是 body:
```json
{
    "path": "/grafana/query",
    "method": "POST",
    "params": [
        {"key": "start_time", "value": "$__isoFrom()"},
        {"key": "end_time", "value": "$__isoTo()"}
    ],
    "body": {
        "metric": "trend",
        "params": {
            "bucket": "1h",
            "severity": "$severity"
        }
    }
}
```

**✅ 决策**: Round 3 重新设计 panel target, 时间范围用 query string, 业务参数用 body。v1.37 端点签名:

```python
@router.post("/query")
async def grafana_query(
    start_time: str,
    end_time: str,
    severity: str = "all",
    channel: str = "all",
    operation: str = "all",
    req: GrafanaQueryRequest = Body(...),  # body
    ...
):
    ...
```

---

## 3. Grafana dataframe 格式 (R2 调研)

### 3.1 官方期望格式

**Simple timeseries** (用于 line/bar/pie):
```json
[
  {
    "target": "Series Name",
    "datapoints": [
      [value, timestamp_ms],
      ...
    ]
  }
]
```

**Table** (用于 table panel):
```json
[
  {
    "type": "table",
    "columns": [
      {"text": "col1", "type": "string"},
      {"text": "col2", "type": "number"}
    ],
    "rows": [
      ["v1", 123],
      ["v2", 456]
    ]
  }
]
```

### 3.2 v1.36 `_compute_*` 输出格式

| 函数 | 输出格式 | 转 Grafana 难度 |
|:---|:---|:---:|
| `_compute_trend` | `{total, buckets: [{ts, count, by_X}], by_X}` | 中 |
| `_compute_response_time` | `{buckets: [{ts, p50, p95, p99}], overall_pXX}` | 低 |
| `_compute_escalation` | `{by_level, by_rule, total, escalated}` | 中 |
| `_compute_channel_stats` | `{channels: {name: {sent, failed, ...}}, total_sent}` | 中 |
| `_compute_silence_hit_rate` | `{total, hit_rate, by_matcher}` | 中 |
| `_compute_am_sync` | `{total_success, total_failed, by_operation, recent_failures}` | 中 |
| `_compute_lock_stats` | `{recent_flushes: [...], historical_recent, last_flush_at}` | 高 |

**⚠️ 发现 (P1)**: 7 个函数输出格式各异, 需要 7 个独立的 `_format_for_grafana()` 适配器。
- 工作量: 70-100 行代码
- 测试: 验证 dataframe 格式正确

---

## 4. v1.36 patch 影响范围总结

| 变更 | 文件 | 行数 | 影响 v1.36 测试 |
|:---|:---|:---:|:---:|
| 新增 Settings 字段 | `app/core/config.py` | +5 | ❌ 无影响 (默认 None) |
| 新增鉴权依赖 | `app/core/deps.py` | +30 | ❌ 无影响 (仅追加) |
| 新增 Grafana Adapter | `app/api/v1/grafana_adapter.py` | +150 | ❌ 无影响 (新文件) |
| 注册新路由 | `app/api/v1/router.py` | +3 | ❌ 无影响 (新路由) |

**P0 验证**: 必须跑 227 个 v1.36 测试, 全部应继续通过 (默认设置下 GRAFANA_SERVICE_TOKEN=None, require_sa_or_admin 行为退化为 require_user 但已经够用)。

**实际行为**: 当 GRAFANA_SERVICE_TOKEN 未设置时, `require_sa_or_admin` 退化为 `get_current_user`, 行为与 v1.36 一致。

---

## 5. Round 3 任务调整 (R2 调研后)

### 5.1 调整

| 原任务 | 调整后 |
|:---|:---|
| T-GRAF-001 require_sa_or_admin | **拆分**: T-GRAF-001a (declaration) + T-GRAF-001b (fallback to current_user) |
| T-GRAF-002 grafana_service_token config | **合并** 到 T-GRAF-001 |
| T-GRAF-003 路由骨架 (4 路由) | **保留**, 增加 GET /grafana/ 空路由 (5 个) |
| T-GRAF-006 /grafana/query 主端点 | **调整**: 接受 start_time/end_time 作为 query param, body 仅含 metric + 业务参数 |
| T-GRAF-007 /grafana/variable | **保留** |
| T-GRAF-009 test_grafana_adapter | **扩充**: 增加 7 个 dataframe 格式验证测试 |

### 5.2 新增

- **T-GRAF-006.5**: 实现 7 个 `_format_for_grafana()` 适配器 (timeseries + table)
- **T-GRAF-016.5**: Round 4: Grafana container 启动 smoke test (CI 专项)

---

## 6. R3 决策 (R2 调研后定)

| 决策 | 选项 | 选定 |
|:---|:---|:---:|
| 时间范围传递方式 | (a) POST body 内嵌, (b) Query param | (b) |
| tag-keys/tag-values | (a) 包含, (b) 不包含 | (b) - P2 不做 |
| Params schema 严格化 | (a) Pydantic 嵌套, (b) dict 容错 | (b) - Round 3 P1 |
| Dataframe 适配 | (a) 7 个适配器, (b) 统一 1 个 | (a) - 差异化输出 |

---

> **Round 2 Step 3 完成**: 进入 Step 4 (Simulation) - 推演 Grafana Adapter 端点
