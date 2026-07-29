# 金丝雀发布操作手册 (S-01~S-05 V4.1)

## 概述

本文档描述 S-01~S-05 五个 Phase 1 优化项作为 `v4.1-s01-s05` 版本的金丝雀发布流程。

**三级推进**: 5% → 25% → 100%，每级观察 ≥24h
**自动回滚阈值**: fallback 率 <5%、漂移告警 <10 次/小时、平均延迟 <500ms、错误率 <10%

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
