# 04-ralph-tasks.md — v1.30-quality-and-monitoring

> **执行原则**: 按物理顺序执行。每完成一个任务标记 `[x]`。
> **基础迭代**: v1.29-launch-readiness (FINAL-GO)

---

## Phase 1: 测试质量修复 (P0)

### T1.1 修复 WebSocket 测试 (test_websocket.py)

- [x] 适配新认证流 `{"type": "auth", "token": ...}`
- [x] 添加 happy path 测试 (auth + ping/pong)
- [x] 添加 reject 测试 (refresh_token, mismatched user_id, missing auth)
- [x] 验证所有场景

### T1.2 修复 WebSocket P0P1 测试 (test_websocket_p0p1.py)

- [x] 改用 message-based auth
- [x] 参数化测试覆盖

### T1.3 添加 _normalize_websocket_token 单元测试

- [x] 覆盖 None / 空 / Bearer 前缀 / 大小写

### T1.4 添加 _receive_auth_token 单元测试

- [x] 覆盖 valid auth / wrong type / invalid JSON / disconnect

### T1.5 修复 auth response contract 测试

- [x] 统一 LoginResponse / RegisterResponse schema
- [x] 修复 2 个 contract 断言

### T1.6 修复 resilience / security 长时序测试

- [x] 添加超时配置
- [x] Mock 优化

### T1.7 修复 fusion resilience 测试

- [x] Mock 模型加载
- [x] 修复 import path

### T1.8 修复 miscellaneous 4 项测试

- [x] 逐一分析失败根因
- [x] 修复或标记合理 skip

---

## Phase 2: 可观测性 (P0)

### T2.1 添加 prometheus_client 依赖

- [x] 更新 `requirements.txt` (决策: 零依赖,自研实现)

### T2.2 创建 metrics 中间件

- [x] `app/core/metrics.py`: 指标定义
- [x] `app/middleware/observability.py`: 请求耗时中间件

### T2.3 创建 /metrics 端点

- [x] `app/api/v1/metrics.py`
- [x] 注册到 router

### T2.4 集成到 main.py

- [x] 注册中间件
- [x] 优雅降级 (无 prometheus_client 时不抛错)

### T2.5 添加 metrics 测试

- [x] 端点可访问
- [x] 包含核心指标
- [x] 指标格式正确

---

## Phase 3: Auth 契约一致性 (P1)

### T3.1 统一 auth 响应 schema

- [x] 添加 `app/schemas/auth_responses.py`
- [x] 三个端点响应使用统一 schema

### T3.2 修复 Pydantic 弃用警告

- [x] 优先迁移 AuthResponse / LoginRequest
- [x] 避免大量破坏性改动

---

## Phase 4: 版本号统一 (P1)

### T4.1 更新 version.py

- [x] RELEASE_VERSION = "v1.30-quality-monitoring"
- [x] RELEASE_DATE = "2026-06-02"
- [x] RELEASE_STATUS = "QUALITY-ENHANCED"

### T4.2 更新 docker-compose.yml

- [x] 镜像 tag 同步

### T4.3 更新 health 端点

- [x] 包含版本号

---

## Phase 5: 文档与交付 (P1)

### T5.1 生成 PROMETHEUS_INTEGRATION.md

- [x] 端点说明
- [x] Grafana dashboard 建议
- [x] 告警规则建议

### T5.2 更新 LAUNCH_BLOCKERS / DEPLOYMENT_CHECKLIST

- [x] 同步 v1.30 状态

### T5.3 生成 DELIVERY_REPORT.md

- [x] 总结测试结果
- [x] 代码变更清单
- [x] 上线建议

### T5.4 更新 RALPH_STATE.md

- [x] 标记完成状态
- [x] 记录 P0 任务

---

## 进度统计

- 总任务数: 22
- P0: 13
- P1: 9
- 完成: **22/22 (100%)**
