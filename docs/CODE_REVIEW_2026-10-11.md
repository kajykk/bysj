# 全量源码审查报告

**审查日期**：2026-10-11
**审查范围**：实际业务源码，跳过 `node_modules`、`.venv`、构建产物（`dist`/`htmlcov`/`__pycache__`）、锁文件、生成文件（`auto-imports.d.ts` 等）、测试文件
**覆盖规模**：
- 后端 `backend/app`：259 个 Python 源文件（api 49 / core 64 / services 66 / ml 27 / models 12 / schemas 21 / tasks 7 / monitoring 8）
- 前端 `frontend/src`：约 350 个源文件（views 181 / api 46 / components 40 / utils 34 / composables 16 / router 5 / stores 5）
- 另含 `main.py`、`constants/`、`utils/`

**方法论**：6 路并行逐文件 Read/Grep 取证，所有结论附「文件 + 行号 + 原始片段」。以下「严重」级结论已由主审二次复核取证（见文末复核清单）。

**严重程度定义**
| 级别 | 定义 |
|---|---|
| 严重 | 可被外部利用的安全漏洞、数据跨租户/跨用户泄露、数据丢失、核心功能静默失效、白屏 |
| 中等 | 特定条件下（并发、大数据量、异常路径）造成错误，或明确的性能/安全弱点 |
| 轻微 | 可维护性、命名一致性、边界健壮性、重复代码 |

---

# 一、后端 `api/` 层（49 文件）

## 严重

### A-01 危机事件三个状态流转端点完全无租户隔离（跨租户越权读写）
`backend/app/api/v1/review.py:175-251`（`handle` / `escalate` / `close`）

```python
service = CrisisEventService(db)
event = await service.handle_crisis_event(event_id=event_id, handled_by=current_user.id, ...)
return ok(service._to_response(event))
```
同一文件 `list_crisis_events:168` 特意传了 `tenant_id=current_user.tenant_id`，这三个写端点没传。服务层 `services/review_service.py:435/472/507` 为裸查询 `select(CrisisEvent).where(CrisisEvent.id == event_id)`，零租户条件。
> 已复核：三个端点确实未传 `tenant_id`。

**后果**：A 租户管理员凭一个 `event_id` 即可读取外校学生的 `input_summary`（自述原文）与自伤/自杀关键词，并可将他校危机事件强制 `close` 为 `resolved`，直接抹掉他校危机响应流程。
**建议**：三个端点传 `current_user.tenant_id`；服务层用与 `get_crisis_events:361-390` 同样的 `join(User).where(tenant_scoped_filter(...))`，不符返回 404（避免存在性泄露）。

### A-02 复核任务详情/分配/处理/升级全链路无租户过滤
`backend/app/api/v1/review.py:287-426`；`services/review_service.py:161-214`

```python
async def get_review_by_id(self, review_id: int) -> ReviewTask | None:
    result = await self.db.execute(select(ReviewTask).where(ReviewTask.id == review_id))
```
`assign_review` / `resolve_review` / `escalate_review` 同样无租户条件。全文件 `tenant` 仅出现 1 次。
**后果**：`require_permission("review.handle")` 只约束调用者本人，不约束被操作对象归属。可跨租户读取、领取（`assign` 把 `assigned_to` 改成自己）、结案他人复核任务。
**建议**：`get_review_by_id(tenant_id=...)` 内 JOIN User 过滤，4 个端点统一传参。

### A-03 埋点查询端点跨租户泄露 `user_id` + `client_ip`
`backend/app/api/v1/analytics_events.py:267-292`

```python
if current_user.role not in (USER_ROLE_ADMIN, USER_ROLE_SUPER_ADMIN):
    raise HTTPException(status_code=403, ...)
```
手写角色判断代替 `require_role_tenant_scoped`，完全绕过租户一致性校验；`_event_store` 是进程内全局 list，无租户维度。
**后果**：任租户管理员可拉取全部租户全部用户的埋点，每条含 `user_id`(:165) 与 `client_ip`(:169)，与文件头「禁止采集 PII」的自述直接冲突。
**建议**：改 `require_platform_admin()` + 事件落库带 `tenant_id`。

### A-04 模型质量指标是硬编码假数据，却被上报 Prometheus
`backend/app/api/v1/metrics_helpers.py:26-77`

```python
_ML_QUALITY = {"structured": {"version": "v1.23_lr_calibrated", "auc": 0.9121, "f1": 0.8541, ...}, ...}
async def collect_ml_quality_metrics() -> None:
    model_auc.set(payload["auc"], modality=modality, model_version=version)
```
**后果**：AUC/F1/ECE/召回/精确率/p95 全部与真实模型无关。真实 AUC 从 0.91 掉到 0.55，监控永远显示 0.9121 —— **静默的错误保证**，且是 Grafana 告警与模型退化判据的输入。对一个以心理健康风险预测为核心的系统，这是数据正确性级别的最高危缺陷。
**建议**：改为从 ModelRegistry/离线评估报告读取；在拿到真实数据前宁可不上报这些 Gauge（NoData 优于绿灯）。

### A-05 训练任务列表/详情向普通用户开放且无归属校验
`backend/app/api/v1/model_predict/status.py:68-88`

```python
_: Annotated[User, Depends(require_permission("user.predict.use"))]
...
return ok(service.get_training_job(job_id))
```
`user.predict.use` 是普通学生权限（同权限用于 `/predict/*`），而 `training/jobs` 属后台运维域（兄弟端点 `/experiment/train` 要求 `admin.predict.audit`）。`get_training_job(job_id)` 是典型 IDOR。
**建议**：改 `require_platform_permission("admin.predict.audit")`，或过滤 `created_by == current_user.id`。

## 中等（精选）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| A-06 | `api/v1/uploads.py:56-58, 270-300` | 扩展名白名单 `[A-Za-z0-9]{1,8}` 覆盖 `html`/`svg`；`FileResponse` 不设 `Content-Disposition: attachment` / `nosniff`，浏览器在**同源上下文**渲染 → 存储型 XSS，可窃取同源 token | 加响应头 `attachment` + `nosniff` + `CSP: default-src 'none'`，或改显式扩展名白名单 |
| A-07 | `api/v1/tenant_branding.py:78-80, 141-149` | `custom_css` 收 1 万字符不清洗，前端内联 `<style>` 时可 `</style><script>` 逃逸 | `cssutils`/`bleach` 白名单清洗；前端用隔离 `<link>` 加载 |
| A-08 | `api/v1/tenant_branding.py:158-167` | 审计 `tenant_id` 写操作者租户，与 `tenant_admin.py:152`、`tenant_export.py:139`（写目标租户）不一致 → 跨租户改品牌配置在目标租户审计里查不到 | 改 `tenant_id=tenant_id` |
| A-09 | `api/v1/reports.py:539-596` | PDF 派发 `try` 同时包住「写 Redis」与「投 Celery」；前者成功后者失败时用**同一 job_id** 建本地影子任务，而 `_resolve_pdf_job:150-166` Redis 优先 → 客户端永远轮询 `queued` | 拆分 try 范围，失败时在同一 job_id 上标记 failed，或回退时换新 job_id |
| A-10 | `api/v1/gdpr.py:63-68` | 流式导出把内部异常塞进 HTTP **200** 响应体（残缺 JSON），状态码与语义双错 | 存在性校验提到 `StreamingResponse` 构造之前，不存在抛 404 |
| A-11 | `api/v1/gdpr.py:315-340` | 管理员匿名化端点 docstring 承诺「供第二人复核」，实现只有一行日志，可一键匿名化另一位 admin/super_admin 且无需密码 | 禁止对 `role in (admin, super_admin)` 调用，或要求双人复核 |
| A-12 | `api/v1/monitoring.py:517-531` | `payload.url` 浏览器完全可控且无格式约束 → 含 `\r\n` 可伪造整条日志（log forging），污染 SIEM | 只保留 origin+path、截断、移除 CR/LF |
| A-13 | `api/v1/monitoring.py:393-454` | `request_details_list` 无默认时间窗口，`MonitoringLog` 是高写入流水表，不传 `start_time` 即近全表扫描 | 加默认 7/30 天窗口并强制下界 |
| A-14 | `api/v1/alerts/_schemas.py:54-65` | SSRF 中性化覆盖不全：`2130706433`（十进制）、`0177.0.0.1`（八进制）、`[fd00:ec2::254]`、DNS rebinding 均可绕过；解析异常走「当域名放行」 | `socket.getaddrinfo` 解析后判断，解析异常 fail-closed |
| A-15 | `api/v1/csp_report.py:20-53 vs 139-174` | 定义良好的 `CSPReportBody`（带 max_length）**从未被引用**，取值全走原始 dict → 长度保护是死代码；`:176-184` 攻击者可控内容直接进日志 | `CSPReportPayload.model_validate(data)`；日志清洗 CR/LF |
| A-16 | `api/v1/counselor.py:161-196` | `list_my_users` 已接租户，`get_user_detail` 未接（`counselor_service_user.py:118-131` 只校验绑定关系） | 同样接受 `tenant_id` 做 join 过滤 |
| A-17 | `api/v1/alerts/__init__.py:320-370` | 告警历史 `total` 来自 SQL count，items 被 Python 端二次过滤 → 分页错乱；`:239-272` webhook 返回裸 dict 不遵循 `ok()` 信封 | 过滤下推 JSONB；webhook 改 `ok({...})` |
| A-18 | `api/v1/auth.py:169-170 vs 227-230` | `login` 刻意不把 refresh_token 放回 body，`/refresh` 却完整回吐 `return ok(tokens)` —— 风险抵御只在一条路径生效 | 统一 cookie-only |
| A-19 | `api/v1/auth.py:260-272` | 密码重置请求无任何审计日志，也未绑定租户（其余三个端点都落了 OperationLog） | 补 `_log_auth_operation` + `tenant_id` |
| A-20 | `api/v1/canary.py:31-304` | 灰度发布全部 6 个写操作均无审计日志，只能靠 `rollback_reason` 里手工拼 `f"{reason} (by user {id})"` 代偿 | 统一写 `OperationLog(action_type="canary.<op>")` |
| A-21 | `api/v1/model_predict/registry.py:66-139` | 模型上线/回退（生产影响最大操作）无审计；`:32-34, 117-119` 内部异常原文进 HTTP detail | 同事务写审计；`detail` 泛化 |
| A-22 | `api/v1/ops_dashboard.py:145-163` | 平均响应时长把全部已解决复核任务拉进 Python 求和，每次打开管理首页调用 | SQL 聚合，至少加 limit 护栏 |
| A-23 | `api/v1/user_data.py`、`user_content.py`、`analytics_events.py`、`grafana_adapter/` | 多个端点完全无 `@limiter`（兄弟端点均有），其中 `text_analyze`/`collect_structured_data` 触发模型推理 | 推理类 `"20/minute"`，列表类 `"60/minute"` |
| A-24 | `api/v1/silences.py:344-351` | AM 侧删除失败仍清空本地 `am_silence_id` → 静默规则在 AlertManager 永久残留且不可管理 | 失败保留 id + 置 `am_sync_state="stale"` 由补偿任务重试 |
| A-25 | `api/v1/user_upload.py:189-199, 295-305` | 先写后判（实际可写入 21MB 才触发删除）；批量只限 10 个文件不限总字节（单次 200MB）；`:129-133` 兜底 except 一行日志都没有 | 预判 `size + len(chunk)`；批量加总大小上限；补 `logger.exception` |
| A-26 | `api/v1/content_governance.py:103-125` | 对已下架内容调用 `/review` 不改变状态却写审计 → 历史查询误以为通过复审 | 非 `pending_review` 返回 409 |
| A-27 | `api/v1/admin.py:300-321` | `/operation-logs/export` 声明 `CSV_EXPORT_RESPONSE` 却返回 JSON 信封；「不分页」全量导出无行上限 | 对齐契约；加 `max_rows` + `truncated` |
| A-28 | `api/v1/metrics.py:100-108` | 每次指标抓取新建 Redis 客户端且不关闭（15s/次 → 4 连接/分钟） | 复用 `app.core.cache.get_redis_client()` 单例 |
| A-29 | `api/v1/model_predict/_common.py:55-157` | `_do_save` 全流程无 try/rollback，在 fire-and-forget 任务中运行 → 连接归还池时处于 pending rollback | `try/except → rollback → logger.exception` |
| A-30 | `api/v1/model_predict/_common.py:168-184` | fire-and-forget 落库，进程退出（滚动发布/SIGTERM）即静默丢评估结果，并跳过危机预警链路 | 注册 lifespan shutdown 等待收敛，或改 Celery |

## 轻微（模式级）
- `operator_role="admin"` 硬编码约 10 处（`silences.py:386,462,496`、`content_governance.py:115,175,231`、`gdpr.py:272,345`、`model_kill_switch.py:85,139`、`tenant_admin.py` 等），入口含 super_admin 却被记成 admin → 统一 `current_user.role`。
- 文件名清洗三份 copy：`admin.py:42-49`、`user_risk.py:24-29`、`reports.py:141-147`。`P1-SEC-030`（长度限制）只修了 `reports.py` 一份 —— **同一个 bug 修了三分之一**。
- 错误信息处理四种「方言」并存：完全不泄漏（`model_validation.py:150-153`，正确范式）/ 部分泄漏（`reports.py`、`review.py`）/ 严重泄漏（`registry.py:34,119`）/ 200 里塞错误 JSON（`gdpr.py`）。
- `raise HTTPException(...) from e` 不一致：`review.py:358,392,426` 漏写。
- 审计写入普遍是「业务一次 commit + 审计第二次 commit」，违反 ADR-012「单端点 ≤1 commit」。

---

