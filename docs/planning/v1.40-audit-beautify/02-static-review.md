# Phase 2: 静态审查 (Static Review) — 发现记录

> 本文件记录 Phase 2 静态审查的发现，对应 `uploads/计划.md` 第三节"前后端代码审查标准"。
> 审查方式：代码静态分析（无需运行时），由 4 个并行子代理深挖各维度。
> 发现的问题同步追加到 `05-audit-issues.md`，UI 美化类问题追加到 `07-visual-beautification.md`。

---

## 📅 时间信息

| 字段 | 值 |
| :--- | :--- |
| 阶段开始时间 | 2026-06-29 |
| 阶段完成时间 | 2026-06-29 |
| 审查维度数 | 10（前端 5 + 后端 5） |
| 子代理数 | 4（前端 2 + 后端 2） |
| 新发现问题数 | 33（ISS-008 ~ ISS-040） |
| 关键定位 | ISS-001 Bandit High = `backend/app/services/canary_manager.py:59` 的 `hashlib.md5()` |

---

## 1. 前端静态审查

### 1.1 代码规范符合性（计划三.1.1）

#### 检查项
- [x] TypeScript 类型不滥用 `any` — **不通过**：ISS-019
- [x] API 类型定义与后端响应保持一致 — 通过
- [~] Vue 组件职责单一（页面/可复用/API/Store 分离） — **部分不通过**：ISS-016
- [x] 命名统一（PascalCase.vue / useXxx.ts / xxxApi.ts / xxxTypes.ts） — 通过
- [x] 无无用代码、无用 import、调试日志 — 通过
- [x] 无重复实现 debounce/resize/formatters 等工具函数 — 通过
- [~] CSS/SCSS 使用统一变量，不硬编码颜色/间距/阴影 — **部分不通过**：ISS-017 / ISS-018

#### 发现详情

**ISS-019（P2）** — `frontend/src/api/request.ts:226` 使用 `as any` 绕过类型检查
- 证据：`error.response?.data as any` 等多处类型断言，掩盖 API 错误响应真实结构
- 建议：定义统一的 `ApiErrorPayload` 类型并在 request.ts 中使用

**ISS-016（P2）** — `frontend/src/views/user/UserRiskPage.vue` 3855 行巨型组件
- 证据：单文件 3855 行，远超计划三.1.1"Vue 组件职责单一"要求
- 建议：按职责拆分为 `RiskAssessmentForm` / `RiskHistoryChart` / `RiskAdvicePanel` / `RiskResourceList` 等子组件

**ISS-017（P2）** — `frontend/src/styles/variables.scss` 与 `frontend/src/styles/theme.scss` 主题变量重复定义
- 证据：两个 SCSS 文件都定义了 primary/success/warning/danger 等色值，但取值不完全一致
- 建议：合并为单一主题变量源，theme.scss 仅导入 variables.scss 并按主题覆盖

**ISS-018（P2）** — 前端多处 CSS 硬编码颜色
- 证据：`UserRiskPage.vue` 中 `#3b82c4`、`#d65a5a`、`#5a9e3a`、`#f0f0f0` 等颜色值硬编码；其他页面也存在
- 建议：统一使用 Element Plus CSS 变量或 SCSS variables

### 1.2 逻辑正确性（计划三.1.2）

#### 检查项
- [x] 路由权限与菜单权限一致 — 通过
- [x] 页面初始化顺序正确，避免未登录状态提前请求敏感 API — 通过
- [x] 表单提交有 loading 和防重复提交 — 通过
- [x] 异步请求有成功/失败/空/加载状态 — 通过
- [~] 列表页面分页/筛选/重置逻辑正确 — **部分不通过**：ISS-010 / ISS-020 / ISS-021
- [x] 编辑弹窗关闭后状态清理 — 通过
- [x] 图表数据缺失时不崩溃 — 通过
- [~] Token 过期/401/403/网络异常处理一致 — **部分不通过**：ISS-023
- [x] WebSocket 重连不重复订阅 — 通过
- [x] 上传/下载失败有清晰反馈 — 通过

#### 发现详情

**ISS-010（P1）** — `frontend/src/composables/useListQueryState.ts:23-34` debounce 导致所有列表页读取过期参数
- 证据：`watch` URL query 后用 `debounce(300ms)` 才同步到 state，用户在 300ms 内进入列表会读到上一次的页码/筛选
- 建议：移除 debounce 或仅对写入 URL 做 debounce，读取应立即同步

