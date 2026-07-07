# Phase 4: 专项审查 (Special Reviews) — 发现记录

> 本文件记录 Phase 4 专项审查的发现，对应 `uploads/计划.md` 第三节"前后端代码审查标准"中的专项维度，
> 以及第六、七、八节的视觉一致性、响应式、UX 与性能优化要求。
> 审查方式：4 个并行子代理分组的 10 项专项走查（代码层面 + 设计规范对照）。
> 非美化类问题追加到 `05-audit-issues.md`（ISS-095+），UI 美化类问题追加到 `07-visual-beautification.md`（VIS-001+）。

---

## 📅 时间信息

| 字段 | 值 |
| :--- | :--- |
| 阶段开始时间 | 2026-06-29 |
| 阶段完成时间 | 2026-06-29 |
| 专项数 | 10 |
| 子代理数 | 4（A 后端专项 / B 性能+错误 / C UI 视觉+响应式+美化 / D UX+性能优化） |
| 新发现问题数 | 66（29 非美化 ISS-095~ISS-123 + 37 美化 VIS-001~027 + VIS-050~059） |
| 关键发现 | 1 个 P0 阻塞（VIS-015 移动端侧边栏无法展开）/ 7 个 P1（ISS-095/100 + VIS-016/017/022/025/054） |

### 10 项专项分组

| # | 专项 | 对应计划章节 | 子代理 | 状态 | 发现问题数 |
| :- | :--- | :----------- | :----- | :--- | :--------- |
| 1 | 权限专项 | 三.1.4 / 三.2.4 | A | ✅ | 2（ISS） |
| 2 | 安全专项 | 三.2.4 / 八 | A | ✅ | 3（ISS） |
| 3 | 可观测性专项 | 三.2.4 / 八 | A | ✅ | 6（ISS） |
| 4 | 错误处理专项 | 三.1.5 / 三.2.5 | B | ✅ | 4（ISS） |
| 5 | 性能专项 | 三.1.3 / 三.2.3 | B | ✅ | 4（ISS） |
| 6 | 视觉一致性专项 | 六.1 | C | ✅ | 11（VIS） |
| 7 | 响应式专项 | 六.2 | C | ✅ | 10（VIS） |
| 8 | 前端美化专项 | 六.1.3 | C | ✅ | 6（VIS） |
| 9 | UX 提升专项 | 七 | D | ✅ | 8（2 ISS + 6 VIS） |
| 10 | 性能优化专项 | 八 | D | ✅ | 12（8 ISS + 4 VIS） |

---

## 1. 权限专项（计划三.1.4 / 三.2.4）

**走查结果**：⚠️ 部分通过

**发现问题**：
- **ISS-095（P1）** — 前后端权限矩阵不一致：前端定义 `admin.alerts.view` / `admin.silences.manage` 权限码，但后端 `require_permission` 装饰器从未校验这两个权限码，管理员越权访问告警/静默规则接口时后端不拦截
  - 证据：`frontend/src/utils/permissions.ts` 定义权限码，`backend/app/api/v1/admin.py` 路由装饰器缺失对应校验
  - 建议：后端补充 `@require_permission('admin.alerts.view')` / `@require_permission('admin.silences.manage')` 校验

- **ISS-097（P3）** — `frontend/src/router/guard.ts` 未校验 JWT exp 过期时间
  - 证据：guard 仅检查 token 是否存在，不解析 exp 字段，过期 token 在路由切换时不会被拦截
  - 建议：guard 中解析 JWT payload，exp 过期时跳转登录页

**横向排查**：与 Phase 3 ISS-041（用户端训练按钮 403）同属权限矩阵不一致问题，建议 Phase 5 统一修复

---

## 2. 安全专项（计划三.2.4 / 八）

**走查结果**：❌ 不通过

**发现问题**：
- **ISS-096（P2）** — WebSocket 在认证前调用 `accept()`，未授权连接可耗尽资源
  - 证据：`backend/app/api/v1/ws.py` 的 `websocket_endpoint` 先 `await websocket.accept()` 再校验 token，攻击者可建立大量未授权连接
  - 建议：先校验 token 再 accept()，校验失败时使用 `close(code=1008)` 关闭连接

- **ISS-098（P2）** — `/metrics` 端点无 `@limiter.limit` 速率限制
  - 证据：`backend/app/api/v1/observability.py` 的 metrics 端点仅靠 token 校验，无速率限制，可被暴力枚举或 DDoS
  - 建议：增加 `@limiter.limit("60/minute")` 限制