# 二、后端 `core/` 层（64 文件）

## 严重

### B-01 `ws.disconnect()` 同步且不加锁，与 `connect()` 的 `asyncio.Lock` 构成竞态
`backend/app/core/ws.py:52-106`

```python
async def connect(...):
    async with self._lock:
        self._connections[user_id].append(ws)      # L78
def disconnect(self, user_id, ws) -> None:         # L94 无锁、非 async
    self._connections[user_id] = [w for w in self._connections[user_id] if w is not ws]
```
> 已复核：`disconnect` 确为 `def` 且无锁。

**后果**：列表重建（L96）与 `append`（L78）无互斥 → lost update。要么新建连接被旧快照覆盖而静默丢失（用户上线后收不到任何消息），要么已关闭连接残留使 `max_global_connections` 计数漂移，最终「连接数满」永久拒绝所有新连接，只能重启进程。
**建议**：`async def disconnect(...)` + `async with self._lock:`；`_local_send_to_user:142` 改 `await self.disconnect(...)`。

### B-02 三个 breaker 的 `init_*` 重新绑定模块全局，与 `db_breaker` 的明文约定直接冲突
`core/ml_breaker.py:129-145`、`celery_breaker.py:175-190`、`smtp_breaker.py:135-150`

```python
global ml_breaker
ml_breaker = CircuitBreaker(...)
```
同目录 `db_breaker.py:323-325` 明文写着「必须就地更新既有单例（`db_breaker.configure`），不能重新赋值模块全局…会造成熔断器状态分裂」，而另外三个恰恰用了被禁止的写法。
**后果**：Python 的 `from X import Y` 是值拷贝绑定，任何在 `init_*()` 前 import 的模块持有旧实例 → 一部分代码路径看到 OPEN，另一部分仍 CLOSED 并继续向已故障下游发请求。
**建议**：三处改 `*.configure(failure_threshold=..., recovery_timeout=..., ...)`。

## 中等（精选）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| B-03 | `config.py:635-647 vs 619-633` | `kill_switch_fail_closed` 用 `.lower() == "production"`（无 strip、非白名单），`dev_credentials_allowed` 用 `strip().lower() in _DEV_CREDENTIAL_ENVS`。`APP_ENV=" production"` 时凭据已 fail-closed 而 Kill Switch **fail-open** | 共用同一判定源 |
| B-04 | `config.py:671-685` | 模块级 `sys.exit(1)` 在 import 期杀死进程，Alembic/CLI/单测/OpenAPI 导出全被终止 | 改 `raise RuntimeError`，由 lifespan 决定 |
| B-05 | `pii_crypto.py:374-412` | 解密失败静默返回占位串 `"[DECRYPTION_FAILED]"`，会被当成真实姓名写进响应/CSV/PDF；若回写 DB 会把占位串加密成合法密文 → **原始 PII 永久不可恢复**，且无日志无指标 | 抛 `PiiDecryptionError` + ERROR 日志 + 指标 |
| B-06 | `safe_pickle.py:177-192` | 白名单放行整个 `app` 包前缀 → `app.*` 下任意类的构造函数都可能被 unpickler 调用；叠加 `_ALLOWED_BUILTINS` 放行 `type`（L196-216）可构造任意类。作者自承风险却未收口 | 改显式子模块清单；移除 `type` |
| B-07 | `model_engine/fusion.py:126-135` | 所有模态都失败时返回 `risk_score=0, severity="none"` —— 正是 `risk_thresholds.py:56-66` 反复强调的「最危险失效模式」（把算不出来表达成无风险），而融合层未被 `ensure_finite_score` 覆盖 | 返回 503 或 `degraded=True` + 强制人工复核 |
| B-08 | `model_engine/fusion.py:70-79` | `asyncio.gather(return_exceptions=True)` 后 `continue` 静默丢弃异常，无日志无指标，响应里看不出缺了哪一路 | `logger.warning` + `modality_failure_total{modality}` + 响应加 `degraded_modalities` |
| B-09 | `model_engine/risk.py:169-191` | `_get_shap_explainer` 用 `id(model)` 作缓存 key。`id()` 在对象 GC 后可复用 → 复用错误 explainer（SHAP 值来自另一个模型），缓存永不清理 → 内存泄漏 | `weakref.WeakKeyDictionary` 或挂到 model 对象上 |
| B-10 | `model_engine/risk.py:118-133` | `_check_crisis_safety` 是第二套危机检测（朴素子串匹配 `settings.crisis_keywords`），与 `crisis_detector.py:179-201`（编译正则 + `CASUAL_EXPRESSIONS` 口语过滤）逻辑冲突：同一句「累死了」两条路径结论相反 | 委托 `self.crisis_detector.scan(text)` |
| B-11 | `model_engine/loading.py:427-456` | 并发首次加载同一模型无 single-flight，N 个并发请求各自加载（BERT 数百 MB）→ 内存峰值 N 倍 OOM | per-`model_id` 的 `asyncio.Lock` / future 去重 |
| B-12 | `model_engine/loading.py:94-143` | 每次加载都对模型文件做全量 SHA256，无缓存 | 按 `(path, mtime, size)` 缓存 |
| B-13 | `model_engine/predict.py:296-309` | `structured_experimental_enabled` 默认 True，单请求跑主模型 + v1.21 + v1.23 + adapter（约 4 倍 CPU），注释自认「生产环境可选关闭」却默认开启 | 生产默认 False；`default_model == v1.23` 时去重 |
| B-14 | `model_engine/predict.py:102-118` | 路由到 lite/anxiety_only 时 `float(None)` 未被捕获 → 500；`:160-171` 主模型加载只捕获两种异常，`ModuleNotFoundError`/`AttributeError`/`MemoryError` 不降级 | 显式 None 分支；统一 `except Exception` 分类 |
| B-15 | `model_engine/predict.py:1036-1067` | BN 校验触发模型二次全量加载（三个文件），若条件持续为真则**每次推理重载三次** | 缓存校验结论，直接走降级 |
| B-16 | `metrics.py:754-766` | Info 指标 `# TYPE {name}` 与样本名 `{name}_info` 不一致 → Prometheus 报无 type directive 或丢弃样本，**Info 指标在生产抓取中实际不可用** | `# TYPE {name}_info gauge` 并对齐 HELP |
| B-17 | `alert_rules.py:441-470` | 生成 `expr: {metric} {comparison} {threshold}`，而 Prometheus 没有 `gt` 运算符；`http_requests_total > 0.001` 语义错误 → 生成的 `alert_rules.yml` 无法加载 | 输出带 `rate()` 的完整 PromQL，或明确标注仅作文档 |
| B-18 | `cache.py:300-366` + `deps.py:90-161` | Token blocklist strict 模式下 Redis 秒级抖动 → 所有需认证请求 503，无本地降级窗口 | 30s 本地降级宽限窗口 + 显著 metric |
| B-19 | `token_blocklist.py:38-84` | 读严格（fail-closed）但写宽松：`revoke_token` 失败仅 `return False`，调用方不检查则用户「已登出」但 token 实际仍有效至自然过期 | revoke 失败抛错返回 503，或缩短 access token 有效期 |
| B-20 | `rate_limit.py:37-72` | `X-Forwarded-For` 右往左跳过 `trust_proxy_hops` 个；若配置值大于实际链长，取到最左侧**客户端可任意伪造**的值 → 每请求换前缀即可完全绕过限流 | 校验 `len(xff_chain) >= hops`，否则回落 `request.client.host` |
| B-21 | `db_breaker.py:65-128` | `_is_connection_failure` 对未分类 `DBAPIError` 一律视为连接失败；`ProgrammingError`（SQL bug）会持续计入并打开熔断 → 把代码 bug 表现成数据库故障 | 与 `database.py:69-101` 的排除口径统一为共享常量 |
| B-22 | `ml_breaker.py:72-111` | `_is_ml_failure` 对未知异常保守返回 True，`AttributeError`/`KeyError`（代码 bug）会触发熔断 | 未知异常记独立指标不触发熔断 |
| B-23 | `tenant_context.py:48-135` | 租户解析优先级 header → subdomain → JWT，`X-Tenant-ID` 优先级最高 → 任何客户端都能自选租户，靠下游校验「先污染后校验」 | 已认证用户用 JWT claim 覆盖 header |
| B-24 | `celery_app.py:291-307` | `_mask_sensitive` 用 14 个键名黑名单，Celery 任务参数中的 `id_card`/诊断记录等本项目实际 PII 原样进入 DLQ 错误日志 | 改白名单或与 `log_sanitizer` 共用词表 |
| B-25 | `celery_app.py:25-32` | `enable_utc=False` 的滚动升级 8 小时偏移风险仅写在注释里，无运行时校验 | 启动期一致性自检 |
| B-26 | `log_sanitizer.py:494-512` | 递归脱敏深度上限 6，超出后**原样返回**（第 7 层以下的 password/id_card 裸奔）。FastAPI body 常嵌套 5-8 层，真实可达 | 超限返回 `"<max_depth_exceeded>"` + warning |
| B-27 | `ws.py:168-187` | `broadcast()` 无锁遍历 + 串行 await，无背压；`:144-187` Redis 发布失败仅 `logger.debug` → 跨进程预警静默丢失 | `gather` + 分批 + `logger.warning` + 指标 |
| B-28 | `ws.py:214-261` | `_pubsub_loop` 用 `socket_timeout=None` 长连接无心跳，中间设备静默断链则阻塞读永不返回 → 进程存活、日志无异常、跨进程消息 100% 丢失 | `health_check_interval` 或周期 ping + 最大无消息间隔重连 |
| B-29 | `deps.py:282-367` | SA token 返回的虚拟 admin 用 `id=0`，进入 `created_by`/`operator_id` 会产生库中不存在的悬空引用 | 建真实 system 账户，或审计映射为字符串标识 |
| B-30 | `event_bus.py:103-120` | `put_nowait` 队列满时静默丢弃，无 metric；审计类事件丢失不可接受 | 递增 `event_bus_dropped_total` + warning |
| B-31 | `sentry.py:107-125` | `traces_sample_rate=1.0` + 事后过滤，所有请求都完整构造 transaction（含 SQL 语句采样）后才丢弃 | 改用原生 `traces_sampler` |
| B-32 | `otel.py:143-170` | `_instrument_fastapi` / `_instrument_sqlalchemy` 是空函数（只 import 探测），函数名承诺「instrument」却什么都不做，给人已自动埋点的错觉 | 重命名或真正完成埋点 |
| B-33 | `risk_thresholds.py:98-112` | `get_fusion_threshold` 返回阈值分数（22/42/62/82）而非等级（0-4），与 `score_to_level` 语义高度相似却不同 → 按 0-4 消费的调用方 `82 >= 3` 恒真 | 重命名为 `get_fusion_threshold_score()` |
| B-34 | `contracts.py:37-43 vs risk_thresholds.py:42-48` | 同一风险等级两套字符串：`low/medium` vs `mild/moderate`。前端拿 fusion 的 `severity`（后者产出）与 `low/medium` 比较会全部失配 | 统一 SSOT，另一处 re-export |
| B-35 | `model_registry_v2.py:279-398` | 「先改内存再落盘」，落盘失败回滚期间未加锁的读可见磁盘上不存在的记录 | 改为先写盘成功再更新内存 |
| B-36 | `model_registry.py:333-357` | `except Exception` 吞掉 V2 registry 生产覆盖失败，静默使用旧静态路径模型 | 生产 fail-fast 或计入指标 |
| B-37 | `security.py:16-61` | 密钥加载 `lru_cache(maxsize=1)` 无法失效，密钥轮换后仍返回旧密钥；`maxsize=1` 还会互相驱逐 | 缓存 key 加 `st_mtime`，提供 `reset_key_cache()` |
| B-38 | `fallback_hierarchy.py:109-141` | 同步 `predict_with_fallback` 在事件循环内抛 `TypeError` 且注释承认不调用 `result.close()` → 协程泄漏 | `result.close()` 后再抛 |
| B-39 | `pii_crypto.py:469-490` | `_hmac_blind_index` 无 key 时运行期 raise；`config.py` 只在 production 强制，staging 未配置则按手机号查用户 500 | 启动期 `ensure_pii_key()` 做环境感知校验 |

## 轻微（模式级）
- **同一模式复制 N 份后各自漂移**（本项目最高频系统性问题）：熔断器 init（4 份，1 对 3 错）、危机检测词表（2 份）、风险等级标签（2 套）、模型元数据（3 份：`MODEL_PATHS` / `MODEL_COMPATIBILITY_REGISTRY` / registry_v2 JSON）、角色定义（`deps.ROLE_HIERARCHY` vs `contracts.USER_ROLES`）、fallback metric 上报（`fallback.py` 内 4 份逐字重复）。
- 静默降级缺可观测性 8+ 处：`ws.py:165,187`、`fusion.py:72`、`event_bus.py:103`、全库指标递增失败的 `logger.debug`。**正确原则「旁路失败不得影响主流程」被过度应用成「失败不留痕」**。
- `_ML_QUALITY`（A-04）之外的「生成即失效」：Info 指标 TYPE 错（B-16）、PromQL 非法（B-17）、p99 返回桶上界系统性高估（`slo.py:114-119`）。
- `seed.py:599-615`：数百种子用户串行 bcrypt（~250ms/次）同步阻塞启动，分钟级。
- `config.py:608-617`：开发环境默认 CORS 放行，以 `APP_ENV=development` 部署到对外机器即开放。
- `text_tokenizer.py:26`：`_EN_ATERN` 疑似 `_EN_PATTERN` 笔误。

---

# 三、后端 `services/` 层（66 文件）

## 严重