**ISS-020（P2）** — `frontend/src/views/counselor/CounselorUsersPage.vue:283-286` 重置按钮未清空 URL 状态
- 证据：reset handler 只更新 local state，未调用 router.replace，刷新页面后筛选条件仍存在
- 建议：reset 时同步清空 URL query

**ISS-021（P2）** — `frontend/src/views/counselor/CounselorReviewListPage.vue` 未使用 useListQueryState
- 证据：与其他列表页风格不一致，自己手写 URL 同步逻辑且漏掉 sort 参数
- 建议：复用 useListQueryState 统一所有列表页

**ISS-023（P2）** — `frontend/src/api/request.ts:177-181` 401 分支可能在非导航期间清空认证但不跳登录
- 证据：401 时直接 `clearAuth()` + `router.push('/login')`，但在 axios 内部调用栈中 `router.push` 可能被覆盖；且非 SPA 导航期间会丢失上下文
- 建议：使用 `window.location.href` 强制跳转，或集中到一个 `forceLogout()` 函数

### 1.3 性能优化（计划三.1.3）

#### 检查项
- [x] 路由页面懒加载已使用 — 通过
- [x] 大型图表按需加载或复用 ECharts 实例 — 通过
- [x] 模板中无高成本函数调用 — 通过
- [x] 列表项较多时分页/虚拟滚动/后端分页 — 通过
- [x] 无重复请求同一资源 — 通过
- [x] 组件卸载时清理定时器/事件监听/ResizeObserver/WebSocket — 通过
- [~] 首屏资源体积可控 — **部分不通过**：ISS-007（element-plus chunk 756KB，已在 Phase 1 记录）
- [ ] Lighthouse 性能/可访问性/最佳实践分数满足验收 — 待 Phase 4 性能专项

#### 发现详情

无新增 P1/P2 问题；ISS-007（element-plus chunk 756KB）延后至 Phase 4 性能专项处理。

### 1.4 安全性（计划三.1.4）

#### 检查项
- [~] 不在 localStorage/sessionStorage 存储不必要敏感信息 — **不通过**：ISS-008 / ISS-009
- [x] 展示富文本前使用净化处理 — 通过（DOMPurify 已配置）
- [x] 不使用 `v-html` 展示未净化内容 — 通过
- [x] 用户输入经过前后端校验 — 通过
- [x] 文件上传限制类型和大小 — 通过
- [x] 敏感操作有二次确认或额外校验 — 通过
- [x] 请求头/CSRF/CORS/CSP 配置与后端一致 — 通过
- [x] 不依赖隐藏按钮作为唯一权限控制 — 通过
- [x] 错误信息不暴露 Token/栈信息/内部路径 — 通过

#### 发现详情

**ISS-008（P1）** — `frontend/src/utils/authStorage.ts:51-58, 92` access_token 明文存 localStorage
- 证据：`localStorage.setItem('access_token', token)` 直接存明文，XSS 攻击可直接读取
- 影响：计划三.1.4 明确要求"不在 localStorage 存储不必要敏感信息"
- 建议：access_token 改存内存（Pinia store + sessionStorage 配合短期 expiry）；refresh_token 改用 HttpOnly Cookie

**ISS-009（P1）** — `frontend/src/views/user/UserRiskPage.vue:2670-2738` 敏感健康/心理数据明文存 localStorage
- 证据：风险评估明细、心理量表答案、生理数据等以明文形式 `localStorage.setItem('risk_cache_*', ...)` 缓存
- 影响：违反计划三.1.4 与 PII 保护要求；XSS 可窃取敏感健康数据
- 建议：移除本地缓存或改用 sessionStorage + 加密；优先让后端按需返回

### 1.5 错误处理机制（计划三.1.5）

#### 检查项
- [x] API 封装统一处理 HTTP 错误 — 通过（request.ts 已封装）
- [x] 页面级错误可恢复 — 通过
- [x] 表单错误定位明确 — 通过
- [x] 业务错误码可被用户理解 — 通过
- [x] 网络断开/超时/500 有统一提示 — 通过
- [~] Chunk 加载失败有处理 — **不通过**：ISS-011（无限刷新 bug）
- [~] 全局错误监控/Sentry 上报包含 request_id 或路由信息 — **部分不通过**：ISS-022