- **ISS-099（P2）** — CSP 报告日志直接记录 URL 字段未做 PII 脱敏
  - 证据：`backend/app/middleware/csp.py` 的 `log_csp_report` 将 report['document-uri'] / report['referrer'] 原样写入日志，可能包含用户敏感信息
  - 建议：对 URL 字段做 PII 脱敏（移除 query 参数、hash 用户 ID）

**横向排查**：与 Phase 2 ISS-008/009（localStorage 明文存储）同属安全合规问题，建议 Phase 5 统一安全加固

---

## 3. 可观测性专项（计划三.2.4 / 八）

**走查结果**：❌ 不通过

**发现问题**：
- **ISS-100（P1）** — 日志格式不含 `request_id` / `trace_id`，无法关联请求链路
  - 证据：`backend/app/core/logging_config.py` 的日志格式为 `%(asctime)s %(levelname)s %(name)s %(message)s`，无 request_id 字段；docstring 声称"支持请求链路追踪"但实现未注入
  - 建议：增加 `RequestIDFilter`，从请求头/上下文提取 request_id 注入日志记录

- **ISS-101（P2）** — `TraceLogFilter` 类已定义但从未注册到任何 handler
  - 证据：`backend/app/core/logging_config.py:45` 定义了 `TraceLogFilter`，但 `configure_logging()` 中从未调用 `handler.addFilter(TraceLogFilter())`
  - 建议：在所有 handler 上注册 TraceLogFilter

- **ISS-102（P2）** — Sentry `init_sentry` 未配置 `before_send`，后端异常事件缺 request_id tag
  - 证据：`backend/app/core/sentry.py` 的 `init_sentry` 调用 `sentry_sdk.init()` 无 `before_send` 回调，异常事件无法关联请求
  - 建议：增加 `before_send` 回调，注入 request_id/trace_id 作为 tag

- **ISS-103（P3）** — `ObservabilityExporter` 五个 `_safe_set_*` 方法静默吞异常，无失败计数指标
  - 证据：`backend/app/services/observability_exporter.py` 的 `_safe_set_gauge` / `_safe_set_counter` 等方法 `except Exception: pass`，导出失败时无任何指标可观测
  - 建议：增加 `observability_export_errors_total` 计数器

- **ISS-104（P3）** — WebSocket 认证失败路径无指标统计
  - 证据：`backend/app/api/v1/ws.py` 认证失败时仅 log，无 `ws_auth_failures_total` 指标
  - 建议：增加认证失败计数指标

- **ISS-105（P3）** — hostname 获取失败时降级为 "unknown"，多实例标识冲突
  - 证据：`backend/app/core/observability.py` 的 `get_hostname()` 失败时返回 "unknown"，多实例环境下所有实例 hostname 相同
  - 建议：降级时使用 hostname + PID 或 UUID 作为实例标识

**横向排查**：ISS-100/101/102 同属请求链路追踪缺失，建议 Phase 5 统一实现 request_id 注入机制

---

## 4. 错误处理专项（计划三.1.5 / 三.2.5）

**走查结果**：⚠️ 部分通过

**发现问题**：
- **ISS-106（P3）** — 网络错误/超时回显原始英文 axios 消息
  - 证据：`frontend/src/utils/request.ts` 的 catch 分支直接展示 `error.message`（如 "timeout of 5000ms exceeded"），未做中文映射
  - 建议：建立错误码到中文文案的映射表，统一展示

- **ISS-107（P2）** — 危机事件记录失败被静默吞掉且无重试/死信
  - 证据：`backend/app/services/risk_service.py` 的 `record_crisis_event` 在 `except Exception: logger.error()` 后直接返回，无重试机制，高危危机事件可能丢失
  - 建议：增加 Celery 重试任务 + 死信队列，失败时告警

- **ISS-108（P3）** — `isUnauthorizedRedirecting` 标志在 `router.onError` 路径未复位
  - 证据：`frontend/src/router/guard.ts` 的 `isUnauthorizedRedirecting` 在 `router.onError` 回调中未重置为 false，后续路由跳转可能被阻塞
  - 建议：在 `router.onError` 中显式重置标志

- **ISS-109（P3）** — 告警 webhook 持久化失败无重试机制，告警可能丢失
  - 证据：`backend/app/services/alert_service.py` 的 `send_webhook` 失败时仅 log，无重试
  - 建议：增加指数退避重试（3 次），失败后写入死信表

**横向排查**：ISS-107/109 同属关键数据丢失风险，建议 Phase 5 统一实现重试+死信机制

---

## 5. 性能专项（计划三.1.3 / 三.2.3）