### C-01 密码重置令牌不是一次性凭据，TTL 内可无限次重置
`backend/app/services/auth_service.py:319-347`

```python
token_data = decode_token(payload.reset_token)
if token_data.get("type") != "password_reset": raise ValueError(...)
user.password_hash = await get_password_hash_async(payload.new_password)
await self._revoke_all_user_refresh_tokens(user_id)
await self.db.commit()
```
> 已复核：全流程无 `jti` 吊销、无 `used` 标记、无「消费」动作。

**后果**：邮件链接/令牌一旦泄露（邮件归档、代理日志、Referer），攻击者可在 TTL 内任意多次重置；且重置不撤销已泄露的 access token —— 而同文件 `change_password:290-299` 是做了 jti 撤销的，**同一文件内两条改密路径安全强度不一致**。
**建议**：reset token 注入 `jti`，成功后 `revoke_token(jti, ttl=exp-now)`；重置成功后同样撤销该用户 access token。

### C-02 fire-and-forget 在 `commit()` **之前**调度 → 中高风险用户的预警与干预被静默丢弃
`services/risk_service_assessment.py:226-256` + `services/risk_service.py:92-106`

```python
self.db.add(risk); await self.db.flush()
from app.services.risk_service import _schedule_warning_and_intervention
_schedule_warning_and_intervention(user_id, risk.id, result["risk_level"])   # L236
...
await self.db.commit()                                                        # L256
```
> 已复核：调度确实在 commit 之前。

**后果**：`ensure_future` 的任务在下一次事件循环迭代即执行，新 session（READ COMMITTED）看到的是 commit 前快照 → 高概率命中 `risk is None` → 静默 return。中高风险学生的**预警通知与干预计划被丢弃**，只留一条 `logger.warning`。因竞态表现为「时有时无」，极难排查。
**建议**：把调度移到 `commit()` 之后（挪一行代码）。

### C-03 PDF 报告所有用户可控文本未经 XML 转义直接喂给 ReportLab `Paragraph`
`services/pdf_report_service.py:166/188/198/229` 与 `:322/344/354/385`（两处重复）

```python
story.append(Paragraph(report_data.title, title_style))
story.append(Paragraph(f"• {rec}", styles["Normal"]))
```
`Paragraph` 把入参当 mini-XML 解析。内容中出现 `<`、`&`（如「抑郁 & 焦虑」）即 `doc.build()` 抛错 → **报告生成整体失败**；用户可控内容还可注入非法标签构成内容注入与 DoS。
**建议**：统一 `escape()` 封装 `_P(text) -> Paragraph(escape(str(text)), style)`；两处 story 构建抽成 `_build_story()` 共用（当前两份 80 行逐字雷同）。

### C-04 `add_group_member` 捕获 `IntegrityError` 后整体 rollback 并吞异常返回 True
`services/counselor_service_group.py:126-131`

```python
try: await self.db.flush()
except IntegrityError:
    await self.db.rollback(); return True
```
三重问题：① 回滚的是**整个事务**而非 savepoint，会连带回滚调用方同请求内已完成的写入；② 吞异常后返回 True，调用方无法区分「成员已存在」与「写入失败」；③ 回滚后又 `add(OperationLog)` + `commit()`，审计与实际记录不一致。
**建议**：改 `async with self.db.begin_nested()` —— 仓库内已有两处正确先例（`intervention_service.py:484`、`risk_service_warning.py:95`）。

### C-05 `validation_engine` 的 `asyncio.gather` 对全量验证集无并发上限
`services/validation_engine.py:374-375`

```python
tasks = [model_engine.predict_structured(feat) for feat in features]
results = await asyncio.gather(*tasks)
```
**后果**：N=数万时瞬间创建数万个 Task 与 future（内存峰值），线程池排队爆炸，单个请求占用全部 worker；无 `return_exceptions=True`，任一失败即整体作废。
**建议**：`asyncio.Semaphore(n)` + 分批。

## 中等（精选）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| C-06 | `auth_service.py:275-282` | `change_password` 吞掉 bcrypt 侧异常降级为「当前密码错误」，服务端故障伪装成用户输入错误，日志是 warning 而非 error | 区分 ValueError 与其他异常，后者 5xx + logger.error |
| C-07 | `auth_service.py:152-166` | 登录先 commit 再查 profile，两次独立事务；profile 查询失败则用户「已登录」却拿不到响应 | profile 查询提到 commit 之前 |
| C-08 | `auth_service.py:132-140` | 登录无任何失败计数/锁定/退避，仅靠事后 Celery 扫描（不阻断） | per-username + per-IP 失败计数 |
| C-09 | `review_service.py:551-561` | 注释声称「截断 detail 至 5000 字符」，代码**完全没有截断** → 超长 note 触发 `StringDataRightTruncation` 使整条危机处置事务回滚 | 真正实现截断或删掉误导性注释 |
| C-10 | `review_service.py:434-440` | 危机事件状态转换无行锁，`_validate_crisis_transition` 存在 TOCTOU；同文件 `assign_review:169` 已用 `with_for_update()`，此处不一致 | 加 `with_for_update()` 或条件 UPDATE 按 rowcount 判定 |
| C-11 | `review_service.py:265-296` | `get_review_stats(days=30)` 的 `days` 参数完全未被使用 → 前端以为拿到「最近 30 天」，实际是全量历史统计 | 补 `created_at` 过滤或删参数 |
| C-12 | `counselor_service_group.py:126-131` 之外 **14 处** | `offset = (page-1)*page_size` 复制 14 次且全无下界校验（`intervention_service.py:176` 仅钳了上界）。`page=0` → `OFFSET must not be negative` → 500 | 抽公共 `paginate()`，统一 `page=max(1,page)` |
| C-13 | `gdpr_service_export.py:263-279`（7 个 `iter_*` 同构） | 流式导出用 OFFSET 分页但**没有 ORDER BY** → 翻页可能重复行或漏行。对 GDPR Art.15/20「完整导出」是实质性合规缺陷 | 立即加 `.order_by(<主键>)` |
| C-14 | `gdpr_service_export.py:105-174` | `export_user_data` 一次性全量拉取 8 张表，其中 `operator_id == user_id` 的**全量操作日志**无 LIMIT 无时间窗 | 加 `max_records` 或强制走流式 |
| C-15 | `anomaly_detection_service.py:134-147 / 318-346 / 410-443` | 三个检测器循环内发 DB 查询（N+1），单次扫描最多 ~700 次串行往返；`:389-407` `LIMIT` 无 `ORDER BY` → 每次扫描检出不同集合 | 批量 `IN (...)` 查询或窗口函数；先排序再 LIMIT |
| C-16 | `crisis_export_service.py:85-86` | 时间过滤用 **aware** UTC，而 `CrisisEvent.created_at` 是 naive `DateTime`（`models/review.py:161-163`），与全仓「列 naive UTC，比较前 `_naive_utc()`」约定相反。PG+asyncpg 下会直接报错 | 改 naive，修正注释 |
| C-17 | `experiment_data.py:36-40 / 81-83` | 数据集不存在时**静默生成合成 demo 数据**训练（`label = 1 if i % 3 == 0 else 0`，规律分布易拟合）→ 生产配置错误时产出「指标漂亮」的假模型并可能被影子对拍放行 | 生产禁止自动生成，直接 `FileNotFoundError` |
| C-18 | `experiment_trainer.py:258-268` | `latest_checkpoint` 按字符串排序 → `"checkpoint-1000" < "checkpoint-500"`，训练超 9 个 epoch 后恢复的是字典序最大而非步数最大的 checkpoint | `key=lambda p: int(p.name.split("-")[-1])` |
| C-19 | `experiment_trainer.py:386-392` | `_predict_scores` 仍硬编码 `[:, 1]`，而同文件 `compute_metrics:155-167` 已兼容单列 sigmoid → 单输出模型下 `IndexError` | 抽 `_positive_proba(logits)` 统一 |
| C-20 | `experiment_evaluator.py:83-98` | BERT 评估逐条推理（batch size = 1），`padding=True` 在单样本下无效，比 batched 慢一个数量级 | 按 32/64 切片批推理 |
| C-21 | `shadow_mode_service.py:47-49` | docstring 称「从 config 读取采样率」，实际 `_sample_rate = 1.0` 硬编码；`shadow_mode_text_enabled` 全文无引用 → **影子模式无法关闭** | 改读 settings + 开头判 enabled |
| C-22 | `drift_monitoring_service.py:103-123` | 异常时 `db_session.rollback()` 会丢弃同批次前面模态已 flush 的告警 | 每模态 `begin_nested()` savepoint |
| C-23 | `drift_monitoring_service.py:253-271` | 告警去重不区分「疑似版本失配」与「真实漂移」→ 一旦存在未处理的 MEDIUM 告警，后续 HIGH/CRITICAL 漂移永远无法建告警 | 去重条件加类型约束或允许升级 |
| C-24 | `alert_lifecycle_service.py:343` | `build_notification_payload` 用 `(alert.severity or ...).value`，而 `severity` 是 String 列（plain str）→ `AttributeError`；同文件 `:250-253` 已正确处理，两处自相矛盾 | 抽 `_severity_str(alert)` |
| C-25 | `canary_manager.py:99-132` | `scalar_one_or_none()` 无 `limit(1)`；`start_canary:221-242` 「先查再插」无唯一约束无锁 → 并发插入两条 RUNNING 后所有 `get_active_canary` 500 | 加 `.limit(1)`；加部分唯一索引 `UNIQUE(route_prefix) WHERE status='RUNNING'` |
| C-26 | `canary_fallback_monitor.py:48-113` | 多实例部署下无分布式锁，N 实例每 30s 全量扫描 + 并发回滚（`review_service.py:57-60` 已有 `pg_advisory_xact_lock` 先例） | 复用 advisory lock 或 Redis 选主 |
| C-27 | `pdf_job_store.py:74-134` / `excel_job_store.py:77-134` | 进程内任务 dict **无任何锁**，而 PDF 生成回调在 `to_thread` 中调用 `update()` → 跨线程竞态；`MAX_PDF_JOBS` 限流是 check-then-act 无原子性 | 加 `threading.Lock`（`training_jobs.py:20` 已有）；合并为 `create_if_below_limit()` |
| C-28 | `user_data_service.py:263-266` | 上一行刚把可能为 None 的 `sentiment_score` 赋给 entry，下一行 `float(result.get("sentiment_score", 0))` → `float(None)` TypeError，整个文本分析接口 500 | `.get()` 后显式判 None |
| C-29 | `model_predict/training_jobs.py:303-304` | 模块导入时执行文件 IO 与全局清理（副作用），拖慢启动、只读文件系统告警、单测互相干扰 | 改显式初始化函数由 lifespan 调用 |
| C-30 | `model_predict_service.py:34-49` | `_sync_modules()` 猴子补丁反复重写被拆分子模块的全局引用（11 处调用前各执行一次），运行期改写模块全局有瞬时不一致窗口，且形成双向依赖 | 改为显式依赖注入 |
| C-31 | `admin_service_archive.py:96-100` | `mask_old_ips` 先把全部待掩码行读进内存（10 万条 ORM 物化）；`:37/67/241` 单次大 DELETE（长事务、锁、WAL 暴涨） | `yield_per` 流式 + 分批 DELETE |
| C-32 | `observability/aggregate.py:134-144` | `GROUP BY` 下推到 JSON 抽取表达式，但 `detail` 是 Text 列无索引 → 窗口内仍是全表扫描 + 逐行 JSON 解析 | 提升为生成列 + 索引 |
| C-33 | `observability/query.py:192` | `_BUCKET_SECONDS[bucket]` 未校验，非法值 KeyError → 500；`:249-259` 静默截断 5000 条使响应时长统计系统性偏差，且 `:204-207` 的 `truncated` 语义已失效 | 校验 + dedup 下推 SQL |
| C-34 | `mttr_service.py:180-184` | `select(OperationLog)` 物化整行 ORM（含 `detail` 大文本），24h 窗口可达数万条 | 只投影需要的列 |
| C-35 | `validation_engine.py:92-102` | `load_dataset` 接受任意 `Path` 无根目录校验 → 路径穿越读取任意 `.csv`/`.json` | `resolve()` + `is_relative_to(data_root)` |
| C-36 | `validation_engine.py:226-229` | `except Exception` 吞掉全部计算异常并返回全 None 的 metrics → 模型验证被误判为通过（对比 `experiment_metrics.py:37-53` 的 `auc_reliable=False` 是正确范式） | 加 `metrics_valid` 标记或抛错 |

## 轻微（模式级）
- **事务约定两派并存且无标记**：「先 flush、调用方 commit」派（`canary_manager`、`alert_lifecycle`、`auto_rollback.execute_rollback`）与「服务层自管 commit」派（`auth_service` 6 处、`counselor_*` 7 处、`admin_*` 7 处）。`auto_rollback` 只 flush，`canary_fallback_monitor.py:82` 必须记得补 commit —— 隐式契约只能靠注释维系。
- **分页 count 与 list 条件手工同步两遍**（`warning_service.py:47-56`、`user_data_service.py:352-364`×3 等），已有正确范式 `select(func.count()).select_from(query.subquery())`（`review_service.py:142`）。
- **异常语义三档并存**：吞掉返回默认值 / 降级+显式标记 / 记录后回滚重抛（`warning_service.py:245-252` 正确）。建议统一到后两者。
- **注释与实现不符**（比缺注释更危险）：`review_service.py:557`（声称截断没截）、`shadow_mode_service.py:48`（声称读 config 实为硬编码）、`query.py:217`（truncated 失效）、`base_service.py:193`（Raises 声明不实）、`pdf_report_service.py:100`（声称校验 charts 实际不渲染 —— `charts` 字段声明了却从不渲染，`has_charts` 是误导性字段）。
- `services/__init__.py` 统一 re-export 会在 import 时拉起全部子模块（含 `sklearn.metrics`、`model_engine`），显著拖慢启动。

