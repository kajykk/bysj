# v1.37 Round 2 锁定 (Lock) — 架构修订完成

> **迭代**: v1.37-grafana-dashboards
> **日期**: 2026-06-03
> **状态**: 🟢 **Round 2 LOCKED** - 架构修订完成
> **下一步**: 进入 Round 3 终定 (生成 04-ralph-tasks.md + 05-test-plan.md)

---

## 1. R2 交付物 (锁定)

| 文档 | 路径 | 状态 |
|:---|:---|:---:|
| 05-architecture-r2.md | `docs/planning/v1.37-grafana-dashboards/05-architecture-r2.md` | ✅ |
| 06-critique-r2.md | `docs/planning/v1.37-grafana-dashboards/06-critique-r2.md` | ✅ |
| 07-research-r2.md | `docs/planning/v1.37-grafana-dashboards/07-research-r2.md` | ✅ |
| 08-simulation-r2.md | `docs/planning/v1.37-grafana-dashboards/08-simulation-r2.md` | ✅ |
| 08-simulation-r2.py | `docs/planning/v1.37-grafana-dashboards/08-simulation-r2.py` | ✅ |
| **R2 Lock 文档** | `docs/planning/v1.37-grafana-dashboards/09-lock-r2.md` | ✅ (本文件) |

---

## 2. R2 关键修订 (vs R1)

| 维度 | R1 设计 | R2 修订 |
|:---|:---|:---|
| **时间范围传递** | POST body 内嵌 `$__isoFrom()` (❌ 错误) | Query param `?start_time=...&end_time=...` (✅) |
| **路由数量** | 4 路由 (缺 Test connection) | **5 路由** (新增 `GET /grafana/`) |
| **Tag 端点** | 未明确 | 不包含 (P2 可选, R1 不用 ad hoc filters) |
| **后端 patch 范围** | 4 路由 + 1 依赖 | 5 路由 + 1 依赖 + 1 config 字段 (T-GRAF-001) |
| **Dataframe 适配** | 模糊 | **7 个独立适配器** (T-GRAF-006) |
| **任务数量** | 16 | **16** (T-GRAF-015 验证) |

---

## 3. 最终任务清单 (R2 Lock - 16 任务)

| ID | 任务 | 文件 | 估时 | P |
|:---|:---|:---|:---:|:---:|
| T-GRAF-001 | require_sa_or_admin + config.grafana_service_token | deps.py + config.py | 30min | P0 |
| T-GRAF-002 | GET /grafana/ + GET /grafana/health | grafana_adapter.py | 15min | P0 |
| T-GRAF-003 | POST /grafana/metrics (7 metric 列表) | grafana_adapter.py | 30min | P0 |
| T-GRAF-004 | POST /grafana/variable (4 types) | grafana_adapter.py | 1h | P0 |
| T-GRAF-005 | POST /grafana/query 路由 + 7 metric 分发 | grafana_adapter.py | 1h | P0 |
| T-GRAF-006 | 7 个 _format_for_grafana_* 适配器 | grafana_adapter.py | 2h | P0 |
| T-GRAF-007 | 注册路由到 router.py | router.py | 5min | P0 |
| T-GRAF-008 | test_grafana_adapter.py (15 测试) | tests/api/ | 1.5h | P0 |
| T-GRAF-009 | test_grafana_auth.py (3 测试) | tests/api/ | 30min | P0 |
| T-GRAF-010 | test_v136_regression.py (8 端点 smoke) | tests/api/ | 30min | P0 |
| T-GRAF-011 | provisioning YAML × 2 | infra/grafana/ | 30min | P1 |
| T-GRAF-012 | docker-compose 增量 | docker-compose.yml | 15min | P1 |
| T-GRAF-013 | .env.example 同步 | .env.example | 10min | P1 |
| T-GRAF-014 | README 编写 | infra/grafana/README.md | 1h | P1 |
| T-GRAF-015 | v1.36 回归 227 测试验证 | CI 必跑 | 1min | P0 |
| T-GRAF-016 | Grafana 容器端到端 (CI 专项) | infra/grafana/test_e2e.sh | 30min | P2 |
| **合计** | — | — | **~10h** | — |

---

## 4. R2 最终架构 (锁定)

### 4.1 端点契约 (5 路由)

| 端点 | 方法 | 用途 | 时间范围 |
|:---|:---:|:---|:---|
| `/grafana/` | GET | Test connection (空) | - |
| `/grafana/health` | GET | Adapter 健康 + 元数据 | - |
| `/grafana/metrics` | POST | 7 metric 列表 | - |
| `/grafana/query` | POST | Panel 数据 (主) | **Query param** |
| `/grafana/variable` | POST | 变量 query | - |

### 4.2 关键路径

```
Grafana Panel target
   ↓ POST /grafana/query
   ↓ Query params: start_time=$__isoFrom()&end_time=$__isoTo()&severity=$severity
   ↓ Body: {"metric": "trend", "params": {"bucket": "1h"}}
FastAPI 路由
   ↓ require_sa_or_admin() ← SA Token 或 Admin User
   ↓ db: AsyncSession
handler (e.g., _trend_handler)
   ↓ params: dict
   ↓ metric=trend
v1.36 _compute_trend(db, start, end, bucket, ...)
   ↓ 返回: {total, buckets, by_X}
_format_for_grafana_trend(result)
   ↓ Grafana dataframe
Grafana Panel
```

### 4.3 与 v1.36 的兼容性 (锁定)

- ✅ **不修改** v1.36 8 个 REST 端点
- ✅ **不修改** v1.36 `_compute_*` 函数
- ✅ **不修改** v1.36 数据库 schema
- ✅ **不破坏** v1.36 227 个测试
- ✅ **追加** 4 文件 + 1 字段 (1 路由文件 + 3 测试文件 + 1 Settings 字段)

---

## 5. 验收标准 (R2 Lock)

| 维度 | 数量 | 备注 |
|:---|:---:|:---|
| P0 AC | 12 | 必须 R3 完成时通过 |
| P1 AC | 3 | README + Provisioning |
| P2 AC | 3 | CI 专项 |
| **合计** | **18** | — |

---

## 6. Round 3 计划 (R2 Lock 后)

| 步骤 | 任务 |
|:---|:---|
| R3S1 | 编写 `04-ralph-tasks.md` + `05-test-plan.md` 终稿 |
| R3S2 | 自查任务依赖 + AC 覆盖 |
| R3S3 | 调研实现细节 (Provisioning 模板等) |
| R3S4 | 推演任务时间 |
| R3S5 | 锁定 R3 → 输出 RALPH_STATE.md Implementation 区域 → 进入 Implementation Phase |

---

## 7. Round 1+R2 综合完成度

| Round | 完成度 |
|:---|:---:|
| R1 Draft / Critique / Research / Simulation / Lock | 100% |
| R2 Draft / Critique / Research / Simulation / Lock | 100% |
| **R1+R2 合计** | **10/10 步 (100%)** |
| **R3** | **0/5 步 (0%)** |
| **整体规划进度** | **10/15 步 (67%)** |

---

> **Round 2 完成**: 等待进入 Round 3 终定