#### 发现详情

**ISS-011（P1）** — `frontend/src/router/index.ts:224-235` chunk 加载失败比较导致无限刷新
- 证据：`router.onError` 处理 chunk 加载失败时，比较 `localStorage.last_reload_time` 与当前时间差，但 `Date.now() - last_reload_time < 30000` 永远在 reload 后立即成立（因为 last_reload_time 已被设为 now），导致要么不刷新要么无限刷新
- 建议：使用 `sessionStorage.reload_count` 限制 5 秒内最多刷新 1 次

**ISS-022（P2）** — `frontend/src/plugins/sentry.ts:52-56` Sentry 上报未关联 request_id
- 证据：Sentry scope 配置了 user/role/route，但未从 axios response headers 抓取 `X-Request-Id` 并 setTag
- 建议：在 request.ts 响应拦截器中获取 `X-Request-Id`，存入 Pinia/Sentry scope；sentry.ts 启动时 setTag('request_id', currentRequestId)

---

## 2. 后端静态审查

### 2.1 代码规范符合性（计划三.2.1）

#### 检查项
- [~] Python 类型标注完整 — **部分不通过**：见 ISS-004（ruff 378 errors）
- [~] FastAPI 路由函数职责清晰，不堆积复杂业务逻辑 — **不通过**：ISS-028 / ISS-029 / ISS-030 / ISS-031 / ISS-032
- [~] 业务逻辑放在 service 层 — **部分不通过**：见上述路由堆积问题
- [~] 数据访问/事务/权限判断边界清晰 — **部分不通过**：ISS-014 / ISS-034 / ISS-036（事务边界缺失）
- [x] 配置项集中在 settings — 通过（但部分硬编码见 ISS-024 / ISS-025）
- [x] 日志使用结构化信息，不打印敏感数据 — 通过
- [x] 异步函数中不执行阻塞 I/O — 通过
- [x] Alembic 迁移与模型变更一致 — 通过

#### 发现详情

**ISS-028（P2）** — `backend/app/api/v1/model_predict.py:51-144` `save_assessment_result` 90+ 行业务逻辑堆积在路由文件
- 证据：路由 handler 内含风险评估结果生成、预警触发、干预计划生成、审计日志、PII 加密等多步逻辑
- 建议：抽取到 `RiskAssessmentService.save_assessment_result()`

**ISS-029（P2）** — `backend/app/api/v1/alerts.py:285-433` `alertmanager_webhook` 150+ 行业务逻辑在路由层
- 证据：webhook 处理含告警解析、静默规则匹配、生命周期更新、审计、通知发送等
- 建议：抽取到 `AlertLifecycleService.handle_alertmanager_webhook()`

**ISS-030（P2）** — `backend/app/api/v1/auth.py:190-279` `refresh_token` 端点业务逻辑应下沉 AuthService
- 证据：refresh_token 路由内含 token 验证、用户查询、新 token 签发、审计日志
- 建议：抽取到 `AuthService.refresh_token()`

**ISS-031（P2）** — `backend/app/api/v1/monitoring.py` 多端点在路由层直接 ORM 聚合查询
- 证据：`/metrics/summary`、`/metrics/users` 等端点直接 `select(...).group_by(...)`，未通过 service 层
- 建议：抽取到 `MonitoringService` 并增加缓存

**ISS-032（P2）** — `backend/app/api/v1/validation.py:42-100+` `ValidationJobStore` 类定义在路由文件
- 证据：模块级 `class ValidationJobStore:` 定义在路由文件中，违反分层
- 建议：移到 `app/services/validation_job_store.py`

### 2.2 逻辑正确性（计划三.2.2）

#### 检查项
- [~] API 入参校验完整 — **部分不通过**：ISS-015 / ISS-033（schema 缺 max_length）
- [x] 数据模型关系/外键/唯一约束符合业务 — 通过
- [x] 风险评估/预警/干预/复核/静默等状态机合法 — 通过
- [~] 并发场景下不会重复处理或数据覆盖 — **不通过**：ISS-014 / ISS-034 / ISS-036（缺 with_for_update）
- [x] 服务层异常不会绕过事务回滚 — 通过
- [x] 后台任务重试策略合理 — 通过
- [x] ML 推理失败时有 fallback 或明确错误 — 通过
- [x] 健康检查不阻塞主线程 — 通过
- [x] 缓存失效逻辑正确 — 通过
- [~] API 入参校验完整（含运行时必崩） — **不通过**：ISS-013（gdpr.py:186 缺 ok 导入）

