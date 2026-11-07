# 全量业务源代码审查报告

- 审查日期：2026-11-06
- 审查对象：`E:/code/bysj`（心理健康风险评估系统 DWS）
- 审查性质：静态代码审查（只读，未修改任何业务源码）

---

## 一、审查范围与口径

### 1.1 权威口径

以 `git ls-files`（版本库跟踪文件）为唯一权威清单，再按扩展名与目录筛出**实际业务源代码**。项目内存在大量状态文件、缓存与产物，这些一律不进入审查范围。

**纳入（业务源码）**

| 模块 | 路径 | 规模 |
|---|---|---|
| 后端 API / Schema | `backend/app/api/**`、`backend/app/schemas/**` | 约 70 个 `.py` |
| 后端核心 / 服务 / 模型 | `backend/app/core/**`、`services/**`、`models/**` | 约 155 个 `.py` |
| 后端 ML / 任务 / 监控 / 工具 | `backend/app/ml|tasks|monitoring|utils/**` | 约 46 个 `.py` |
| 前端源码 | `frontend/src/**`（`.vue` / `.ts` / `.scss`） | 411 个，其中 `.vue`/`.ts` 275 个 |
| 交付与建模脚本 | `scripts/**`、`backend/scripts/**` | 77 个 `.py` |
| 数据库迁移 | `backend/alembic/versions/**` | 21 个 `.py` |

重复度量化扫描实际命中：`backend_py` 504 个文件 / 108,268 规范化行，`frontend_vue_ts` 275 个文件 / 40,223 规范化行。

**明确排除**

- 状态与缓存：`.git/`、`.workbuddy/`、`.pytest_cache/`、`.ruff_cache/`、`.hypothesis/`、`.cache/`、`__pycache__/`、`*.pyc`、`.coverage`、`coverage.xml`、`htmlcov/`、`.import_linter_cache/`
- 依赖目录：`backend/.venv/`、`frontend/node_modules/`
- 构建产物：`frontend/dist/`、`dist-http/`、`dist-tsc-app/`、`*.map`、`playwright-report/`、`test-results/`、`outputs/`、`reports/`
- 锁文件：`package-lock.json`、`pnpm-lock.yaml`、`yarn.lock`、`requirements*.lock`、`*.sha256`
- 非源码文件：`*.md`（`docs/` 630 份）、`*.log`、`*.db`、`*.csv`、`*.json` 产物、`*.bin`/`*.pkl`/`*.pt` 模型工件、`*.png`、`*.pdf`（`原文/`）、`datasets/`、`data/`、`models/` 工件
- 测试代码：`backend/tests/**`、`frontend/src/**/*.test.ts`、`*.spec.ts`、`e2e/`（测试不是业务源码；仅用作交叉验证参考）
- 配置/文档类：`*.yml`、`.env.example`、`Dockerfile`、`nginx.conf`（不作为业务源码计入，仅在需要确认运行时可达性时查阅）

### 1.2 方法与复核深度

1. **全量静态扫描**：对纳入范围跑安全/异常/注入/重复/命名模式扫描（硬编码凭据、`text(f"...")`/`execute(f"...")` SQL 拼接、`v-html`/`innerHTML`/`eval`、裸 `except: pass`、`localStorage` 敏感存储、TODO 登记项等）。
2. **分模块深度实读**：5 路并行审查员分别负责后端 API/Schema、后端核心/服务、ML/任务/脚本/迁移、前端基础设施、前端视图/组件，每条发现必须打开文件、给出精确行号与逐字代码片段。
3. **主审二次复核**：所有「严重」条目、绝大多数「中等」条目及部分「轻微」条目由主审重新打开源码确认，并检查运行时可达性（路由是否注册、参数是否来自用户输入、防御分支是否可触发、是否存在全局默认防护）。

**复核结果**：剔除 1 条明确误报——`frontend/src/composables/usePerformanceMonitor.ts:342` 曾被认为「`sendBeacon` 无法带 Bearer 导致上报被 401 丢弃」，实读 `backend/app/api/v1/monitoring.py:471-483` 确认 `/frontend-metrics` **明确设计为无需鉴权**（含匿名用户采集），该问题不成立，不列入清单。另对 2 条做了降级/改述：`user_risk.py` 的「无限流」不成立（`backend/app/core/rate_limit.py:93-105` 有全局 `default_limits` 生产 60/minute），改述为「限流粒度不一致」并降为轻微；`scripts/refresh_model_pickles.py` 的代码注入因属本地运维脚本、需先具备模型目录写权限，由「严重」降为「中等」。

### 1.3 局限

- 纯静态审查：**未运行全量测试、未启动服务、未做动态渗透验证**，运行时行为类结论以源码可达性为依据。
- 数据集与模型工件不在版本库，ML 脚本的端到端可复现性未验证。
- 「轻微」条目中部分由分模块审查员实读确认，主审按模式扫描交叉验证，未逐条二次打开文件；「严重」条目全部经主审二次打开确认。

---

## 二、结论速览

| 模块 | 严重 | 中等 | 轻微 | 主要风险特征 |
|---|---:|---:|---:|---|
| A 后端 API / Schema | 1 | 3 | 5 | 同一平台级鉴权口径未全线贯通 |
| B 后端核心 / 服务 / 监控 | 0 | 7 | 4 | 防护「做了一半」、静默降级、资源放大 |
| C ML / 任务 / 脚本 / 迁移 | 1 | 7 | 5 | 假数字进交付产物、脚本静默失败 |
| D 前端基础设施 | 0 | 3 | 4 | 广播/守卫接线不完整、开放跳转 |
| E 前端视图 / 组件 | 1 | 8 | 4 | 加载失败渲染成 0、重复样式与骨架 |
| **合计** | **3** | **28** | **22** | **53 条** |

六个维度均有条目覆盖（功能 bug/逻辑错误、安全、性能与资源、错误处理与边界、命名/结构一致性、重复代码与可维护性）；每条按主维度归类，同一问题可能同时涉及多个维度。`L-22` 为存量已登记开放项，仅作提示、不计入上述统计。

---

## 三、问题清单（按模块与等级）

### 模块 A — 后端 API 与 Schema（`backend/app/api/`、`backend/app/schemas/`）

#### 严重

**[S-01] 分析事件查询跨租户泄露用户行为与 IP · 安全** — `backend/app/api/v1/analytics_events.py:269-288`
- 证据：`:275` `if current_user.role not in (USER_ROLE_ADMIN, USER_ROLE_SUPER_ADMIN):`；`:282` `records = list(_event_store)`；写入侧 `:162-172` 每条记录含 `user_id`、`metadata`、`client_ip`，**且不含 `tenant_id` 字段**。
- 问题：`_event_store` 是进程级全局列表，汇聚全平台所有用户的事件；查询端点只有裸角色判断、没有任何租户维度过滤，租户 B 的 admin 可读到租户 A 全部用户的行为数据与客户端 IP。对照 `backend/app/api/v1/gdpr.py:256-264`，同类平台级端点已因同一越权问题升级为 `require_platform_admin()`，此处漏改。路由确已在 `backend/app/api/v1/__init__.py:6,42` 注册并生效。
- 建议：写入时附加 `tenant_id`，查询按 `current_user.tenant_id` 过滤；或统一改用 `require_platform_admin()` 明确平台级语义；从响应中移除 `client_ip`，并对 `limit`/`event_type` 做白名单校验。

#### 中等

**[M-01] CSP 上报端点的 Pydantic 校验是不可达死代码 · 功能 bug / 安全** — `backend/app/api/csp_report.py:69`、`:156-184`
- 证据：`:69` `async def receive_csp_report(request: Request) -> Response:`；`:177-184` `logger.info("CSP violation: directive=%s blocked=%s ...", directive, blocked, document, source, line)`。
- 问题：`:20-53` 定义的 `CSPReportBody`/`CSPReportPayload`（含 `max_length=2048/8192`）从未声明为 body 参数，校验完全不触发；`:140-174` 直接从原始 JSON `.get()` 取值写 `logger.info`，可注入换行伪造日志、用超长字段撑爆日志。对照 `backend/app/api/v1/monitoring.py:516` 的 `receive_frontend_metrics` 已正确调用 `model_validate`。注释「M-API-11 修复」与实际实现不符。
- 建议：签名改为 `receive_csp_report(request: Request, payload: CSPReportPayload)`，用校验后字段记日志；至少对四个字段做长度截断与 CRLF 转义。注意浏览器 `application/csp-report` 的 Content-Type 兼容。