**走查结果**：⚠️ 部分通过

**发现问题**：
- **ISS-110（P3）** — CSV/PDF 导出伪流式，整内容加载到内存
  - 证据：`backend/app/api/v1/reports.py` 的 CSV 导出用 `pd.DataFrame.to_csv()` 生成完整字符串再返回，PDF 用 `io.BytesIO()` 一次性生成，大数据量时内存峰值高
  - 建议：CSV 改用 `StreamingResponse` + 生成器，PDF 改用后台任务 + 文件流

- **ISS-111（P3）** — `ObservabilityExporter` 每 60s 串行 8 个 DB 查询
  - 证据：`backend/app/services/observability_exporter.py` 的 `export_metrics` 顺序执行 8 个 `session.execute()`，无并发
  - 建议：使用 `asyncio.gather` 并发查询

- **ISS-112（P3）** — `RiskService.assess_structured` 同步调用 SHAP `explain_prediction`
  - 证据：`backend/app/services/risk_service.py:assess_structured` 在请求处理中同步调用 SHAP，增加 200-500ms 延迟
  - 建议：SHAP 解释改为异步任务或延迟计算

- **ISS-113（P4）** — `terser` 在 `devDependencies` 中但未实际启用
  - 证据：`frontend/package.json` 声明 terser 依赖，但 `vite.config.ts` 的 `build.minify` 使用默认 esbuild
  - 建议：移除未使用的 terser 依赖，或显式配置 `build.minify: 'terser'`

**横向排查**：ISS-110 与 Phase 3 ISS-080（CSV 导出仅当前页）同属导出功能问题，建议 Phase 5 统一重构导出模块

---

## 6. 视觉一致性专项（计划六.1）

**走查结果**：❌ 不通过

**发现问题（11 个 VIS，详见 `07-visual-beautification.md`）**：
- **色彩类**：VIS-001（硬编码颜色散落）/ VIS-006（UserModelTrainingPage 引入 Tailwind 调色板冲突）
- **字体类**：VIS-002（字号未建立层级规范 24/20/16/12px）
- **间距类**：VIS-003（卡片间距不统一，未使用 4/8px spacing system）
- **圆角类**：VIS-004（圆角 4/6/8px 混用，未建立 radius token）
- **阴影类**：VIS-005（阴影强度不一致，未建立 shadow token）
- **图标类**：VIS-007（图标大小 16/18/20px 混用，线性/填充风格混用）
- **表格类**：VIS-008（表头样式不统一，行高/对齐/背景色各页不同）
- **弹窗类**：VIS-009（8 种弹窗宽度无 token，移动端无适配）
- **空状态类**：VIS-010（空状态文案不统一）
- **加载态类**：VIS-011（页面级/局部 loading 混用，未定义分层规范）

**横向排查**：视觉一致性问题遍布全项目，建议 Phase 5 统一建立 design token 系统（color/spacing/radius/shadow/typography）

---

## 7. 响应式专项（计划六.2）

**走查结果**：❌ 不通过（含 1 个 P0 阻塞）

**发现问题（10 个 VIS，详见 `07-visual-beautification.md`）**：
- **VIS-015（P0）** — 移动端侧边栏收起后无法再次展开 + BottomNav 未引入，移动端导航完全不可用
- **VIS-016（P1）** — 断点系统三套并存（useBreakpoint 576/768/992/1200/1400 vs MainLayout 768 vs LoginPage 960/480），响应式行为不一致
- **VIS-017（P1）** — 5 个列表页表格无移动端卡片化（用户/预警/复核/日志/模板）
- **VIS-012（P2）** — MainLayout 侧边栏在移动端固定不可收起，挤压内容
- **VIS-013（P2）** — 顶部栏用户菜单/通知/主题切换在移动端溢出
- **VIS-014（P2）** — 表格列过多时横向溢出无提示和固定列
- **VIS-018（P2）** — 弹窗在移动端宽度超出屏幕，无 max-width 约束
- **VIS-019（P2）** — 多按钮在移动端换行混乱，无统一 flex-wrap 策略
- **VIS-020（P2）** — 多列卡片在小屏压缩变形，无响应式列数调整
- **VIS-021（P3）** — 空状态插图在小屏过大，无 max-width 限制

**横向排查**：VIS-015 是 P0 阻塞，移动端导航完全不可用，Phase 5 必须优先修复；VIS-016 断点系统不统一是根本原因，建议先统一断点系统再修复其他响应式问题

---

## 8. 前端美化专项（计划六.1.3）

**走查结果**：⚠️ 部分通过

