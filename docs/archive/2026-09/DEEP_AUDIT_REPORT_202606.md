# 全量深度审核报告

> 审核日期：2026-06-25
> 审核范围：backend/app（core / api / services / ml / tasks / schemas）+ frontend（src / 配置 / 部署）
> 审核说明：已忽略所有状态文档与 ralph 文档，仅审核实际功能代码
> 审核方法：5 路并行深度代码审核 + 关键 bug 二次验证 + 误报修正

---

## 一、执行摘要

本次审核对 Depression Warning System（FastAPI + Vue 3 + ML）进行了全量代码审核，覆盖后端 31 个核心模块、25 个 API 端点、28 个服务、25 个 ML 模块、5 个 Celery 任务，以及前端 50+ 个文件（API 层、组件、composables、路由、构建配置、部署配置）。

### 问题统计

| 模块 | CRITICAL | HIGH | MEDIUM | LOW | 合计 |
|------|---------|------|--------|-----|------|
| 后端核心（core） | 2 | 9 | 16 | 8 | 35 |
| 后端 API（api） | 6 | 12 | 17 | 11 | 46 |
| 后端服务（services） | 8 | 17 | 19 | 7 | 51 |
| 后端 ML + 任务 | 2 | 6 | 9 | 10 | 27 |
| 前端（frontend） | 5 | 8 | 23 | 20 | 56 |
| **合计** | **23** | **52** | **84** | **56** | **215** |

### 误报修正（经二次验证）

以下问题在子代理初审中报告，经直接读取源码复核后确认误报或需降级：

- **误报**：`core/model_engine.py:1676` 生理模型概率取反。实际该模型为自定义 numpy MLP，`predict_proba` 返回单列 sigmoid 输出，`proba[0][0]` 即 P(depression)，方向正确。
- **误报**：`core/ws.py:63` `send_to_user` 迭代时列表被修改。实际 `disconnect` 通过重新赋值 `self._connections[user_id] = [...]` 创建新列表，不修改原列表引用，迭代安全。
- **降级**：`core/ws.py:25` `ConnectionManager.connect` 竞态。在单 event loop 下 `connect` 是同步方法，检查与 append 之间无 await，原子安全。仅在多 worker 部署下存在风险，降级为 LOW。
- **已实现**：`ws.py` WebSocket 鉴权实际已完善（URL token 拒绝 + 10s 认证超时 + token 类型/user_id 双重校验 + 用户状态校验 + 300s idle timeout + ping/pong 心跳 + 连接数上限）。

### 最紧急 Top 10 问题

1. **C-1**（services/auto_rollback_service.py:187）savepoint 内调用 commit() 破坏事务隔离
2. **C-2**（services/alert_lifecycle_service.py:77）状态机缺陷：CLOSED 告警无法重开但文档承诺可重开
3. **C-3**（services/gdpr_service.py:305）GDPR 被遗忘权遗漏大量含 PII 的表（ConsultationRecord、InterventionPlan、CrisisEvent 等）
4. **C-4**（api/v1/alerts.py:244）开发环境 webhook 完全无鉴权，可注入伪造告警触发外部通知
5. **C-5**（api/v1/review.py:88）咨询师水平越权：resolve/escalate 无 owner 校验
6. **C-6**（ml/model.py:135 + trainer.py:306）M-3 线程安全修复不完整，并发下 Dropout 可能被静默跳过
7. **C-7**（api/v1/alerts.py:269）webhook `generatorURL` 缺协议校验，可触发 SSRF
8. **C-8**（api/v1/user_upload.py:84）MIME 校验可被 polyglot 文件绕过
9. **C-9**（frontend/api/userFileApi.ts:8）FormData 上传时手动设置 Content-Type 破坏 boundary
10. **C-10**（frontend/api/request.ts:61）refresh 请求发送空字符串 Authorization 头导致刷新永远失败

---

## 二、后端核心模块审核（app/core）

### CRITICAL

#### C-Core-1 `pii_crypto.py:208` 盲索引 fallback 使用硬编码密钥
- **问题**：当 `pii_encryption_key` 为空且非生产环境时，`compute_blind_index` 使用硬编码 `"dev-only-fallback-key"` 计算 HMAC。开发环境所有盲索引（email_hash、phone_hash）基于公开密钥，攻击者可对已知明文批量计算反查 PII。
- **修复**：移除 fallback，直接 `raise RuntimeError`。`config.py` 的 `model_validator` 已保证非生产环境自动生成随机密钥，此处不应再 fallback。

#### C-Core-2 `model_engine.py:470` Keras 模型加载修改全局 `Dense.from_config`
- **问题**：使用 `with _keras_load_lock:` 临时替换全局类方法 `Dense.from_config`，若 `load_model` 内部触发其他线程的模型加载，会用到被修改的 `Dense.from_config`，造成不可预测行为。
- **修复**：使用 `tf.keras.models.load_model` 的 `custom_objects` 参数传递兼容 Dense 子类，避免修改全局类。

### HIGH

#### H-Core-1 `database.py:41` get_db 自动 commit 可能提交非预期变更
- **问题**：`yield session` 后自动 `await session.commit()`。对于只读路由，若 SQLAlchemy 触发 auto-flush，可能将意外变更提交。
- **修复**：改为不自动 commit，由路由显式 commit；或增加 `is_modified()` 检查。

#### H-Core-2 `cache.py:23` `threading.Lock` 用于保护异步 Redis 客户端
- **问题**：`_redis_client_lock = threading.Lock()` 在 asyncio 上下文中是反模式，若未来 `from_url` 改为阻塞会卡死事件循环。
- **修复**：改为 `asyncio.Lock`，或在启动钩子中提前完成初始化。

#### H-Core-3 `cache.py:108` Redis 异常时重置客户端可能引发雪崩
- **问题**：`cache_get`/`cache_set` 捕获任何异常后都调用 `_reset_redis_client()`，瞬时网络抖动下所有并发请求都重置并重建连接，引发连接风暴。
- **修复**：增加退避机制或断路器模式；区分连接异常与应用异常。

#### H-Core-4 `rate_limit.py:44` X-Forwarded-For 解析信任链不完整
- **问题**：取 X-Forwarded-For 的第一个 IP，但攻击者可通过受信代理发送 `X-Forwarded-For: fake_ip, real_ip`，使 `split(",")[0]` 返回 `fake_ip` 绕过限流。
- **修复**：从右向左遍历 X-Forwarded-For，跳过所有受信代理 IP，第一个非受信代理 IP 才是真实客户端 IP。

#### H-Core-5 `config.py:70` `SKLEARN_VERSION` 是函数而非 property
- **问题**：注释称 lazy property，但实际定义为普通函数 `def SKLEARN_VERSION()`。调用方若写 `settings.SKLEARN_VERSION`（不带括号）会得到函数对象而非版本字符串。
- **修复**：使用 `@cached_property` 或修正注释。

#### H-Core-6 `model_registry_v2.py:300` 性能回归检查只检查 f1_score
- **问题**：遍历所有 metric 但只在 `metric == "f1_score"` 时执行回归检查，precision/recall/auc 等被静默忽略。
- **修复**：移除 `if metric == "f1_score"` 条件，对所有 metric 执行检查。

#### H-Core-7 `seed.py:34` 种子用户默认密码硬编码
- **问题**：`_E2E_ADMIN_PASSWORD = os.getenv(..., "E2E@Admin#S3cure!Dev")`。若 `app_env` 误配置为非 production，默认密码启用，形成已知弱口令后门。
- **修复**：默认值设为 `None`，未配置时直接 `raise RuntimeError`。

#### H-Core-8 `exceptions.py:142` 验证错误处理在循环内重复导入
- **问题**：`_validation_exception_handler` 在循环内 `from app.core.config import settings` 并调用 `settings.app_env.lower()`，每个错误重复导入与比较。
- **修复**：将导入与判断移到循环外。

#### H-Core-9 `middlewares.py:31` `request_id_middleware` 异常时 response 未定义
- **问题**：`try: response = await call_next(request) finally: set_current_trace(None)`。若 `call_next` 抛异常，`response.headers[...]` 会抛 `UnboundLocalError`。
- **修复**：将 headers 设置移到 try 块内。

### MEDIUM