**[M-02] 用户可控正则拼进 `re.match` 且逐行重复编译 · 安全 / 性能** — `backend/app/api/v1/metrics_helpers.py:334-336`、`:295`
- 证据：`:334` `regex_filters = re.findall(r'(\w+)=~"([^"]*)"', query)`；`:336` `if k in labels and not re.match(f"^({pattern})$", labels[k]):`。`query` 来源 `backend/app/api/v1/metrics.py:187` `query: str = ""`（无 `max_length`）。
- 问题：持有 metrics token 者可用 `|`、`.*` 篡改过滤语义，或构造超长/灾难性回溯正则在 `async` 端点内同步阻塞事件循环；且这两步位于 `for line in body.split("\n")` 的每一行内重复执行， exposición 文本越长开销越大。
- 建议：给 `query` 加 `max_length`，`pattern` 用 `re.escape` 或仅允许 `[A-Za-z0-9_.*-]` 白名单，把 `regex_filters` 提到行循环外预编译，必要时用带 timeout 的正则引擎。

**[M-03] 操作日志导出无时间跨度上限、非流式 · 性能 / 资源** — `backend/app/api/v1/admin.py:342-363`
- 证据：`:358` `"""ISS-080: 导出全部筛选条件下的操作日志（不分页）"""`；`:363` `return ok({"items": items, "total": len(items)})`。
- 问题：`start_time`/`end_time` 无跨度上限、`action_type` 无长度约束，一次性把全部命中行装进响应体；同文件 `/crisis-events/export` 已有 90 天跨度校验（`:548-552`）与 `StreamingResponse` 流式输出（`:622`），口径不一致。日志量大时全表扫描 + 海量对象驻留内存。端点已有 `10/minute` 限流，故不是「无限流」问题。
- 建议：复用 crisis 导出口径——加 90 天跨度与记录数上限，补 `action_type` 长度约束，改为逐行 `StreamingResponse` CSV。

#### 轻微

**[L-01] 导出/推理端点限流粒度与同类端点不一致 · 性能** — `backend/app/api/v1/user_risk.py:59-66`
- 证据：`:59` `@router.get("/export", responses={...})` 上方无 `@limiter.limit`；对照 `backend/app/api/v1/reports.py:75,220` 为 `5/minute`。
- 问题：全局默认限流仍在（`rate_limit.py:93-105`，生产 60/minute），但 `/export` 会生成 CSV/PDF 并 commit，60 次/分钟对重 IO 端点偏高，与同类导出端点的严格口径不一致。**注意：不是「完全无限流」**。
- 建议：给导出/推理端点补 `5/minute`、查询类补 `20/minute`，与 `reports.py` 对齐。

**[L-02] 进程内事件存储使「90 天保留」与多 worker 一致性承诺落空 · 功能 bug** — `backend/app/api/v1/analytics_events.py:73-76`、`:174-179`
- 证据：`:73-76` `_event_store: list[dict[str, Any]] = []` / `_MAX_STORE_SIZE = 20000`；`:178` `del _event_store[:overflow]`。
- 问题：存储仅存在于单进程内存，重启即全部丢失、多 worker 之间互不共享（各 worker 只看到自己那部分事件）；超过 20,000 条按最旧淘汰，与文档承诺的「90 天保留期」语义不同；同时 `/events` 查询只能看到本进程数据。
- 建议：迁移到数据库表或 Redis（带 TTL），并把 `retention_expires_at` 作为真实过期依据；若短期保留内存实现，需在文档与 `/consent` 响应中明确「进程内、重启丢失」。

**[L-03] 单文件与批量上传的校验顺序不一致，未校验文件先落盘 · 安全 / 重复** — `backend/app/api/v1/user_upload.py:251-253`
- 证据：`:251` `size, content = await _save_upload_stream(file, save_path)`，随后 `:253` 才 `_validate_mime_type`；批量端点 `:108-112`（H-API-8 修复）已改为先读 8KB 校验 MIME 再落盘。
- 问题：两份近乎重复的上传实现口径不一致；单文件端点在 MIME/病毒扫描前已把未校验内容写入磁盘，校验失败只靠 `except` 块 `unlink`，Windows 句柄占用时会残留文件。
- 建议：`upload_file` 复用 `_process_batch_file` 的顺序（`read(8192)` + `seek(0)` + 校验后再落盘），并抽取公共函数消除重复。

**[L-20] 批量导出 schema 的 `filters` 与行数据无约束 · 边界** — `backend/app/schemas/reports.py:47`、`:34`
- 证据：`:47` `filters: dict[str, Any] | None = Field(default=None, description="Filters to apply")`；同文件 `:41-43` 的 `data` 有 `max_length=10000`、`:50` `filename` 有 `max_length=100`。
- 问题：唯独 `filters` 与 `BatchExportDataItem.data` 缺键数/值长/嵌套深度约束，`reports.py:242,275` 直接 `model_dump()` 交给 Excel 导出，10,000 行 × 任意大对象会放大内存与导出耗时。
- 建议：参照 `schemas/admin.py:61-94` 的 `validate_config_value`，补键数上限、标量类型、字符串长度与嵌套深度校验。

**[L-21] 校验任务请求模型的字符串字段缺长度上限 · 边界** — `backend/app/schemas/validation.py:11`
- 证据：`:11` `model_version: str = Field(..., description="Model version to validate")`（`dataset_path`/`baseline_version`/`baseline_dataset_path` 同样）。
- 问题：与项目其余请求模型普遍带 `max_length` 的口径不一致，超长值会原样写入 Redis job 并经 `/validation/{id}/status` 回显。
- 建议：补 `max_length`（版本类 64、路径类 512），并在 `_validate_dataset_path` 入口先拒绝超长输入。

---

### 模块 B — 后端核心 / 服务 / 模型 / 监控（`backend/app/core|services|models|monitoring/`）

#### 中等

**[M-04] 含凭据的 Redis URL 被写入 info/critical 日志 · 安全** — `backend/app/core/rate_limit.py:83`、`:269`、`:283`
- 证据：`:83` `logger.info("Rate limiter using Redis backend: %s", redis_url)`；`:269`/`:283` `f"REDIS_URL={redis_url}"`。
- 问题：默认 `redis://localhost:6379/0`（`core/config.py:210`）无凭据，但生产按部署惯例常配置 `redis://:password@host:6379/0`；该 URL 同时是 token blocklist、密码重置码的后端，完整明文进日志后，可读日志者即可取得 Redis 凭据并篡改撤销状态/重置码。
- 建议：统一走脱敏函数，用 `urlsplit` 只记 host/port/db，password 打码；三处日志点一并修改。

**[M-05] 有效绑定码明文写入审计日志 · 安全** — `backend/app/services/counselor_service_binding.py:181-197`
- 证据：`:188-190` `detail={"old_bind_code": old_code, "new_bind_code": new_code, ...}`；`:196` `await self.db.commit()`；`:197` `return new_code`。
- 问题：`new_code` 是刚生成且仍有效的绑定码，被长期留存在 `OperationLog.detail`；能查看操作日志的人可拿它调用 `bind_by_code` 把用户绑到该咨询师，进而访问名下学生风险数据。
- 建议：审计 detail 只记 `rotated=True` 或绑定码的 HMAC 前 8 位，禁止写明文。

**[M-06] 注册不落租户 ID，非默认租户无法自助注册 · 功能 bug** — `backend/app/services/auth_service.py:99-106`、`:149-152`
- 证据：`:99-106` `user = User(username=..., email=..., email_hash=..., password_hash=..., role=..., status="active")`（无 `tenant_id`）；`models/user.py:64-67` `tenant_id ... default=DEFAULT_TENANT_ID`；登录侧 `:149-152` `.where(User.tenant_id == (tenant_id if tenant_id is not None else DEFAULT_TENANT_ID))`。
- 问题：登录已按请求租户隔离（AUDIT-2026-10-06 P0-1），但注册仍落到默认租户 1；在租户 B 子域注册的用户随后在同一子域登录必然查不到，属认证链路两端口径不一致。唯一性检查 `:87-94` 同样缺租户维度。
- 建议：`register` 增加 `tenant_id` 形参并显式赋值，由路由传 `get_request_tenant_id(request)`；唯一性检查同步加租户维度。

**[M-07] 影子对拍 Task 无强引用、异常无人接收 · 错误处理 / 边界** — `backend/app/services/shadow_mode_service.py:88`（另见 `shadow_comparison_service.py:74`）
- 证据：`:88` `asyncio.create_task(self._shadow_predict(text, production_result))`。
- 问题：创建的 Task 未保存引用、无 `done_callback`，可能被事件循环 GC 静默取消，异常变成 "never retrieved"；对拍样本无痕丢失后 `is_shadow_acceptable` 在 `total < min_samples` 时返回 True 放行，使未验证的候选模型可被激活。
- 建议：维护 `self._tasks: set[Task]`，`add_done_callback(self._tasks.discard)`，回调内 `task.exception()` 记录失败并计数；放行判据改为「样本数达标且失败率低于阈值」。

