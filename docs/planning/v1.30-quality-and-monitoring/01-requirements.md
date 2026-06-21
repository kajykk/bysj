# v1.30-quality-and-monitoring 需求文档

> **迭代名称**: v1.30-quality-and-monitoring
> **上一迭代**: v1.29-launch-readiness (FINAL-GO)
> **创建日期**: 2026-06-02
> **类型**: Quality & Observability 增强

---

## 1. 迭代目标

### 1.1 核心目标

在 v1.29 上线就绪基础上，提升系统质量、可观测性和防御能力：

1. **测试通过率 100%**: 修复剩余 32 个非阻塞 WebSocket/Contract 测试
2. **生产可观测性**: 添加 Prometheus /metrics 端点，集成 Sentry/结构化日志
3. **认证契约一致性**: 统一 auth 响应格式
4. **版本演进**: v1.28-final → v1.30 (语义版本)

### 1.2 成功标准

| 标准 | 当前 | 目标 | 验收方式 |
|---|---|---|---|
| 全量测试通过率 | 95.3% (32 失败) | **100%** | pytest |
| 核心测试通过率 | 100% | 100% (保持) | pytest |
| /metrics 端点 | 不存在 | **可用** | curl/集成测试 |
| Prometheus 指标 | 不存在 | **≥5 类** | 端点响应 |
| 版本号一致性 | v1.28-final | **v1.30** | /version API |

---

## 2. 需求范围

### 2.1 测试质量 (P0)

#### 2.1.1 WebSocket 测试修复

- [ ] `tests/api/test_websocket.py`: 适配新的 `{"type": "auth", "token": ...}` 认证流
- [ ] `tests/api/test_websocket_p0p1.py`: 同上
- [ ] 添加 unit test 覆盖 `_normalize_websocket_token`
- [ ] 添加 unit test 覆盖 `_receive_auth_token` 异常路径

#### 2.1.2 Contract 测试修复

- [ ] `tests/contract/test_auth_api.py`: 修复 auth 响应格式断言
- [ ] 添加 schema 校验统一处理

#### 2.1.3 API 测试稳定性

- [ ] Resilience / security 长时序测试: 添加超时与 mock 优化
- [ ] Fusion resilience 测试: 修复模型加载 mock
- [ ] Miscellaneous 4 项: 逐一分析修复

### 2.2 可观测性 (P0)

#### 2.2.1 Prometheus /metrics 端点

- [ ] 新增 `app/api/v1/metrics.py` 提供 `/api/v1/metrics`
- [ ] 指标类别：
  - `http_requests_total{method,path,status}` - 计数器
  - `http_request_duration_seconds_bucket{le,method,path}` - 直方图
  - `model_inference_total{model_name,status}` - 计数器
  - `model_inference_duration_seconds{model_name}` - 直方图
  - `websocket_connections_active` - 仪表
  - `db_pool_size` / `db_pool_checkedout` - 仪表
  - `app_info{version,status}` - 信息
- [ ] 集成 prometheus_client (`prometheus-client>=0.19`)
- [ ] 添加 ASGI 中间件记录请求指标
- [ ] 添加测试覆盖

#### 2.2.2 性能指标采集

- [ ] FastAPI 中间件: 自动记录请求耗时
- [ ] 模型推理耗时: 统一包装
- [ ] DB 连接池: 定期抓取
- [ ] 缓存命中率: 如果启用

### 2.3 认证契约 (P1)

#### 2.3.1 Auth 响应统一

- [ ] 登录响应: `{access_token, refresh_token, token_type, user}`
- [ ] 注册响应: `{user_id, username, ...}` 与登录一致
- [ ] 刷新响应: `{access_token, refresh_token, token_type}`
- [ ] Pydantic schema 统一

#### 2.3.2 Auth Contract 测试

- [ ] 修复 2 个 contract 测试断言
- [ ] 添加 contract 校验工具

### 2.4 版本号统一 (P1)

- [ ] `app/api/v1/version.py` 更新为 `v1.30-quality-monitoring`
- [ ] `docker-compose.yml` 镜像 tag 更新
- [ ] `backend/Dockerfile` 中 LABEL 同步
- [ ] 健康检查端点返回版本号

---

## 3. 非功能需求

### 3.1 性能

- /metrics 端点响应时间 < 50ms
- 指标采集不影响 API 性能 (P99 增量 < 5ms)
- 测试全量 < 5 分钟

### 3.2 可靠性

- 指标采集失败不影响主请求
- 优雅降级: prometheus_client 缺失时不抛错
- 测试无 flaky

### 3.3 可维护性

- 指标命名规范 (Prometheus 约定)
- 标签基数受控 (避免高基数)
- 文档同步更新

---

## 4. 验收标准

### 4.1 测试验收

- [x] 32 个失败测试全部修复
- [x] 全量测试通过率 100%
- [x] 核心测试通过率 100% (保持)
- [x] 新增测试覆盖 /metrics 端点 (≥5 个测试)

### 4.2 可观测性验收

- [x] /metrics 返回 Prometheus 格式
- [x] 包含 5+ 类指标
- [x] Docker Compose 集成说明
- [x] Grafana dashboard 配置建议文档

### 4.3 部署验收

- [x] 镜像可构建
- [x] 健康检查通过
- [x] /version 返回 v1.30
- [x] /metrics 端点可访问

---

## 5. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 修复 WebSocket 测试改动大 | 影响面广 | 单独 PR 隔离，逐步验证 |
| Prometheus client 性能 | 拖慢 API | 仅必要指标，标签基数受控 |
| Auth 响应契约变动 | 前端可能受影响 | 保持向后兼容字段 |
| sklearn/joblib 版本冲突 | 序列化失败 | 锁定 1.7.2 |

---

## 6. 迭代边界

### 包含

- 修复 32 个非阻塞测试
- 添加 Prometheus /metrics
- Auth 响应一致性
- 版本号统一

### 不包含

- 训练新模型 (后续迭代)
- K8s Helm (后续迭代)
- 多模态扩展 (后续迭代)
- 前端功能升级

---

> **文档版本**: v1.0
> **最后更新**: 2026-06-02
