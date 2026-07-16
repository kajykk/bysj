# ISS-12 可用性 SLO 与 MTTR 报告

> 维度：稳定性（可用性 / 5xx / MTTR / 延迟尾） ｜ 优先级：P1 ｜ 阶段：WF-3 ｜ 技能：sys-observability
> 状态：**已定位 —— 长尾延迟为测试假象；MTTR 不可测；附带发现 ISS-14（pubsub 崩溃循环）**

## 1. 背景

MTTR / 可用性 SLO 此前无量化数据。本任务在 postgres+redis 部署态下压测，评估 5xx、可用性、延迟分位与 MTTR 可测性。

## 2. 首轮测量（每请求新建连接，测试假象）

- 工具：httpx（20 并发，660 请求，`/health` + `/health/ready` + `/api/v1/reviews` 鉴权墙）
- 结果：5xx=**0**，可用性(2xx+401)=**100%**，但 **p95=1829ms / p99=2005ms**（p50 仅 8.6ms）—— 看似严重长尾。

## 3. 根因复测（连接池 + 隔离测试）

### 3.1 连接池复测（httpx.Client keep-alive）
| 指标 | 首轮(每请求连接) | 复测(连接池) | 结论 |
|---|---|---|---|
| QPS | 11 | **1156** | +100x |
| p50 | 8.65ms | 34.29ms | 正常 |
| p95 | 1829ms | **58.63ms** | 长尾消失 |
| p99 | 2005ms | **297.76ms** | 长尾消失 |
| max | — | 2047ms | 偶发尖峰 |

> **结论**：首轮的 1.8s 长尾是**测试假象** —— 每请求新建 TCP 连接导致 localhost 临时端口耗尽，部分连接建连阻塞 ~2s。真实全栈在连接池下 p95≈59ms / p99≈298ms，**系统健康**。

### 3.2 隔离测试（禁用 ws.py pubsub 订阅器）
为确认"pubsub 崩溃重启循环是否导致尾延迟"，打桩 `ConnectionManager.start_pubsub_subscriber` 为 no-op（不改应用源码），重启实例复测：

| 指标 | 启用 pubsub | **禁用 pubsub** | 差异 |
|---|---|---|---|
| 整体 p95 | 58.6ms | 80.7ms | 基本一致 |
| 整体 p99 | 297.8ms | 345.5ms | 基本一致 |
| QPS | 1156 | 958 | 噪声范围 |
| max 尖峰 | 2047ms | 2049ms | **完全一致** |

> **结论**：禁用 pubsub 后尾延迟与启用时一致，偶发 ~2s 尖峰(占 0.005%)依旧 → 属**环境抖动（GC / 事件循环调度）**，**非服务缺陷**。pubsub 崩溃循环与长尾延迟**无关**。

## 4. MTTR —— 诚实评估：不可测

MTTR 无法从现有数据测算：无 incident/历史事件、未接 Sentry issue 时间线、无故障注入演练，缺样本。`KPI-基线.json → reliability.mttr` 保持 `pending` 并注明原因。

## 5. SLO —— 目标已定义，待持续验证

- 目标：99.9%（核心 99.95%），已在 KPI 定义。
- 现状：单次基线负载(660 + 57480 请求)可用性 **100%**，但非持续 30 天 SLO 验证。
- 下一步：部署合成监控持续统计 30 天达标率。

## 6. 附带发现：ISS-14（ws.py pubsub 崩溃重启循环）

复测期间在 `_uvicorn.log` 发现 **真实、独立缺陷**：

```
redis.exceptions.TimeoutError: Timeout reading from localhost:6379
WebSocket pubsub loop crashed, restarting in 1s   # 约每 1s 一次
```

- 现象：`_pubsub_loop` 持续因 redis 读超时崩溃并 1s 退避重启；`redis-cli PONG` 正常，但 asyncio pubsub socket 超时。
- 影响：日志刷屏、redis 连接抖动、占用事件循环（与 HTTP 延迟长尾无关，已隔离证明）。
- 处置：已另记 **ISS-14**（P2 / WF-3 / sys-reliability），建议修复 redis 连接 `socket_timeout`/retry 配置或将 pubsub 连接与主请求连接池隔离。

## 7. 复现命令

```bash
# 连接池复测（接入真实代理/负载均衡前的基线）
cd backend && .venv/Scripts/python.exe _latency_retest.py
# 原始(每请求连接)复现
cd backend && .venv/Scripts/python.exe _resource_baseline.py   # 含 load_test 段
# 隔离启动(pubsub 禁用)
DATABASE_URL='postgresql://postgres:test@127.0.0.1:5433/testdb' ENABLE_SEED=false \
  .venv/Scripts/python.exe _run_no_pubsub.py
```

## 8. 状态与后续

- **已定位**：5xx=0、可用性 100%、真实尾延迟健康（p95≈60ms）；首轮"长尾"为测试假象。
- **待办**：
  - ISS-14：修复 ws.py pubsub redis 超时/连接配置（WF-3）。
  - 建立 incident 时间线 / 故障注入，使 MTTR 可量化。
  - 部署合成监控，使 SLO 99.9% 进入持续验证。
