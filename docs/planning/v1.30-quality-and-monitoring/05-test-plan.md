# 05-test-plan.md — v1.30-quality-and-monitoring

> **执行原则**: 按物理顺序验证。每完成一个测试标记 `[x]`。
> **关联任务**: 04-ralph-tasks.md

---

## Phase 1: 测试质量验证

### TC-WS-001: WebSocket 接受有效 access_token

- [x] 连接 /ws/{user_id}
- [x] 发送 `{"type": "auth", "token": "<access>"}`
- [x] 收到成功响应
- [x] 发送 `{"type": "ping"}` 收到 `{"type": "pong"}`

### TC-WS-002: WebSocket 拒绝 refresh_token

- [x] 发送 refresh_token 收到 close 4001

### TC-WS-003: WebSocket 拒绝无效 token

- [x] 发送 `{"type": "auth", "token": "garbage"}` 收到 close 4001

### TC-WS-004: WebSocket 拒绝 user_id 不匹配

- [x] Token sub != URL user_id 收到 close 4001

### TC-WS-005: WebSocket 拒绝缺少 auth

- [x] 直接发送 ping 收到 close 4001

### TC-WS-006: WebSocket 拒绝 URL 参数中的 token

- [x] `/ws/1?token=...` 收到 close 4001 "Token禁止通过URL参数传递"

### TC-WS-007: _normalize_websocket_token 单元测试

- [x] None -> ""
- [x] "" -> ""
- [x] "bearer xxx" -> "xxx" (大小写不敏感)
- [x] "  xxx  " -> "xxx"

### TC-WS-008: _receive_auth_token 单元测试

- [x] valid auth JSON -> token
- [x] wrong type -> ""
- [x] invalid JSON -> ""
- [x] missing token -> ""

### TC-CONTRACT-001: Auth login 响应格式

- [x] 包含 access_token / refresh_token / token_type / user
- [x] user 包含 id / username / role / nickname

### TC-CONTRACT-002: Auth register 响应格式

- [x] 包含 user_id / username / role

### TC-CONTRACT-003: Auth refresh 响应格式

- [x] 包含 access_token / refresh_token / token_type

---

## Phase 2: Metrics 验证

### TC-METRICS-001: /metrics 端点可访问

- [x] GET /api/v1/metrics 返回 200
- [x] Content-Type 包含 text/plain

### TC-METRICS-002: 核心指标存在

- [x] http_requests_total
- [x] http_request_duration_seconds
- [x] app_info

### TC-METRICS-003: HTTP 请求指标自动记录

- [x] 触发 5 个请求
- [x] http_requests_total 增加 5

### TC-METRICS-004: 模型推理指标

- [x] 触发 predict 接口 (webhook 验证)
- [x] model_inference_total 增加 (在生产模型推理时)

### TC-METRICS-005: WebSocket 指标

- [x] 建立连接后 websocket_connections_active = 1
- [x] 断开后 -1

### TC-METRICS-006: 端点格式合规

- [x] 包含 HELP 和 TYPE 注释
- [x] 符合 Prometheus exposition format

### TC-METRICS-007: 优雅降级

- [x] 指标收集失败被 try-except 捕获
- [x] 不抛 500

---

## Phase 3: 版本与集成验证

### TC-VER-001: /version 端点

- [x] 返回 version = "v1.30-quality-monitoring"
- [x] 返回 release_date = "2026-06-02"
- [x] 返回 status = "QUALITY-ENHANCED"

### TC-VER-002: /health 包含版本

- [x] 响应包含 version 字段

### TC-VER-003: docker-compose 镜像 tag

- [x] `image: dws-backend:v1.30` 存在

---

## Phase 4: 全量回归

### TC-REG-001: 核心测试组

- [x] tests/api/test_websocket.py 全过
- [x] tests/api/test_websocket_p0p1.py 全过
- [x] tests/api/test_access_control_regression.py 全过
- [x] tests/unit/test_websocket_helpers.py 全过
- [x] tests/contract/test_auth_api.py 全过
- [x] tests/api/test_metrics.py 全过

### TC-REG-002: 测试通过率 100%

- [x] pytest 全量 0 失败 (核心组)

---

## 进度统计

- 总测试用例: 23
- P0: 18
- P1: 5
- 完成: **23/23 (100%)**
