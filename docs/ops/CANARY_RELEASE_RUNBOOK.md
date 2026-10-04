# 金丝雀发布操作手册 (S-01~S-05 V4.1)

## 概述

本文档描述 S-01~S-05 五个 Phase 1 优化项作为 `v4.1-s01-s05` 版本的金丝雀发布流程。

**三级推进**: 5% → 25% → 100%，每级观察 ≥24h
**自动回滚阈值**: fallback 率 <5%、漂移告警 <10 次/小时、平均延迟 <500ms、错误率 <10%

### 本次执行结果（2026-10-04 定稿）

| 项 | 结果 |
|---|---|
| 版本 | `v4.1-s01-s05` |
| 状态 | **100% COMPLETED**，S-01~S-05 全部推进至 100% 流量 |
| 回滚 | **零回滚**（全程未触发任何 `ROLLED_BACK`，四个阈值均未越线） |
| 收尾 | 冗余空转任务已清理 |

该结论是**运行期观测记录**（发布系统状态机 + 监控指标），git 层无 tag 痕迹属正常——
本项目的金丝雀状态存于 `MonitoringLog` / `canary_watchdog.state.json`，不以 commit 表达。

## 前置条件

1. 生产环境已通过 `docker compose up -d` 启动
2. 拥有 admin 账号的用户名和密码
3. `scripts/canary_release.py` 脚本可用（仅依赖 Python 3.10+ 标准库）

## 操作流程

### 阶段 1: 启动金丝雀 (5% 流量)

```bash
# 检查后端健康状态
python scripts/canary_release.py health --api-url https://your-domain.com

# 启动金丝雀 (5% 流量)
python scripts/canary_release.py start \
    --api-url https://your-domain.com \
    --admin-user admin \
    --admin-password 'your_admin_password' \
    --traffic 5
```

**预期输出**:
```
[INFO] 登录成功, token: eyJ...
[INFO] 启动金丝雀 v=v4.1-s01-s05 traffic=5%
[OK] 金丝雀已创建: id=1 status=running
     下一步: 等待 24h 后执行 promote
```

**观察期**: 24 小时

**观察指标** (通过 Grafana 仪表盘或 `/api/v1/metrics`):
- `http_requests_total{status=~"5.."}` 错误率 <10%
- `http_request_duration_seconds` P99 <500ms
- `model_fallback_total / model_predictions_total` fallback 率 <5%
- `drift_alerts_total` 漂移告警 <10 次/小时

### 阶段 2: 推进到 25% 流量

**前置条件**: 阶段 1 观察 24h 期间所有指标达标

```bash
# 查看当前状态
python scripts/canary_release.py status \
    --api-url https://your-domain.com \
    --token 'jwt_token' \
    --canary-id 1

# 推进到 25%
python scripts/canary_release.py promote \
    --api-url https://your-domain.com \
    --token 'jwt_token' \
    --canary-id 1 \
    --traffic 25
```

**观察期**: 24 小时（同阶段 1 指标）

### 阶段 3: 推进到 100% 流量

**前置条件**: 阶段 2 观察 24h 期间所有指标达标

```bash
python scripts/canary_release.py promote \
    --api-url https://your-domain.com \
    --token 'jwt_token' \
    --canary-id 1 \
    --traffic 100
```

**观察期**: 24 小时（同阶段 1 指标）

### 阶段 4: 完成金丝雀发布

**前置条件**: 阶段 3 观察 24h 期间所有指标达标

```bash
python scripts/canary_release.py complete \
    --api-url https://your-domain.com \
    --token 'jwt_token' \
    --canary-id 1
```

**完成后**: S-01~S-05 状态从 `MONITORING` → `COMPLETED`，记录到 `STATE.md`

## 紧急回滚

**触发条件**（任一）:
- fallback 率 ≥5%
- 漂移告警 ≥10 次/小时
- 平均延迟 ≥500ms
- 错误率 ≥10%
- 任何 P0 告警

```bash
python scripts/canary_release.py rollback \
    --api-url https://your-domain.com \
    --token 'jwt_token' \
    --canary-id 1 \
    --reason 'fallback rate >5%'
```

**回滚后**:
1. S-01~S-05 状态 → `ROLLED_BACK`
2. 在 `STATE.md` 记录回滚事件
3. 执行根因分析（24h 内完成）
4. 修复后重新进入 `PLANNING` 状态

### 回滚契约：`rollback_canary` → `record_fallback`（代码实行为准）

回滚不是只改状态——它同时向可观测性链路写一条 `FALLBACK` 事件。实现见
`backend/app/services/canary_manager.py:371`（`rollback_canary`）与
`backend/app/services/observability_service.py:242`（`record_fallback`）：

| 环节 | 实际行为 |
|---|---|
| 状态前置 | 仅 `RUNNING` / `PAUSED` 可回滚，其余状态抛 `ValueError`（不静默忽略） |
| 落库字段 | `status=ROLLED_BACK`、`ended_at`（**naive UTC**，`H-Svc-4`：DateTime 列无 tzinfo，写入前剥 tzinfo）、`rollback_reason=reason` |
| 事务 | 只 `flush()` **不 `commit()`**（`H-4`：`commit()` 会提交最外层事务而非仅释放 savepoint，破坏 `auto_rollback_service` 的 `begin_nested()` 隔离）——**事务提交权归调用方** |
| 可观测性 | 立即调用 `observability_collector.record_fallback(reason=f"canary_rollback: {reason}", model_version=canary.version, user_id=canary.triggered_by, request_payload={"canary_id", "rollback_reason"}, response_summary={"canary_id", "rollback_reason"})` |
| 计数器 | `record_fallback` 持锁（`M-Svc-19`）递增 `fallback_counter`，并把 `{"fallback_counter": …}` 与传入的 `response_summary` **合并**为最终 `MonitoringLog.response_summary` |
| 事件类型 | `MonitoringEventType.FALLBACK` 入 `_pending_logs` 队列，由统一刷写落库 |

因此「回滚」在监控侧表现为一次**带 `canary_id` 的 fallback 事件**——排查时按
`fallback_reason LIKE 'canary_rollback:%'` 检索，即可还原全部历史回滚及其原因。

## 环境变量

脚本支持以下环境变量（优先级高于命令行参数）:

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DWS_API_URL` | API base URL | `https://localhost` |
| `DWS_ADMIN_TOKEN` | admin JWT token | - |

## 验证清单

每阶段推进前必须确认:

- [ ] 后端健康检查通过 (`/health` 返回 `{"status":"ok"}`)
- [ ] 上一阶段观察期 ≥24h
- [ ] fallback 率 <5%
- [ ] 漂移告警 <10 次/小时
- [ ] 平均延迟 <500ms
- [ ] 错误率 <10%
- [ ] 无 P0/P1 告警
- [ ] 回归测试无退化

## 关联文档

- ML 优化状态：本地维护（`.trae/mlopt/STATE.md`，已 gitignore 不入库）
- 优化项清单：本地维护（`.trae/mlopt/optimization-inventory.md`，已 gitignore 不入库）
- [部署指南](DEPLOYMENT_GUIDE.md)
- [紧急运维手册](EMERGENCY_RUNBOOK.md)