- **M-Core-1** `config.py:109` `model_validator` 中突变 `self` 字段，线程不安全。建议改用 `mode="before"` 修改输入字典。
- **M-Core-2** `config.py:217` CORS 通配符校验在运行时而非启动时，应在 `model_validator` 中校验。
- **M-Core-3** `pii_crypto.py:158` 解密失败静默返回 `"[DECRYPTION_FAILED]"`，密钥轮换场景下数据静默丢失。建议记录 ERROR 日志或抛异常。
- **M-Core-4** `cache.py:174` MD5 取前 16 字符作为 cache key（64 bit），百万级 key 下碰撞概率非零。建议 SHA256 前 16 字符。
- **M-Core-5** `crisis_detector.py:139` `_is_casual_expression` 阈值 15 字过低，正常口语化表达（>15字）会被误判。建议提升至 30-50 字。
- **M-Core-6** `metrics.py:45` `Counter.inc` 不校验负值，破坏 Prometheus 语义。建议加 `if amount < 0: raise ValueError`。
- **M-Core-7** `model_engine.py:1661` BN running stats 检查后重载不重新验证，重载失败仍带错误 stats 推理。
- **M-Core-8** `fallback_hierarchy.py:115` 同步路径中收到 coroutine 时 `result.close()` 可能清理不完整。建议仅记录日志并抛异常。
- **M-Core-9** `tracing.py:84` `_lock = threading.Lock()` 声明但从未使用，死代码。
- **M-Core-10** `request_id.py:10` 不校验客户端传入的 `x-request-id` 格式，可注入 CRLF。建议校验 `[a-zA-Z0-9-]{8,64}`。
- **M-Core-11** `risk_thresholds.py:66` `get_fusion_threshold` 语义混乱，低置信度强制返回 moderate，score=0 返回 mild 而非 0。
- **M-Core-12** `seed.py:533` `_seed_users` 查询所有用户无 WHERE 过滤，大数据集下 OOM。
- **M-Core-13** `sentry.py:51` `range(500, 599)` 遗漏 599，建议 `range(500, 600)`。
- **M-Core-14** `model_registry_v2.py:116` `_load_registry` 异常捕获不全，只捕获 `JSONDecodeError`/`KeyError`，其他异常会传播导致启动崩溃。
- **M-Core-15** `ws.py:25` `connect` 竞态（原 C-03 降级）：单 event loop 下同步方法原子安全，但多 worker 部署下有风险。建议加 `asyncio.Lock` 或改 async。
- **M-Core-16** `health.py:116` `lightweight_health_snapshot` 返回静态 `database=True` 未实际检查，建议标记 `verified=False`。

### LOW

- **L-Core-1** `security.py:62` 密码重置 token 缺少 `jti`，无法单独吊销。
- **L-Core-2** `celery_app.py:139` tuple 子类重建可能失败，建议 `return tuple(masked)`。
- **L-Core-3** `exceptions.py:169` 通用异常处理器在开发环境也返回笼统消息，应返回更多调试信息。
- **L-Core-4** `cache.py:151` `make_cache_key` 不处理 `params` 中的 None 值，可能导致缓存分裂。
- **L-Core-5** `model_engine.py:1557` `_predict_physiological` 检查 PyTorch 但模型实际是 numpy。
- **L-Core-6** `health.py:116` `lightweight_health_snapshot` 命名误导。
- **L-Core-7** `seed.py:776` `date.today()` 使用本地时区，跨时区部署不一致。
- **L-Core-8** `model_registry.py:318` `normalize_model_id` 是 no-op，可能误导调用方。

---

## 三、后端 API 层审核（app/api）

### CRITICAL

#### C-API-1 `alerts.py:244` 开发环境 webhook 完全无鉴权
- **问题**：当 `alertmanager_webhook_secret` 未设置且 `app_env != "production"` 时，`/alerts/webhook` 端点完全开放，任何外部请求都能注入伪造告警，触发 `CompositeNotifier` 真实通知通道，造成告警风暴、社会工程攻击。
- **修复**：开发环境也强制要求 Bearer token（使用默认 dev secret），或限制 `127.0.0.1` 来源。

#### C-API-2 `metrics.py:44` Prometheus 端点开发环境开放
- **问题**：与 C-API-1 同样问题，`/metrics` 完全开放泄露 `http_requests_total{path}`、`db_pool_size`、`model_inference_total` 等内部指标。
- **修复**：所有环境都强制 token；或限制源 IP 至监控服务器。

#### C-API-3 `alerts.py:269` webhook `generatorURL` 缺协议校验导致 SSRF
- **问题**：`generatorURL` 仅长度限制，无协议白名单。攻击者可注入 `javascript:`、`data:`、内网 URL（`http://169.254.169.254/`），通过通知渠道触发 SSRF/XSS。
- **修复**：增加 `http(s)://` 协议前缀校验；对内网 IP 黑名单；通知前 HTML 转义。

#### C-API-4 `admin_metrics.py:29` 内存指标无脱敏
- **问题**：`/admin/metrics-summary` 暴露 `top_paths`（含 admin 接口路径）、`db_pool_size`、`env`、`version`，admin token 泄露即暴露完整 API 表面。
- **修复**：对 `top_paths` 模糊化（如 `/api/v1/admin/*`）；移除 `env` 或返回 `is_production` 布尔值。

#### C-API-5 `review.py:88` 咨询师水平越权
- **问题**：`resolve_review`/`escalate_review` 仅校验 `review.handle` 权限，未检查 `task.assigned_to == current_user.id`，任何咨询师都能操作任意任务。
- **修复**：在路由或 service 层增加：若 `current_user.role == "counselor"` 则必须 `task.assigned_to == current_user.id`，否则 403。

#### C-API-6 `validation.py:317` 路径遍历残留风险
- **问题**：`_validate_dataset_path` 使用 `resolve()` + `relative_to` 校验，但 Windows 下 null byte 或保留名（`CON`、`AUX`）行为不一致，可能绕过。
- **修复**：拒绝包含 `\x00`、`..`、绝对路径前缀的输入；存储时只存相对路径。

### HIGH

#### H-API-1 `counselor.py:116` 用户咨询记录更新无归属校验
- **问题**：`update_consultation_record` 完全依赖 service 内部校验，路由层无显式 owner 检查，若 service 疏漏则构成 IDOR。
- **修复**：路由层显式校验 `user_id` 必须绑定到 `current_user`。

#### H-API-2 `user_data.py:47` 异常信息泄露
- **问题**：`ValueError` 原文拼接到 HTTP 422 响应 `detail=f"评估失败: {exc}"`，可能泄露内部字段名、模型路径。
- **修复**：仅返回模糊错误 "输入数据校验失败"，将 `exc` 写入日志。

#### H-API-3 `alerts.py:399` severity 过滤使用 contains 子串匹配
- **问题**：`OperationLog.detail.contains(...)` 生成 `LIKE '%"severity": "P0"%'`，不利用索引，百万级 OperationLog 查询造成 DoS。
- **修复**：为 OperationLog 增加独立 `severity` 字段；过渡期使用 PostgreSQL `->>` JSON 查询并加 GIN 索引。

#### H-API-4 `alerts.py:447` acknowledge_alert 无锁存在 TOCTOU 竞态
- **问题**：先 SELECT 检查 existing_ack 再 INSERT，两个 admin 并发确认同一 alert 会插入两条记录。
- **修复**：增加 `UNIQUE(target_id, action_type) WHERE action_type='alert_acknowledged'` 约束；或 `INSERT ... ON CONFLICT DO NOTHING`。

#### H-API-5 `alerts.py:223` webhook 无速率限制
- **问题**：`/alerts/webhook` 即使有密钥也无 `@limiter.limit`，单次 webhook 可含 500 条 alert，每条触发 4 个通知通道。
- **修复**：添加 `@limiter.limit("10/minute")`；批量通知时合并通道调用。

#### H-API-6 `admin.py` 所有 admin 端点无限流
- **问题**：所有 `/admin/*` 端点（dashboard、stats、archive-logs、export 等）无 `@limiter.limit`。`archive-logs` 单次调用归档全部日志可能造成 DB 长事务。
- **修复**：所有 admin 写操作加 `@limiter.limit("10/minute")`；archive-logs 改为后台任务。

#### H-API-7 `gdpr.py:110` export 流式输出无 size 限制
- **问题**：`export_my_data` 流式导出 8 个 section，重度用户可能产生数百 MB JSON，导致带宽耗尽和前端 OOM。
- **修复**：增加 max_records_per_section；导出前预估大小并设上限。