#### 发现详情

**ISS-013（P1）** — `backend/app/api/v1/gdpr.py:186` GDPR 删除端点缺少 `ok` 函数导入，运行时必崩
- 证据：
  ```python
  # gdpr.py:186
  return ok(result)  # NameError: name 'ok' is not defined
  ```
- 影响：管理员触发 GDPR 删除时返回 500，违反计划二.4 "GDPR/隐私：操作有二次确认与审计"
- 建议：在文件头补充 `from app.core.response import ok`，并补充单测覆盖该端点

**ISS-014（P1）** — `backend/app/services/risk_service.py:675-696` `_auto_generate_intervention` 缺少 `with_for_update`，并发可能创建重复干预计划
- 证据：方法内先 `select(InterventionPlan).where(user_id == ...)`，再 `add(InterventionPlan(...))`，未加行锁
- 影响：用户重复提交评估时，两个并发事务可能同时读到"无计划"，各自创建一份，违反计划三.2.2"并发场景下不会产生重复处理"
- 建议：`select(...).with_for_update()` 或在 InterventionPlan.user_id 上加唯一约束（status='active'）

**ISS-015（P1）** — `backend/app/schemas/reports.py:36` `BatchExportRequest.data` 缺少 `max_length`，OOM 风险
- 证据：
  ```python
  # reports.py:36
  data: list[str]  # 无 max_length 约束
  ```
- 影响：调用方传入超大 list 时，PDF 生成任务可能 OOM，违反计划二.5 "分页 page/page_size 边界限制"
- 建议：`data: list[str] = Field(max_length=500)`，超过返回 422

**ISS-033（P2）** — 多个 schema 字段缺 `max_length`
- 证据（合集）：
  - `ReviewEscalateRequest.reason`（counselor.py）
  - `WarningHandleRequest.note`（warnings.py）
  - `ConsultationCreateRequest.next_plan` / `notes`（consultations.py）
  - `GroupCreateRequest.description`（groups.py）
  - `UserRiskReportRequest`（reports.py）
  - `StructuredCollectRequest.data_payload`（assessments.py）
- 建议：统一补充 `Field(max_length=N)`，N 按业务上限设定

**ISS-034（P2）** — `backend/app/services/warning_service.py:80-103` `mark_read` 缺 `with_for_update`，并发产生重复审计日志
- 证据：先 select warning，再 update status='read'，未加行锁；两个请求同时进来都会进入"未读→已读"分支并各写一条 audit log
- 建议：`select(WarningNotification).where(...).with_for_update()`

**ISS-035（P2）** — `backend/app/services/alert_lifecycle_service.py:88-91` `_transition_history` 仅内存存储
- 证据：状态转换历史存到 `self._transition_history: list[dict]` 实例属性，服务重启后丢失
- 影响：违反计划二.4 "告警管理：生命周期状态正确"中的可追溯要求
- 建议：持久化到 `AlertTransitionHistory` 表或 audit_log

**ISS-036（P2）** — `backend/app/tasks/scheduler.py:76-148` `_daily_risk_scan_impl` 缺 `with_for_update`
- 证据：扫描用户风险时，先 select 用户列表，再逐个查最新评估，未加锁；与 `risk_service._auto_generate_intervention` 类似的并发风险
- 建议：在批量扫描时使用 `with_for_update(skip_locked=True)` 避免重复处理

### 2.3 性能优化（计划三.2.3）

#### 检查项
- [x] 列表接口必须分页 — 通过
- [~] 查询避免 N+1 — **不通过**：ISS-026 / ISS-027
- [x] 高频接口使用合理索引 — 通过
- [x] 大文件/PDF/导出使用异步任务或流式响应 — 通过
- [x] 模型加载不在每次请求中重复执行 — 通过
- [x] Redis/缓存连接复用 — 通过
- [x] 健康检查接口轻量 — 通过
- [~] 指标标签避免高基数 — **部分不通过**：ISS-037（P3）
- [x] 后台任务有超时和重试限制 — 通过