---

# 四、`ml/` `models/` `schemas/` `tasks/` `monitoring/`

## 严重

### D-01 实验产物清理的「active 模型保护集」对**目录型模型**失效
`backend/app/tasks/scheduler.py:984-1023`

```python
active_paths.add(str(Path(model_path_str).resolve()))     # 收集的是路径本身（可能是目录）
...
for file_path in entry.rglob("*"):
    if file_path.is_file():                                # 比对侧只遍历文件
        if str(file_path.resolve()) in active_paths:
```
> 已复核。而 `core/model_engine/loading.py:575-584 / 618-631` 明确 BERT 是**目录**加载（`AutoTokenizer.from_pretrained(model_path)`）。
**后果**：注册模型路径是目录时，文件路径永远不等于目录路径 → 保护判定恒 False → `shutil.rmtree` 删除**正在服务的模型目录**（L1042），线上推理 503 且模型文件物理删除不可恢复。这是本函数唯一的安全闸。
**建议**：`active_paths` 同时收录目录及其下所有文件，或改前缀匹配 `any(p.resolve().startswith(a) for a in active_paths)`。

### D-02 `stale_warning_reminder` 是空任务：只打日志，无任何提醒动作
`backend/app/tasks/scheduler.py:401-432`

```python
for warning in stale_warnings:
    if warning.counselor_id:
        logger.info("Reminder: Warning %d ... is unhandled for >24h ...")   # 仅此
```
**后果**：高危（level≥3）预警超 24h 未处理**永远不会有二次提醒**，且任务每天「成功」完成，监控完全健康 —— 静默功能缺失，心理健康场景等同漏报。
**建议**：复用 `_notify_warning()` 推送，并写 `reminded_at`/`remind_count` 做幂等。

### D-03 `pytorch_mlp` 显式 `weights_only=False`，生产被 `safe_torch_load` 强制改写为 True → 加载必然失败
`backend/app/ml/pytorch_mlp.py:226-252` vs `core/safe_pickle.py:494`

```python
checkpoint = safe_torch_load(path, weights_only=False, trusted_root=_trusted_root, ...)
model = cls(input_dim=checkpoint["input_dim"], hidden_dims=checkpoint["hidden_dims"], ...)
```
生产强制 `weights_only=True` 时只还原 tensor，而此处需要 `input_dim/hidden_dims/dropout_rate/use_batch_norm` 等非张量元信息 → KeyError。
**后果**：PyTorch 路径在生产 100% 不可用（dev 可用 → 测试全绿、上线即炸，典型环境差异型缺陷），失败原因被「强制 weights_only」的 warning 掩盖。
**建议**：架构元信息单独存 JSON 侧车（与 `model.py` 方案一致），`state_dict` 用 `weights_only=True`。

### D-04 `_load_model` 传给 `safe_joblib_load` 的哈希与文件自身哈希恒等 → 哈希校验形同虚设
`backend/app/core/model_engine/loading.py:485-520`

```python
# 下面传给 safe_joblib_load 的 expected_hash 与 precomputed_hash（即文件自身哈希）恒等，
# 因此该参数不提供额外保护 —— 真正的保护来自 safe_joblib_load 内部的 require_hash / 侧车校验。
```
注释已自认。一旦侧车缺失且非生产（`require_hash` 不强制），**零完整性校验加载**。
**建议**：`expected_hash` 传 registry 锚点而非文件自哈希；非生产也强制 `require_hash=True`。

### D-05 `fuse()` 未拦 NaN → 融合分被静默判为满级高风险
`backend/app/ml/fusion_engine.py:166-170, 237`

```python
if v is None or not isinstance(v, (int, float)): raise TypeError(...)
...
fused_score = max(0.0, min(100.0, raw_fused))     # NaN 时 min(100.0, nan) 返回 100.0
```
`float('nan')` 也是 `float`，一路参与加权求和。这正是 `fallback.py:59-92` 的 `_finite` docstring 里已修掉的同一陷阱，但融合层没有防护。
**后果**：任一模态产出 NaN → 融合分 100 → risk_level 4 → 触发无必要的危机干预。
**建议**：循环内加 `if not math.isfinite(v): raise ValueError(...)`。

### D-06 `predict_text` 对超长文本无上限（fusion 入口可传 MB 级）
`core/model_engine/predict.py:542-554, 660-661` + `schemas/model_predict.py:99-102`

`TextPredictRequest` 有 `max_length=5000`（`:28-30`），但 `FusionPredictRequest.text` **完全无约束**，而 `predict_fusion` 直接透传。
**后果**：单请求即可打满线程池（CrisisDetector 正则扫描 + TextAnalyzer + TF-IDF 三重 O(n)），拖垮所有模态推理。
**建议**：入口长度截断 + 给 `FusionPredictRequest.text` 加 `max_length`。

## 中等（精选）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| D-07 | `scheduler.py:276-293, 324-339` | 超时重试后，已提交页的告警被 dedupe 命中（`inserted_id is None`）→ **不再推送**，永久停在「已入库未推送」 | 加 `notified_at` 字段，扫描开头先补发存量 |
| D-08 | `scheduler.py:821-826, 880` | `_cleanup_uploads_dir_impl` 在 DB 引用查询失败时降级为**空保护集照删**（与 `:1009` 的「失败即中止」策略完全相反）。上传文件含用户头像与咨询师证书，删除后 404 不可恢复 | 引用获取失败 raise 让任务重试 |
| D-09 | `scheduler.py:291-292, 417, 461, 878` | 时区双轨制：代码 `datetime.now(UTC).replace(tzinfo=None)` vs 列 `server_default=func.now()`（DB 本地时区）。MySQL+Asia/Shanghai 下固定 **8 小时偏差**，「24h 未处理」实际判为 16h/32h | 统一为全库存 UTC naive |
| D-10 | `scheduler.py:988-1011` | 保护集解析失败即 `raise` 中止，无「部分失败」容忍 → 一条路径不存在就每周重试每周失败，`models/trained/` 持续增长直至磁盘写满 | 区分「路径不存在」（跳过）与「非法/权限」（中止）+ 停滞告警 |
| D-11 | `tasks/model_training.py:147-159` | 训练的是 BERT 却把产物注册为 `ModelType.LOGISTIC_REGRESSION`、`version` 硬编码 `"v1"` → 加载器可能把 BERT 目录交给 joblib | model_type 由配置传入；version 用时间戳 |
| D-12 | `tasks/model_training.py:200-206, 247-280` | 长训练任务无心跳，worker 被杀后 Redis 状态永久 `running`，前端轮询永久「运行中」 | 写 `heartbeat_at` + 超时判定；`task_revoked` 信号兜底 |
| D-13 | `tasks/pdf_report.py:415-428` | 重试耗尽后 `return {"status":"failed"}` → Celery 记 **SUCCESS**，告警规则完全看不见（`alerts.py:59-69` 已改 `raise exc`，此处未推广） | 对齐，`except MaxRetriesExceededError: raise exc` |
| D-14 | `tasks/observability.py:52` | `self.retry(exc=exc)` 未 `raise` → 返回值被丢弃，任务正常返回 SUCCESS，**锁统计 flush 从未真正重试** | `raise self.retry(exc=exc)` |
| D-15 | `tasks/alerts.py:148-158` | 归档批次固定 `limit(1000)`，每日一次 → 告警风暴期队列单调增长，`OperationLog` 无限膨胀而日志永远显示「成功归档 1000 条」 | 循环分页至无候选（带总时长上限） |
| D-16 | `core/model_engine/loading.py:575-584, 618-631` | BERT 分支从 HuggingFace Hub 远程下载，绕过 `trusted_root` 白名单与 `.sha256` 侧车体系；`revision` 若指向 `main` 则上游变更可静默替换模型 | 强制 `local_files_only=True` + 路径落 trusted_root，或删除 Hub 分支 |
| D-17 | `core/model_engine/loading.py:526, 548` | `.keras` 分支用 `tf.keras.models.load_model` 直连，是四条加载路径中**唯一完全裸奔**的（不过 trusted_root、不过侧车、未显式 `safe_mode`） | 显式 `safe_mode=True` + 复用 `_validated_model_file()` |
| D-18 | `models/*.py` 多表 | 外键缺索引（`review.py:43/129/145`、`intervention.py:34/55/75`、`counselor.py:51`、`admin.py:91/166/169/215`）→ 父表 DELETE 触发全表扫描锁；`user_id` 单独查询无索引 | 补 `index=True`（PG 不自动为外键建索引） |
| D-19 | `models/intervention.py:75` | `TaskExecution.task_id` 用 CASCADE，删除任务模板会连带删除**全部历史执行证据**（合规审计材料），且 `InterventionPlan.progress` 突变为 0 | 改 RESTRICT/SET NULL + 冗余 `task_title` 快照 |
| D-20 | `models/admin.py:20-44` | `ModelRegistry` 缺 `(model_name, version)` 唯一约束，而 `model_training.py` 每次训练都以 `version="v1"` 注册 → 无限累积同名同版本行，加载到的模型不可预测 | 加 `UniqueConstraint("model_name","version")` 或 active 部分唯一索引 |
| D-21 | `models/*.py` | `default=`（Python 侧）与 `server_default=`（DB 侧）混用无约定；`server_default="0"` 对 Boolean 在 SQLite 生成 `DEFAULT '0'`（字符串）与 CHECK 约束潜在冲突，MySQL 行为又不同 | 布尔列统一 `server_default=text("0")`；状态列统一 server_default |
| D-22 | `schemas/model_predict.py:17-24, 60, 99-102` | `dict[str, Any]` 校验强度分三档：`TabularPredictRequest` 仅限 50 键（无深度/大小/key 字符集校验），`FusionPredictRequest` 零校验，而 `schemas/assessment.py:21-45` 已有 `_payload_depth` 正确实现却没被复用 | 抽到 `schemas/common.py` 统一应用 |
| D-23 | `schemas/validation.py:11-18` | `dataset_path` 接受任意字符串（可含 `../`、绝对路径），直接作为数据集读取路径 → 路径遍历读任意文件 | 复用 `tasks/model_training.py:30` 的 `_SAFE_PARAM_PATTERN` 或 `is_relative_to` |
| D-24 | `monitoring/notifier.py:106-124` | 同步 `time.sleep(2**attempt)` 指数退避，最坏单次 send 阻塞 18 秒（5+1+5+2+5）；`escalation.py:219-276` 循环内逐条 await → N 条告警耗尽线程池 | 改异步重试或专用 executor + 并发上限 |
| D-25 | `monitoring/escalation.py:219-278` | 整轮循环后才 commit，外部 HTTP 耗时全部计入事务，且 `notifier.send(db=db)` 在事务内还写 DB | 先提交升级记录再发通知（与 scheduler「先落库再推送」同范式） |
| D-26 | `ml/hyperparameter_tuning.py:43-52` | `_append_tuning_cache` 每次追加都全量读+全量写（网格 162 次重写），`"w"` 截断写在进程被杀时留下损坏文件 → 下次 `JSONDecodeError` 返回空列表，**全部缓存丢失，搜索从头跑** | 改 append-only JSONL 或临时文件 + `os.replace` |
| D-27 | `ml/evaluation.py:75-112` | `compute_roc_curve` 未处理 score ties、梯形积分缺 (1,1) 收尾点 → AUC 有偏 | 用 `sklearn.metrics.roc_curve` + `auc` |
| D-28 | `ml/data_cleaner.py:175-195` | `load()` 从 JSON 读但**未做 `.sha256` 侧车校验**（`save()` 会写）→ cleaner 统计量（直接影响推理特征分布）可被篡改无校验 | `load()` 内调 `_verify_integrity(require_checksum=True)` |
| D-29 | `main.py:195-206, 231, 318` | preload 后台任务无 done_callback，异常不上报；`preload` 失败则 `start_persist()` 永不执行 → Prometheus `model_*` 指标永久为 0 而 `/health` 仍健康；关闭序列 `stop_persist` 若 `_me` 未初始化会 NameError 中断后续清理 → 连接泄漏 | try/except + capture_exception；`start_persist` 独立于 preload 成败；每步独立 try |

## 轻微（模式级）
- **两套并行实现/约定**（P1 级根因）：时区（naive UTC vs `_to_aware_utc`）、危机关键词（正则 vs 子串）、两个 `BaseModel` 类（`ml/unified_model_interface.py:27` 与 Pydantic 同名）、三个 `ModelRegistry` 同名、路径根解析（`parents[3]` vs 4×`parent` vs `settings.model_dir`）。
- **非原子文件/状态写入**：`hyperparameter_tuning.py:43-52`（截断写）、`model_training.py:180-193`（exists+hset 非原子，可能复活残缺 Hash）。
- `scheduler.py:220, 260-262`：`(now - created_at).days` 对负 timedelta 向下取整，未来时间戳会产生负「未评估天数」并拼进 `trigger_reason`。
- `tasks/model_training.py:30-43`：`job_id` 未校验即拼进 Redis key。
- `ml/data_split.py:87`：从 train 复制样本到 val，与 `verify_no_data_leakage` 的契约互斥。
- `ml/loss.py:41 vs 91-93`：两个 loss 的梯度 epsilon 处理不一致，BCE 解析梯度缺 `/n` 与链式项。

---

# 五、前端基础设施（api / router / stores / composables / utils）

## 严重

### E-01 WebSocket 重连达上限后永久放弃，无网络恢复/页面可见性监听
`frontend/src/composables/useWebSocket.ts:234-251`