**发现问题（6 个 VIS，详见 `07-visual-beautification.md`）**：
- **VIS-022（P1）** — 登录页缺乏品牌感，背景单调，未使用柔和渐变或抽象图形
- **VIS-023（P2）** — 用户 Dashboard KPI 卡片图标不统一，色彩和趋势标识缺乏规范
- **VIS-024（P2）** — 管理 Dashboard 指标卡片无颜色编码，风险/告警类指标未使用清晰颜色区分
- **VIS-025（P1）** — 列表页视觉结构不统一（标题区/筛选区/操作区/表格区/分页区）
- **VIS-026（P2）** — 详情页信息分组不清晰，未使用信息分组卡片
- **VIS-027（P3）** — 深色模式下部分图表对比度不足，tooltip 背景色不随主题切换

**横向排查**：VIS-022/025 是 P1，影响用户第一印象和操作效率，建议 Phase 5 优先修复登录页和列表页视觉结构

---

## 9. UX 提升专项（计划七）

**走查结果**：❌ 不通过

**发现问题（2 ISS + 6 VIS，详见 `05-audit-issues.md` / `07-visual-beautification.md`）**：
- **ISS-114（P2）** — BentoCell 无 click 事件，卡片本身不可点击，Dashboard 快捷入口无法跳转
  - 证据：`frontend/src/components/BentoCell.vue` 无 `@click` emit，父组件无法监听点击
  - 建议：增加 click emit + hover 态视觉反馈

- **ISS-115（P3）** — LoginPage 登录按钮 type 默认未显式声明
  - 证据：`frontend/src/views/LoginPage.vue` 的 `<el-button>` 未声明 `type="primary"`，依赖默认样式
  - 建议：显式声明 `type="primary"`

- **VIS-050（P2）** — ActionColumn 删除确认对话框未用 danger 色，仅默认 primary
- **VIS-051（P2）** — 表单提交按钮 loading 状态不统一，部分按钮无 loading/disabled
- **VIS-052（P3）** — 批量操作未显示选中数量，执行前无确认
- **VIS-053（P2）** — 加载失败仅 toast 提示，无重试按钮
- **VIS-054（P1）** — 权限不足仅弹 toast，无友好 403 页面
- **VIS-055（P2）** — 缺少 Skeleton 骨架屏，页面加载时白屏或 spinner 居中

**横向排查**：VIS-051 与 Phase 3 ISS-045（异步按钮 loading 不统一）同源，建议 Phase 5 统一封装 `useAsyncLock` composable

---

## 10. 性能优化专项（计划八）

**走查结果**：❌ 不通过

**发现问题（8 ISS + 4 VIS，详见 `05-audit-issues.md` / `07-visual-beautification.md`）**：
- **ISS-116（P2）** — Sentry 同步加载进入首屏主包
  - 证据：`frontend/src/main.ts` 顶部 `import * as Sentry` 同步加载，增大首屏体积
  - 建议：改用动态 import 或 `async` 加载

- **ISS-117（P2）** — `request.ts` 无 5xx 自动重试
  - 证据：`frontend/src/utils/request.ts` 的拦截器对 5xx 直接抛错，无重试逻辑
  - 建议：增加 5xx 自动重试（2 次，指数退避）

- **ISS-118（P2）** — `request.ts` 无页面切换取消请求
  - 证据：路由切换时未调用 `AbortController.abort()`，旧页面请求继续执行
  - 建议：在路由守卫中调用 abort，取消未完成请求

- **ISS-119（P2）** — `admin_service.get_stats` 13 个顺序 COUNT 无缓存
  - 证据：`backend/app/services/admin_service.py:get_stats` 顺序执行 13 个 COUNT 查询，无 Redis 缓存
  - 建议：增加 Redis 缓存（TTL 60s）

- **ISS-120（P2）** — 全项目无 `selectinload` / `joinedload`，N+1 风险
  - 证据：所有 SQLAlchemy 查询使用默认懒加载，访问关系字段时触发 N+1 查询
  - 建议：在列表查询中使用 `selectinload(Model.relation)`

- **ISS-121（P2）** — Redis `from_url` 未设 `max_connections`
  - 证据：`backend/app/core/cache.py` 的 `redis.from_url(url)` 无 `max_connections` 参数
  - 建议：增加 `max_connections=50`

- **ISS-122（P2）** — `lighthouserc.js` 文件缺失，CI 流程将引用不存在的配置
  - 证据：`frontend/lighthouserc.js` 不存在，但 `package.json` 的 `perf:audit` 脚本引用它
  - 建议：创建 `lighthouserc.js` 配置文件