**[M-08] 图片 EXIF 清洗用逐像素 Python 对象重建 · 性能 / 资源** — `backend/app/services/file_security_service.py:80-96`
- 证据：`:94` `data = list(img.getdata())`；`:95-96` `clean_img = Image.new(img.mode, img.size)` / `clean_img.putdata(data)`；`:92` 注释称「使用 img.copy() + save() 重编码」但实现并非如此。
- 问题：像素上限允许到 25,000,000，每个像素被实例化为 Python 元组，单个几 MB 的构造 PNG 即可让工作线程峰值内存达数 GB；动画 GIF 也只保留首帧。注释与实现不符。
- 建议：改为 `img.save(tmp, format=..., **kw)` 直接重编码（Pillow 内部不产生逐像素 Python 对象），动画 GIF 用 `save_all=True` 逐帧处理。

**[M-09] `app_env` 归一化口径漂移可绕过生产 fail-fast · 安全 / 命名一致性** — `backend/app/core/config.py:339,342,366,379,384,396,725,760,784` vs `:446,494,746`
- 证据：`:339` `if self.app_env.lower() == "production" and ...`；`:446` `is_production = self.app_env.strip().lower() == "production"`。
- 问题：同一字段两套判定。当 `APP_ENV="production "`（尾随空格）时，弱 JWT 密钥、SQLite、HTTP 重置链接等生产校验被静默跳过，而部署侧校验（`.strip().lower()`）却按生产执行，出现「按生产部署、按开发放行」的错位。
- 建议：定义 `is_production` 属性统一 `strip().lower()`，全文件改用它；或在 `model_validator` 入口先归一化 `self.app_env`。

**[M-10] 告警升级扫描固定截断 500 条且未过滤已确认告警 · 功能 bug / 边界** — `backend/app/monitoring/escalation.py:181-200`
- 证据：`:182` docstring「扫描所有未确认 firing 告警」；`:188-193` `where(action_type == "alert_fired", target_type == "alert")` + `.limit(500)`，无「未确认」条件、无游标。
- 问题：按 `created_at` 倒序只取最新 500 条，历史已确认告警或积压新告警占满额度后，较老的未确认告警永远不会被扫描，P1→P0 升级与 1 小时合规追踪静默漏掉；与 docstring 承诺不符。
- 建议：where 中加未确认/未升级条件，或按 `created_at` 游标分页遍历全量待处理集合，避免用固定 limit 截断。

#### 轻微

**[L-04] `.upper()` 折叠绑定码字符集，实际熵低于设计意图 · 安全** — `backend/app/services/counselor_service_binding.py:203`、`:226`
- 证据：`:203` `return secrets.token_urlsafe(10)[:10].upper()`；`:226` 做大小写敏感等值比较。
- 问题：`token_urlsafe` 是 62 进制大小写字母，`.upper()` 把字母表压到 36 并折叠大小写，10 字符实际熵约 51.7 bits，低于 `:201-202` 注释宣称的强度提升。
- 建议：去掉 `.upper()` 保留原字符集，或两侧统一 `casefold()` 比较，或改 `secrets.token_hex(8)` 定长 64 bits。

**[L-05] `ilike` 通配符未转义 · 功能 bug / 性能** — `backend/app/services/content_service.py:47`
- 证据：`like_kw = f"%{keyword}%"`。
- 问题：用户输入 `%`/`_` 未转义，输入单个 `%` 即可匹配全部内容绕过关键词过滤；前导通配符同时使索引失效导致全表扫描。
- 建议：转义 `%`、`_`、反斜杠并指定 `escape="\\"`，或改走全文检索。

**[L-06] 影子采样使用固定种子 42，跨实例样本可预测 · 功能 bug** — `backend/app/services/shadow_mode_service.py:50`（另见 `shadow_comparison_service.py:45`）
- 证据：`self._random = random.Random(42)`。
- 问题：进程重启及多 worker 间采样序列完全相同；运维把 `sample_rate` 调低时（默认 1.0 不触发）对拍集合可预测且跨实例重复，一致率统计样本偏斜。
- 建议：用系统熵播种，或按 `(user_id, request_id)` 做确定性哈希分桶。

**[L-07] `_para_text` 在两个导出模块逐字重复 · 重复代码** — `backend/app/services/risk_service_export.py:18` 与 `pdf_report_service.py:15`
- 证据：两处均为 `return _xml_escape(str(value))`，注释同源。
- 问题：Paragraph 转义规则各自演进时会漂移，新增导出模块会复制第三份。
- 建议：抽到 `app/services/_report_common.py` 单一实现，两处改为导入复用。

**[L-22] `init_sentry` 失败时 `/health/startup` 仍误记 ok · 错误处理**（存量已登记开放项） — `backend/app/main.py` / `core/health.py`
- 说明：项目笔记中已列为第二十七批遗留开放项，本轮未重复计入 53 条统计，仅提示整改时与 M-07 的「静默降级」一并处理。

---

### 模块 C — ML / 任务 / 交付脚本 / 迁移（`backend/app/ml|tasks|utils/`、`scripts/`、`backend/scripts/`、`backend/alembic/versions/`）

#### 严重

**[S-03] 缺模型文件时返回伪造「实测」指标并写入切换决策 · 功能 bug / 可信度** — `scripts/compare_text_models.py:140-169`、`:274-301`
- 证据：`:157-158` `if not tfidf_path.exists() or not model_path_file.exists():` / `logger.warning("Baseline model files not found, using simulated metrics")`；`:160-169` 返回硬编码 `f1: 0.9681, roc_auc: 0.98, latency_ms: 2.0` 等；`:276` `if bert_metrics is None or baseline_metrics is None: sys.exit(1)`。
- 问题：与 `evaluate_bert_model`（`:135-137` 失败返回 `None`）口径不一致，模拟值以 `dict` 形式绕过 `main` 的失败检查，直接参与 `:281` `make_switch_decision` 并写入 `:294-301` 的 `comparison_report.json` 与 `switch_decision.txt`，产出**无任何数据支撑的模型切换结论**。这属于「脏条目被渲染成假数据进输出」，是本项目最不能接受的一类缺陷。
- 建议：缺文件直接 `return None` 或抛异常；若必须占位，返回值打 `simulated=true` 标记并让 `make_switch_decision` 显式拒绝该输入，同时报告里不得出现「实测」外观的数字。

#### 中等

**[M-11] 模型路径拼进 `python -c` 源码导致任意代码执行 · 安全** — `scripts/refresh_model_pickles.py:48-60`、`:99-115`
- 证据：`:54` `f"    joblib.load(r'{path}')\n"`；`:60` `subprocess.run([sys.executable, "-c", code], ...)`；`:101-108` `--model-dir` 用户可控、`root.rglob("*.pkl")` 决定 `path`。
- 问题：文件名含单引号或换行即可闭合 `r'...'` 字符串并注入任意 Python 代码，子进程以当前用户权限执行；脚本带 `--apply`（`:103`）且会 `joblib.dump` 写盘（`:147`）。**评级理由**：属本地运维脚本、攻击者需先能在模型目录放置特制文件名，不是远程攻击面，故定为中等而非严重；一旦满足即任意代码执行。
- 建议：改为 `subprocess.run([sys.executable, "-c", code, str(path)])`，子进程内用 `sys.argv[1]` 取路径，绝不把路径拼进源码文本。

**[M-12] CI 无模型文件时「0 项检查」仍输出 ALL CHECKS PASSED · 功能 bug** — `backend/scripts/check_compatibility.py:96-106`、`:165`
- 证据：`:97-106` `if not models_dir.exists(): return {..., "total": 0, "ok": True, "detail": "... skipping (CI mode)"}`；`main` 把 `critical_checks` 限定为仅 `sklearn_version`。
- 问题：模型与兼容性两项永远不影响退出码，质量门禁在常态（模型不入 git）下给出全绿但零检查的假信号。
- 建议：缺目录时返回 `ok=False` 且 `skipped=true`，由 `main` 依据 `CI_ALLOW_MISSING_MODELS` 显式决定放行，并在输出中区分「通过」与「跳过」。

**[M-13] 侧车清理只扫顶层，与生成/审计的递归口径不一致 · 功能 bug** — `backend/app/utils/checksum.py:143`
- 证据：`for sidecar in directory.glob("*.sha256"):`；对照 `backend/scripts/generate_sidecars.py:69` 与审计端均用 `rglob("*")`。
- 问题：`models/artifacts/` 等子目录下的孤立 `.sha256` 永远清不掉，`--cleanup` 报告「已删除 0」但仍有残留。
- 建议：改用 `directory.rglob("*.sha256")`，三端口径统一。