#### H-API-8 `user_upload.py:84` MIME 校验可被 polyglot 文件绕过
- **问题**：`_validate_mime_type` 只检查 magic 返回的 MIME，但允许 `audio/x-m4a` 等容器格式，可上传嵌恶意脚本的 polyglot。`upload_batch` 中 MIME 校验放在 save 之后，文件已落盘。
- **修复**：MIME 校验前置到 save 之前；对 `original_name` HTML 转义；集成 ClamAV。

#### H-API-9 `silences.py:42` 静默 matcher 可匹配所有告警
- **问题**：允许 `{"alertname": ""}` 空 value matcher（AlertManager 语义为匹配所有），可使所有告警被静默。未限制 `starts_at` 不能早于 now。
- **修复**：拒绝空 value；`starts_at` 必须 >= now - 5min。

#### H-API-10 `counselor.py:164` group_id 无归属校验
- **问题**：`add_group_member` 依赖 service 内部校验，错误返回模糊信息，可能向他人分组添加任意用户。
- **修复**：路由层增加 group 归属预校验；明确区分 404 与 403。

#### H-API-11 `alerts.py:269` 通知异常吞掉导致状态不一致
- **问题**：webhook 内对 `should_send`、`_persist_alert_log`、`notifier.send` 均 `except Exception` 兜底，持久化失败的告警丢失无重试，通知失败的告警状态仍为 "firing"。
- **修复**：持久化失败回写 AlertManager `error` 状态；通知失败标记为 "notify_failed"；返回 processed/failed 两个计数。

#### H-API-12 `auth.py:112` login 返回完整 user 对象
- **问题**：`data` 可能含 `user.id/role/username/email/phone` 等字段，response body 包含 `refresh_token` 与 Cookie 双轨重复。
- **修复**：响应体只返回 `access_token` 和必要非敏感字段；refresh_token 仅通过 Cookie。

### MEDIUM

- **M-API-1** `alerts.py:124` webhook 内 time 比较使用 mixed aware/naive，服务器非 UTC 时查询窗口偏移 8 小时。
- **M-API-2** `review.py:41` **危机事件列表 start_date/end_date 参数被完全忽略**（已验证真实 bug）。`CrisisEventFilter` 只接收 status/page/page_size。建议改为 datetime 类型并加入 filter。
- **M-API-3** `admin.py:156` audit-logs page_size 上限 200（其他端点 100），`action_types` 无长度限制。
- **M-API-4** 多个端点硬编码 `order_by(desc(created_at))` 不支持自定义排序，大表无索引时全表扫描。
- **M-API-5** `observability.py:222` `json.loads` 失败时设为空 dict，但 `created_at` 为 None 时 `_ensure_aware(None)` 抛 AttributeError 导致 500。
- **M-API-6** `observability.py:94` Cache Stampede 修复有缺陷：`_inflight_futures` 进程内不共享，leader 抛异常时所有 waiter 500 无 fallback。
- **M-API-7** `grafana_adapter.py:304` `start_time`/`end_time` 类型不一致（datetime vs str），`_parse_iso_datetime` 对多 "Z" 替换错误。
- **M-API-8** `auth.py:307` logout 日志含 user_id；`change_password`/`reset_password`/`update_profile` 完全无审计日志，违反合规。
- **M-API-9** `auth.py:54` Cookie dev 环境 `samesite="lax"` 但 `secure=False`，refresh cookie 通过非 HTTPS 传输。
- **M-API-10** `user_upload.py:185` upload_batch 10 文件共 200MB，串行处理可能触发网关超时。
- **M-API-11** `csp_report.py:49` 端点无鉴权，字段未做长度限制，可被伪造报告污染日志。
- **M-API-12** `analytics.py:115` web vitals 跨用户可见，`url` 可能含 query string 敏感参数，`limit` 无上限。
- **M-API-13** `auth.py:93` register 返回 user 对象可能泄露 password_hash/role，无邮箱验证流程。
- **M-API-14** `admin.py:240` CSV 导出无 filename 注入防护和 CSV Formula Injection 防护。
- **M-API-15** `silences.py:217` delete_silence 重复 DELETE 每次都写 OperationLog，无幂等性。
- **M-API-16** `observability.py:208` trend 限制 10000 但无分页，超出时统计失真无提示。
- **M-API-17** `user_intervention.py:47` 任务状态变更（complete/feedback/skip/postpone）路由层无 OperationLog，违反精神卫生干预合规。

### LOW

- **L-API-1** `version.py` 与 `admin_metrics.py:79` 硬编码版本号 `v1.32-observability-complete`，但其他模块用 v1.36/v1.37，版本号散落各处。
- **L-API-2** `monitoring.py:294` 使用 `Literal` 但文件顶部未 import，运行时抛 `NameError`，端点不可用。
- **L-API-3** `alerts.py` 多处 `[:5000]` 截断 detail，但 `silences.py:236` 未截断可能超 DB 字段限制。
- **L-API-4** `analytics.py:141` health 端点无鉴权泄露 service 名。
- **L-API-5** `user_risk.py:45` export filename 拼接可能 header 注入，pdf 分支类型未校验。
- **L-API-6** `admin.py:206` update_model 路由层未记录 OperationLog，审计责任不清晰。
- **L-API-7** `validation.py:403` 任务结果可被任意 admin 读取，无 created_by 过滤。
- **L-API-8** `observability.py:68` cache key 不含 user，但 isoformat 时区格式差异导致缓存命中率低。
- **L-API-9** `csp_report.py:73` 未校验 Content-Type，body 读取依赖框架行为。
- **L-API-10** `observability.py:208` trend 限制 10000 截断但无提示。
- **L-API-11** `user_intervention.py` 任务操作无审计。

---

## 四、后端服务层审核（app/services）

### CRITICAL

#### C-Svc-1 `auto_rollback_service.py:187` savepoint 内调用 commit() 破坏事务隔离
- **问题**：`execute_rollback` 在 savepoint 内调用 `await db_session.commit()`，会提交整个外层事务并释放所有 savepoint，导致：1) 单个 canary 回滚会提交调用方所有未提交更改；2) savepoint 隔离失效，后续 canary 检查运行在已污染事务上。
- **修复**：将 `commit()` 改为 `flush()`，由 `check_all_canaries` 的 `begin_nested()` 管理 savepoint。

#### C-Svc-2 `alert_lifecycle_service.py:77` 状态机缺陷：CLOSED 告警无法重开
- **问题**：`VALID_TRANSITIONS[CLOSED] = set()` 表示终态，但 `reopen_alert` 文档说"Reopen a resolved or closed alert"，调用 `transition_alert(TRIGGERED)` 会失败。业务逻辑矛盾。
- **修复**：若需重开 CLOSED：`CLOSED: {TRIGGERED}`；否则删除"or closed"措辞并抛明确异常。

#### C-Svc-3 `counselor_service.py:623` `bind_by_code` TOCTOU 竞态
- **问题**：placeholder 修改分支直接 `binding.user_id = user_id; await flush()`，若 `(actual_user_id, counselor_id)` 已被占用，flush 抛 IntegrityError 未被捕获。
- **修复**：try/IntegrityError 包裹 flush，失败后查询并复用已存在 binding。

#### C-Svc-4 `risk_service.py:470` CSV 导出未做公式注入防护
- **问题**：`csv.DictWriter.writerows` 直接写入 severity、assessment_type 等字段，未应用 `crisis_export_service._sanitize_csv_cell`。含 `=`、`+`、`@`、`-` 前缀时 Excel 触发公式注入。
- **修复**：抽出 `_sanitize_csv_cell` 为公共工具，写入每个字段前调用。

#### C-Svc-5 `risk_service.py:484` `_generate_pdf_report` 中 BytesIO 资源泄漏
- **问题**：`buffer = io.BytesIO()` 创建后 `return buffer.getvalue()` 从未 `close()`，未用 `with` 语句。并发调用时 worker 累积内存。
- **修复**：`with io.BytesIO() as buffer:` 后 `return buffer.getvalue()`。

#### C-Svc-6 `experiment_trainer.py:94` `compute_metrics` 中 `probs[:, 1]` 可能 IndexError
- **问题**：假设 logits 最后一维 >= 2，若模型 `num_labels=1` 或 shape 为 `(N, 1)`，抛 IndexError 使整个训练在 evaluate 阶段失败。
- **修复**：加 shape 检查 `if probs.shape[-1] < 2: probs = probs[:, 0]`。