- **ISS-123（P3）** — App.vue 全屏 loading 遮罩可能阻塞 INP
  - 证据：`frontend/src/App.vue` 的全屏 loading 使用 `position: fixed` + 高 z-index，阻塞用户交互
  - 建议：改用非阻塞式 loading 或 Skeleton

- **VIS-056（P2）** — ECharts 实例未统一管理，存在重复初始化和内存泄漏风险
- **VIS-057（P2）** — 搜索框未使用 debounce，高频输入触发多次请求
- **VIS-058（P2）** — aria-label 覆盖率严重不足（全项目仅 3 处）
- **VIS-059（P3）** — 弹窗打开后焦点未进入弹窗，关闭后未回到触发元素

**横向排查**：ISS-116/122/123 + VIS-056/057 同属前端性能问题，建议 Phase 5 统一优化首屏加载和运行时性能

---

## 11. Phase 4 横向排查（Iron Rule #9）

### 11.1 重复问题剔除
- **子代理 A 原始 ISS-100（硬编码 dev metrics token "dev-only-metrics-token"）**：与已知 ISS-025 重复，已剔除，不记录为新问题
- **子代理 D 原始 ISS-112（Dashboard 异常静默横向扩展）**：合并到已知 ISS-046/ISS-082，不单独记录

### 11.2 同类问题横向排查
| 类别 | 关联问题 | 排查结论 |
| :--- | :--- | :--- |
| 权限矩阵不一致 | ISS-095, ISS-041 | 前后端权限码定义不同步，建议 Phase 5 统一权限矩阵 |
| 请求链路追踪缺失 | ISS-100, ISS-101, ISS-102 | 日志/Sentry/Tracing 均缺 request_id，建议统一实现 RequestIDFilter |
| 关键数据丢失风险 | ISS-107, ISS-109 | 危机事件/告警 webhook 失败无重试，建议统一实现重试+死信机制 |
| 导出功能问题 | ISS-110, ISS-080 | CSV 导出伪流式+仅当前页，建议统一重构导出模块 |
| 异步按钮 loading 不统一 | VIS-051, ISS-045 | 同源问题，建议统一封装 `useAsyncLock` composable |
| 安全合规问题 | ISS-096, ISS-098, ISS-099, ISS-008, ISS-009 | WebSocket/Metrics/CSP/localStorage 多处安全缺陷，建议 Phase 5 统一安全加固 |
| 前端性能问题 | ISS-116, ISS-122, ISS-123, VIS-056, VIS-057 | Sentry 同步加载/lighthouserc 缺失/loading 遮罩/ECharts 泄漏/debounce 缺失，建议统一优化 |
| 视觉一致性 | VIS-001~011 | 11 类视觉 token 缺失，建议统一建立 design token 系统 |
| 响应式 | VIS-012~021 | 10 个响应式问题，根因是断点系统不统一（VIS-016），建议先统一断点 |

---

## 12. Phase 4 闭环检查 (Gate Checklist)

- [x] 10 项专项审查全部完成
- [x] UI 美化类问题已全部记录至 `07-visual-beautification.md`
- [x] 非美化类问题已全部追加至 `05-audit-issues.md`
- [x] 同类问题已横向排查（Iron Rule #9）

---

## 📊 Phase 4 统计

| 维度 | 数值 |
| :--- | ---: |
| 走查专项数 | 10 |
| 子代理数 | 4 |
| 新发现非美化问题数 | 29（ISS-095 ~ ISS-123） |
| 新发现美化问题数 | 37（VIS-001~027 + VIS-050~059） |
| 合计 | 66 |

### 级别分布

| 级别 | 非美化（ISS） | 美化（VIS） | 合计 |
| :--- | ---: | ---: | ---: |
| P0 阻塞 | 0 | 1 | 1 |
| P1 高 | 2 | 5 | 7 |
| P2 中 | 14 | 24 | 38 |
| P3 低 | 12 | 7 | 19 |
| P4 建议 | 1 | 0 | 1 |
| **合计** | **29** | **37** | **66** |

### 子代理贡献分布

| 子代理 | 负责专项 | 非美化（ISS） | 美化（VIS） | 合计 |
| :--- | :--- | ---: | ---: | ---: |
| A | 权限+安全+可观测性 | 11 | 0 | 11 |
| B | 错误处理+性能 | 8 | 0 | 8 |
| C | 视觉一致性+响应式+前端美化 | 0 | 27 | 27 |
| D | UX 提升+性能优化 | 10 | 10 | 20 |
| **合计** | — | **29** | **37** | **66** |