**[M-14] PII 回填迁移一次性 `fetchall()` + 逐行 UPDATE · 性能** — `backend/alembic/versions/h9d4e5f6a7b8_add_pii_encryption_email_hash.py:84-111`
- 证据：`:84-86` `fetchall()`；`:111` `sa.text("UPDATE users SET email_hash = :email_hash WHERE id = :id")` 位于循环内。
- 问题：用户量大时全表载入内存 + 每行一次数据库往返 + 长事务，易触发升级超时。
- 建议：`fetchmany(500)` 分页 + `executemany` 批量 UPDATE，分批提交。

**[M-15] scaler 变换失败静默改用未标准化特征，污染模型对比报告 · 错误处理** — `backend/scripts/modeling/v1_23/04_compare_with_existing_models.py:144-152`
- 证据：`:144-147` `try: X_v121_scaled = v121_scaler.transform(X_v121)` / `except Exception: X_v121_scaled = X_v121`；`:151` `v121_metrics = compute_metrics(...)`。
- 问题：特征列/顺序错配这类真实故障被完全吞掉，用未标准化特征算出的 AUC/F1 仍写入「是否切换默认结构化模型」的对比报告，决策基于失真数字且无任何告警。
- 建议：捕获后向上抛，或把该模型标记 `unreliable` 并跳过对比；至少 `logger.exception` 并在报告里写明 `v121_metrics` 不可信。

**[M-16] 校准模型写盘失败被完全吞掉，仍报训练成功 · 错误处理** — `backend/scripts/modeling/v1_25/02_train_lite_model.py:199`
- 证据：`:199` `joblib.dump(lgb_calibrated, model_dir / "mmpsy_lite_model_gbdt.pkl")`，紧随 `except Exception: pass`。
- 问题：产物缺失但 `metrics["gbdt_auc"]` 仍在，脚本照常打印指标与 Go/No-Go，制造「训练成功」假象。
- 建议：`logger.exception` 并把 `gbdt_artifact_saved=False` 写入 `metrics.json`，或直接向上抛使任务标记为 FAILURE。

**[M-17] OOD 基线注释称「来自 metrics.json」实为硬编码常量 · 命名一致性 / 可信度** — `scripts/d3_ood_validation.py:64-66`、`:132-139`、`:258-290`
- 证据：`:66` `"f1": 0.7891,`；`:64` 注释称 `INDOMAIN_BASELINE`「来自 metrics.json」；`:132-139` `load_text_model()` 实际读取 `TEXT_METRICS_PATH` 的真实 `test_metrics` 并打印。
- 问题：`f1_drop`/`auc_drop` 与 `severe_overfit` 判定全用硬编码常量，`metrics.json` 更新后报告仍沿用旧值，结论与真实产物脱节。
- 建议：由 `metrics["test_metrics"]` 构造基线并写入报告；常量仅在读取失败时报错，不做静默兜底。

#### 轻微

**[L-08] CLI 裸 `pickle.load` 绕过运行时白名单 · 安全** — `scripts/ml_training/predict_cli.py:21`
- 证据：`model = pickle.load(f)`；运行时加载路径已由 `app/core/safe_pickle.py` 实施白名单与哈希校验。
- 问题：`scripts/` 下 20 余处仍裸用 `pickle`/`joblib.load`，模型目录若被替换成恶意 `.pkl`，一次 predict 即执行任意代码。
- 建议：统一改用 `app.core.safe_pickle.safe_joblib_load` 并校验 `.sha256` 侧车，把 `model_path` 限制在受控模型目录内。

**[L-09] `load_metrics` 缺缓存，每次调用全量 SHA256 · 性能** — `backend/app/ml/model_loader.py:309`、`:393-400`
- 证据：`:309` `def load_metrics(path: Path | str | None = None) -> dict:` 无 `@lru_cache`；同文件注释声明其余工件加载器均带缓存。
- 问题：管理接口频繁调用时重复 open 并对整个文件做 `_verify_integrity` 全量哈希。
- 建议：拆出 `_load_metrics_cached(path)` 加 `@lru_cache(maxsize=8)`，并纳入 `_ARTIFACT_LOADERS` 以便 `clear_artifact_cache` 一并失效。

**[L-10] `_compute_sha256` 重复实现且本文件已导入同模块 · 重复代码** — `backend/scripts/generate_sidecars.py:31`、`:58`
- 证据：`:31` 本地 `def _compute_sha256(path: Path) -> str:`；`:58` 已 `from app.utils.checksum import ...`。
- 问题：与 `app/utils/checksum.py:22` 逐字重复，未来分块大小/编码口径单点修改会造成两处漂移。
- 建议：直接导入并删除本地副本。

**[L-11] CV 失败静默置 nan，报告无法区分数据问题与代码失败 · 边界** — `backend/scripts/modeling/eval/v1_24/02_validate_mmpsy.py:96`
- 证据：`auc_3f = float("nan")` 位于 `except Exception` 内，无日志、无状态标记。
- 建议：`logger.exception(...)` 并在报告里标注 `auc_3f_status="failed"`。

**[L-23] 三个生理训练脚本高度同源 · 重复代码** — `scripts/train_physiological.py`、`train_physiological_lightgbm.py`、`train_physiological_xgboost.py`
- 证据：见第四节量化统计，两两之间存在 122~136 个重复 10 行窗口。
- 建议：抽公共数据加载/切分/评估管线，三者只保留模型构造与超参差异；同时避免「同一处口径 bug 要改三遍」。

---

### 模块 D — 前端基础设施（`frontend/src/api|router|stores|utils|composables|config/`）

#### 中等

**[M-18] 跨标签页 token 广播未接线，BroadcastChannel 监听永不触发 · 功能 bug** — `frontend/src/stores/auth.ts:56-69`、`:71-95`；`frontend/src/api/request.ts:74-77`
- 证据：`auth.ts:56-68` `broadcastAuthSync` 内含 `channel.postMessage(next.token || '')`；`request.ts:74-77` 同名函数**只** `dispatchEvent(new CustomEvent(AUTH_SYNC_EVENT, ...))`；`auth.ts:84-94` 注册了 `tokenChannel.onmessage`。
- 问题：全仓生产代码中 `stores/auth.ts` 的 `broadcastAuthSync` 无任何调用点（`login` 只调 `persistAuth`、`logout` 只调 `clearStoredAuth`、刷新走 `request.ts` 的 CustomEvent 版本）。token 存 `sessionStorage`，不触发 `storage` 事件（`auth.ts:97-119` 的 storage 监听只同步 `user`），因此多标签页下 A 标签登录/续期后 B 标签 token 不同步，ISS-008 声称的跨标签同步实际未接通。
- 建议：在 `persistAuth`/`logout`/`refreshSession` 内统一调用同一个 `broadcastAuthSync`，让 `request.ts` 的刷新成功与 `clearAuthState` 复用它（含 BroadcastChannel），删除重复实现。

**[M-19] chunk 加载失败刷新把 `to.fullPath` 直接交给 `location.assign` · 安全** — `frontend/src/router/index.ts:311-324`
- 证据：`:323` `window.location.assign(to.fullPath)`。
- 问题：`fullPath` 未做同源校验，若访问路径以 `//` 开头（catch-all 路由会保留），刷新时被当作协议相对 URL 导航到外部主机；项目在 `LoginPage` 已明确拦截 `//host`、`http(s)://`，此处漏了同一校验。触发需同时满足「chunk 加载失败 + 畸形路径」，概率低但后果是开放跳转。
- 建议：改用 `window.location.reload()`，或用 `new URL(to.fullPath, location.origin)` 解析后校验 `url.origin === location.origin` 再 assign。

**[M-20] 角色 fail-closed 只覆盖 `/admin`，咨询师区仍用未验证角色放行 · 安全** — `frontend/src/router/guard.ts:73-88`
- 证据：`:76` `if (isAdminArea(toPath, meta) && !roleVerified) return '/login'`；`:83-85` `if (!roles.includes(auth.role))`（`auth.role` 来自 store）；`auth.ts:40-43` `isRoleVerified` 才比对 JWT claim。
- 问题：`roleVerified=false`（例如 localStorage 中 `user.role` 被篡改）时，`/counselor/*` 仍用未验证的 `auth.role` 通过 `meta.role` 与 `hasPermission` 判定，普通用户可进入咨询师后台前端结构并按 counselor 渲染操作按钮。后端 RBAC 是否拦截不在本次静态审查范围内，前端不应把该判断当权限边界。
- 建议：把 fail-closed 扩展到所有受 `meta.role`/`meta.permissions` 保护的非 user 区，或让角色判定改用 `parseJwtRole(token)` 的 claim 而非 `user.role`。