#### C-Svc-7 `experiment_metrics.py:20` 单类 y_true 时 `average="binary"` 抛异常
- **问题**：若验证集恰好只含一个类别，`precision_recall_fscore_support(average="binary")` 抛 `ValueError` 未被捕获。
- **修复**：`average_param = "binary" if num_classes == 2 else "weighted"`，并整体 try/except。

#### C-Svc-8 `gdpr_service.py:305` GDPR 被遗忘权遗漏大量含 PII 的表
- **问题**：`anonymize_user` 仅匿名化 User/UserProfile/EmergencyContact/UserCounselorBinding/RefreshTokenSession/RiskAssessment。但以下含 PII 表完全未处理：ConsultationRecord（notes）、InterventionPlan/InterventionTask（feedback_note）、CrisisEvent（input_summary）、WarningNotification（trigger_reason）、ContentViewHistory、DataDraft、TextEntry、PhysiologicalRecord 等。严重违反 GDPR Article 17。
- **修复**：补充所有含 PII 表的匿名化；自由文本字段替换为 `"[ANONYMIZED]"`。

### HIGH

#### H-Svc-1 `canary_manager.py:226` update_traffic_percent 等内部 commit 破坏调用方事务
- **问题**：`update_traffic_percent`/`pause_canary`/`resume_canary` 调用 `await db_session.commit()`，但 `start_canary`/`rollback_canary`/`complete_canary` 已修复为 `flush()`。事务边界不一致。
- **修复**：统一改为 `flush()`，由调用方管理事务。

#### H-Svc-2 `admin_service.py:369` 时区处理不一致
- **问题**：`get_stats` 用 aware UTC 与 naive DateTime 列比较，`archive_old_logs` 用 `datetime.now(UTC).replace(tzinfo=None)` 生成 naive。如果模型列无 `timezone=True`，`get_stats` 的 aware 比较会抛 `TypeError`。
- **修复**：统一使用 `datetime.now(UTC).replace(tzinfo=None)`，或为模型列添加 `timezone=True`。

#### H-Svc-3 `alert_lifecycle_service.py:149` 向 naive DateTime 列写入 aware datetime
- **问题**：`alert.resolved_at = datetime.now(timezone.utc)` 直接赋 aware UTC 给 naive DateTime 列，SQLAlchemy 静默丢弃 tzinfo，与 admin_service 不一致。
- **修复**：统一使用 `datetime.now(timezone.utc).replace(tzinfo=None)`。

#### H-Svc-4 `canary_manager.py:182` `started_at`/`ended_at` 写入 aware 但列是 naive
- 同 H-Svc-3。

#### H-Svc-5 `content_service.py:195` `latest_risk.risk_level` 为 None 时崩溃
- **问题**：`risk_level = latest_risk.risk_level if latest_risk else 1`，若 `risk_level` 字段为 None，后续 `_risk_default_category(None)` 中 `if risk_level >= 4` 抛 `TypeError`。
- **修复**：`risk_level = latest_risk.risk_level if latest_risk and latest_risk.risk_level is not None else 1`。

#### H-Svc-6 `experiment_evaluator.py:49` 假设 sklearn 模型有 `predict_proba`
- **问题**：并非所有 sklearn 分类器都有 `predict_proba`（如 SVC 默认 `probability=False`），缺失时抛 AttributeError。
- **修复**：`if hasattr(model, "predict_proba"): ... elif hasattr(model, "decision_function"): ... else: [0.5] * len(y_true)`。

#### H-Svc-7 `risk_service.py:547` `_check_warning_trigger` 中 previous_level 未防御 None
- **问题**：`previous_level = previous.risk_level if previous else 0`，若 `previous.risk_level is None`，后续 `current_risk.risk_level > previous_level` 抛 TypeError。
- **修复**：`previous_level = previous.risk_level if previous and previous.risk_level is not None else 0`。

#### H-Svc-8 `risk_service.py:647` `_create_plan_from_template` 返回 None 未告警
- **问题**：若无活跃模板，隐式返回 None，`_auto_generate_intervention` 不检查，高风险用户无干预计划但 API 响应 `intervention_actions` 非空。
- **修复**：无模板时 `logger.warning`，并在 `assess_structured` 中根据 plan 设置 `intervention_actions`。

#### H-Svc-9 `risk_service.py:35` `_pdf_executor` 全局线程池未关闭
- **问题**：`ThreadPoolExecutor(max_workers=4)` 模块级定义，应用 shutdown 时未调用 `shutdown(wait=True)`，进程退出时 worker 可能仍持有任务。
- **修复**：提供 `shutdown()` 函数，在 FastAPI lifespan 的 shutdown 阶段调用。

#### H-Svc-10 `observability_service.py:133` `consume_flushed_logs` 非线程/协程安全
- **问题**：直接 `logs = self._flushed_buffer; self._flushed_buffer = []` 未持 `_lock`，与 `_flush` 并发时可能读到中间状态。
- **修复**：在 `_lock` 内消费。

#### H-Svc-11 `email_service.py:66` `time.sleep` 在 `asyncio.to_thread` 中长时间阻塞
- **问题**：重试 `time.sleep` 累计 7 秒阻塞单个线程，高并发密码重置下可能耗尽线程池。
- **修复**：改为 `await asyncio.sleep(delay)`（需重构为 async）；或限制 SMTP 并发数。

#### H-Svc-12 `experiment_trainer.py:210` 静默吞异常返回空列表
- **问题**：`_predict_labels`/`_predict_scores` `except Exception: return []`，调用方 `accuracy_score([], [])` 抛 ValueError，被 metrics try/except 捕获后 AUC 降级 0.5，训练失败被掩盖为低指标。
- **修复**：让异常向上传播，或返回 None 并在调用方判断。

#### H-Svc-13 `counselor_service.py:79` `handle_warning` 非幂等
- **问题**：`if warning.is_handled: return True`，已处理为 IGNORE 后调用 HANDLE 仍返回 True 但 DB 仍是 IGNORE。
- **修复**：检查 `warning.handle_action == action`，不一致时返回 False 或抛异常。

#### H-Svc-14 `intervention_service.py:422` `_should_execute_today` 不处理 start_date 为 None
- **问题**：`if today < start_date` 抛 `TypeError: '<' not supported between 'date' and 'NoneType'`，整个 `get_active` 接口 500。
- **修复**：`if start_date is None or today < start_date: return False`。

#### H-Svc-15 `intervention_service.py:342` `_load_task_execution` 自动创建执行记录掩盖业务错误
- **问题**：`complete_task`/`mark_task_missed`/`skip_task` 通过 `_get_or_create_execution`，若任务尚未排期到今天，系统自动创建 pending execution 后立刻转为 completed，绕过 schedule 检查。
- **修复**：对状态变更操作改用 `_get_execution`（只读），不存在则返回 (None, None)。

#### H-Svc-16 `validation_engine.py:242` `int()` 可能失败
- **问题**：`y_true = int(true_value); y_pred = int(pred_value)`，若标签为非数字字符串抛 ValueError，metrics 字段全 None。
- **修复**：try/except 包裹，失败时跳过或做标签映射。

#### H-Svc-17 `admin_service.py:458` `register_model` 不去重 model_id
- **问题**：flush 抛 IntegrityError 后仍尝试 `commit()` 会抛 `PendingRollbackError`，掩盖原始错误。
- **修复**：try/IntegrityError 包裹，rollback 后抛业务异常。

### MEDIUM