```ts
if (this.reconnectAttempts >= this.maxReconnectAttempts) {   // max = 10
  ElNotification({ ..., duration: 0 }); captureMessage(...); return   // 永久停止
}
const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000)
```
**后果**：退避 1,2,4,8,16,30,30… 累计约 **2.5 分钟**就用尽 10 次。合盖、隧道、WiFi 切换等常见超 3 分钟断网都会让 WS 永久断连；之后即便网络恢复、`online` 事件触发、用户主动操作，**都没有任何重试入口**，唯一恢复手段是刷新页面。`/ws` 负责推送 `warning` / `counselor_warning` 与任务进度 —— 静默丢实时预警意味着咨询师可能收不到高危学生预警。
**建议**：① 监听 `online` / `visibilitychange` 重置计数并重连；② 提供 `wsClient.retryNow()`；③ 达上限后进低频无限重试（60s）而非停止。

### E-02 写操作（POST/PUT/DELETE）在 401 后一律自动重试 → 可能重复提交
`frontend/src/api/request.ts:182-215`

```ts
if (status === 401 && originalRequest && !originalRequest._retry) {
  originalRequest._retry = true
  const newToken = await refreshAccessToken()
  if (newToken) { flushPendingRequests(newToken); return request(originalRequest) }   // 不区分 method
}
```
**后果**：对非幂等写请求（`/warnings/{id}/handle`、`/alerts/silences`、`/tasks/{id}/complete`、`/gdpr/delete/{userId}`、`/reports/pdf/async`），若请求已落库仅因 token 在处理期间过期返回 401，重试会**二次写入**。
**建议**：仅对 `GET/HEAD/OPTIONS` 自动重试；写操作要求 `Idempotency-Key` 或显式 `retryable: true`；`flushPendingRequests` 对非安全方法直接 reject。

## 中等（精选）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| E-03 | `api/request.ts:325-333` | `promise.finally(cb)` 返回派生 Promise，请求失败时该派生 Promise 无人处理 → 每次失败请求额外触发一次 `unhandledrejection`，经 `main.ts:63-71` 向 Sentry 上报一份噪音（已 Node 运行时验证） | 改 `promise.then(ok, err => delete)` |
| E-04 | 全仓库零 `AbortController` | 快速翻页/切路由时旧响应覆盖新数据；`plugins/sentry.ts:50` 的 `ignoreErrors: ['Request aborted']` 因此无效 | API 方法透传 `signal`；`axios.isCancel` 短路 |
| E-05 | `api/request.ts:45-61, 182-215` | `isRefreshing` 仅单标签页单例，多标签页各自发起 `/auth/refresh`（同一 Cookie）。后端若用轮换/一次性策略，先成功者会踢掉其他标签页 | 用 `BroadcastChannel`（`stores/auth.ts:47` 已有通道）或 `navigator.locks` 做跨标签页互斥 |
| E-06 | `api/request.ts:299-308` | GET 去重 key 不含 `baseURL`/`responseType` → 同 URL 的 blob 与 json 请求共用 inflight Promise，拿到错误类型响应体 | key 加入 baseURL/responseType/data |
| E-07 | `api/request.ts:34-43` + `utils/authStorage.ts:100-116` | token 存 sessionStorage（**同样可被 XSS 读取**，注释称「缩小窗口」只缩短持久化时长）；且每请求都 base64 解码 + `JSON.parse` 整个 JWT payload | 短期内存 token + storage 仅兜底；进程内缓存 `{token, expMs}` |
| E-08 | `utils/authStorage.ts:49-86` | 客户端解析 JWT `exp` 判过期：不校验签名/算法；以本地时钟比较无 leeway（时钟快 → 刚登录就被登出）；`_isTokenExpired` 会**直接删除**凭证 | 只用于提前触发静默刷新，不用于删除决策；±60s leeway |
| E-09 | `utils/authStorage.ts:8, 75-78, 151-171` | `token_expiry` 机制是死代码（全仓无调用方传 `expiresIn`）；且写入不对称：有 token 无 expiresIn 时既不写也不清除旧值 → 未来一旦有人传，下次不传会留下上一个 token 的过期时间 → **首屏即被登出** | 显式清除或删除双轨机制 |
| E-10 | `utils/authStorage.ts:10-22, 32-37` | 存储可用性只探测一次，运行时失败全部写入被静默吞掉 → 用户以为登录成功，下次导航被踢回登录页，控制台与 Sentry 无痕迹 | 每次读写 try/catch + 首次失败降级上报 |
| E-11 | `utils/httpError.ts:32-42` + `errorPolicy.ts:20-30` | `getNetworkErrorMessage` **零调用**（唯一命中是定义处）→ ISS-106「网络错误映射为中文」从未生效，用户仍看到 `"timeout of 60000ms exceeded"` 英文原文，而 `request.ts:251` 注释声称已修复 | 在 `normalizeHttpError` 的 `status===0` 分支调用 |
| E-12 | `utils/exportUtils.ts:42-55` | CSV **表头**既未加引号、未转义、也未做公式注入防护（只有单元格做了）→ `label` 含 `,`/`"`/`\n` 会错位或注入行；以 `=cmd|'/C calc'!A1` 开头的 label 被 Excel 当公式执行 | 表头与单元格共用 `csvCell()` |
| E-13 | `utils/formatUtils.ts:5-23` | 日期格式化隐含本地时区：`'2026-10-01'` 按规范解析为 **UTC 午夜** → UTC-5 用户得到 9月30日（**差一天**）；`'2026-10-01T00:00:00'`（无 Z）又按本地解析 | 后端统一 ISO8601 带 offset；纯日期单独 `formatDateOnly()` 用 `slice(0,10)` |
| E-14 | `stores/layout.ts:7-19` | Pinia store **初始化同步路径**裸调 `localStorage`，无 try/catch → Safari 无痕/配额溢出抛 `SecurityError` → store 构造失败 → **应用首屏白屏**（`useTheme.ts:8-24`、`useOnboarding.ts:22-36` 都已保护，此处遗漏） | 统一 `safeLocalStorage` |
| E-15 | `router/index.ts:243-252` | `getStoredToken()` 返回空被无条件等价为「token 过期」。存储不可用时 `persistAuth` 静默丢弃但内存 ref 仍置 → 每次导航都命中该分支 → **无限跳登录页，用户完全无法使用系统** | 区分 `getStoredToken()` 与 `getStoreAvailable()`，给出明确提示 |
| E-16 | `router/index.ts:82-167` + `config/permissions.ts` | 大量路由只有 `role` 没有 `permissions`；`PAGE_PERMISSIONS` 中 7 个键**从未被任何路由引用**（`hasPermission` 唯一调用点是 `guard.ts:51`）→ 纯装饰性配置，维护者误以为已生效。高敏页 `admin/crisis-events` 无任何细粒度权限声明 | 补齐 permissions + 加静态检查 |
| E-17 | `router/index.ts:77-80` | 根路由 `/` 无 redirect 也无空 children → 登录后访问 `/` 渲染 MainLayout 但 `<router-view>` 为空，用户看到「半白屏」 | `{ path: '/', redirect: () => resolveRoleHome(role) }` |
| E-18 | `stores/auth.ts:156-177` | 登出清理靠动态 import，失败被 `catch {}` 静默吞掉不上报；而 `restore()` 只重读 token/user，**完全不触碰** taskProgress/analytics → 注释所说「兜底」不存在。后果：A 登出 B 登录后 `taskProgressMap` 仍保留 A 的任务（含 job_id/下载链接），`_consented` 沿用 A 的同意状态 → **跨用户数据泄漏 + 隐私同意冒用** | 静态导入或内联兜底；`login()` 同样全量 reset |
| E-19 | `composables/useWebSocket.ts:58-80` | WS 去重 fallback key 在无 `warning_id` 时按 `type:user_id:created_at:risk_level:trigger_reason` 去重 → 同一用户同一秒批次生成的多条预警被判定重复**静默丢弃**（恰是高强度/多因子场景）。叠加 E-01 形成「既不重连、又去重」双重漏报 | 缺 `warning_id` 时降级为「保留但不去重」 |
| E-20 | `composables/useWebSocket.ts:113-120` | 注释称「userId 不放 URL 避免被日志记录」，改放 **query string** —— query 与 path 一样会被 nginx/ALB/CDN access log 完整记录，修改未达成目标 | 从 URL 移除，改在 onopen 的 auth 帧发送 |
| E-21 | `composables/useAnalytics.ts:42-43` 等 | 硬编码 `/api/v1/...` 绕过 `API_BASE_URL`；`.catch(() => {})` 完全静默 → 跨域部署时埋点全部 404 且无监控信号 | 用 `buildApiUrl()` |
| E-22 | `composables/usePerformanceMonitor.ts:330-346` | 卸载时 Beacon 上报**无法携带 Authorization**，而 `useAnalytics.ts:106-111` 的注释已明确否决该方案（要么被 401 丢弃，要么成为无鉴权写入通道） | 改用 `fetch(keepalive: true, headers)` |
| E-23 | `plugins/sentry.ts:10, 70-80` + `main.ts:12-14` | `main.ts` 注释称「空实现缓冲」—— 实为 `() => {}` **直接丢弃**。Sentry 延迟到 mount 后加载，恰恰是首屏最关键的 chunk 解析/hydration 错误全部丢失 | 实现真缓冲队列或提前同步加载 |
| E-24 | `main.ts:29-44, 73` | 未 `await router.isReady()` 即 `mount`，首屏 mount 与初始导航并发，401 的 `router.replace` 可能被覆盖，且 `isUnauthorizedRedirecting` 已被置位 → 一段时间内合法 401 跳转被抑制 | `await router.isReady()` 后再 mount |
| E-25 | `api/request.ts:159-163` | 任何成功响应都复位 `isUnauthorizedRedirecting`，而 `router.replace` 是异步的 → 期间并发成功请求会复位标志，下一个 401 重复提示+重复导航 | 改用时间戳一次性 guard |
| E-26 | `api/adminApi.ts:99-119`、`reportsApi.ts:69-89`、`gdprApi.ts:18` 等 | Blob 导出把 403/500/401 的 JSON 错误体当作文件下载，`res.data as Blob` 无校验 → 用户下载到内容是 `{"detail":"无权限"}` 的「.pdf」，界面却提示导出成功 | 统一 `requestBlob()`：检查 content-type，否则 parse 错误并 reject |
| E-27 | `api/request.ts:176-180` | 401 透传白名单硬编码 regex，依赖相对 url；任何新增以 401 表达业务错误的端点都会被误判为会话过期触发强制登出 | 下沉为 API 声明能力 |
| E-28 | `api/request.ts:310-334` | 猴子补丁 `instance.request`，运行时验证（axios 1.20.0）显示快捷方法绑定到内部 `context` 而非 `instance` → **当前行为是偶然正确**，axios 升级后所有 `request.get()` 会被静默去重 | 改显式包装函数 + ESLint 约束 |
| E-29 | `stores/loading.ts:20-43` | 计数无超时兜底，`setGlobalLoading(false)` 无法清除未配对的 `loadingCount` → 视觉永久转圈且无法关闭 | 提供 `resetLoading()` + 超时自动释放 |
| E-30 | `composables/useTaskProgress.ts:31-50, 95-112` | 每 5s 对每个 running 任务各发一个请求（20 任务 = 每 5s 20 请求），无 AbortController 无退避；每次更新 `new Map()` 全量复制触发 3 个 computed 全量过滤 | 改 `reactive(Map)`；改用批量端点 |
| E-31 | `config/permissions.ts:3-59` | 权限矩阵是后端 `PERMISSION_MATRIX` 的**手工镜像**，无法感知后端语义漂移；叠加纯前端校验（role 来自可篡改的 localStorage）收益/成本比偏低 | 由 `/auth/me` 下发 effective permissions 作唯一真源 |

## 轻微（模式级）
- **注释与实际行为不符**（本模块最高频）：`request.ts:251`（声称已映射中文，函数零调用）、`useWebSocket.ts:115`（声称避免日志，query 照样进日志）、`main.ts:13`（声称缓冲，实为丢弃）、`plugins/sentry.ts:16`（`console.warn` 被生产 esbuild drop）、`authStorage.ts` 的 `token_expiry` 死代码。**根因：注释写得比验证充分**。
- **同一逻辑多处实现且漂移**：错误提取（`httpError.normalizeHttpErrorInfo` vs `errorDetail.getErrorDetail`）、CSV 转义（`exportUtils` vs 3 处 view 手写）、类型（`ActiveIntervention`/`InterventionHistoryItem`/`UserManageItem`/`WARNING_STATUS`/`PageResult` 各两份）、API（`modelApi` vs `userRiskApi`、`reportsApi` celery 变体）。
- **静默失败路径**：`catch {}` 在心理健康场景下直接转化为业务风险（`auth.ts:156`、埋点、性能上报、存储降级）。
- 跨用户/跨标签页状态隔离不彻底：登出漏清 `inflightRequests`、`unreadWarningCount`、`onboarding`、`loadingCount`；BroadcastChannel 只广播 token 不广播 user（角色不一致窗口）；onboarding key 按 role 而非 userId 隔离（第二个同角色用户永远看不到引导）。
- `plugins/sentry.ts:45-52` 的 `ignoreErrors` 含 `'Network Error'` 会过滤掉真实网络故障，另两项无效。
- `base.ts:1-6` 未规范化 `VITE_API_BASE_URL` 尾斜杠 → `//path` 双斜杠。

---

# 六、前端业务组件（views 181 / components 40）

## 严重

### F-01 `probability` 为 null 时整棵结果卡白屏，且注释自承「此处是遗漏」却只修了相邻字段
`frontend/src/views/user/components/TextAssessTab.vue:217-227`