#### 轻微

**[L-12] 后端错误 detail 原样展示给用户 · 安全** — `frontend/src/utils/httpError.ts:48`
- 证据：`const detailRaw = response?.data?.detail ?? response?.data?.message ?? ...`，无长度截断与敏感模式过滤，经 `showHttpFeedback` 的 `ElMessage` 及 `request.ts:259` 的 `redirectToLogin(detail || ...)` 直接展示。
- 建议：截断 200 字符，过滤 Traceback/SQL/文件路径，5xx 一律走本地化通用文案，仅 4xx 业务错误透传。

**[L-13] 404 任务状态静默忽略导致无限轮询 · 边界 / 性能** — `frontend/src/composables/useTaskProgress.ts:47`
- 证据：`catch { // 404/网络异常：任务已过期或被清理，静默忽略 }`；`ensurePollTimer` 每 5s 轮询，`ensureCleanupTimer` 只回收 completed/failed。
- 建议：按 status 区分，404/410 时把任务置 failed 或从 Map 删除，让定时器自动收敛。

**[L-14] 同一导出端点两套封装且返回类型不一致 · 重复代码** — `frontend/src/api/userFileApi.ts:4`、`reportsApi.ts`
- 证据：`exportRiskPdf` 一处返回 `AxiosResponse`、另一处 `.then((res) => res.data)` 返回 `Blob`。
- 建议：收敛到 `reportsApi` 一处统一返回 `Blob`，另一处删除或 re-export。

**[L-15] 三处各自实现 axios 错误 detail 提取，规则已漂移 · 重复代码** — `frontend/src/utils/errorDetail.ts:5` vs `httpError.ts` vs `errorPolicy.ts`
- 证据：`getErrorDetail` 不识别 `userMessage`、不读 `error.message` 兜底、不参与统一映射，同一错误经不同入口得到不同文案。
- 建议：`getErrorDetail` 委托 `normalizeHttpErrorInfo(error, fallback).detail`，仅保留一处逻辑。

---

### 模块 E — 前端视图 / 组件 / 布局（`frontend/src/views|components|layouts/`）

#### 严重

**[S-02] 预警数加载失败时渲染成 0，三态保护不可达 · 功能 bug / 漏报** — `frontend/src/views/counselor/CounselorDashboard.vue:55-76`、`:256-274`
- 证据：`:258` `const unhandledCount = ref<number | null>(0)`；`:60` `<template v-else-if="unhandledCount === null">`（注释「**绝不渲染成 0**」）；`:269-270` `} catch { // keep defaults }`。
- 问题：`catch` 既不置 `null` 也不回滚，`unhandledCount` 保持初值 `0`；接口失败时模板走 `v-else` 分支，把「加载失败」显示成「确实没有待处理预警」，正是注释所警告的漏报信号。M27/ROUND_23 的三态设计在失败路径上未接线。
- 建议：`catch` 中置 `unhandledCount.value = null`，重试成功时恢复数值；补一条「接口 reject 时显示 — 且不出现 0」的回归测试（可用真实 `counselorApi` 替身只替换网络层，不用 mock 掉组件状态）。

#### 中等

**[M-21] 敏感操作仅靠客户端角色 `v-if` 收敛 · 安全** — `frontend/src/views/counselor/CounselorReviewListPage.vue:287`、`:188,197`
- 证据：`const isAdmin = computed(() => isAdminRole(auth.role))`；「领取/指定分配」按钮仅用 `v-if` 隐藏，`assignReview`/`openAssignDialog`/`submitAssign` 内无二次角色校验。
- 问题：`:285-286` 注释说明后端会校验学生绑定关系，因此**这不等于已证实的后端越权**；但前端把 store 角色当作操作权限的唯一收敛点，与 M-20 叠加时（角色未验证）会暴露不该出现的操作入口。
- 建议：处理函数入口加二次角色校验，权限判定下沉后端 RBAC，前端 `v-if` 只作展示层收敛。

**[M-22] 反馈内容全文拼进外部 URL，且无条件提示「提交成功」 · 安全 / 边界** — `frontend/src/components/common/HelpCenter.vue:242-254`
- 证据：`:249` `const body = encodeURIComponent(feedbackMessage.value)`；`:250` `window.open(`${GITHUB_ISSUES_URL}/new?title=${title}&body=${body}`, '_blank')`；`:253` `ElMessage.success(...)`。`title` 已 `slice(0,50)`，`body` 无 `maxlength`。
- 问题：超长输入撑爆 URL 导致反馈丢失；弹窗被拦截返回 `null` 时仍提示成功；未加 `noopener,noreferrer`；把用户反馈直接送到公开 GitHub issue 也有隐私考量。
- 建议：给 `el-input` 加 `maxlength/show-word-limit` 并前置长度校验，检查 `window.open` 返回值、补 `'noopener,noreferrer'`，失败时不报成功；优先改走内部反馈接口。

**[M-23] 路由 id 为 NaN 时仍发起读写请求 · 边界** — `frontend/src/views/counselor/CounselorReviewDetailPage.vue:193-199`、`:215`
- 证据：`const id = Number(route.params.id)`，随后 `getReviewDetail(id)` / `resolveReview(id, ...)` 无 `Number.isFinite` 校验；同类 `UserAssessmentDetailPage.vue:130` 已有兜底。
- 建议：加 `if (!Number.isFinite(id))` fail-closed，并抽公共参数解析函数供各详情页复用。

**[M-24] 表格 `deep: true` 监听 + `JSON.stringify` 兜底键 · 性能** — `frontend/src/components/common/PageTable.vue:102-117`、`:86`
- 证据：`:102` `watch(() => props.data, (newData, oldData) => {`；`:117` `}, { deep: true })`；`:104-105` 每次对所有行 `getRowKey`（`:86` 以 `JSON.stringify(row)` 兜底）。组件被 10 处页面复用。
- 建议：去掉 `deep: true` 只监听数组引用；用行 id 缓存取代每次 `JSON.stringify`。

**[M-25] `.bento-cell` 卡片样式在 6+ 组件逐字重复 · 重复代码** — `frontend/src/views/user/components/user-dashboard/InterventionPlanCard.vue:105-116`（另见 `LatestAssessmentCard.vue:104`、`QuickActionsCard.vue:53`、`SystemStatusCard.vue:90`、`RecentActivityCard.vue:86`、`RiskTrendChart.vue:229`）
- 证据：量化统计中与 `LatestAssessmentCard.vue` 有 65 个共同重复 10 行窗口；`BentoCell.vue:59-60` 的 ISS-106 已登记该问题。
- 建议：抽 `@mixin bento-cell`（`styles/mixins.scss` 已有同类 mixin）或统一改用 `BentoCell.vue`，删除各组件内重复样式。

**[M-26] 8+ 个 StatsCard 骨架逐行重复 · 重复代码** — `frontend/src/views/admin/components/admin-alerts/AlertStatsCard.vue:2`、`AssessmentsStatsCard.vue:5-14`、`WarningStatsCard.vue:5-14`、`CrisisEventStatsCard.vue` 等
- 证据：`el-card + header + SkeletonScreen + stat-grid + stat-tile` 骨架一致，仅 i18n key 与字段名不同；量化统计中两两张卡片有 46 个共同重复窗口。
- 建议：抽通用 `<StatsCard :title :loading :items>`，各页面只传数据，与 `BentoCell`/`StatefulContainer` 的抽象层级保持一致。

**[M-27] 登录页与重置密码页提交骨架与整段样式重复 · 重复代码** — `frontend/src/views/login/ResetPasswordPage.vue:218-229` vs `LoginPage.vue:375-386`
- 证据：51 个共同重复 10 行窗口，含 `try/catch/finally + getErrorDetail + ElMessage` 与 `.auth-shell`/`.auth-form-panel` scoped 样式。
- 建议：抽 `useAuthFormSubmit` composable 统一 loading/错误/成功，auth-shell 样式提到共享类，两页只保留表单字段。

**[M-28] 风险趋势图两套实现并存 · 重复代码 / 结构一致性** — `frontend/src/views/user/components/user-dashboard/RiskTrendChart.vue:65` vs `frontend/src/components/charts/RiskTrendChart.vue:2`
- 证据：业务卡片自行 `import { echarts } from '@/utils/echarts'` 手写 option、resize 与配色；通用组件已用 `BaseChart + DataPoint` 封装同一图表。
- 建议：业务卡片改为组合通用图表（传 `data`/`height`），自身只保留标题、天数切换与骨架屏；并把业务卡片改名 `RiskTrendCard.vue` 消除同名不同职责（见 L-16）。