- **M-Svc-1** `crisis_export_service.py:76` 全量加载到内存，大日期范围下可能 OOM。建议 `yield_per(1000)` 流式读取。
- **M-Svc-2** `excel_export_service.py:165` `_format_value` 把数字转字符串，Excel 失去数值类型无法求和/排序。
- **M-Svc-3** `experiment_data.py:84` `train_test_split` 未验证 temp_df 二次分割的 stratify 最小样本。
- **M-Svc-4** `gdpr_service.py:184` 流式迭代器 OFFSET 分页在数据变动时跳过/重复。建议 keyset pagination。
- **M-Svc-5** `model_predict_service.py:251` `predict_text` 不验证空文本，下游模型可能产生 NaN。
- **M-Svc-6** `review_service.py:189` `escalate_review` 复用 `resolved_by` 字段，统计时升级任务被误算为已解决。
- **M-Svc-7** `review_service.py:265` `record_crisis_event` 不验证 `crisis_keywords` 长度。
- **M-Svc-8** `review_service.py:325` `handle_crisis_event` 不校验 `action` 值，任意字符串可写入。
- **M-Svc-9** `warning_service.py:122` `_parse_time_value` 不校验范围，`time(25, 70, 99)` 抛 ValueError。
- **M-Svc-10** `warning_service.py:150` `notify_channels` 无类型/枚举校验。
- **M-Svc-11** `user_data_service.py:182` `result["sentiment_score"]` 可能 KeyError。
- **M-Svc-12** `risk_service.py:640` `_auto_generate_intervention` 注释与实现不一致（实际事务原子性保证，但可读性差）。
- **M-Svc-13** `observability_exporter.py:97` `_loop` 异常时无退避，DB 长时间不可用时日志爆炸。
- **M-Svc-14** `input_validator.py:112` `validate_tabular` 对 list/dict/set 直接拒绝，可能误判合法输入。
- **M-Svc-15** `pdf_report_service.py:252` `_estimate_page_count` 正则可能高估页数。
- **M-Svc-16** `experiment_evaluator.py:86` 一个模型失败导致整体 compare 失败。
- **M-Svc-17** `admin_service.py:500` `archive_old_logs` DELETE rowcount 在 SQLite 与 PostgreSQL 行为不同。
- **M-Svc-18** `risk_service.py:155` `assess_structured` heuristic fallback 中 `0 or 7` 替换 0 值睡眠时长，错误降低风险分。
- **M-Svc-19** `observability_service.py:146` `record_*` 方法在 async 上下文中调用同步 deque.append 未持锁。

### LOW

- **L-Svc-1** `alert_lifecycle_service.py:85` `_transition_history` 仅内存，多实例部署丢失。
- **L-Svc-2** `counselor_service.py:565` `_generate_bind_code` 熵较短（约 60 bits）。
- **L-Svc-3** `experiment_metrics.py:23` AUC 失败静默返回 0.5 可能误导。
- **L-Svc-4** `experiment_trainer.py:195` `train_physiological_model` 返回空 train_history，前端图表空。
- **L-Svc-5** `risk_service.py:750` `_score_to_severity` 与 `_score_to_level` 阈值不一致。
- **L-Svc-6** `content_service.py:82` `get_content_detail` 中 `content.view_count` 内存值可能与 DB 不一致。
- **L-Svc-7** `admin_service.py:168` `list_operation_logs` 与 `list_audit_logs` 大量重复代码。

---

## 五、后端 ML 模块与 Celery 任务审核（app/ml + app/tasks）

### CRITICAL

#### C-ML-1 `model.py:135` + `trainer.py:306` M-3 线程安全修复不完整（已验证真实）
- **问题**：M-3 修复为 `forward()` 增加局部 `training` 参数避免线程竞态，BatchNorm 已正确接收。但 `_dropout_forward()` 仍检查 `self.training` 实例属性而非使用传入的 `training` 值；`trainer.py` 的 `train_epoch()`（`model.training = True`）和 `evaluate()`（`model.training = False`）仍直接修改实例状态。两者叠加导致并发场景下 Dropout 可能被静默跳过，模型在无正则化下训练。
- **代码**：
```python
# model.py:135-140 - _dropout_forward 检查 self.training 而非局部 training
def _dropout_forward(self, x, rate):
    if not self.training or rate == 0:  # BUG
        return x, np.ones_like(x)

# trainer.py:306, 357 - 直接修改实例状态
model.training = True   # train_epoch
model.training = False  # evaluate
```
- **修复**：`_dropout_forward` 增加 `training` 参数；`train_epoch`/`evaluate` 改为 `model.forward(X, training=True/False)`，删除对 `model.training` 的赋值。

#### C-ML-2 `model_loader.py:41` save 方法不生成 .sha256 但 load 方法强制要求（已验证真实）
- **问题**：M16/M17 修复要求 `load_model`/`load_scaler`/`load_cleaner` 等 6 类加载方法调用 `_verify_integrity(path, require_checksum=True)` 强制要求 `.sha256` 侧车文件存在。但对应的 `save()` 方法均只写 JSON 不生成校验文件。训练完成后直接 `load_model()` 会抛 `ValueError: 缺少校验文件`。
- **修复**：在每个 `save()` 末尾调用 `_compute_sha256(path)` 并写入 `path.with_suffix(path.suffix + ".sha256")`；或提供统一 `save_with_checksum()` 工具。

### HIGH

#### H-ML-1 `pytorch_mlp.py:313` `best_state_dict` 在 val_f1=0 时不保存
- **问题**：`best_val_f1 = 0.0`，严格 `>` 比较，val_f1 恒为 0 时 `best_state_dict` 始终 None，早停后不恢复权重，模型保留最差 epoch 权重。
- **修复**：`best_val_f1 = -1.0`，或改为 `if best_state_dict is None or val_f1 >= best_val_f1`。

#### H-ML-2 `text_analyzer.py:43` 未处理 None/非字符串输入
- **问题**：`re.findall(text)` 若 text=None 抛 TypeError。融合引擎中文本模态缺失时可能传 None。
- **修复**：`if not text or not isinstance(text, str): return {"risk_factors": [], ...}`。

#### H-ML-3 `model_monitor.py:184` `get_health_status` 无锁读取共享状态
- **问题**：`record_prediction()` 在锁内修改 `latency_history`（替换列表引用），但 `get_health_status()` 在锁外 `np.mean(self.latency_history)` 读取，可能读到部分更新。
- **修复**：在锁内拷贝所需状态后在锁外计算。

#### H-ML-4 `canary_controller.py:148` 串行对比 + 重复推理，3 倍延迟
- **问题**：`predict()` 第 150 行调用路由模型，`_log_comparison()` 又重新调用 old + new 模型（含重复）。每次预测实际产生 3 次模型推理。
- **修复**：将已计算结果传入 `_log_comparison()` 避免重复推理。

#### H-ML-5 `scheduler.py:105` aware/naive datetime 比较不一致
- **问题**：`WarningNotification.created_at >= datetime.now(UTC) - timedelta(days=1)` 中 aware 与 naive 列比较，SQLite 下可能字符串比较导致窗口偏移。
- **修复**：使用 `datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)`。

#### H-ML-6 `scheduler.py:126` flush 后发通知，commit 失败时通知无法撤回
- **问题**：`db.flush()` 写入 WarningNotification 后 `_notify_warning()` 发 WebSocket，若 `db.commit()` 失败 rollback，用户收到告警但 DB 无记录。
- **修复**：将通知发送移到 commit 之后。

### MEDIUM

- **M-ML-1** `canary_controller.py:302` `load_state` 不恢复 `comparison_history`，重启后丢失对比数据。
- **M-ML-2** `smote.py:54` 少数类 1 样本时静默不生成合成样本，SMOTE 静默失败。
- **M-ML-3** `data_split.py:52` `stratified_split` 对小类可能产生 0 样本的验证/测试子集（`int(3 * 0.15) = 0`）。
- **M-ML-4** `observability.py:70` `_flush_lock_stats_impl` 在 `flush_lock_stats` 返回 False 时仍 commit。
- **M-ML-5** `model_training.py:153` 异常不重抛，Celery 无法追踪任务失败。
- **M-ML-6** `statistical_tests.py:40` `bootstrap_ci` 不处理退化 bootstrap 样本产生的 NaN 指标。
- **M-ML-7** `model_loader.py:81` `check_model_exists` 不检查 `CLEANER_STATS_PATH`，推理时可能缺少清洗参数。
- **M-ML-8** `data_cleaner.py:171` `transform_single` 不强制特征顺序，可能传入模型的特征顺序与训练时不一致。
- **M-ML-9** `data_split.py:143` `verify_split_integrity` 使用 `set(map(tuple, X))` 对浮点 NaN 比较失效。

### LOW

