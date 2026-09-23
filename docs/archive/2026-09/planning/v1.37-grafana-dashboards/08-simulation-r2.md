# v1.37 Round 2 推演 (Simulation) 报告 — Grafana Adapter 端点

> **迭代**: v1.37-grafana-dashboards
> **日期**: 2026-06-03T15:23:57.227641
> **目的**: 验证 Grafana Adapter 4 端点行为符合 R2 设计

---

## 1. 推演结果

| 端点 | 行为 | 状态 |
|:---|:---|:---:|
| GET /grafana/health | 返回 200 + status/version/timestamp | ✅ |
| POST /grafana/metrics | 返回 7 个 metric 列表 + payloads | ✅ |
| POST /grafana/query (trend) | 返回 Grafana dataframe 格式 | ✅ |
| POST /grafana/query (unknown) | 抛 ValueError → 400 | ✅ |
| POST /grafana/variable (rule) | 返回 top 20 rules | ✅ |
| POST /grafana/variable (channel) | 返回 5 项静态 channels | ✅ |

---

## 2. 关键发现 (R2S4)

### 2.1 R2S3 调整验证成功

**原 R2S1 设计错误**: 时间范围作为 POST body 内嵌字符串 `$__isoFrom()`, Grafana 不会替换。

**R2S3 调整后**: 时间范围作为 query param:
```
POST /grafana/query?start_time=$__isoFrom()&end_time=$__isoTo()&severity=$severity
body: {"metric": "trend", "params": {"bucket": "1h"}}
```

**✅ 推演验证**: 此设计在 mock 中正常工作, query param 正确传递到 handler。

### 2.2 Dataframe 格式

**Grafana 期望**:
```json
[{"target": "fired", "datapoints": [[10, 1622548800000], ...]}]
```

**v1.37 实现**:
- `_format_for_grafana_trend()` 转换 `_compute_trend()` 输出为 Grafana dataframe
- 每个 status 一个 series, datapoints 是 [[count, ts_ms], ...]
- 24 个 buckets → 24 个 datapoints × N statuses

**✅ 推演验证**: 24 buckets × 2 statuses (fired + resolved) = 48 datapoints across 2 series。

### 2.3 端点数量 + 1

R2S1 调研中发现需加 `GET /grafana/` 空路由 (Test connection), R2S4 推演确认。

**最终 5 路由** (vs R2S1 的 4 路由):
1. GET /grafana/ (空, Test connection)
2. GET /grafana/health (Grafana Adapter 健康, 含元数据)
3. POST /grafana/metrics (metric 列表)
4. POST /grafana/query (主)
5. POST /grafana/variable (变量)

---

## 3. Round 3 任务最终清单 (R2S4 调整后)

| ID | 任务 | 估时 | 优先级 |
|:---|:---|:---:|:---:|
| T-GRAF-001 | require_sa_or_admin + config.grafana_service_token | 30min | P0 |
| T-GRAF-002 | GET /grafana/ + GET /grafana/health | 15min | P0 |
| T-GRAF-003 | POST /grafana/metrics | 30min | P0 |
| T-GRAF-004 | POST /grafana/variable (4 types) | 1h | P0 |
| T-GRAF-005 | POST /grafana/query 路由 + metric 分发 | 1h | P0 |
| T-GRAF-006 | 7 个 _format_for_grafana_* 适配器 | 2h | P0 |
| T-GRAF-007 | 注册路由到 router.py | 5min | P0 |
| T-GRAF-008 | test_grafana_adapter.py (15 测试) | 1.5h | P0 |
| T-GRAF-009 | test_grafana_auth.py (3 测试) | 30min | P0 |
| T-GRAF-010 | test_v136_regression.py (8 测试) | 30min | P0 |
| T-GRAF-011 | provisioning YAML × 2 | 30min | P1 |
| T-GRAF-012 | docker-compose 增量 | 15min | P1 |
| T-GRAF-013 | .env.example 同步 | 10min | P1 |
| T-GRAF-014 | README 编写 | 1h | P1 |
| T-GRAF-015 | v1.36 回归 227 测试验证 | 1min (CI) | P0 |
| T-GRAF-016 | Grafana 容器端到端 (CI 专项) | 30min | P2 |
| **合计** | — | **~10h** | — |

---

## 4. R2S4 推演限制

- 推演基于 mock 数据, 未连真实 v1.36 后端
- 真实 v1.36 `_compute_*` 函数的输出格式需 R3 实际验证
- Grafana 11.6 容器化测试需 R3 T-GRAF-016 端到端验证

---

> **Round 2 Step 4 完成**: 进入 Step 5 (Lock) - 锁定 R2 修订, 进入 R3