#### 发现详情

**ISS-026（P2）** — `backend/app/tasks/scheduler.py:88-138` `daily_risk_scan` 任务 N+1 查询（约 4N 次）
- 证据：
  ```python
  for user in users:  # N 次
      latest = await session.execute(select(RiskAssessment).where(user_id=user.id).order_by(...))  # N 次
      profile = await session.execute(select(UserProfile).where(user_id=user.id))  # N 次
      plan = await session.execute(select(InterventionPlan).where(user_id=user.id))  # N 次
      # 还有 warning 查询
  ```
- 建议：使用 `selectinload(User.risk_assessments)` / `selectinload(User.profile)` 一次性预加载

**ISS-027（P2）** — `backend/app/tasks/scheduler.py:207-246` `daily_intervention_check` 嵌套循环 N+1 查询
- 证据：外层 for 干预计划，内层 for 任务，每个任务再查用户与评估
- 建议：用 `selectinload(InterventionPlan.tasks)` + `joinedload(InterventionTask.user)` 预加载

**ISS-037（P3）** — `backend/app/core/middlewares.py:60` metrics 中间件路径回退可能导致高基数标签
- 证据：`route_path = request.scope.get("route").path`，未匹配时回退到 `request.url.path`，原始 path 含 ID 时会产生高基数 Prometheus 标签
- 建议：未匹配时使用 `"/unmatched"` 统一标签

### 2.4 安全性（计划三.2.4）

#### 检查项
- [x] 密码哈希算法安全 — 通过（bcrypt 已配置）
- [~] Token 签名/过期/刷新策略合理 — **部分不通过**：ISS-039 / ISS-040
- [x] 所有敏感 API 进行认证与授权 — 通过（除 ISS-038 /version 端点）
- [x] 资源归属校验完整 — 通过
- [x] CORS 白名单不使用生产环境通配符 — 通过
- [x] 速率限制对登录/上传/导出/验证码接口生效 — 通过
- [x] PII 加密/脱敏/日志过滤有效 — 通过
- [x] 文件上传防路径穿越/类型伪造/超大文件 — 通过
- [x] SQLAlchemy 查询避免拼接 SQL — 通过
- [x] 生产环境不自动 `create_all`，依赖 Alembic — 通过
- [x] 错误响应不暴露栈和内部配置 — 通过
- [~] Bandit 安全扫描通过 — **不通过**：ISS-001 / ISS-012（hashlib.md5）+ 硬编码密钥 ISS-024 / ISS-025

#### 发现详情

**ISS-012（P1）** — `backend/app/services/canary_manager.py:59` 使用 `hashlib.md5()`（**ISS-001 定位结果**）
- 证据：
  ```python
  # canary_manager.py:59
  digest = hashlib.md5(str(user_id).encode()).hexdigest()[:8]
  return int(digest, 16) % 100
  ```
- 影响：Bandit B324 标记为 High（hashlib-insecure-hash-function），计划八.4 要求"高危安全问题为 0"
- 说明：该 md5 用于灰度发布百分比计算，非密码学用途，但 Bandit 仍判定为不安全
- 建议修复（二选一）：
  1. 改用 `hashlib.sha256(str(user_id).encode()).hexdigest()[:8]`（推荐，最简单）
  2. 标注为非安全用途：`hashlib.md5(..., usedforsecurity=False)`（Python 3.9+）
- 关联：本问题即 ISS-001 的 Phase 2 定位结果，需同步更新 ISS-001 详情与状态

**ISS-024（P2）** — `backend/app/api/v1/alerts.py:323` 硬编码开发环境密钥 `"dev-only-webhook-secret"`
- 证据：
  ```python
  # alerts.py:323
  if secret != "dev-only-webhook-secret":
      raise HTTPException(401)
  ```
- 影响：生产环境若误启用，密钥已公开；违反计划三.2.4 "配置项集中在 settings，不硬编码环境差异"
- 建议：移到 `settings.alertmanager_webhook_secret`，未配置时 503

**ISS-025（P2）** — `backend/app/api/v1/metrics.py:57` 硬编码开发环境令牌 `"dev-only-metrics-token"`
- 证据：与 ISS-024 同类问题
- 建议：移到 `settings.metrics_token`