- **L-ML-1** `evaluation.py:131` 校准曲线第一个 bin 排除 score=0 的样本（用 `>` 而非 `>=`）。
- **L-ML-2** `feature_analysis.py:23` 常数列产生 NaN 相关系数未报告。
- **L-ML-3** `scaler.py:32` `fit` 不处理输入 NaN，传播到模型。
- **L-ML-4** `drift_detector.py:275` PSI 单 bin 贡献无上限，空 bin 可导致 PSI 爆炸。
- **L-ML-5** `loss.py:34` BCE 梯度分母额外加 epsilon，改变梯度量级。
- **L-ML-6** `fusion_engine.py:198` `fuse` 不验证 `modality_scores` 值类型，None 导致 TypeError。
- **L-ML-7** `hyperparameter_tuning.py:225` `inner_folds` 参数被忽略，与文档描述不符。
- **L-ML-8** `alerts.py:157` delete 后访问 row 属性依赖 SQLAlchemy 内部行为。
- **L-ML-9** `scheduler.py:190` `end_date` 与 `today` 时区不一致。
- **L-ML-10** `scheduler.py:126` flush 后发通知，commit 失败时通知无法撤回（与 H-ML-6 关联）。

---

## 六、前端审核（frontend）

### CRITICAL

#### C-FE-1 `userFileApi.ts:8` FormData 上传时手动设置 Content-Type 破坏 boundary
- **问题**：上传 `FormData` 时显式设置 `'Content-Type': 'multipart/form-data'`，会丢失 `boundary` 参数，后端无法解析请求体。
```ts
request.post('/user/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' }, params })
```
- **修复**：删除 `headers: { 'Content-Type': 'multipart/form-data' }`，让浏览器自动设置带 boundary 的 Content-Type。

#### C-FE-2 `request.ts:61` refresh 请求发送空字符串 Authorization 头
- **问题**：`headers: { Authorization: '' }` 让 axios 发送 `Authorization: `（空值），部分后端将空值视为非法 token 返回 401，导致刷新永远失败。
- **修复**：删除 `headers: { Authorization: '' }`；如需清除，使用 `delete config.headers.Authorization`。

#### C-FE-3 `request.ts:36` 防御性超时(15s)短于实际请求超时(60s/420s)
- **问题**：`DEFENSIVE_PENDING_TIMEOUT_MS = 15000`，但 `DEFAULT_API_TIMEOUT_MS = 60000`、`LONG_RUNNING_API_TIMEOUT_MS = 420000`。长超时任务在 15s 后被拒绝，后续重试永远无法完成。
- **修复**：防御性超时应 >= `DEFAULT_API_TIMEOUT_MS`，建议 65000ms 或动态计算。

#### C-FE-4 `BaseChart.vue:95` + `MainLayout.vue:102` keep-alive 组件内 ECharts 生命周期不匹配
- **问题**：`BaseChart.vue` 仅使用 `onMounted`/`onUnmounted`，但 keep-alive 在 deactivate 时调用 `onDeactivated` 而非 `onUnmounted`。deactivate 时实例与 ResizeObserver 不会被清理（内存泄漏），reactivate 时也不会重新初始化（图表空白）。
- **修复**：在 `BaseChart.vue` 中同时注册 `onActivated`/`onDeactivated`。

#### C-FE-5 `usePerformanceMonitor.ts:168` CLS 最终值在页面卸载前未提交
- **问题**：`collectCLS` 只在「新会话窗口开始」时才更新 `metrics.value.cls`。页面在当前会话窗口内被关闭时，最终 CLS 累积值不会被写入，`reportWithBeacon` 上报的是旧值或 undefined。
- **修复**：在 `handleBeforeUnload`/`handleVisibilityChange` 触发 `reportWithBeacon` 之前，先把当前 `clsSessionEntries` 累加到 `metrics.value.cls`。

### HIGH

#### H-FE-1 `App.vue` + `router/index.ts` 路由切换时全屏 loading 阻塞 UI
- **问题**：`beforeEach` 调用 `startProgress()` → `loadingStore.startLoading()` → `App.vue` 的 `v-loading.fullscreen.lock` 锁定整个屏幕。每次路由切换全屏遮罩。
- **修复**：改用顶部进度条（NProgress 风格），不要全屏锁定。

#### H-FE-2 `request.ts:191` 全局 GET 去重可能返回错误类型 Promise
- **问题**：`inflightRequests` 复用 Promise，刷新期间所有相同 GET 请求共享同一 pending Promise，若 refresh 耗时 10s，所有并发消费者被阻塞 10s。
- **修复**：为关键实时数据接口提供 `bypassDedupe: true` 选项。

#### H-FE-3 `useWebSocket.ts:174` 重连失败后无用户提示
- **问题**：`maxReconnectAttempts = 10` 用尽后直接 return，无任何用户提示。用户长时间断网后以为自己仍在线，但不再收到预警。
- **修复**：达到最大重连次数时通过 `ElNotification` 提示「实时连接已断开，请刷新页面」，并通过 `captureMessage` 上报 Sentry。

#### H-FE-4 `usePerformanceMonitor.ts:253` fetch 上报未携带 credentials
- **问题**：`fetch(opts.reportUrl, { ... })` 默认不发送 Cookie。若后端需鉴权（同源场景下需要 refresh_token Cookie），请求被拒绝。
- **修复**：显式添加 `credentials: 'include'`。

#### H-FE-5 `package.json:35` `terser` 误置于 dependencies
- **问题**：`terser` 是构建期工具，放在 `dependencies` 会增大生产安装体积。
- **修复**：移至 `devDependencies`。

#### H-FE-6 `router/index.ts:121` 缺少 scrollBehavior
- **问题**：`createRouter` 未配置 `scrollBehavior`，浏览器前进/后退不会恢复滚动位置。
- **修复**：`scrollBehavior(to, from, savedPosition) { return savedPosition || { top: 0 } }`。

#### H-FE-7 `usePerformanceMonitor.ts:271` sendBeacon 发送字符串被当作 text/plain
- **问题**：`navigator.sendBeacon(opts.reportUrl, payload)` 当 payload 是字符串时，Content-Type 为 `text/plain;charset=UTF-8`，后端可能 422 拒绝。
- **修复**：用 `new Blob([payload], { type: 'application/json' })` 包装后再 sendBeacon。

#### H-FE-8 `request.ts:4` 模块顶层 import router 造成循环依赖
- **问题**：`import router from '@/router'` 与 `router/index.ts` → `views/*` → `@/api/*` → `request.ts` 形成循环依赖，`router` 在 `request.ts` 加载时可能为 `undefined`。
- **修复**：改为惰性获取 `const getRouter = () => import('@/router').then(m => m.default)`。

### MEDIUM

- **M-FE-1** `useWebSocket.ts:92` userId 暴露在 URL 路径中，被 nginx access log 记录。
- **M-FE-2** `useWebSocket.ts:84` 无连接建立超时，TCP 无响应时挂起数十秒。
- **M-FE-3** `request.ts:193` inflight key 使用 JSON.stringify 对对象属性顺序敏感。
- **M-FE-4** `request.ts:99` `isUnauthorizedRedirecting` 在导航取消后不会复位，后续 401 不再触发跳登录。
- **M-FE-5** `MainLayout.vue:217` WebSocket 通知文案硬编码中文，未走 i18n。
- **M-FE-6** `BaseChart.vue:86` watch 不深度监听，依赖父组件传入新引用（隐式契约）。
- **M-FE-7** `useListQueryState.ts:20` setQuery 未防抖，连续输入触发多次路由替换。
- **M-FE-8** `i18n/index.ts:41` 动态 import 模板字符串难以静态分析。
- **M-FE-9** `usePerformanceMonitor.ts:147` INP 计算可能高估（未按 interactionId 分组）。
- **M-FE-10** `nginx.conf:92` WebSocket proxy_read_timeout 86400s（24小时）过长，僵尸连接占用资源。
- **M-FE-11** `nginx.conf:14` 未设置 `gzip_comp_level`，默认 1 压缩率低。
- **M-FE-12** `nginx.conf:45` CSP 缺少 `frame-ancestors 'self'`。
- **M-FE-13** `nginx.conf:5` auth 限流 5r/m 过严，正常用户易被限流。
- **M-FE-14** `vite.config.ts:149` `chunkSizeWarningLimit: 500` 过低，几乎每个 vendor chunk 都触发警告。
- **M-FE-15** `vite.config.ts:52` PWA NetworkFirst 10s 超时过长，弱网用户等待 10s。
- **M-FE-16** `sentry.ts:12` 缺少 `ignoreErrors`/`denyUrls` 过滤，噪声被上报浪费配额。
- **M-FE-17** `Dockerfile:11` `npm ci 2>/dev/null || npm install` 丢弃错误输出，fallback 可能生成不一致依赖。
- **M-FE-18** `MainLayout.vue:128` `cachedComponentNames` 依赖组件名推断，重命名后缓存静默失效。
- **M-FE-19** `index.html:16` + `csp.ts:40` + `nginx.conf:45` 生产环境 CSP meta 与 header 重复，易遗漏同步。
- **M-FE-20** `useTheme.ts:6` localStorage 未做异常保护，隐私模式下抛异常。
- **M-FE-21** `request.ts:2` + `router/index.ts:2` 显式 `import { ElMessage }` 与 auto-import 冲突，抵消 tree-shaking。
- **M-FE-22** `vite.config.ts:151` `minify: 'terser'` 比 esbuild 慢 5-10 倍。
- **M-FE-23** `usePerformanceMonitor.ts:84` metrics ref 频繁触发响应式。建议 `shallowRef`。