```vue
<!-- SEC-FIX-2026-10-05: ... 下方 246/252 行本就做了 != null 防御，此处是遗漏。 -->
<p>{{ (textPredictResult.probability * 100).toFixed(2) }}%</p>                                    <!-- 225 未修 -->
<p>{{ textPredictResult.sentiment_score != null ? textPredictResult.sentiment_score.toFixed(2) : '-' }}</p>  <!-- 227 已修 -->
```
> 已复核：注释明确写「此处是遗漏」，225 行确未修。
**后果**：模型回退路径返回 `probability: null` 时 `null.toFixed` 抛 TypeError → 渲染中断，用户刚提交的结果卡消失。心理健康场景下用户会重复提交。
**建议**：225 行加 `!= null` 兜底；把格式化收敛到 `utils/riskFormatters` 统一做 null 处理。

### F-02 `LazyImage` 的 IntersectionObserver 在卸载时永不释放（内存泄漏）
`frontend/src/components/common/LazyImage.vue:224-230, 265-270`

```ts
const handleRetry = () => { ...; setupObserver() }        // 重建，旧的没 disconnect
onUnmounted(() => {
  if (observer && containerRef.value) {                    // Vue 3 在 unmount 阶段先把 ref 置 null
    observer.unobserve(containerRef.value); observer.disconnect()
  }
})
```
`containerRef.value` 在 `onUnmounted` 内**恒为 null** → `disconnect()` 永不执行。每个未进视口就卸载的实例残留一个 observer 持有已脱离文档的 DOM 节点。
**建议**：`onUnmounted(() => { observer?.disconnect(); observer = null })`；`setupObserver` 开头先 disconnect 旧的。

### F-03 9 个统计卡片统一 `page_size: 200` 拉全量到前端做统计 —— 性能 + 统计口径双错
命中（同一模式 9 处）：
```
views/user/components/user-intervention/InterventionStatsCard.vue:75
views/user/components/user-assessments/AssessmentsStatsCard.vue:118
views/user/components/user-warnings/WarningStatsCard.vue:103
views/counselor/components/counselor-warnings/CounselorWarningStatsCard.vue:96
views/counselor/components/counselor-users/UserOverviewStatsCard.vue:101
views/admin/components/admin-crisis-events/CrisisEventStatsCard.vue:85
views/admin/components/admin-alerts/AlertStatsCard.vue:94
views/admin/components/admin-silences/SilenceStatsCard.vue:67
views/admin/components/admin-operation-logs/OperationLogStatsCard.vue:85
```
```ts
const data = await userApi.getUserWarnings({ page: 1, page_size: 200 })
const items = data.items || []
stats.total = data.total ?? items.length                                   // 分母用服务端总数
stats.highRisk = items.filter(i => normalizeWarningRiskLevel(i.risk_level) === 3).length   // 分子只覆盖前 200
```
**后果**：每页打开都传 200 条完整记录（含正文）做 5 次全量 filter；数据超 200 条时**分子截断、分母不截断 → 统计结果是错的**。
**建议**：后端提供 `/stats` 聚合端点（本仓 `counselorApi.getReviewStats()` 已是正确范例）；前端抽 `useStatsCard()`。

### F-04 导出无上限全量翻页
`frontend/src/views/user/UserAssessmentsPage.vue:286-320`

```ts
const exportPageSize = 100; let currentPage = 1
do { const data = await ... ({ page: currentPage, page_size: exportPageSize, ... }); ... } while (...)
```
无总量上限、无中断机制、无进度反馈，只锁了按钮。数据量大时发出成百上千个串行请求，中途失败前功尽弃。
**建议**：改后端流式导出（`AdminOperationLogsPage` 已有先例）；前端至少加 `total` 上限 + 进度 + AbortController。

### F-05 `CounselorReviewDetailPage` 请求失败时永久显示骨架屏
`frontend/src/views/counselor/CounselorReviewDetailPage.vue:163-167, 193-200`

```vue
<el-card v-if="review">...</el-card>
<SkeletonScreen v-else :rows="10" variant="text" />
```
`v-else` 把「加载中」与「加载失败/ID 非法」混为一谈。失败后 `review` 保持 null → 永远停留在骨架屏，只有一个一闪而过的 Message。`Number(route.params.id)` 为 NaN 时同样落此死状态。
**后果**：咨询师看不到危机复核任务详情，也无法重试。
**建议**：引入 `loadError` ref，`v-else-if` 走错误态 + 重试；`Number.isFinite(id)` 前置校验。

### F-06 `ExperimentTab` 的 `confusion_matrix` 未判空 + 结果处理重复
`frontend/src/views/user/components/ExperimentTab.vue:288-306, 362-387`

```ts
const cm = res.confusion_matrix
confusionMatrix.value = { tn: cm.tn, fp: cm.fp, fn: cm.fn, tp: cm.tp }     // cm 为 null 即 TypeError
experimentSummary.value = { ..., val_accuracy: res.metrics.accuracy, ... } // 无 ?.
```
而调用方 377 行却写了 `res.metrics?.accuracy` —— 同一字段两套防御标准。`confusion_matrix` 为 null 时被 `try` 吞成一条「评估失败」，掩盖真实原因。
**建议**：统一 `?? {}` / `?.`，删除 374-379 行的重复赋值。

## 中等（精选）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| F-07 | `experiment-charts/EvalResultCard.vue:198-200` | `role === 'admin' \|\| role === 'counselor'` **漏了 super_admin**（`permissions.ts:58` 定义 super_admin 为权限最高角色）→ super_admin 看到的比 admin 少，权限模型自相矛盾 | 抽 `isAdminRole()`/`isStaffRole()` |
| F-08 | 5 处：`AdminOperationLogsPage.vue:225`、`AdminAuditLogsPage.vue:275`、`CounselorDashboard.vue:239-240`、`CounselorUsersPage.vue:218`、`UserAssessmentsPage.vue:190` | `const canXxx = hasPermission(auth.role, '...')` 在 setup 顶层直接读 → **不建立响应式依赖**，角色变化后 UI 停在旧权限状态（对比 `UserRiskPage.vue:199` 用了 computed，同仓两种写法） | 统一 `computed(() => hasPermission(...))` |
| F-09 | `components/common/ActionColumn.vue:55-97` | `confirmText` 默认 `'确定'`（truthy）→ **任何未显式传参的 ActionColumn 都弹二次确认**，且内容显示「确定」毫无信息量。「编辑」「查看详情」等只读操作被无故拦截 | 默认值改 `''`（传了才确认） |
| F-10 | `views/counselor/CounselorDashboard.vue:200-217` | 快捷操作区两个按钮完全无权限门控（同文件 Hero 卡和副卡都做了 `v-if`），门控不一致 | 补齐 `v-if` |
| F-11 | `views/login/LoginPage.vue:310-320` | redirect 校验未要求以 `/` 开头、未拦 `javascript:`/`data:`、未按角色校验目标域（普通用户可构造 `?redirect=/admin/dashboard`） | 白名单 `startsWith('/') && !startsWith('//')` + 角色域一致性 |
| F-12 | `views/login/LoginPage.vue:331-351, 357-377` | `loading.value = true` 在 `await validate()` **之后**，两次点击/回车+点击会各自发起 login → 重复登录请求 | loading 提到函数最开头 |
| F-13 | `CounselorReviewListPage.vue:67-77`（及 `CounselorUsersPage.vue:284-287`） | 「查询」按钮不重置页码 → 第 5 页改筛选后仍查第 5 页，返回空列表，用户以为没数据 | 查询前 `page.value = 1` |
| F-14 | `CounselorReviewListPage.vue:305-323` 等 5+ 处 | 列表请求无竞态保护（无 seq / AbortController），旧响应覆盖新数据。而 `useUserContentData.ts:127-142` 已写了正确的 `requestSeq` 模式，**只在 1 个文件用了** | 推广 `requestSeq` |
| F-15 | `CounselorUserDetailPage.vue:359-406` | `saveConsultation` 校验失败直接 `return` 无提示（模板还标了 required）；`saveGroup` 完全无校验；`addCurrentUserToGroup` 无 loading/行级锁 → 连点重复加 | 走 `el-form` rules；加 `rowPendingIds` |
| F-16 | `CounselorUserDetailPage.vue:286-295` | 一行塞 4~5 个声明（`computed` 与 `ref` 混排）；`Number(route.params.id)` 无 NaN 守卫，NaN 直接进请求 | 拆行；`Number.isFinite` 校验 |
| F-17 | `RiskReportTab.vue:134-140` + `:4` | `sortable="custom"` 无 `@sort-change` handler，同时列级 `sortable` + `sort-method` → 两套机制冲突，**点击表头排序无反应**；`:empty="false"` 硬编码 + `v-if="report"` → report 为 null 时整页完全空白无空态 | 去掉 `sortable="custom"`；`:empty="!loading && !report"` |
| F-18 | `RiskStatusCard.vue:66-78`、`CounselorReviewDetailPage.vue:48-52` | `risk_score` 直传 CountUp `:end` 与 `el-progress :percentage`，为 null 时渲染 `NaN` | `?? 0`；CountUp 内部 `Number.isFinite` 兜底 |
| F-19 | `UserRiskPage.vue:295-301, 336` | `autoFusionReady` 一旦置 true **永不重置** → 用户在文本页第二次提交会被**强行切到融合 Tab**，打断操作 | 加 `hasAutoFused` 只触发一次，或改 Toast 提示 |
| F-20 | `user-settings-page/FileUploadCard.vue:46-58, 184-200` | `accept` 只是选择框过滤提示；`auto-upload=false` 且无 `before-upload` → **扩展名从未被校验**，任意类型（含 .exe）直接上传。大小校验做了，类型遗漏 | 提交前按白名单过滤扩展名 |
| F-21 | `PhysioTab.vue:284-286, 343, 361` | `savePhysioHistory()` 在 try 块内无保护，sessionStorage 配额溢出抛错 → **服务端已写入成功**却提示「记录失败」，用户重复提交 | 本地持久化单独 try/catch 降级 |
| F-22 | `experiment-charts/MisclassifiedTable.vue:138, 204-208` | `kind === 'all'` 的「导出全部」实际取 `pagedSampleRows`（当前页 5 条） | 改 `filteredSampleRows` |
| F-23 | `experiment-charts/MisclassifiedTable.vue:156-161` | CSV 只转义双引号，漏 `sanitizeCellForExcel`（其余 5 处都做了） | 复用 `exportToCSV` |
| F-24 | `AdminReportsPage.vue:51-58`（同 `GdprTab:216`、`TaskProgressNotification:170`） | `URL.revokeObjectURL` 同步执行 → 大文件/Safari 下载中断或 0 字节。同仓四种实现（同步/延迟 1000ms/exportUtils/…） | 统一 `utils/download.ts` |
| F-25 | `AdminReportsPage.vue:206-220` | 同步/异步两个生成按钮共用 `generating`，互相阻塞；`generateAsync` 启动轮询后立即置 false，此时又可点同步 → 两个 PDF 任务并发 | 拆 `syncGenerating`/`asyncGenerating` |
| F-26 | `AdminReportsPage.vue:27-37` | `trendText` JSON 解析失败静默置空无提示；`excelFilename` 用户可任意输入直接用于 `a.download` 与后端参数，无分隔符/长度校验 | catch 里提示；文件名加正则校验 |
| F-27 | `AdminObservabilityPage.vue:49-73` | `loadAll` 无 in-flight 守卫（8 个请求响应交错覆盖）；`toggleAutoRefresh` 未先 clear 已有 timer → 引用覆盖泄漏；`onUnmounted` 未置 null；`:43` 硬编码英文 `'error'` | 加守卫 + `stopTimer()` 前置 + i18n |
| F-28 | `admin-settings-page/SecurityTab.vue:86-104` | `Promise.all` 部分成功：前面已写入后端但整体提示「保存失败」→ 安全配置处于部分生效的不一致状态；`deep: true` 监听 configs，父组件 reload 后会**覆盖用户刚改未保存的值** | `allSettled` 逐项汇报；watch 改为只在 configs 从空变非空时同步 |
| F-29 | `components/common/PageTable.vue:82-145` | ① `deep: true` 监听整个列表 + 行 key fallback 是 `JSON.stringify(row)`（100 行 ×20 字段每次刷新几千次属性访问 + 整行序列化）；② MutationObserver `subtree: true` 观察表头子树，排序/滚动/悬浮每次 style 变更都**同步** `localStorage.setItem` + `getComputedStyle`（强制 reflow） | 行 key 改 prop 必传；watch 改浅监听；observer 回调 200-300ms 防抖 |
| F-30 | `UserAssessmentDetailPage.vue:104-139, 167-175` | 评估详情（含用户填写的原文 + 风险评分）写入 sessionStorage（同文件自己已意识到生理数据敏感才用 sessionStorage，此处把**更敏感**的数据也放了）；`window.history.length > 1` 是整个标签页的，用户先访问别的网站再进应用时 `router.back()` 可能**跳出应用** | 详情载荷只在内存传递；`goBack` 用固定 `router.push` |
| F-31 | `ResetPasswordPage.vue:145-149` | reset token 通过 URL query 传入，提交后/使用后未清除 → 进入浏览器历史、Referer、前端日志 | 读取后立即 `router.replace({ query: {} })` |
| F-32 | `ExperimentTab.vue:336-345` | `bertDisabled = true` 是常量 → `trainBert`/`evaluateBert` 函数体（~40 行）**完全不可达的死代码**；`:74-104` 导入/对比按钮无 `:disabled="experimentLoading"` | 真正移除或改为能力探测 computed；按钮统一 disabled |
| F-33 | `StructuredAssessTab.vue:246-259` | `handleStepNext` 的 `else` 分支永不执行（按钮 `v-if="structuredStep < 3"`）；`formRef?.validate()` 在 ref 未挂载时返回 undefined，`.catch` 不触发 → 掩盖真实问题 | 删死分支；显式判空 |
| F-34 | `CounselorReviewDetailPage.vue:220/240` | 把「用户取消确认框」与「API 失败」塞进同一 catch，靠 `error === 'cancel'` 字符串比较，Element Plus 升级易失效 | 用 `.then/.catch(() => {})` 分离写法 |
| F-35 | `user-model-training/TrainingRegistryCard.vue:223-227` | `row.metrics` 未判空（同文件 230-238 的 `shadowTotal`/`shadowRate` 都做了保护）→ 整行渲染失败 | `const m = row.metrics ?? {}` |
| F-36 | `layouts/MainLayout.vue:66, 184-186, 197-200` | `onMounted` 的 500ms `setTimeout` 未保存 id 也未清理；`keep-alive` 缓存三个设置页 → 不重新 onMounted，其 `deep: true` 自动保存 watch 在后台仍跑，切回来展示缓存旧配置 | 保存 timer id 清理；缓存页用 `onActivated` 刷新 / `onDeactivated` 停轮询 |