**ISS-038（P3）** — `backend/app/api/v1/version.py:10-12` `/version` 端点无鉴权暴露版本信息
- 证据：`@router.get("/version")` 无 `Depends(get_current_user)`，返回 APP_VERSION
- 影响：攻击者可探测版本号匹配已知 CVE
- 建议：添加 `Depends(require_admin)` 或仅在 `/health` 中返回 major version

**ISS-039（P3）** — `backend/app/core/config.py:184` access_token 过期时间 120 分钟过长
- 证据：`ACCESS_TOKEN_EXPIRE_MINUTES: int = 120`
- 影响：access_token 被盗后窗口期过长，业界建议 15-60 分钟
- 建议：改为 60 分钟，refresh_token 维持 7 天

**ISS-040（P4）** — `backend/app/core/config.py:183` JWT 使用 HS256 对称签名
- 证据：`JWT_ALGORITHM: str = "HS256"`
- 影响：HS256 要求签名方与验证方共享同一密钥，多服务部署时密钥分发风险高
- 建议：后续多服务部署时迁移到 RS256（公钥验证 + 私钥签名）

### 2.5 错误处理机制（计划三.2.5）

#### 检查项
- [x] 全局异常处理已安装 — 通过（app/exceptions.py 已配置）
- [x] 业务/认证/权限/校验/系统异常区分明确 — 通过
- [x] 错误响应包含 request_id — 通过（middleware 已注入）
- [x] 服务层异常记录日志但不泄露敏感数据 — 通过
- [x] 后台任务失败有状态记录 — 通过
- [x] 外部依赖失败有降级或明确错误 — 通过
- [x] 数据库事务失败自动回滚 — 通过
- [x] WebSocket 异常断开有清理逻辑 — 通过

#### 发现详情

错误处理层无新增 P1/P2 问题；ISS-013（gdpr.py 缺 ok 导入）虽属运行时崩溃，但根因是导入缺失，归入 2.2 逻辑正确性。

---

## 3. Phase 2 闭环检查 (Gate Checklist)

- [x] 前端静态审查清单全部走查（1.1-1.5 共 5 节）
- [x] 后端静态审查清单全部走查（2.1-2.5 共 5 节）
- [x] 发现的问题已全部记录至 `05-audit-issues.md`
- [ ] UI 美化类问题已记录至 `07-visual-beautification.md`（Phase 4 美化专项时补充）
- [x] 同类问题已横向排查（Iron Rule #9）
  - 横向排查 1：所有"路由层业务逻辑堆积"已合并为 ISS-028 ~ ISS-032
  - 横向排查 2：所有"schema 缺 max_length"已合并为 ISS-033
  - 横向排查 3：所有"缺 with_for_update"已分别记录（ISS-014 / ISS-034 / ISS-036）
  - 横向排查 4：所有"硬编码密钥/令牌"已分别记录（ISS-024 / ISS-025）
  - 横向排查 5：所有"localStorage 明文存储"已分别记录（ISS-008 / ISS-009）

---

## 4. Phase 2 总结

### 4.1 关键成果
1. **ISS-001 Bandit High 已定位**：`canary_manager.py:59` 的 `hashlib.md5()`，已新增 ISS-012 作为修复工单
2. **发现 1 个运行时必崩端点**：`gdpr.py:186` 缺 `ok` 导入（ISS-013）
3. **发现 2 个 P1 安全合规问题**：前端 access_token / 敏感健康数据明文存 localStorage（ISS-008 / ISS-009）
4. **发现 3 个 P1 并发数据一致性问题**：缺 `with_for_update`（ISS-014 / ISS-034 / ISS-036）
5. **横向排查完成**：5 类同类问题已合并或分别记录

### 4.2 新增问题统计
| 级别 | 新增数 | 编号区间 |
| :--- | ---: | :--- |
| P1 | 8 | ISS-008 ~ ISS-015 |
| P2 | 21 | ISS-016 ~ ISS-036 |
| P3 | 3 | ISS-037 ~ ISS-039 |
| P4 | 1 | ISS-040 |
| **合计** | **33** | ISS-008 ~ ISS-040 |

### 4.3 下一步
- 进入 Phase 3 功能走查：6 角色 × 8 操作
- P0 仍为 0，可正常进入 Phase 3
- Phase 2 → Phase 3 闭环条件已满足（见上方 §3）