### LOW

- **L-FE-1** `taskTypes.ts:1` 跨目录相对路径脆弱。
- **L-FE-2** `useBreakpoint.ts`/`useECharts.ts` 每个组件实例都注册独立 resize 监听。
- **L-FE-3** `useTheme.ts:9` 未在 SSR 安全检查。
- **L-FE-4** `i18n/index.ts:45` `console.error` 被 `drop_console` 吞掉。
- **L-FE-5** `router/index.ts:118` catch-all 重定向到 /login 而非 404。
- **L-FE-6** `router/guard.ts:13` `resolveRoleHome` 未处理未知角色。
- **L-FE-7** `sentry.ts:23` `tracesSampleRate` 默认 0.1 偏高。
- **L-FE-8** `useWebSocket.ts:211` listeners 数组用 filter 重建，O(n) 移除。建议用 Set。
- **L-FE-9** `useWebSocket.ts:35` 去重 Set 在 listener 抛错后仍消费。
- **L-FE-10** `usePerformanceMonitor.ts:51` observeMetric 返回的 cleanup 未在 observer 创建失败时返回。
- **L-FE-11** `package.json:27` 显式声明 `@vue/compiler-sfc` 等冗余。
- **L-FE-12** `index.html:42` loading-skeleton 顶部 4px 条无实际内容。
- **L-FE-13** `csp.ts:31` DEV_POLICY 允许任意 localhost 端口。
- **L-FE-14** `Dockerfile:35` HEALTHCHECK 命中 nginx 而非后端。
- **L-FE-15** `useECharts.ts:86` `useChartResize` 默认参数为空函数。
- **L-FE-16** `BaseChart.vue:95` onMounted 内再套 nextTick 多余。
- **L-FE-17** `alertsApi.ts:150` `toPageResult` 默认 page_size 取 raw.items.length 语义不直观。
- **L-FE-18** `nginx.conf:17` gzip_types 缺少现代类型。
- **L-FE-19** `router/index.ts:26` 大量 webpackChunkName 注释对 Vite 无效。
- **L-FE-20** `useWebSocket.ts:223` 全局单例 wsClient 在测试间状态污染。

---

## 七、功能验证结果

### 7.1 路由注册验证
- ✅ `app/api/v1/__init__.py` 已注册全部 24 个 router（admin/auth/counselor/gdpr/metrics/observability/silences/grafana_adapter 等），无遗漏。
- ✅ `app/main.py` 已挂载 `api_router`、`csp_report_router`，注册异常处理器、CORS、限流、中间件、WebSocket 端点、健康检查。
- ✅ Lifespan 正确管理 init_db、seed、model_engine.preload、Sentry、ObservabilityExporter 资源生命周期。

### 7.2 鉴权与权限验证
- ✅ **WebSocket 鉴权完善**（已验证）：URL token 拒绝 + 10s 认证超时 + token 类型/user_id 双重校验 + 用户状态校验 + 连接数上限 5 + 300s idle timeout + ping/pong 心跳。
- ❌ **API 层多处鉴权缺陷**：review.py 的 resolve/escalate 无 owner 校验（C-API-5）；alerts/metrics dev 环境完全无鉴权（C-API-1/2）；counselor.py 多端点依赖 service 内部校验（H-API-1/10）。
- ❌ **审计日志缺失**：user_intervention 任务状态变更、auth 的 change_password/reset_password/update_profile 等关键操作路由层无 OperationLog，违反精神卫生干预合规要求。

### 7.3 业务逻辑验证
- ❌ **危机事件列表日期参数被忽略**（已验证，M-API-2）：`review.py:41` 的 `list_crisis_events` 接收 `start_date`/`end_date` 但完全不传入 `CrisisEventFilter`，用户以为按日期过滤实际未生效。
- ❌ **告警状态机缺陷**（C-Svc-2）：CLOSED 告警无法重开但 `reopen_alert` 文档承诺可重开。
- ❌ **M-3 线程安全修复不完整**（已验证，C-ML-1）：`_dropout_forward` 仍检查 `self.training`，`trainer.py` 仍修改实例状态，并发下 Dropout 可能被静默跳过。
- ❌ **save/load 工作流断裂**（已验证，C-ML-2）：6 类 `save()` 不生成 `.sha256`，但 `load_*()` 强制要求，训练后直接加载会失败。
- ❌ **GDPR 被遗忘权不完整**（C-Svc-8）：遗漏 ConsultationRecord、InterventionPlan、CrisisEvent 等大量含 PII 表。

### 7.4 性能与稳定性验证
- ❌ **事务管理不一致**：service 层部分用 `flush()`，部分用 `commit()`，部分用 `begin_nested()`。auto_rollback_service 在 savepoint 内 commit 破坏隔离（C-Svc-1）。
- ❌ **时区处理不统一**：`datetime.now(UTC)`、`datetime.now(UTC).replace(tzinfo=None)`、`datetime.now(timezone.utc)` 三种写法混用，多处 aware/naive 比较问题。
- ❌ **资源泄漏**：`risk_service._generate_pdf_report` 的 BytesIO（C-Svc-5）、`risk_service._pdf_executor` 线程池（H-Svc-9）、前端 keep-alive 图表（C-FE-4）。
- ❌ **前端 FormData 上传破坏**（已验证，C-FE-1）：手动设置 Content-Type 导致 boundary 丢失。
- ❌ **前端 token 刷新永远失败**（已验证，C-FE-2）：空 Authorization 头被后端拒绝。

### 7.5 监控与可观测性
- ✅ Prometheus metrics、Sentry、request_id tracing、CSP report、observability exporter 已实现。
- ❌ admin 端点无限流（H-API-6），webhook 无限流（H-API-5），可被 DoS。
- ❌ observability trend 限制 10000 无分页（L-API-10），统计失真。
- ❌ observability single-flight 进程内不共享（M-API-6），多 worker 下失效。

---

## 八、前端性能优化方案

### 8.1 页面加载速度
1. **修复 C-FE-1（FormData）/ C-FE-2（refresh）**：这两个 CRITICAL 直接导致上传功能不可用、token 刷新失败，用户被迫频繁重新登录。
2. **缩短 PWA NetworkFirst 超时**（M-FE-15）：10s → 3s，弱网用户快速回退缓存。
3. **优化 chunkSizeWarningLimit**（M-FE-14）：500 → 1000，减少噪声。
4. **改用 esbuild 压缩**（M-FE-22）：`minify: 'terser'` → `minify: 'esbuild'` + `esbuild.drop: ['console', 'debugger']`，构建快 5-10 倍。
5. **移除冗余依赖**（H-FE-5、L-FE-11）：`terser` 移至 devDependencies；移除 `@vue/compiler-sfc` 等显式声明。

### 8.2 资源加载策略
1. **修复循环依赖**（H-FE-8）：`request.ts` 顶层 import router 改为惰性获取，避免 ESM 部分初始化。
2. **移除无效 webpackChunkName 注释**（L-FE-19）：依赖 vite.config.ts 的 manualChunks。
3. **优化 keep-alive 配置**（M-FE-18）：在对应 SFC 中显式 `defineOptions({ name: '...' })`。
4. **清理 index.html CSP meta**（M-FE-19）：生产环境仅由 nginx header 控制。