#### 轻微

**[L-16] 同名组件不同职责，import 易引错 · 命名一致性** — `frontend/src/views/user/components/user-dashboard/RiskTrendChart.vue:2` 与 `frontend/src/components/charts/RiskTrendChart.vue`
- 建议：业务卡片改名 `RiskTrendCard.vue`，通用图表保留原名，目录按「通用放 components/、业务卡片放 views/」统一。

**[L-17] 布局组件 500ms 定时器未随卸载清理 · 性能** — `frontend/src/layouts/MainLayout.vue:185`、`:198`
- 证据：`setTimeout(() => { ... tryStartOnboarding() })` 未保存 ID，`onUnmounted` 只清理 WebSocket。
- 建议：保存 timer ID 并在 `onUnmounted` 中 `clearTimeout`。

**[L-18] 无谓的 `deep: true` 监听 · 性能** — `frontend/src/components/common/TaskProgressNotification.vue:110`
- 证据：`{ deep: true }` 但回调只遍历顶层 `task.job_id`。
- 建议：去掉 `deep: true`，引用比较已足够覆盖数组替换。

**[L-19] 净化后富文本图片无懒加载 · 性能** — `frontend/src/views/user/components/user-content/ContentDetailDialog.vue:43,122`
- 说明：`v-html="sanitizedHtml"` 已由 `useUserContentData.ts:136` 的 `DOMPurify.sanitize(..., DOMPURIFY_CONFIG)` 净化，`sharedContentUtils.ts:8-22` 是显式标签/属性白名单并禁用 script、`on*` 与危险 URI，**不构成 XSS**。仅长文多图会一次性并发加载。
- 建议：净化后给 `img` 补 `loading="lazy"`/`decoding="async"`，或限制图片数量。

---

## 四、重复代码量化统计

口径：以 `git ls-files` 为文件清单；逐行规范化（删空行、删 `#`/`//`/`/*`/`<!--` 注释行、折叠连续空白、去首尾空白）；对规范化行序列做 **W=10 行滑窗、步长 1**，拼接后取 SHA1 前 16 位作为块 hash；「跨文件重复组」= 涉及 ≥2 个文件的 hash；「独立重复区段」= 按文件合并重叠窗口后的段数。脚本置于系统临时目录，未写入仓库。

| 组 | 文件数 | 规范化行 | 滑窗数 | 重复窗口组 | 跨文件重复组 | 独立重复区段 | 涉及文件占比 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `backend_py`（`backend/app|scripts|alembic/`、`scripts/`） | 504 | 108,268 | 103,791 | 1,120 | 640 | **215** | 104 / 504 = **20.6%** |
| `frontend_vue_ts`（`frontend/src/**`） | 275 | 40,223 | 37,799 | 609 | 588 | **174** | 90 / 275 = **32.7%** |
| 合计 | 779 | 148,491 | 141,590 | 1,729 | 1,228 | **389** | 194 个文件 |

最典型重复文件对（重复窗口数）：

- `scripts/train_physiological_lightgbm.py` ↔ `train_physiological_xgboost.py`：**136**；与 `train_physiological.py` 另有 127 / 122 —— 三个训练脚本几乎同源。
- `frontend/.../InterventionPlanCard.vue` ↔ `LatestAssessmentCard.vue`：**65**（`.bento-cell` 样式段）。
- `frontend/src/views/login/LoginPage.vue` ↔ `ResetPasswordPage.vue`：**51**（提交骨架 + auth-shell 样式）。
- `frontend/.../CounselorSettingsPage.vue` ↔ `PasswordCard.vue`：**48**。
- `frontend/.../AssessmentsStatsCard.vue` ↔ `WarningStatsCard.vue`：**46**（StatsCard 骨架）。
- `backend/app/core/score_adapter.py` ↔ `backend/scripts/modeling/v1_24/04_train_adapter.py`：**30**（生产实现与训练脚本分叉风险最高的一组）。

前端组件内另有 12 处 `ISS-0xx TODO` 已登记的待优化项（`PageTable.vue:3-4`、`BentoCell.vue:59-60` 等），属已登记项，未单独计为缺陷。

---

## 五、整体质量评估

**总体结论：工程成熟度高，属于「治理完善但一致性有缺口」的代码库，可维护性是当前最大短板。**

### 做得扎实的部分（全量扫描实证）

- **注入面基本清零**：对 `backend/app` 全量扫描 `text(f"...")`/`execute(f"...")`/`%` 拼接/`+ 表名` 等模式，未发现可构造的 SQL 注入路径；参数化查询与 ORM 为主。
- **XSS 面收敛**：全仓 `v-html`/`innerHTML`/`eval`/`new Function` 仅 1 处生产使用（`ContentDetailDialog.vue:43`），且经 DOMPurify 显式白名单净化；其余命中均在测试或 CSP 注释中。另有 `csp.ts` 静态闸门。
- **鉴权体系完整**：`require_platform_admin`、`require_permission`、JWT claim 与 store 角色比对（`isRoleVerified`）、登录绑定请求租户、HttpOnly Cookie 刷新令牌、全局默认限流（生产 60/minute）、PII 加密与盲索引、审计日志均有实现；注释中带审计编号的整改可追溯到代码。
- **异常处理经过系统裁定**：全量扫描仅命中 1 处 `except Exception: pass`（`core/cache.py:310-311`），且属缓存降级；项目已对 341 处 except 候选逐条分型。
- **硬编码凭据基本清零**：`backend/app` 仅命中 `_DEV_WEBHOOK_SECRET = "dev-only-webhook-secret"`（`api/v1/alerts/__init__.py:70`，带 `# nosec B105`、dev-only 语义），未发现生产密钥硬编码。

### 主要风险特征

**不是「传统漏洞」，而是「同一防护只做了一半」**。本次 3 条严重问题里有 2 条属于这一类：

1. 平台级鉴权升级到了 `gdpr.py`，却漏在 `analytics_events.py`（S-01）；
2. 三态渲染在模板里写好了，却在 `catch` 里没接线（S-02）；
3. Pydantic 模型定义好了，却没挂到端点签名（M-01）；
4. BroadcastChannel 监听注册好了，却没有广播方（M-18）；
5. 单文件/批量上传、导出端点、CSP 上报 vs 前端指标上报，都存在「一份修了另一份没修」的口径漂移。

这类缺陷不会报错、不会让测试变红，只会安静地给出错误结果——与项目 README 自述的风险观一致，也正是本轮审查最值得优先处理的部分。

**第二风险是「静默失败产出好看数字」**：S-03（伪造指标）、M-12（0 项检查报通过）、M-15/M-16（异常吞掉后照常出报告）分散在交付脚本里，与运行时 API 的严谨程度形成明显落差。

**第三是可维护性**：389 个独立重复区段、194 个文件涉及跨文件重复，前端 32.7% 的文件存在跨文件复制；同一处口径变更需同步改 3~8 份，是上述「漂移」问题的结构性成因。

### 分级判断说明

- 「严重」= 可直接导致跨租户数据泄露、临床预警漏报、或交付产物出现无依据的结论。
- 「中等」= 有明确触发条件的安全/正确性/资源问题，通常需要特定前置条件（持有 token、特定环境、特定输入）。
- 「轻微」= 风格一致性、局部性能、防御纵深不足，暂无实证的直接损害路径。

---

## 六、优先整改清单（按优先级排序）

### P0 — 立即修复（3 项，均为「不会报错的错误结果」）

| # | 条目 | 动作 | 验收判据 |
|---|---|---|---|
| 1 | **S-01** 分析事件跨租户泄露 | 写入补 `tenant_id`、查询按租户过滤 / 改 `require_platform_admin()`、响应移除 `client_ip` | 用两个租户各造 1 条事件，租户 B admin 查询结果不含租户 A 记录；补一条双租户集成测试（两侧不得各自 mock 数据库） |
| 2 | **S-02** 预警数加载失败显示 0 | `catch` 中置 `unhandledCount.value = null`，成功时恢复 | 让 `getCounselorUnhandledWarningCount` reject，页面显示「—」+ 失败文案，**DOM 中不出现 0** |
| 3 | **S-03** 伪造指标进切换决策 | 缺文件返回 `None`/抛异常；占位值打 `simulated=true` 并被决策函数拒绝 | 移走 baseline pkl 后脚本以非 0 退出、且**不生成** `comparison_report.json` |

### P1 — 本轮整改（接线与防线补齐）

