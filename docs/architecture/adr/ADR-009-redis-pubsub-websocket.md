# ADR-009: Redis pubsub 而非 RabbitMQ 用于 WebSocket 多 worker 消息广播

## 状态 (Status)
Accepted

## 日期 (Date)
2026-07-03

## 上下文 (Context)
DWS 系统通过 WebSocket 向用户与咨询师实时推送告警、预警、危机干预通知 (例如: 风险评分突升、咨询师接管请求、危机事件状态变更)。

生产部署采用多 Uvicorn worker (默认 4 个) 以利用多核。WebSocket 连接是有状态的: 一个用户的连接只存在于某一个 worker 进程内。问题由此产生:

- 用户 A 的 WebSocket 连接在 worker-1, 但触发告警的请求 (例如定时任务在 worker-3 跑出新的风险评估) 在 worker-3;
- worker-3 无法直接把消息推给 worker-1 的连接;
- 若不做跨 worker 广播, 用户 A 将收不到告警, 严重影响危机干预时效。

因此需要一个跨 worker 的消息总线, 将「某 worker 触发的告警」广播到「所有 worker」, 各 worker 再转发给各自持有的目标用户连接。

约束:
- 系统已部署 Redis (用于缓存、Celery broker、限流), 不希望引入新中间件;
- 延迟敏感: 告警推送延迟需 < 200ms (危机干预场景);
- 用户连接数上限 5 (防滥用), 总连接规模在数千级别, 不需要 Kafka 级吞吐。

## 决策 (Decision)
使用 Redis pubsub 作为 WebSocket 跨 worker 消息总线, 实现位于 `app/core/ws.py` 的 `ConnectionManager`。

### 频道设计
- 用户级频道: `ws:user:{user_id}` — 定向推送给某用户的所有连接;
- 广播频道: `ws:user:broadcast` — 推送给所有在线用户 (用于系统公告/全局告警)。

### 消息格式
```json
{"node_id": "<uuid4 hex>", "message": {...}, "broadcast": false}
```
- `node_id`: 每个 worker 进程启动时生成 (`uuid.uuid4().hex`), 用于识别消息来源, 防止回环;
- `message`: 实际业务消息体 (告警/预警/干预通知);
- `broadcast`: 是否为广播消息。

### 投递流程
1. **发送方 worker**:
   - 本地投递: 直接遍历本进程内该用户的 WebSocket 连接发送 (覆盖本 worker 上的连接);
   - 跨 worker 投递: `await client.publish(f"{WS_PUBSUB_CHANNEL_PREFIX}{user_id}", payload)` 发布到 Redis 频道;
   - Redis publish 失败仅记录日志不阻塞业务流程 (返回 False, 调用方仅 log)。
2. **订阅方 worker**:
   - 每个 worker 启动时创建后台 `asyncio.Task` (`_pubsub_task`) 订阅 `ws:user:*` 模式;
   - 收到消息后检查 `node_id`: 若等于本进程 `_node_id`, 跳过 (防止回环); 否则向本进程内该用户的连接转发。
3. **连接管理**:
   - 每用户最多 5 个连接 (`MAX_CONNECTIONS_PER_USER`), 超出拒绝;
   - 连接字典读写用 `asyncio.Lock` 保护 (`_lock`), 防止并发 connect 导致计数错乱;
   - 连接数通过 Prometheus gauge `websocket_connections_active` 暴露。

### 容错
- Redis 连接断开时, pubsub 订阅自动重连 (redis-py 内建), 重连期间消息丢失由上层 at-least-once 协议缓解 (重要告警同时入库 `alerts` 表, 客户端重连后通过 REST 拉取漏掉的告警);
- `_publish_to_redis` 失败不抛异常, 仅返回 False 并 log warning, 避免阻塞告警生成主流程。