### 8.3 渲染性能
1. **修复路由全屏 loading**（H-FE-1）：改用顶部进度条，不要全屏锁定。
2. **添加 scrollBehavior**（H-FE-6）：恢复浏览器前进/后退滚动位置。
3. **优化 metrics ref 响应式**（M-FE-23）：`usePerformanceMonitor` 改用 `shallowRef`。
4. **修复 keep-alive 图表生命周期**（C-FE-4）：注册 `onActivated`/`onDeactivated`。
5. **BaseChart onMounted 去掉多余 nextTick**（L-FE-16）：避免图表闪现空白。

### 8.4 交互响应速度
1. **修复防御性超时**（C-FE-3）：15s → 65s，长超时任务不被中断。
2. **修复 GET 去重阻塞**（H-FE-2）：为实时数据接口提供 `bypassDedupe`。
3. **setQuery 防抖**（M-FE-7）：连续输入不触发多次路由替换。
4. **修复 `isUnauthorizedRedirecting` 不复位**（M-FE-4）：在 `router.afterEach` 中复位。
5. **WebSocket 重连失败提示**（H-FE-3）：达到最大重连次数时通知用户刷新。

### 8.5 Nginx 配置优化
1. **缩短 WebSocket 超时**（M-FE-10）：86400s → 3600s，配合客户端心跳 60s。
2. **设置 gzip_comp_level**（M-FE-11）：添加 `gzip_comp_level 4;`。
3. **添加 frame-ancestors**（M-FE-12）：CSP 追加 `frame-ancestors 'self'`。
4. **放宽 auth 限流**（M-FE-13）：5r/m → 10r/m，对 `/auth/refresh` 单独配置。
5. **修复 Dockerfile HEALTHCHECK**（L-FE-14）：改为 `wget http://localhost/health`。

### 8.6 监控与上报
1. **修复 fetch credentials**（H-FE-4）：显式 `credentials: 'include'`。
2. **修复 sendBeacon Content-Type**（H-FE-7）：用 Blob 包装为 `application/json`。
3. **修复 CLS 最终值提交**（C-FE-5）：卸载前累加当前 session entries。
4. **修复 INP 计算**（M-FE-9）：按 interactionId 分组取每组最大 duration。
5. **Sentry 噪声过滤**（M-FE-16）：添加 `ignoreErrors`/`denyUrls`。
6. **Sentry 采样率**（L-FE-7）：生产 0.01，开发 1.0。

---

## 九、修复优先级建议

### 阶段一：立即修复（阻断性 CRITICAL，1-2 天）

**后端**：
1. C-Svc-1 auto_rollback_service savepoint 内 commit 破坏事务
2. C-Svc-8 GDPR 被遗忘权遗漏 PII 表
3. C-API-1/2 alerts/metrics dev 环境无鉴权
4. C-API-3 alerts webhook SSRF
5. C-API-5 review 咨询师水平越权
6. C-API-6 validation 路径遍历残留
7. C-ML-1 M-3 线程安全修复不完整（Dropout 静默跳过）
8. C-ML-2 save/load 工作流断裂（.sha256 校验）
9. C-Svc-2 alert 状态机缺陷
10. C-Svc-3 counselor bind_by_code TOCTOU
11. C-Svc-4/5/6/7 各类崩溃与泄漏

**前端**：
1. C-FE-1 FormData 上传 Content-Type 破坏
2. C-FE-2 refresh 空 Authorization 头
3. C-FE-3 防御性超时过短
4. C-FE-4 keep-alive 图表生命周期
5. C-FE-5 CLS 最终值未提交

### 阶段二：本周修复（HIGH，3-5 天）

- 全部 H-Core-*（9 项）
- 全部 H-API-*（12 项）
- 全部 H-Svc-*（17 项）
- 全部 H-ML-*（6 项）
- 全部 H-FE-*（8 项）

### 阶段三：下个迭代（MEDIUM，1-2 周）

- 全部 M 级别问题（84 项）
- 重点关注：时区统一、事务边界规范、异常处理规范、性能优化

### 阶段四：机会修复（LOW，长期）

- 全部 L 级别问题（56 项）
- 重构重复代码、补充文档、清理死代码

---

## 十、通用模式问题与建议

### 10.1 事务管理规范
**问题**：service 层部分用 `flush()`，部分用 `commit()`，部分用 `begin_nested()`，事务边界不一致。

**建议**：制定团队规范——service 层只用 `flush()`，事务由 API 层通过 `get_db()` 依赖统一管理。savepoint 仅在需要部分回滚的复合操作中使用，且内部严禁 `commit()`。

### 10.2 时区处理统一
**问题**：`datetime.now(UTC)`、`datetime.now(UTC).replace(tzinfo=None)`、`datetime.now(timezone.utc)` 三种写法混用，aware/naive 比较问题多处存在。

**建议**：提供统一工具函数 `utcnow_naive()` 和 `utcnow_aware()`，全项目统一使用。数据库列统一添加 `timezone=True`（PostgreSQL）或显式声明 naive UTC 语义（SQLite）。

### 10.3 异常处理规范
**问题**：多处 `except Exception` 后仅日志记录返回空值/None，掩盖根因。`experiment_trainer` 静默吞异常导致训练失败被掩盖为低指标。

**建议**：区分可恢复异常（如缓存失败）与致命异常（如模型推理失败）。致命异常必须向上传播，可恢复异常必须记录完整堆栈（`logger.exception`）并返回明确的降级标记。

### 10.4 鉴权与审计统一
**问题**：API 层鉴权责任不清晰，部分在路由层、部分在 service 层。审计日志同理。

**建议**：使用 FastAPI dependency 统一注入鉴权与审计。所有状态变更操作（POST/PUT/DELETE）必须记录 OperationLog，包含 operator_id、target_type、target_id、action、detail、ip_address、request_id。

### 10.5 锁与并发规范
**问题**：`threading.Lock` 与 `asyncio.Lock` 混用，`threading.Lock` 在 asyncio 上下文中是反模式。

**建议**：asyncio 应用中保护异步资源用 `asyncio.Lock`，保护同步数据结构（dict/deque）可用 `threading.Lock` 但需在文档中说明。共享状态的读操作也必须在锁内拷贝后释放锁再计算。

### 10.6 输入验证与输出编码
**问题**：多处输入未校验（CSV 导出、filename、CSP report 字段），输出未编码（CSV Formula Injection、header 注入、XSS）。

**建议**：所有用户输入在 Pydantic schema 层校验类型、长度、格式、范围。所有输出到 CSV/header/HTML 的内容必须经过对应的转义（`_sanitize_csv_cell`、header value 白名单、HTML escape）。

---

## 附录：审核覆盖范围

### 已审核文件清单（共 130+ 文件）

**后端核心（31 文件）**：cache.py, celery_app.py, config.py, contracts.py, crisis_detector.py, database.py, deps.py, exceptions.py, fallback_hierarchy.py, health.py, instance.py, metrics.py, middlewares.py, model_compatibility.py, model_engine.py, model_registry.py, model_registry_v2.py, openapi_responses.py, pii_crypto.py, rate_limit.py, request_id.py, response.py, review_reasons.py, risk_thresholds.py, safe_pickle.py, security.py, seed.py, sentry.py, states.py, tracing.py, ws.py

**后端 API（25 文件）**：v1/ 目录全部 23 个文件 + analytics.py + csp_report.py

**后端服务（28 文件）**：services/ 目录全部文件

**后端 ML（25 文件）**：ml/ 目录全部文件

**后端任务（5 文件）**：tasks/ 目录全部文件

**前端（50+ 文件）**：src/main.ts, App.vue, csp.ts, api/ 全部, components/ 全部, composables/ 全部, config/ 全部, harness/, i18n/, layouts/, mocks/, plugins/, router/, index.html, package.json, vite.config.ts, nginx.conf, Dockerfile

### 已忽略的范围（按用户要求）

- 所有状态文档（.trae/rules/Ralph.md 等）
- 所有 ralph 文档（docs/planning/v*/04-ralph-tasks.md 等）
- 所有 DELIVERY_REPORT、LAUNCH_BLOCKERS 等过程性文档
- 旧版审核报告（本报告已覆盖）

---

**报告生成时间**：2026-06-25
**审核模型**：GLM-5.2
**审核方法**：5 路并行深度代码审核 + 关键 bug 二次验证 + 误报修正
**总问题数**：215（CRITICAL 23 / HIGH 52 / MEDIUM 84 / LOW 56）