4. **M-11** `refresh_model_pickles.py` 改 `sys.argv[1]` 传路径，消除代码注入。
5. **M-06** `register` 显式传 `tenant_id`，唯一性检查加租户维度；补非默认租户注册→登录端到端用例。
6. **M-20** 路由 `roleVerified` fail-closed 扩展到所有受 `meta.role` 保护的非 user 区。
7. **M-18** 统一 `broadcastAuthSync` 并在 `persistAuth`/`logout`/刷新成功处调用，删除重复实现。
8. **M-01** CSP 端点挂上 `CSPReportPayload`，日志字段做长度截断与 CRLF 转义。
9. **M-05 + L-04** 绑定码不写明文审计、`.upper()` 折叠字符集一并修正。
10. **M-04** Redis URL 三处日志统一脱敏（只记 host/port/db）。
11. **M-10** 告警升级查询加未确认条件或改游标分页，去掉固定 `limit(500)`。
12. **M-07** 影子 Task 保存强引用 + `done_callback`，并把「样本不足即放行」改为显式判据。

### P2 — 质量与资源

13. **M-12 / M-16 / M-15 / M-17** 四个交付脚本消除静默失败与硬编码基线（统一口径：失败即非零退出或显式标记不可信）。
14. **M-03 / L-01** 导出端点加 90 天跨度上限、改流式、统一限流粒度。
15. **M-02** `query` 加长度上限、正则白名单、预编译移出循环。
16. **M-08** 图片清洗改直接 `img.save` 重编码；**L-03** 单文件上传校验顺序对齐批量端点。
17. **M-09** `app_env` 统一 `strip().lower()`；**L-05** `ilike` 通配符转义。
18. **M-13** 侧车清理改 `rglob`；**M-14** 迁移批量化。
19. **M-19 / M-22 / M-23 / L-12** 前端开放跳转、反馈 URL 长度/成功提示、NaN 路由 id、错误 detail 截断。
20. **M-24 / L-17 / L-18 / L-19** 去掉无谓深监听、清理定时器、图片懒加载。

### P3 — 结构性治理（治本，建议单独排期）

21. **重复代码收敛**：优先级依次为 ① 三个生理训练脚本抽公共管线（L-23，并消除 `score_adapter` 与训练脚本的分叉）→ ② `StatsCard` 通用组件（M-26，影响 8+ 文件）→ ③ `@mixin bento-cell`（M-25，影响 6+ 文件）→ ④ `useAuthFormSubmit` + 共享 auth 样式（M-27）→ ⑤ `RiskTrendCard` 合并与改名（M-28 / L-16）。每完成一项同步清理对应 `ISS-0xx TODO`。
22. **统一抽象层**：错误提取（L-15）、导出端点封装（L-14）、`_para_text`（L-07）、`_compute_sha256`（L-10）各收敛到单一实现。
23. **Schema 补约束**（L-20 / L-21）、`load_metrics` 缓存（L-09）、CLI 统一 `safe_pickle`（L-08）、`L-02` 事件存储落库或明确文档口径。
24. **把「一致性」变成机器可检**：项目已有 AST 闸门与变异见证的实践，建议为 P0/P1 的接线类修复各补一条「翻转实现必须翻转断言」的闸门测试，避免同类漂移再次静默复发。

---

## 七、未验证与后续建议

- 本报告为静态审查结论，**未执行全量 pytest / 前端测试 / 构建，也未做动态渗透**；所有修复需按项目既有纪律配「可复现失败案例 + 改前/改后读数 + 一次真实变异（红→恢复绿）」再入库。
- M-21 中「后端是否真的拦截越权」、M-20 中「篡改角色能否进入咨询师工作台」需运行时用真实对象最小端到端验证；测试替身不能作为集成证据。
- 数据集/模型工件不在版本库，ML 脚本的「提交产物 == 单命令产物」需在有数据的机器上复算。
- 存量开放项 `init_sentry` 失败时 `/health/startup` 误记 ok（第二十七批遗留）未计入 53 条，建议与 M-07 的静默降级一并处理。

---

## 八、ROUND_35 整改闭环（2026-11-06）

> 本节是第一~七节的**状态更新**。第七节「未验证」清单已逐项处理；第六节 P2/P3
> 未落地项按性价比与回归风险取舍执行，未做的项在 8.3 明确列出理由。

### 8.1 验证缺口已补

| 缺口 | 处置 | 证据 |
|---|---|---|
| 未跑全量 pytest / 前端测试 / 构建 | 已跑，读数见 8.4 | 前端全量 1546 passed / 4 skipped（123 文件）、`vite build` rc=0 |
| M-20/M-21 运行时 RBAC 未验证 | 新增**真实对象**端到端闸门 | `backend/tests/api/test_round35_rbac_real_object_e2e.py` 3 passed：显式 pop `get_current_user` 测试替身，真实注册→真实 JWT→真实 `require_role`，断言 403 且同一 token 在 user 级端点 200（排除「401 伪装成 403」）；另证篡改 `CURRENT_USER` 不影响真实后端。`frontend/src/router/guard.realstore.test.ts` 3 passed：真实 Pinia store 计算 `isRoleVerified` + router 接线断言 |
| P1/P2 未各配专属变异 | 8 条后端接线闸门 + 4 条前端广播接线闸门 | `backend/tests/test_round35_wiring_gates.py` 8 passed、`frontend/src/utils/authBroadcast.wiring.test.ts` 4 passed；`backend/tests/tools/mutate_round35.py` **11/11 RED**、每处 try/finally 字节快照还原 sha256 一致、末臂全绿（日志随提交入库） |
| S-01 保留 `client_ip` 字段声明 | 彻底删除 | 采集（`submit_events`）、契约（`AnalyticsEventRecord`）、响应三处均移除；重生成 `backend/tests/contract/openapi.json`；`test_analytics_response_contract.py` 改钉「无 client_ip + 键集合精确」。契约快照同时补齐历史漂移（`/auth/profile` GET、`LoginUserBrief` 等） |
| 存量 `init_sentry` 误记 ok | **复核为已修复，台账过期** | `main.py:111-123` 在 `init_sentry()` 返回 False 时返回 `SKIPPED`，由 `record_step_sync` 记 skipped；`test_p2_63_round39_startup_truthfulness.py` + `test_sentry.py` 44 passed。已更正 `.workbuddy/memory/MEMORY.md` 的过期条目 |

### 8.2 既有失败基线修复（6 + 1 例）

- **6 例配置测试**：2026-11 生产部署校验新增 `MODEL_BERT_REVISION`（40 位 hash）/`JWT_ISSUER`/`JWT_AUDIENCE` 后，测试 fixture 未同步，构造 production Settings 时在测到目标前被拦下。补统一前置 `_PRODUCTION_DEPLOYMENT_ENV`（不放宽任何断言）；同时把 `test_production_rs256_still_requires_key_paths` 从「被无关部署消息喂成的假绿」改为钉真实 RS256 消息的强断言。
- **1 例 Redis 用例**：`test_request_reset_accepts_json_email` 接上 `memory_blocklist`，让断言落在请求/响应契约而非本机 6379 是否监听；fail-closed 语义仍由专属用例把守。
- **配置默认值漂移**：`app/core/model_engine/predict.py:861` 的 `getattr(settings, "text_bilingual_review_threshold", lower)` 私自引入第二份默认值来源（且会让上界塌到下界），改直接读 Settings 声明值。
- 修复后该组 `49 passed`。

### 8.3 P2/P3 执行结果与剩余排期

已落地：**M-03**（导出 90 天跨度 + 记录数上限 + `action_type` 长度 + 逐行 CSV 流；连带前端 `adminApi.ts`/`AdminOperationLogsPage.vue` 改 Blob 下载、重生成契约快照）、**L-01**、**M-08**（`img.save` 重编码 + GIF 逐帧）、**L-03**（单文件/批量上传共用校验顺序）、**L-20/L-21**（schema 约束）、**L-07**（`_para_text` 收敛 `_report_common.py`）、**M-14**（迁移 `fetchmany(500)` + 批量 UPDATE）、**M-17**（OOD 基线改读真实 `metrics.json`，缺文件报错退出）、**L-08**（`safe_joblib_load` + 受控根目录）、**L-09**（`load_metrics` 缓存）、**L-11**（CV 失败状态标记）、**L-02**（事件存储口径在源码注释明示）、**M-19/M-21/M-22/M-23/M-24**、**L-12~L-19**、**L-23**（三训练脚本抽 `physio_training_common.py`，5 个公共函数 × 3 脚本 `is` 全等、CLI 参数集合改前改后一致）、**M-27**（`useAuthFormSubmit`）、**M-25 部分**（5 个逐字重复卡片抽 `@mixin bento-cell`，postcss 比对「选择器→声明集合」DIFF_COUNT=0）、**M-28/L-16 部分**（业务卡片改名 `RiskTrendCard.vue`，旧名保留 re-export）。
- 新发现并修复：ROUND_34 只把 `refresh_bind_code` 的 else 分支改成指纹，其余 **4 处 `record_audit(detail=...)` 仍明文写绑定码**；本轮全部收敛为 `bind_code_fingerprint`，并由 G2 闸门钉死。