## 替代方案 (Alternatives Considered)
1. **RabbitMQ fanout exchange** — 专为消息广播设计, 支持持久化与确认。优点: 消息可靠; 缺点: 需引入 RabbitMQ 中间件 (新增容器、运维、监控), 而系统已有 Redis, 增加运维负担; WebSocket 通知是「尽力推送 + 客户端拉取兜底」语义, 不需要 MQ 级持久化; RabbitMQ fanout 路由开销也比 Redis pubsub 高。
2. **数据库轮询** — worker 周期性查 `alerts` 表的 `delivered=False` 记录。缺点: 轮询延迟高 (1–5s), 高频查表打 DB, 且无法做到「用户在线时立即推送」。
3. **每个用户连接所有 worker** — 客户端同时连 4 个 worker。缺点: 资源浪费 (连接数 ×4), 客户端复杂度极高, 消息去重困难。
4. **限制单 worker 部署** — 只跑 1 个 Uvicorn worker, 无需跨进程广播。缺点: 单点故障, 无法利用多核, 不满足生产可用性要求。
5. **Redis Streams** — 介于 pubsub 与 MQ 之间, 支持持久化与消费组。比 pubsub 重, 且 WebSocket 在线推送不需要持久化 (离线消息由 alerts 表 + REST 拉取处理), 引入消费组管理复杂度不值得。

## 后果 (Consequences)
- **正面**:
  - 复用现有 Redis, 零新增中间件, 部署与运维成本不变;
  - 低延迟: Redis pubsub 端到端延迟 < 5ms, 满足 < 200ms SLO;
  - 自动扩展: 新增 worker 自动订阅频道, 无需额外配置;
  - `node_id` 回环防护简单可靠, 不依赖外部协调;
  - 与已有 Redis 缓存/限流/Celery 共用连接池, 资源利用率高。
- **负面**:
  - Redis pubsub 无持久化: 订阅者断开期间的消息会丢失。通过上层 at-least-once 协议缓解 — 重要告警同时写 `alerts` 表, 客户端重连后通过 `GET /api/v1/user/warnings?since=<last_id>` 拉取漏掉的消息;
  - Redis 故障时整个 WebSocket 推送链路失效。通过 Redis Sentinel/Cluster + `db_breaker` 熔断 + 客户端轮询兜底缓解;
  - `ws:user:{user_id}` 频道数等于在线用户数, Redis 频道表膨胀。当前规模 (数千用户) 可接受, 超大规模需改用 sharded pubsub。
- **中性**:
  - 需正确处理 `node_id` 回环: 忘记检查会导致消息被原 worker 重复投递;
  - 订阅任务需在 worker 关闭时优雅取消, 避免 `Event loop is closed` 警告;
  - 连接断开后 Redis 频道不会自动清理 (pubsub 无订阅计数), 但 redis-py 客户端断开时自动 unsubscribe, 实际无泄漏;
  - 客户端需实现「WebSocket 推送 + REST 拉取兜底」双通道, 不能假设 WebSocket 100% 可达。

## 关联 (Related)
- 实现: `backend/app/core/ws.py` (`ConnectionManager`, `WS_PUBSUB_CHANNEL_PREFIX`, `_node_id`, `_publish_to_redis`, `_pubsub_task`)
- 共享客户端: `backend/app/core/cache.py` (`get_redis_client`)
- 告警服务: `backend/app/services/alert_lifecycle_service.py`, `backend/app/services/warning_service.py`
- 前端: `frontend/src/composables/useWebSocket.ts`, `frontend/src/composables/useWebSocket.test.ts`
- 监控: `backend/app/core/metrics.py` (`websocket_connections_active` gauge)
- 测试: `backend/tests/test_websocket.py`, `backend/tests/test_websocket_p0p1.py`, `backend/tests/test_ws_pubsub.py`, `backend/tests/test_websocket_auth.py`
- 兜底: `backend/app/api/v1/user_warning.py` (REST 拉取漏掉的告警)
- 相关 ADR: ADR-008 (ready 探针检查 Redis 连通性, 影响 WebSocket 推送可用性)