## 轻微（模式级）
- **空 catch 静默吞错 ≥7 处**：`CounselorDashboard.vue:254`、9 个 StatsCard、`TrainingRegistryCard.vue:276/298/316`、`AdminReportsPage.vue:33` → 失败显示全 0，与「真的 0 条」无法区分。
- **数值字段未判空直接 `.toFixed()` / 传 progress**：`TextAssessTab:225`、`RiskReportTab:20`、`RiskStatusCard:67/73`、`CounselorReviewDetailPage:49`、`TrainingRegistryCard:226` → TypeError → 白屏。
- **Blob 下载 6 处 4 种实现**（另加 `exportToCSV` 共 7 种）。
- **列表页骨架 12 处重复**（loading + 分页 + 筛选 + 错误态，每页约 60 行）→ 抽 `useListQuery()` 可消除全仓约 700 行重复。
- **管理员角色判断 8 处重复 + 1 处遗漏**。
- **风险等级/状态映射四件套 100% 重复**：`CounselorReviewListPage.vue:406-458` 与 `CounselorReviewDetailPage.vue:249-301` 逐行相同，另有 `CounselorUsersPage.vue:235-245` 第三份变体。
- 中英文混用/硬编码中文：`ActionColumn.vue:45,73-75`、多处 `console.error('[StructuredAssess] ...')` / `console.warn('结构化...')`。
- 魔法数字：`page_size: 100/200`、`slice(0, 20)`、`shadowRate >= 0.75`、500ms、`24*3600*1000`。
- `LoginPage.vue:21-23`：`isLogin ? t('auth.brandLoginLede') : t('auth.brandLoginLede')` 三元两分支相同，注册页显示登录文案（复制粘贴漏改）。
- **正面**：全仓 `v-html` 仅 1 处（`ContentDetailDialog.vue:43`），已 DOMPurify 白名单净化。

---

# 七、整体质量评估

## 7.1 总体判断

这是一个**经过了多轮系统性安全加固的中大型全栈项目**（抑郁/心理健康风险预测 + 咨询师复核 + 危机干预），工程水位明显高于同规模毕业设计或原型项目。证据充分：

**做得好的方面（真实存在，非客套）**
1. **NaN/非有限值防护已成体系**：`risk_thresholds.ensure_finite_score` → 各推理出口 `math.isfinite` 拦截 → 回退层 `_finite()`/`_clamp_score()` 三层闭环，每处附实测证据注释。说明团队是真验证过失效模式才修的。
2. **反序列化安全闭环**：`safe_pickle.py`「路径白名单 + 大小上限 + SHA256 侧车 + 类白名单 Unpickler + 生产强制 weights_only/hash + fail-closed 不退回裸 joblib」，全项目 4 个加载点无一裸调用 —— 中型项目里少见。
3. **注释驱动的三段式修复文化**：`ISS-xxx / SEC-FIX / AUDIT-2026-10-xx / M-xx / P1-SEC-xxx` 编号齐全，「原实现缺陷 → 修复方案 → 取舍说明」完整，排障价值极高。
4. **ML 工程规范**：`DataCleaner` fit/transform 分离、每 fold 独立 fit scaler + 独立 SMOTE 种子、跨数据集填 NaN、nested_cv 早停集切分 —— 数据泄漏防护到位。
5. **阻塞 IO 卸载**：`asyncio.to_thread` 覆盖 sklearn 推理、HTTP 请求、模型 preload、通知发送。
6. **限流/时间窗/分页护栏**在大部分端点已落地；前端 XSS 面极小（全仓 `v-html` 1 处且已净化），开放重定向已闭环，CSV 公式注入防护大部分已做。

## 7.2 系统性风险（比单点 bug 更值得关注）

| 风险 | 说明 | 影响 |
|---|---|---|
| **① 租户隔离是逐函数手工实现，因此必然漏** | `core/deps.py` 已在入口做了「请求租户 == 用户租户」校验，但**对象级（行级）隔离无框架保障**，靠每个服务函数自己写 `tenant_scoped_filter`。结果：`review_service.py` 全文 `tenant` 出现 1 次；`counselor_service_user.get_user_detail` 有列表无详情；`analytics_events` 连入口校验都绕过。**最典型的是 `review_service.py:375-389` 作者为一处写了详尽注释解释为何必须 JOIN User，却在同类相邻三个方法里完全忘记** —— 问题不是认知不足，是缺不可绕过的机制 | 严重：跨租户数据泄露 + 可篡改 |
| **② 同一模式复制 N 份后各自漂移** | 熔断器 init（4 份，1 对 3 错）、危机词表（2 套结论可能相反）、风险等级标签（`low/medium` vs `mild/moderate`）、模型元数据（3 份）、角色定义（2 套）、文件名清洗（3 份，长度限制只修了 1 份）、CSV 转义（1 处表头漏）、Blob 下载（7 种） | 中~严重：同一个 bug 修了三分之一，后续必再犯 |
| **③ 「静默降级」被过度应用成「失败不留痕」** | `ws.py` Redis 发布失败 `logger.debug`、`fusion.py` 吞模态异常、`event_bus` 队列满丢弃、`pii_crypto` 解密失败返回占位串、多个 Celery 任务 `return {"status":"failed"}` 被记 SUCCESS、前端 `catch {}` 7+ 处。**正确原则（旁路失败不影响主流程）被误用为（失败不留痕）** | 严重：在心理健康场景直接转化为漏预警 |
| **④ 注释与实现不符** | `metrics_helpers` 硬编码假指标、`review_service` 声称截断没截、`shadow_mode_service` 声称读 config 实为硬编码、`pdf_report_service` 声称校验 charts 实际不渲染、前端 `getNetworkErrorMessage` 零调用、`main.ts` 声称 Sentry 缓冲实为丢弃。**比缺少注释更危险** —— 维护者会基于错误前提做决策 | 中~严重 |
| **⑤ 事务约定两派并存 + 隐式契约** | 「服务层 flush、调用方 commit」与「服务层自管 commit」并行；「业务 commit + 审计第二次 commit」违反 ADR-012 | 中等：审计可丢、状态可半写 |
| **⑥ 前端权限模型收益/成本比偏低** | `config/permissions.ts` 是后端矩阵的**手工镜像**（无法防语义漂移）；多数路由只配 `role` 不配 `permissions`（7 个 permission 键从未被引用，纯装饰）；`role` 来自可篡改的 localStorage；`ExperimentTab` 还漏了 super_admin | 中等：维护成本 > 实际收益 |

## 7.3 分模块评分（主观，10 分制）

| 模块 | 安全 | 正确性 | 性能 | 可维护性 | 说明 |
|---|---|---|---|---|---|
| `backend/app/core` | 7 | 7 | 6 | 7 | 加固痕迹最重（`safe_pickle` 优秀），但复制漂移与静默降级问题集中 |
| `backend/app/api` | 6 | 7 | 7 | 7 | 无裸 SQL/命令注入（优秀），**租户隔离是最大短板** |
| `backend/app/services` | 7 | 6 | 6 | 8 | 注释密度最高质量最好，事务与分页约定不统一 |
| `ml/ models/ schemas/ tasks/` | 6 | 6 | 6 | 7 | ML 工程规范好，但两套并行实现 + 定时任务「静默停止」风险 |
| 前端基础设施 | 7 | 7 | 7 | 7 | 请求层设计完整，但缺取消/竞态治理，注释与实现不符偏多 |
| 前端业务组件 | 8 | 6 | 5 | 6 | XSS 面极小（优秀），但列表页重复度高、null 防御不彻底、统计口径错误 |

**总体**：工程能力扎实、安全意识到位，当前主要风险不在「会不会写」，而在**「同一件事做了 N 份且各自漂移」**和**「降级路径不留痕」**。

---

# 八、优先整改项

## P0（立即修，涉及数据安全 / 核心功能静默失效）

| # | 问题 | 位置 | 修复成本 |
|---|---|---|---|
| 1 | 危机事件 3 个流转端点 + `get_review_by_id` 全链路加租户谓词 | `api/v1/review.py:175-426` + `services/review_service.py:161-214, 435/472/507` | 低 |
| 2 | **fire-and-forget 移到 `commit()` 之后**（当前中高风险学生的预警+干预被静默丢弃） | `services/risk_service_assessment.py:236` → 移到 `:256` 之后 | **一行** |
| 3 | 密码重置令牌加 `jti` 一次性核销 + 重置后撤销 access token | `services/auth_service.py:319-347` | 低（复用已有 `revoke_token`） |
| 4 | PDF 报告全部用户可控文本 XML 转义（含 `&` 即整体生成失败） | `services/pdf_report_service.py:166/188/198/229` + `:322/344/354/385` | 低 |
| 5 | `_ML_QUALITY` 硬编码假指标改为真实数据或停止上报 | `api/v1/metrics_helpers.py:26-77` | 中 |
| 6 | `ws.disconnect()` 改 async + 加锁 | `core/ws.py:94-106` | 低 |
| 7 | 三个 breaker 的 `init_*` 改 `configure()` 就地更新 | `core/ml_breaker.py:129`、`celery_breaker.py:175`、`smtp_breaker.py:135` | 低 |
| 8 | 实验产物清理保护集兼容目录型模型（否则会物理删除在服模型） | `tasks/scheduler.py:984-1023` | 低（改前缀匹配） |
| 9 | `stale_warning_reminder` 补真实提醒动作（当前是空任务） | `tasks/scheduler.py:401-432` | 中 |
| 10 | 训练任务端点权限收紧 + `FusionPredictRequest` 补 `max_length` | `api/v1/model_predict/status.py:68-88`、`schemas/model_predict.py:99-102` | 低 |

## P1（本迭代修）

| # | 问题 | 位置 |
|---|---|---|
| 11 | 前端 WS 重连达上限后永久放弃 → 加 `online`/`visibilitychange` 监听 + 低频无限重试 | `composables/useWebSocket.ts:234-251` |
| 12 | 写操作 401 自动重试 → 仅安全方法重试，加幂等键 | `api/request.ts:182-215` |
| 13 | `TextAssessTab:225` `probability` null 白屏 | `views/user/components/TextAssessTab.vue:225` |
| 14 | `LazyImage` observer 永不释放 | `components/common/LazyImage.vue:265-270` |
| 15 | 9 个 StatsCard `page_size: 200` → 后端 `/stats` 聚合端点 | 9 个 `*StatsCard.vue` |
| 16 | `add_group_member` 改 `begin_nested()` savepoint | `services/counselor_service_group.py:126-131` |
| 17 | `validation_engine` 的 `asyncio.gather` 加 Semaphore + 分批 | `services/validation_engine.py:374-375` |
| 18 | `fuse()` 拦 NaN（当前会静默判为满级高风险） | `ml/fusion_engine.py:166-170` |
| 19 | `pytorch_mlp` 架构元信息改 JSON 侧车（当前生产 100% 不可用） | `ml/pytorch_mlp.py:226-252` |
| 20 | uploads 下载加 `Content-Disposition: attachment` + `nosniff` | `api/v1/uploads.py:270-300` |
| 21 | `operator_role="admin"` 硬编码 → `current_user.role`（约 10 处） | 多文件 |
| 22 | 14 处 `offset = (page-1)*page_size` 缺下界校验 → 抽公共 `paginate()` | services 多文件 |
| 23 | GDPR 导出 7 个 `iter_*` 加 `ORDER BY`（当前可能漏行，合规实质缺陷） | `services/gdpr_service_export.py:263-279` |
| 24 | `anomaly_detection_service` 三处循环内 N+1（单次最多 ~700 往返） | `services/anomaly_detection_service.py:134/318/410` |
| 25 | `crisis_export_service` aware/naive 时区不一致 | `services/crisis_export_service.py:85-86` |
| 26 | `experiment_data` 数据集缺失时禁止静默生成合成数据 | `services/experiment_data.py:36-40, 81-83` |
| 27 | 前端 `Promise.finally` 悬垂拒绝（Sentry 噪音）+ 引入 AbortController | `api/request.ts:325-333` |
| 28 | 前端 `layout.ts` localStorage 无保护导致白屏 / 存储不可用时被永久踢登录 | `stores/layout.ts:7-19`、`router/index.ts:243-252` |
| 29 | 前端 CSV 表头公式注入 + 转义 | `utils/exportUtils.ts:42-55` |
| 30 | 前端 `getNetworkErrorMessage` 零调用 → 网络错误中文映射失效 | `utils/errorPolicy.ts:20-30` |