**剩余排期（有明确理由，非遗漏）**：
- **M-26** 通用 `StatsCard`：8 张卡的 `.stat-grid` 宽度、变体类名、`.stat-unit` 节点、权限门、`defineExpose` 均有实质差异，且把外壳移入通用组件会让各页 `<style scoped>` 选择器失效、改变 CSS 计算值。
- **M-28** 业务卡片组合通用图表：两套数据契约（0-1 `{date,value}` vs 0-100 `risk_score`）、配色、tooltip、legend/dataZoom 均不同，组合会改变视觉与行为。
- **M-25** 剩余 `RiskStatusCard.vue`（带 position/overflow/z-index 覆写）与 admin-dashboard 两张 B 套卡片（不同 radius/shadow/token 值）。
- 上述三项需**视觉回归 baseline** 才能证明等价，单独排期；本轮按「宁可少做也不破坏行为」处理。
- 两个 `train_physiological_{lightgbm,xgboost}.py` 文件头已标 DEPRECATED（由 `train_physiological.py --model` 取代），L-23 抽公共管线后仍保留，后续可评估删除。

### 8.4 实测读数

- **最终后端全量**：`44 failed, 7684 passed, 21 skipped, 187 warnings in 1261.58s (0:21:01)`（排除本机卡住的 `test_api_contract.py`）；改前 `51 failed, 7677 passed`，净变化 **-7 failed / +7 passed**。归类与 A/B 实证见 8.5。
- 变异见证：`mutate_round35.py` 11/11 RED，字节还原一致，末臂 backend 8 passed / frontend 7 passed / RBAC e2e 3 passed。
- 契约快照变动端点：`test_api_contract.py -k` 过滤 7 passed / 202 deselected。
- 前端全量：`123 files / 1546 passed / 4 skipped`；`vue-tsc --noEmit` rc=0；`vite build` rc=0。
- 既有失败组修复后 49 passed；Sentry 启动真实性闸门 44 passed。
- 约束口径：全量 `test_api_contract.py` 的 hypothesis 在本机 59 个端点通过后卡在训练端点的 Redis/Celery result store 重连（localhost:6379 无监听），与本轮 5 个变动 path 无交集；该文件已单独跑变动端点 7 passed，动态渗透与「有数据机器复算 ML 产物」仍需外部环境。

### 8.5 最终全量复验与失败归类（收尾）

**A/B 判据（按失败测试文件分组，而非精确 nodeid）**：

- v1 把 short-summary 的精确 nodeid 直接喂给 pytest，被两类噪声击穿：pytest 对非 ASCII 参数化 id 使用 `\uXXXX` 转义（脚本误做反转义），且部分 FAILED 行尾部被截断。首轮输出 `rc=4 / FAILED=0` 是**假读数**，已作废，**未据此下过任何结论**；保存完整输出后看到真实错误 `ERROR: not found: ...test_text_risk_levels`。
- v2 两臂口径一致：工作树跑 19 个失败文件 → `51 failed / 668 passed`，与全量 51 例**逐一对上**（FULL_ONLY=0）；逐文件字节回退 HEAD 后跑同一批文件 → `44 failed / 675 passed`；`restore byte-identical=True`、`new files restored=True`（52 tracked 备份 / 10 新文件 park）。
- 结论：**44 例既有、7 例本轮引入、HEAD_ONLY=0**。
- **终局校验**：最终全量的 44 例 FAILED 集合与 A/B 的 PREEXISTING 44 例**集合相等**（`final - pre = []`、`pre - final = []`），7 例 INTRODUCED 无一残留 ⇒ 修复完整、无连带回归。

**7 例本轮引入的分类与处置**（逐条论证见 `docs/P2_11_ROUND11_AUDIT.md` 文末「ROUND_35 全量复验后的基线同步」）：

| 类别 | 例数 | 处置 |
|---|---|---|
| 孤儿组件显形 | 2 | 修正既有漏报口径，登记清单与审计文档 |
| 扫描锚点行号漂移 | 2 | 同步基线行号，AST 断言未弱化 |
| #35 桶计数 | 1 | 按实测重算并逐批记账 |
| 上传接线断言被合法重构击穿 | 2 | 升级为 AST 调用链断言 |

- **孤儿组件 2 例**：M-28/L-16 把业务卡片改名为 `RiskTrendCard.vue` 后，闸门按 basename 判引用的旧 `<RiskTrendChart>` 标签消失，使同名的通用组件 `components/charts/RiskTrendChart.vue` 显形为孤儿。全仓实测它**一直**无引用方（`components.d.ts` 由 unplugin-vue-components 自动生成、不证明被使用；`charts.test.ts` 是纯逻辑测试、不 import 组件）。故 `ORPHAN_BASELINE` 9→10 是**修正既有漏报**，不是新增死代码、也不是放宽棘轮；组件已同步登记进 `_AUDITED_ORPHANS` 与审计文档，此后仍「只降不升」。按既有惯例不删除该组件。
- **行号漂移 2 例**：L-03 抽公共 helper 致 `user_upload.py` 的 `except (magic.MagicException, OSError)` 由 162 行前移到 149 行；`TestP235Round13Batch33Wiring.CANDIDATES` 同步为 149，断言仍用 AST 核对 handler 存在、所属函数与接线唯一性。
- **桶计数 1 例**：M-08 把 EXIF 清洗改为 `img.save` 重编码后新增「临时文件清理失败静默忽略」handler，真降级候选 331→332、X 118→119（W=111 不变）。分类器 C 桶只识别 `aclose/close/stop/cancel` 且只检查 handler 体内文本（此处仅 `pass`，`unlink` 在 try 体内），故如实判 X（真降级留档）；**未改分类器**，以免牵动其余 331 条历史裁定。
- **上传接线 2 例**：`test_sec_p2_003_stab_p2_009_sec_p2_005.py` 原按源码字面量切片断言 `process_uploaded_file` 出现在端点函数体内，被 L-03 的公共管线抽取击穿。改为 AST 逐环验证 `upload_file` / `upload_batch` → `_process_batch_file` → `_validate_and_save_upload` → `to_thread(process_uploaded_file, ...)`，不受注释与字符串字面量干扰，任一环断开即红，**强度高于原断言**。

**专属变异见证**：`backend/tests/tools/mutate_round35_ab.py` + 同名 `*_result.log`（仓库内可复现路径，非临时脚本）。4 个真实变异全部 RED —— M1 断上传调用链（杀 2 例）、M2 handler 行号前移一行（杀 2 例）、M3 删清理 handler（杀桶计数）、M4 新增未引用组件（杀孤儿棘轮 2 例）；每个变异 `try/finally` 字节还原并校验 sha256，末臂 `7 passed` GREEN ⇒ `PASS (4/4 RED, restored byte-identical, final GREEN)`。

**44 例既有失败（仍开放，非本轮引入）**：HEAD 版同样失败，本轮未改动相关实现。按模块分布：阈值/分级类 13（`test_core_utils` 8 + `test_iss02_risk_thresholds` 4 + `test_core_modules` 1）、金丝雀/回滚类 7、静态清点类 11（`test_p2_11` 7 + `test_p2_10` 1 + `test_p2_38` 1 + `test_p2_41` 2）、性能断言类 4、契约类 3、其它 6（expected_risk 3 / ml_breaker 1 / importlinter 1 / auto_rollback 1）。其中 `test_importlinter_config` 为既有环境性必红。逐项修复需另立项并各配专属变异。

**仍未闭环的缺口（如实记账）**：

- 动态渗透测试（真实多租户/越权运行时验证；本轮只做到真实对象 RBAC e2e 与静态接线闸门）。
- 有数据机器上的 ML 产物复算（`datasets/`、`data/external/` 不在版本库，CI 只能复算到 csv/json 层）。
- 8.3 列出的 M-26 / M-28 组合图表 / M-25 剩余卡片，需**视觉回归 baseline**。
- 全量 `test_api_contract.py` 的 hypothesis 在本机卡 Redis/Celery result store（localhost:6379 无监听）；变动端点已单独 7 passed。
- 44 例既有失败基线本身。
- 日志尾部 `SystemExit: 1` 是 pytest `cleanup_numbered_dir` 与本机 `sitecustomize.py` bulk-delete guard 在解释器退出阶段冲突，发生在 passed/failed 汇总**之后**，属环境噪声而非断言失败（CI 无此 shim）。