## P2（后续优化，消除系统性根因）

| # | 事项 |
|---|---|
| 31 | **租户隔离机制化**：给 `ReviewTask`/`CrisisEvent` 等统一封装 repository，或在查询层让缺约束的查询直接报错（项目对 `TenantColumnMissingError` 已有同类做法） |
| 32 | **指定 SSOT 并 re-export**：危机词表、风险等级标签、模型元数据、角色定义、文件名清洗、CSV 转义、Blob 下载 —— 每类指定唯一来源，其余 re-export，CI 加重复检查 |
| 33 | **统一审计 helper**：`_audit(db, request, actor, action, target, detail)`；写操作同步落、读操作改异步队列；`ip_address` 与 `tenant_id` 归属规则统一 |
| 34 | **统一错误信息方言**：引入 `ServiceError(client_message, internal_detail)`，中间件层最后一道脱敏路由 |
| 35 | **静默降级治理**：所有 `except → logger.debug/continue/return` 必须留 metric；所有 Celery 任务失败必须 `raise`（对齐 `alerts.py:59-69`） |
| 36 | 前端抽 `useListQuery()` composable（内置竞态守卫 + 页码重置 + 三态），覆盖 12 个列表页，预计消除约 700 行重复 |
| 37 | 前端抽 `isAdminRole()`/`isStaffRole()`；路由 `permissions` 补齐 + 静态检查 |
| 38 | 注释与实现一致性核查：把「注释所述行为必须有测试或调用点」固化为检查项 |
| 39 | 删除死代码：`ExperimentTab` 的 `bertDisabled` 分支、`exportUtils` 之外的重复实现、`observability_service._flushed_buffer` |
| 40 | 契约测试：`render_prometheus_rules()` 用 `promtool check rules` 校验；`render_exposition()` 用 `prometheus_client.parser` 校验 |

---

# 附：主审二次复核清单

以下「严重」结论已由主审直接读取源码复核，**证据确认无误**：

| 结论 | 复核位置 | 结果 |
|---|---|---|
| A-01 危机事件三端点无租户隔离 | `backend/app/api/v1/review.py:175-251` | ✅ 确认三个端点均未传 `tenant_id`，而 `:168` 传了 |
| B-01 `ws.disconnect` 同步无锁 | `backend/app/core/ws.py:94-106`（对照 `:52-92` 的 `async with self._lock`） | ✅ 确认为 `def` 且无锁 |
| C-01 重置令牌非一次性 | `backend/app/services/auth_service.py:319-347` | ✅ 确认无 jti 吊销/used 标记/消费动作 |
| C-02 fire-and-forget 在 commit 前 | `backend/app/services/risk_service_assessment.py:236` vs `:256` | ✅ 确认调度在 `await self.db.commit()` 之前 |
| D-01 产物清理保护集对目录失效 | `backend/app/tasks/scheduler.py:984-1023` | ✅ 确认收集路径、比对文件，且 `is_file()` 过滤 |
| F-01 `probability` 未判 null | `views/user/components/TextAssessTab.vue:217-227` | ✅ 确认注释自承「此处是遗漏」，225 行未修而 227 行已修 |

其余条目来自 6 路子审的逐文件 Read/Grep 取证，均附文件与行号，建议按 P0/P1 顺序逐条落地时自行复核。

---

# 附：P1 整改追记（2026-10-13，第二轮）

> 本节为**追加快照**，不修改上文任何既有表格与结论（上文是 2026-10-11 的历史记录）。
> P0 全部 10 项已于前一轮闭环；本轮处理 P1 中「真实风险 + 小改动 + 可客观断言」的 4 项。
> 闸门文件：`backend/tests/test_p1_audit_2026_10_13.py`（20 条，每项均做过回退红信号对照实验）。

## P1-18 `fuse()` 拦非有限值 —— 实测比报告写的更严重

报告原文只说「NaN 会静默判为满级高风险」。实测（`_tmp_nan_probe.py`，2026-10-13）确认是**双向**错判：

| 输入 | 改前 `risk_score` | 改前 `risk_level` | 临床含义 |
|---|---|---|---|
| `NaN` | 100.0 | 4 | **满级危机**（假阳性） |
| `+Inf` | 100.0 | 4 | 满级危机 |
| `-Inf` | 0.0 | 0 | **无风险**（假阴性，更危险） |

成因链（已在闸门里固化为断言）：NaN 比较恒为 False → `raw_fused < 0 or > 100` 不告警 →
`min(100.0, nan)` 保留 100.0 → `_score_to_level` 里的 `ensure_finite_score` 拿到的是**已裁剪的
有限值**，永远拦不到原始 NaN。⇒ **「下游拦不住」的典型：守卫位置比守卫存在与否更关键。**

修复：在 `fuse()` 输入校验处提前拦（`app/ml/fusion_engine.py`），复用既有
`NonFiniteRiskScoreError`，与 AUDIT-2026-10-08 (P0-5)「提前显式拦截、让失效原因如实反映」同口径。
上游融合端点已有 `except Exception → 422`，故是干净 fail-closed（非 500）。

## P1-23 GDPR 流式导出 7 个 `iter_*` 补 `ORDER BY`

`gdpr_service_export.py` 的 7 个迭代器用 `LIMIT/OFFSET` 分页但**无 ORDER BY**。SQL 不保证此时
的返回顺序，同一行可能两页都出现、也可能整页被跳过 —— 对「数据主体有权拿到全部个人数据」
而言是**合规实质缺陷**，不是性能问题。已按主键升序补稳定排序（8 个迭代器，含
`iter_intervention_tasks` 的分页查询）。

## P1-20 uploads 响应头 —— **刻意偏离报告建议**

报告原话是「加 `Content-Disposition: attachment` + `nosniff`」。**只采纳了后者**，理由有实测依据：

`app/api/v1/uploads.py` 模块头 15-18 行明确写着 `<audio src>` / `<img src>` 等浏览器原生标签
无法携带 Authorization header，端点因此额外支持 `?token=` —— **内联渲染是被有意支持的用法**，
公共资源 `/uploads/audio/mindfulness_10min.mp3` 正是靠它播放。强制 `attachment` 会把正念音频与
头像预览全变成下载，属功能回归。

改为两条不破坏内联渲染的头：`X-Content-Type-Options: nosniff`（禁 MIME 嗅探）+ 
`Content-Security-Policy: default-src 'none'; sandbox`（即便用户直接导航到 `.html`/`.svg`
——文件名白名单允许这两种扩展名——脚本也不在本源执行）。
闸门里除「头存在」外另加一条**反向闸门**：`content-disposition` 不得含 `attachment`，
防止后人照报告原文改回去。

## P1-26 数据集缺失禁止静默生成合成数据

`experiment_data.py` 改前：数据集文件不存在 → 自动生成 240 行合成样本 → 照常训练/评估。
调用方拿到的指标看起来完全正常，实际测的是随机数。这是**数据造假路径**，且一旦指标被写进
报告或用于上线决策无法事后追溯。

改为默认 `FileNotFoundError`（fail-closed），仅 `allow_synthetic=True` 时造数并留 warning。
`ExperimentService.import_dataset` 透传该开关；API 层补 `except FileNotFoundError → 404`。

⚠️ **连带发现（值得单列）**：`tests/services/test_experiment_service.py` 有两个用例
（`test_import_dataset_raises_on_invalid_ratios_sum` / `test_import_dataset_raises_on_negative_ratio`）
**改前根本没建 CSV**，靠「文件不存在就自动造数」才走到比例校验 —— 也就是说**既有测试把静默造数
当成了前置条件**。这正是「先翻既有测试」的价值：它们不仅固化设计意图，也可能固化缺陷。已改为
显式落真实数据集。

## P1-25 危机导出时区 —— 经复核为**陈旧条目**

报告指 `crisis_export_service.py:85-86` aware/naive 不一致。实测该处现已是
`datetime.combine(start_date, time.min, tzinfo=timezone.utc)`（aware UTC），由既有 M-4 修复覆盖。
**无需改动**，此处记账以免后人重复排查。

## 本轮验证读数

- 新增闸门 20 条全绿；每项都做了回退红信号对照实验：
  #18 回退 → 4 红；#23 移除 `order_by` → 1 红；#20 移除头 → 1 红、
  **反向**加回 `attachment` → 1 红；#26 回退 → 1 红。
- 受影响既有测试：`104 passed, 1 skipped`（fusion ×3 / experiment_service / uploads ×2）+ 
  `119 passed`（gdpr / model_predict api / uploads api）+ `196 passed`（training / predict_service /
  non-finite 守卫）。合计 **419 passed, 1 skipped**。

## 未做（如实记账）

- 本轮**未跑 backend 全量**（约 37 分钟），以 CI 全量为准。
- 前端 P1（#11-14、#27-30）本轮未动，留待下一轮；本轮仅后端。
- 报告剩余 P1 未处理项：#15、#16、#17、#19、#21、#22、#24。

---

# 附：P1 整改追记（2026-10-13，第三轮）

> 同为**追加快照**，不修改上文任何既有表格与结论。
> 闸门文件：`backend/tests/test_p1_audit_2026_10_13_round2.py`（8 条，均做过回退红信号对照）。

## P1-16 `add_group_member` 重复 insert 只回滚 savepoint

`counselor_service_group.py` 改前在 `IntegrityError` 时执行 `await self.db.rollback()`——
它回滚的是**整个 Session 事务**，会把调用方（API 层/上层服务）在此之前 flush 的**其它待提交
改动一并丢弃**。而这些改动不在本函数视野里，现场表现为「别处的数据莫名没写进去」，极难归因。

改为 `async with self.db.begin_nested()`：异常只回滚到 savepoint，外层事务完好，
后续审计日志与 commit 照常进行。闸门断言的是「同事务里先前的改动**仍然存活**」——
这正是改前唯一会丢的东西。

## P1-21 审计日志 `operator_role` 不再硬编码 `"admin"`

全仓 20 处 `operator_role="admin"`。问题在于这些端点的鉴权依赖
`require_platform_admin()` / `require_permission(...)`，它们**同时放行多个角色**
（含 `super_admin`、咨询师）→ super_admin 改预警阈值被记成 "admin"、咨询师关闭危机事件
也被记成 "admin"。第二人复核时无法区分「谁做的」，审计日志失去取证价值。

处置：
- API 层 17 处 → `operator_role=current_user.role`（逐处确认 `current_user` 在作用域）。
- 服务层 3 处（`upsert_config` / `upsert_threshold` / `_write_crisis_audit_log`）→
  新增**必填关键字参数且无默认值**：漏传直接 `TypeError`，不给「忘记传」留静默兜底
  （与 P0-1 租户隔离同一套手法）。三个危机处置方法同步透传。

闸门三条：签名必填（introspect）+ 审计角色如实落库 + **全仓 API 层源码扫描**
（兜住「新增端点时又抄了一遍硬编码」）。

⚠️ 连带：`tests/unit/test_review_service.py` 的 `_CrisisEventServiceT1` 适配层、
`tests/unit/test_review_tenant_isolation.py` 的 3 处调用、以及
`tests/services/test_admin_service.py` 的 9 处调用需同步补参数。适配层必须**允许透传**
（`operator_role="counselor"` 默认值仅作测试便利），否则调用方一传就
`unexpected keyword argument`。

## P1-19 —— **实测推翻报告，故不改动实现，只加锁定闸门**

报告原文称「`pytorch_mlp` 架构元信息改 JSON 侧车（当前生产 100% 不可用）」。
实测（torch 2.11.0+cpu，2026-10-13）：

    weights_only=True  OK; keys = [dropout_rate, hidden_dims, input_dim, param_count,
                                   state_dict, use_batch_norm]
    PyTorchMLP.load()  OK; input_dim = 10 hidden_dims = [32, 16]

成因：检查点里只有 primitive 类型（int/float/bool/list）+ `state_dict`，而 torch 的
`weights_only` 反序列化器**允许 primitive**，所以 `safe_torch_load` 在生产被强制
`weights_only=True`（ISS-046）后依然能加载。**报告该条结论失实，改了也白改。**

但仍加了闸门：一旦将来有人往检查点塞非 primitive 元信息（自定义类/模块对象），
`weights_only=True` 会加载失败 → CI 立刻红，那才是真需要改 JSON 侧车的信号。

⇒ **沉淀：审查报告条目本身也要取证。连续两轮（#25 时区、#19 侧车）发现陈旧/失实条目，
后续 P1/P2 落地前应先用最小实测确认「问题当前是否真的存在」。**

## P1-22 经取证降级（暂不改）

报告称 14 处 `offset = (page-1)*page_size` 缺下界校验。实测 API 层**已有 25 处**
`page: int = Query(default=1, ge=1)` 覆盖，HTTP 路径下取不到负 offset；服务层的
残余风险仅来自内部调用方。抽公共 `paginate()` 需动 18 处，收益主要是防御性，
故本轮不处理，降级留待与 #17/#24 一并做。

## 本轮验证读数

- 新增闸门 8 条全绿；回退均现红：#16 回退 `rollback()` → 1 红；#21 回退一处硬编码
  → 源码扫描 1 红；#21 去掉必填默认值 → 签名闸门 1 红。
- 受影响既有测试：91（review/tenant/gdpr）+ 58（export/kill_switch/silence/upload）
  + 139（admin/tenant/silence/content API）+ 73（admin_service/metrics + 两轮闸门）
  = **361 passed**。

## 未做（如实记账）

- 未跑 backend 全量，以 CI 为准。
- 剩余 P1：#15、#17、#19（已加闸门，无需改实现）、#22（已降级）、#24；前端 #11-14、#27-30。
