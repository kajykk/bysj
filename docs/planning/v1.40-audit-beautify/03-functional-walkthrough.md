# Phase 3: 功能走查 (Functional Walkthrough) — 发现记录

> 本文件记录 Phase 3 功能走查的发现，对应 `uploads/计划.md` 第二节"详细功能实现检查表"。
> 审查方式：以代码层面走查为主（项目存在 ISS-002 pytest collection error 与 ISS-003 前端单测失败，运行时启动受限），
> 验证各角色核心业务流程闭环、状态机合法性、权限边界。
> 发现的问题同步追加到 `05-audit-issues.md`（ISS-041 ~ ISS-094，共 54 个新问题）。

---

## 📅 时间信息

| 字段 | 值 |
| :--- | :--- |
| 阶段开始时间 | 2026-06-29 |
| 阶段完成时间 | 2026-06-29 |
| 走查角色数 | 6（admin / dr_wang / dr_chen / user_none / user_moderate / user_high） |
| 走查方式 | 代码层面走查 + 业务流程闭环验证 |
| 子代理数 | 4（用户端 / 咨询师端 / 管理端 / 通用+后端 API+业务流） |
| 新发现问题数 | 54（ISS-041 ~ ISS-094） |
| 关键发现 | 3 个 P0 阻塞（危机事件状态流转缺失 / 静默规则编辑缺失 / AdminSettings GDPR 区块缺失） |

### 6 角色说明
| # | 角色 | 账号 | 走查重点 |
| :- | :--- | :--- | :--- |
| 1 | 管理员 | admin | 8 模块：Dashboard / 模板 / 操作日志 / 危机事件 / 告警 / 静默规则 / 系统设置 / GDPR |
| 2 | 咨询师 A | dr_wang | 6 模块：Dashboard / 用户列表 / 用户详情 / 预警处理 / 复核任务 / 设置（绑定 user_none/user_low/user_moderate_anxiety） |
| 3 | 咨询师 B | dr_chen | 6 模块：同上（绑定 user_mild/user_borderline_moderate/user_high） |
| 4 | 无风险用户 | user_none | 8 模块：Dashboard / 风险评估 / 评估历史 / 干预计划 / 内容中心 / 预警信息 / 模型训练 / 设置 |
| 5 | 中度风险用户 | user_moderate | 同上 + 验证干预计划已激活、预警已触发 |
| 6 | 高风险用户 | user_high | 同上 + 验证危急预警、紧急干预计划 |

---

## 1. 通用功能检查表走查（计划二.1）

> 14 个检查项 × 前后端对照

| 检查项 | 前端检查 | 后端检查 | 走查结果 | 关联问题 |
| :----- | :------- | :------- | :------- | :------- |
| 登录认证 | 登录表单校验、错误提示、登录后跳转 | Token 生成、密码校验、账号状态校验 | ✅ 通过 | — |
| 权限控制 | 路由守卫、菜单权限、按钮权限 | API 鉴权、角色/权限校验 | ⚠️ 部分通过：用户端训练按钮对 user 角色必 403 | ISS-041 |
| 角色分流 | user/counselor/admin 首页跳转 | 用户角色准确返回 | ✅ 通过 | — |
| 401 处理 | Token 失效自动跳转登录 | 统一返回未认证错误 | ⚠️ 部分通过：详见 ISS-023 | ISS-023 |
| 403 处理 | 显示无权限页面或提示 | 后端拒绝越权请求 | ⚠️ 部分通过：训练端点 403 错误归因到后端服务 | ISS-041 |
| 表单提交 | 必填校验、格式校验、loading、防重复 | 参数校验、业务校验、事务处理 | ⚠️ 部分通过：异步按钮 loading/disabled 不统一；密码强度前端未强制 | ISS-045 / ISS-054 |
| 列表查询 | 分页、筛选、排序、空状态 | 分页参数、过滤条件、性能索引 | ⚠️ 部分通过：内容中心列表分页写死；操作日志 operatorName 筛选无效 | ISS-049 / ISS-084 |
| 详情页面 | 加载态、错误态、空态 | 资源不存在返回 404 | ⚠️ 部分通过：已处理预警返回 404 语义不准确；openDetail 失败 dialog 不关闭 | ISS-050 / ISS-070 |
| 文件上传 | 类型/大小校验、进度、失败提示 | 文件校验、存储、安全扫描 | ✅ 通过 | — |
| 文件导出 | 下载反馈、文件名正确 | MIME、权限、数据范围 | ⚠️ 部分通过：CSV 导出仅当前页；filename 未 RFC 5987 编码 | ISS-080 / ISS-092 |
| 国际化 | 中英文文案一致 | 错误码/错误消息可映射 | ✅ 通过 | — |
| 深色模式 | 页面、表格、弹窗、图表适配 | 无 | ✅ 通过 | — |
| 可观测性 | 前端错误上报、请求 ID 透传 | 日志、指标、Tracing、Sentry | ⚠️ 部分通过：Sentry 未关联 request_id（详见 ISS-022） | ISS-022 |
| WebSocket | 连接、重连、权限、消息展示 | 鉴权、订阅、广播、断开清理 | ✅ 通过 | — |

---

## 2. 用户端功能走查（计划二.2，6 角色 × 8 模块）

> 子代理 1 走查范围：admin / dr_wang / user_none / user_moderate / user_high
> 共发现 16 个新问题（ISS-041 ~ ISS-056）

### 2.1 用户首页（UserDashboard.vue）

**走查结果**：⚠️ 部分通过

**发现问题**：
- **ISS-046（P3）** — `UserDashboard.vue:638-646` `handleLogout` 未捕获 `auth.logout()` 异常
  - 证据：`await auth.logout()` 调用未包 try/catch，网络异常时未提示用户但页面已跳走
  - 建议：包 try/catch，异常时降级清理本地状态后跳转登录

### 2.2 风险评估（UserRiskPage.vue）

**走查结果**：⚠️ 部分通过

**发现问题**：
- **ISS-042（P2）** — `UserRiskPage.vue:2994-3017` 文本预测检测到危机关键词未弹危机对话框
  - 证据：文本预测分支检测到 crisis_keywords 后只 push 一条提示，未触发 `crisisDialogVisible.value = true`；与结构化评估融合逻辑不一致
  - 影响：用户在文本预测中表达自杀意念时无法触发紧急干预流程
  - 建议：统一在 `handlePredict` 与 `handleSubmit` 中检测到危机关键词后均触发危机对话框

- **ISS-047（P3）** — `UserRiskPage.vue:870-886` 结构化评估结果面板缺失"危机关键词"提示路径
  - 证据：结果面板仅显示风险等级、维度分数、建议，未展示触发危机关键词的具体文本片段
  - 建议：增加"危机关键词提示"卡片，红字提示用户寻求专业帮助

### 2.3 评估历史（UserAssessmentsPage.vue / UserAssessmentDetailPage.vue）

**走查结果**：⚠️ 部分通过

**发现问题**：
- **ISS-043（P2）** — `user_risk.py:95-103` + `UserAssessmentDetailPage.vue:34-39` 评估详情 summary/detail 后端永远返回 None
  - 证据：`/api/v1/user/assessments/{id}` 端点返回的 `summary` 与 `detail` 字段在 schema 中定义为 Optional 但 service 层从未填充
  - 影响：用户查看历史评估详情时看到空白，违反计划二.2"评估历史详情可见"
  - 建议：service 层生成评估摘要（risk_level + top_factors + suggestion），详情页填充维度明细

- **ISS-048（P3）** — `UserAssessmentsPage.vue:47-51` 导出按钮无 loading 状态
  - 证据：`handleExport` 调用 `riskApi.exportAssessments()` 期间按钮可重复点击
  - 建议：增加 `exportLoading` ref，导出期间禁用按钮

### 2.4 干预计划（UserInterventionPage.vue）

**走查结果**：✅ 通过

未发现新增 P1/P2 问题。

### 2.5 内容中心（UserContentPage.vue）

**走查结果**：⚠️ 部分通过

**发现问题**：
- **ISS-044（P2）** — `UserContentPage.vue:122-130` 收藏切换无 loading/防抖
  - 证据：`toggleFavorite` 直接调用 `contentApi.toggleFavorite(item.id)`，快速点击会发送多个相反请求导致状态不一致
  - 建议：增加 `favoriting: Set<number>` 状态，请求中禁用按钮

- **ISS-049（P3）** — `UserContentPage.vue:377-414` 列表分页写死 `page=1, page_size=9`，无分页控件
  - 证据：`loadList` 固定使用 page=1，模板中无 el-pagination 组件
  - 影响：内容超过 9 条时无法查看后续内容
  - 建议：增加分页控件，使用 `useListQueryState` 同步 URL

- **ISS-050（P3）** — `UserContentPage.vue:445-458` openDetail 失败时 dialog 不关闭
  - 证据：`try { const detail = await contentApi.getDetail(id); dialogVisible.value = true } catch { ElMessage.error }`，catch 中未重置 `dialogVisible`
  - 建议：catch 中显式 `dialogVisible.value = false`

### 2.6 预警信息（UserWarningsPage.vue）

**走查结果**：✅ 通过

未发现新增 P1/P2 问题。

### 2.7 模型训练（UserModelTrainingPage.vue）

**走查结果**：❌ 不通过

**发现问题**：
- **ISS-041（P1）** — `UserModelTrainingPage.vue:164-171, 434-451` "运行训练流水线"按钮对普通 user 角色必 403
  - 证据：按钮在 user 角色界面也显示，但后端 `/api/v1/admin/model/retrain` 要求 `admin.predict.audit` 权限；点击后前端报"后端服务异常"，错误归因错误
  - 影响：用户端"模型训练"模块对 user 角色完全不可用，违反计划二.2"模型训练"模块要求
  - 建议：前端按钮根据角色显隐（仅 admin 可见），或后端为 user 角色开放只读模式

- **ISS-051（P3）** — `UserModelTrainingPage.vue:427-432` 训练任务状态轮询无最大次数限制
  - 证据：`setInterval(pollTaskStatus, 3000)` 在任务 pending 时无限轮询，未设置 timeout/maxAttempts
  - 建议：增加 maxAttempts=100（5 分钟），超时后停止并提示用户

- **ISS-052（P3）** — `UserModelTrainingPage.vue:23-35` "模型就绪"标签硬编码
  - 证据：`<el-tag>模型就绪</el-tag>` 文本硬编码，未从后端 `task.status` 动态渲染
  - 建议：根据 status 渲染不同标签（pending/training/ready/failed）

- **ISS-053（P3）** — `UserModelTrainingPage.vue:229-244` 训练日志仅前端 push 的本地日志
  - 证据：`logs.value.push(...)` 添加的是前端生成的进度文本，未拉取后端真实训练日志
  - 建议：通过 WebSocket 或轮询 `/api/v1/admin/model/train_logs` 获取后端日志

### 2.8 用户设置（UserSettingsPage.vue）

**走查结果**：⚠️ 部分通过

**发现问题**：
- **ISS-054（P3）** — `UserSettingsPage.vue:573-602` 密码修改前端校验不强制强度
  - 证据：前端 rules 仅校验长度 ≥ 8，未校验大小写/数字/特殊字符组合
  - 建议：与后端 password policy 对齐，前端 rules 增加复杂度校验

- **ISS-055（P4）** — `UserSettingsPage.vue:199-209` 个人信息保存无邮箱格式前端校验
  - 证据：email 字段未使用 `type: 'email'` rule，用户可保存无效邮箱格式
  - 建议：增加 `{ type: 'email', message: '邮箱格式不正确' }` rule

- **ISS-056（P4）** — `UserSettingsPage.vue:647-667` 账户匿名化成功后未调用 `auth.logout`
  - 证据：`handleAnonymize` 成功后仅 ElMessage.success + 跳转登录，未清理本地 token
  - 建议：先 `await auth.logout()` 再跳转登录页

### 2.9 用户端横向排查（Iron Rule #9）

- **ISS-045（P2，横向）** — 异步按钮 loading/disabled 状态不统一
  - 证据：UserContentPage.toggleFavorite 无 loading；UserAssessmentsPage.handleExport 无 loading；UserModelTrainingPage.startTraining 有 loading；UserSettingsPage.handleSaveProfile 有 loading
  - 影响：用户可对无 loading 的按钮快速重复点击，触发重复请求
  - 建议：统一封装 `useAsyncLock` composable，所有异步按钮强制使用

- **数据范围隔离**：通过（user 角色仅能访问自己数据，所有 API 均通过 `current_user.id` 过滤）
- **状态机合法性**：通过（风险评估/预警/干预计划状态转换合法）

---

## 3. 咨询师端功能走查（计划二.3，2 角色 × 6 模块）

> 子代理 2 走查范围：dr_wang / dr_chen
> 共发现 15 个新问题（ISS-057 ~ ISS-071）

### 3.1 咨询师首页（CounselorDashboard.vue）

**走查结果**：⚠️ 部分通过

**发现问题**：
- **ISS-063（P2）** — `CounselorDashboard.vue:23-179` 缺失"待复核"统计卡
  - 证据：Dashboard 仅显示"我的用户数 / 待处理预警 / 今日新增评估"，无"待复核任务"统计
  - 影响：咨询师无法快速感知待复核任务数量，违反计划二.3 Dashboard 模块要求
  - 建议：增加"待复核任务"统计卡，点击跳转 CounselorReviewListPage

- **ISS-064（P2）** — `CounselorDashboard.vue:182-207` 缺失"风险用户概览"
  - 证据：Dashboard 下方列表显示所有绑定用户，无风险等级标识与排序
  - 建议：增加"高风险用户"Top 5 列表，按 risk_level 排序

### 3.2 用户列表（CounselorUsersPage.vue）

**走查结果**：⚠️ 部分通过

**发现问题**：
- **ISS-065（P2）** — `CounselorUsersPage.vue:12-46` + `counselor_service.py:144-151` 缺失"风险排序"功能
  - 证据：列表默认按 created_at 倒序，模板中无 risk_level 排序选项
  - 影响：咨询师无法快速定位高风险用户
  - 建议：增加排序下拉，后端 `list_assignments` 支持 `sort_by=risk_level`

- **ISS-069（P3）** — `CounselorUsersPage.vue:86-90` 邮箱列与后端返回字段不匹配
  - 证据：表格列绑定 `row.email`，但 `counselor_service.list_assignments` 因 PII 脱敏不返回 email 字段
  - 影响：邮箱列永远显示空白
  - 建议：移除邮箱列，或后端返回脱敏邮箱（如 `a***@example.com`）

### 3.3 用户详情（CounselorUserDetailPage.vue）

**走查结果**：❌ 不通过

**发现问题**：
- **ISS-057（P1）** — `CounselorUserDetailPage.vue:39-158` 缺失"风险轨迹 / 评估记录 / 干预记录"三个 tab
  - 证据：模板仅有"基本信息 / 预警记录"两个 tab；后端 `counselor_service.get_user_detail` 返回数据包含 risk_history/assessments/interventions，但前端未渲染
  - 影响：咨询师无法查看用户完整风险轨迹与历史评估，违反计划二.3"用户详情"模块要求
  - 建议：增加三个 tab，绑定后端返回数据；可参考管理端用户详情实现

### 3.4 预警处理（CounselorWarningsPage.vue）

**走查结果**：❌ 不通过

**发现问题**：
- **ISS-058（P1）** — `CounselorWarningsPage.vue:188-217` 缺失"升级"动作
  - 证据：操作列仅有"处理 / 忽略"按钮，无"升级"按钮；后端 `counselor.py` 也无 `/escalate` 端点
  - 影响：咨询师无法将高危预警升级到管理员，违反计划二.3"预警处理"模块要求
  - 建议：前端增加"升级"按钮（带备注输入），后端新增 `POST /api/v1/counselor/warnings/{id}/escalate`

- **ISS-059（P1）** — `CounselorWarningsPage.vue:424-449` "备注"功能未在 UI 实现
  - 证据：`handleCounselorWarning` 函数签名含 `note` 参数，但模板中无备注输入框；调用时 `note` 永远为空字符串
  - 影响：咨询师处理预警时无法记录处理思路，违反计划二.3"预警处理"模块要求
  - 建议：处理对话框增加 `el-input type="textarea"` 绑定 note

### 3.5 复核任务（CounselorReviewListPage.vue / CounselorReviewDetailPage.vue）

**走查结果**：❌ 不通过

**发现问题**：
- **ISS-060（P1）** — `CounselorReviewListPage.vue:218-232` 缺失"任务领取"功能
  - 证据：列表操作列仅有"查看"按钮，无"领取"按钮；`counselorApi` 中无 `assignReview` 方法
  - 影响：咨询师无法主动领取复核任务，违反计划二.3"复核任务"模块要求
  - 建议：前端增加"领取"按钮，后端 `counselor.py` 暴露 `POST /api/v1/counselor/reviews/{id}/assign`

- **ISS-061（P1）** — `review_service.py:130-144` `assign_review` 并发竞态条件
  - 证据：先 `select(ReviewTask).where(id=review_id)` 检查 status='pending'，再 `update(status='assigned', assignee_id=...)`，未加行锁
  - 影响：两个咨询师同时领取同一任务时，都会通过 status 检查并各自写入 assignee_id，最终数据不一致
  - 建议：`select(...).with_for_update()`，或在 UPDATE 语句中加 `WHERE status='pending'` 并检查 rowcount

- **ISS-062（P2）** — `review_service.py:159-173` 未分配任务可被任意咨询师直接 resolve/escalate
  - 证据：`resolve_review` 与 `escalate_review` 仅检查 `assignee_id == current_user.id`，但未先检查 status='assigned'
  - 影响：管理员手动创建的 pending 任务可被任意咨询师直接 resolve，绕过领取流程
  - 建议：在 resolve/escalate 前增加 `if task.status != 'assigned': raise BusinessException`

- **ISS-071（P3）** — `review_service.py:221-253` 复核统计卡与列表数据范围不一致
  - 证据：`get_review_stats` 统计所有 status 的任务（含已关闭），列表默认仅显示 status in ['pending', 'assigned']
  - 影响：统计卡数字与列表数量不匹配，咨询师困惑
  - 建议：统计卡按列表筛选条件统计，或明确标注"全部/待处理"

### 3.6 咨询师设置（CounselorSettingsPage.vue）

**走查结果**：⚠️ 部分通过

**发现问题**：
- **ISS-066（P2）** — `CounselorSettingsPage.vue:1-158` 缺失"通知偏好"功能
  - 证据：设置页仅有"基本信息 / 工作时间"两个 section，无"通知偏好"
  - 影响：咨询师无法配置预警通知渠道（邮件/站内信），违反计划二.3"设置"模块要求
  - 建议：增加"通知偏好"section，绑定 `counselor.notification_settings`

### 3.7 咨询师端横向排查（Iron Rule #9）

- **ISS-067（P2，横向）** — `withMockFallback` 在生产环境可能误导咨询师
  - 证据：`CounselorUsersPage` 与 `CounselorWarningsPage` 均使用 `withMockFallback(apiCall, mockData)`，生产环境后端异常时返回 mock 数据
  - 影响：咨询师看到的是 mock 数据而非真实数据，可能做出错误决策
  - 建议：生产环境禁用 mock fallback，改为显示错误提示

- **ISS-068（P2，横向）** — 预警状态机过于简单（仅 handle/ignore，缺 escalated 状态）
  - 证据：`WarningNotification.status` 仅 'unread/read/handled/ignored'，无 'escalated'
  - 影响：与 ISS-058 关联，无法实现升级流程
  - 建议：扩展状态机增加 'escalated' 状态

- **ISS-070（P3）** — `counselor.py:58-60` 已处理预警被错误报告为"不存在"（404 语义不准确）
  - 证据：`get_warning` 在 status in ['handled', 'ignored'] 时返回 404，而非 200 + 状态字段
  - 建议：返回 200 + warning 数据 + status 字段，前端按状态显示

---

## 4. 管理端功能走查（计划二.4，1 角色 × 8 模块）

> 子代理 3 走查范围：admin
> 共发现 20 个新问题（ISS-072 ~ ISS-091），含 3 个 P0 阻塞

### 4.1 管理首页（AdminDashboard.vue）

**走查结果**：⚠️ 部分通过

**发现问题**：
- **ISS-081（P2）** — `AdminDashboard.vue:318-355` 组件状态硬编码，部分组件健康状态始终为"正常"
  - 证据：`componentStatus` 数组中 `health: 'ok'` 硬编码，未从 `/api/v1/admin/health/components` 拉取
  - 影响：管理员看到虚假的健康状态
  - 建议：onMounted 时拉取真实组件状态

- **ISS-082（P2）** — `AdminDashboard.vue:326-362` `loadStats/checkHealth` 异常被完全静默吞掉
  - 证据：`try { ... } catch (e) { console.error(e) }`，未 ElMessage.error 也未上报 Sentry
  - 影响：管理员无法感知 Dashboard 数据加载失败
  - 建议：catch 中显示错误提示，并上报 Sentry

### 4.2 模板管理（AdminTemplatesPage.vue）

**走查结果**：❌ 不通过

**发现问题**：
- **ISS-075（P1）** — `AdminTemplatesPage.vue:89-113` 缺少删除功能
  - 证据：操作列仅有"编辑 / 启停"按钮，无"删除"按钮；后端 `admin.py` 也无 DELETE 端点
  - 影响：管理员无法删除废弃模板，违反计划二.4"模板增删改查"要求
  - 建议：前端增加"删除"按钮（二次确认），后端新增 `DELETE /api/v1/admin/templates/{id}`

- **ISS-083（P2）** — `AdminTemplatesPage.vue:80-87` 启停操作无二次确认
  - 证据：`handleToggleStatus` 直接调用 `adminApi.toggleTemplate(id)`，无 MessageBox.confirm
  - 影响：管理员误点击会立即生效，可能影响在用模板
  - 建议：增加 `ElMessageBox.confirm('确认启停该模板？')`

### 4.3 操作日志（AdminOperationLogsPage.vue）

**走查结果**：⚠️ 部分通过

**发现问题**：
- **ISS-080（P1）** — `AdminOperationLogsPage.vue:264-294` 导出 CSV 仅导出当前页，非全部筛选结果
  - 证据：`handleExportCSV` 直接将 `tableData.value`（当前页）转为 CSV，未调用后端导出接口
  - 影响：管理员导出的日志不完整，违反计划二.4"操作日志"模块要求
  - 建议：调用后端 `GET /api/v1/admin/operation_logs/export?...filters` 流式下载

- **ISS-084（P2）** — `AdminOperationLogsPage.vue:45-52` `filters.operatorName` 字段筛选无效
  - 证据：filters 表单含 operatorName 输入框，但 `loadLogs` 请求参数仅传 `operator_id`，未传 operatorName
  - 影响：管理员无法按操作人姓名搜索日志
  - 建议：后端 `/api/v1/admin/operation_logs` 支持 `operator_name` 模糊搜索

### 4.4 危机事件（AdminCrisisEventsPage.vue）

**走查结果**：❌ 不通过（P0 阻塞）

**发现问题**：
- **ISS-072（P0）** — `AdminCrisisEventsPage.vue` + `review.py` 危机事件状态流转功能完全缺失
  - 证据：
    - 前端仅有列表展示与筛选，无"处理 / 升级 / 关闭"按钮
    - 后端 `review_service.py:handle_crisis_event` 服务方法存在但未在 `review.py` 路由中暴露为 API 端点
  - 影响：管理员无法处理危机事件，高危用户无法闭环管理，违反计划二.4"危机事件"模块要求
  - 建议：
    1. 后端 `review.py` 新增 `POST /api/v1/admin/crisis-events/{id}/handle`、`/escalate`、`/close` 端点
    2. 前端操作列增加"处理 / 升级 / 关闭"按钮（带备注输入）

- **ISS-085（P2）** — `AdminCrisisEventsPage.vue:321-331` `handleSearch/handleReset` 未将筛选条件同步到 URL
  - 证据：handler 仅更新 local state，未调用 `router.replace({ query: ... })`
  - 建议：使用 `useListQueryState` 统一管理

- **ISS-086（P2）** — `review.py:56-78` 高危事件无权限分级控制
  - 证据：`GET /api/v1/admin/crisis-events` 仅要求 admin 角色，未区分 crisis_level
  - 影响：低权限管理员可查看所有高危事件详情
  - 建议：增加 `require_permission('admin.crisis.high')` 校验

### 4.5 告警管理（AdminAlertsPage.vue）

**走查结果**：⚠️ 部分通过

**发现问题**：
- **ISS-087（P2）** — `AdminAlertsPage.vue:185-204` 缺少"静默"和"升级"操作入口
  - 证据：操作列仅有"查看 / 确认"按钮，无"静默 / 升级"
  - 影响：管理员需切换到 AdminSilencesPage 才能创建静默规则，违反计划二.4"告警管理"模块要求
  - 建议：增加"静默"按钮（弹窗创建静默规则），"升级"按钮（升级到危机事件）

- **ISS-088（P2）** — `alert_lifecycle_service.py:67-314` 告警状态机两套机制并存且未统一
  - 证据：`Alert` 模型有 `status` 字段（active/acknowledged/resolved），`AlertLifecycleService` 又维护 `_transition_history` 内存状态
  - 影响：状态来源不明确，重启后内存状态丢失（详见 ISS-035）
  - 建议：统一使用 `Alert.status` 字段，废弃 `_transition_history`

- **ISS-089（P2）** — `alerts.py:436-526` 告警确认状态查询需 JOIN，但未实现
  - 证据：`GET /api/v1/alerts` 返回 `acknowledged_by_name` 字段，但 service 层未 JOIN User 表，字段始终为 None
  - 建议：`select(Alert, User.username).join(User, Alert.acknowledged_by == User.id)`

### 4.6 静默规则（AdminSilencesPage.vue）

**走查结果**：❌ 不通过（P0 阻塞）

**发现问题**：
- **ISS-073（P0）** — `AdminSilencesPage.vue:166-183` + `silences.py` 静默规则编辑/启停功能完全缺失
  - 证据：
    - 前端表格仅展示列表，无"编辑 / 启停 / 删除"操作列
    - 后端 `silences.py` 仅有 `POST /`（创建）和 `GET /`（列表），无 PUT/PATCH/DELETE 端点
  - 影响：管理员创建错误的静默规则后无法修改或停用，只能等过期，违反计划二.4"静默规则"模块要求
  - 建议：
    1. 后端新增 `PUT /api/v1/admin/silences/{id}`（编辑）、`PATCH /api/v1/admin/silences/{id}/status`（启停）、`DELETE /api/v1/admin/silences/{id}`（删除）
    2. 前端增加操作列与编辑对话框

### 4.7 系统设置（AdminSettingsPage.vue）

**走查结果**：❌ 不通过

**发现问题**：
- **ISS-074（P0）** — `AdminSettingsPage.vue` GDPR 区块完全缺失
  - 证据：全文 1-378 行无任何 GDPR 相关代码（gdpr / privacy / anonymize / export_data 关键字均无匹配）
  - 影响：管理员无法在管理端处理用户的 GDPR 请求，违反计划二.4"GDPR"模块要求
  - 建议：增加 GDPR 区块，复用 `gdpr.py` 后端 API（需先修复 ISS-079 让管理员可处理任意用户）

- **ISS-077（P1）** — `AdminSettingsPage.vue:1-378` 缺少"安全配置"和"通知配置"模块
  - 证据：仅有"基本配置 / 阈值配置 / 模型配置"，无"安全配置"（密码策略 / Token 过期 / 速率限制）与"通知配置"（邮件 / 短信 / Webhook）
  - 影响：违反计划二.4"系统设置"模块要求
  - 建议：增加两个 section，绑定 `admin_service.get_config(group='security'|'notification')`

- **ISS-078（P1）** — `admin_service.py:301-341` 配置 key 未做白名单校验，可写入任意键
  - 证据：`upsert_config(key, value)` 直接 `Config(key=key, value=value)`，无白名单校验
  - 影响：管理员（或被劫持的管理员账号）可写入恶意配置项，污染系统配置
  - 建议：维护 `ALLOWED_CONFIG_KEYS` 白名单，非白名单 key 拒绝写入

- **ISS-090（P2）** — `admin_service.py:120-130, 329-338` 阈值/配置变更未记录前后值
  - 证据：`OperationLog` 仅记录 `action='update_threshold'`，未记录 `before_value` 与 `after_value`
  - 影响：违反计划二.4"操作日志：关键操作有审计"的可追溯要求
  - 建议：`OperationLog.details` 增加 `before` / `after` 字段

### 4.8 GDPR/隐私（gdpr.py + AdminSettingsPage.vue GDPR 区块）

**走查结果**：❌ 不通过

**发现问题**：
- **ISS-079（P1）** — `gdpr.py:119-186` GDPR 端点仅支持用户本人操作，管理员无法处理任意用户
  - 证据：`export_my_data` / `anonymize_my_account` / `delete_my_account` 均使用 `current_user.id`，无 `target_user_id` 参数
  - 影响：管理员无法代为处理用户的 GDPR 请求（例如用户已注销账号但需导出数据），违反计划二.4"GDPR"模块要求
  - 建议：增加管理员专用端点 `POST /api/v1/admin/gdpr/export/{user_id}` 等，需 `require_admin`

- **ISS-091（P2）** — `gdpr_service.py:355-543` `anonymize_user` 未覆盖所有 PII 表
  - 证据：仅 anonymize 了 User / UserProfile / RiskAssessment，未覆盖 PhysiologicalRecord / StructuredAssessment / WarningNotification 等
  - 影响：匿名化后仍可通过生理数据关联到原用户，违反 GDPR"被遗忘权"
  - 建议：补充 anonymize 所有 PII 表，并增加 `anonymize_log` 审计

> **注**：ISS-013（gdpr.py:186 缺 ok 导入）已在 Phase 2 记录，此处仅确认未修复。

### 4.9 管理端横向排查（Iron Rule #9）

- **审计日志缺失横向**：ISS-076 + ISS-090 + 子代理 4 的 C.2-1 合并 — `admin.py` upsert_template / upsert_threshold / upsert_config 三个端点均未写 OperationLog，统一在 ISS-076 跟踪
- **危机/告警状态机横向**：ISS-072 + ISS-087 + ISS-088 — 状态机相关缺失统一在 Phase 5 修复时协调

---

## 5. 后端 API 功能走查（计划二.5，13 类）

> 子代理 4 走查范围：通用检查表 + 后端 API + 业务流闭环
> 共发现 3 个新问题（ISS-092 ~ ISS-094），C.2-1 合并到 ISS-076

| 类型 | 检查内容 | 走查结果 | 关联问题 |
| :--- | :------- | :------- | :------- |
| 请求模型 | Pydantic Schema 完整、字段约束正确 | ⚠️ 部分通过：见 ISS-015 / ISS-033 | ISS-015 / ISS-033 |
| 响应模型 | 响应结构稳定、字段命名一致 | ⚠️ 部分通过：评估详情 summary/detail 返回 None | ISS-043 |
| 错误响应 | 统一错误码、错误消息、request_id | ⚠️ 部分通过：ValueError 统一映射 404 语义不准确 | ISS-093 |
| 权限 | 每个敏感接口验证角色和资源归属 | ⚠️ 部分通过：高危事件无权限分级 | ISS-086 |
| 数据事务 | 多表写入有事务边界 | ⚠️ 部分通过：缺 with_for_update 详见 ISS-014/034/036/061 | ISS-014 / ISS-034 / ISS-036 / ISS-061 |
| 幂等性 | 重复提交安全 | ⚠️ 部分通过：upsert 端点无幂等键 | ISS-094 |
| 分页 | page/page_size 边界限制 | ⚠️ 部分通过：BatchExportRequest.data 缺 max_length | ISS-015 |
| 排序筛选 | 字段白名单 | ⚠️ 部分通过：operatorName 筛选无效 | ISS-084 |
| 文件接口 | 类型、大小、路径、安全响应头 | ⚠️ 部分通过：CSV Content-Disposition 未 RFC 5987 编码 | ISS-092 |
| WebSocket | 鉴权、订阅、断线清理 | ✅ 通过 | — |
| 后台任务 | Celery 任务重试、异常记录 | ✅ 通过 | — |
| 健康检查 | live/ready/startup 语义清晰 | ✅ 通过 | — |
| 指标 | Prometheus 指标命名、标签控制 | ⚠️ 部分通过：见 ISS-037 | ISS-037 |

### 5.1 详细发现

- **ISS-092（P3）** — `admin.py:324-327` CSV 导出 `Content-Disposition` filename 未 RFC 5987 编码
  - 证据：`Content-Disposition: attachment; filename="操作日志.csv"`，中文 filename 未编码
  - 影响：部分浏览器（如旧版 Safari）无法正确解析中文文件名
  - 建议：`filename*=UTF-8''{urlencode(filename)}`

- **ISS-093（P3）** — `admin.py:84-85` ValueError 统一映射 404，语义不准确
  - 证据：`except ValueError: raise HTTPException(404, "Resource not found")`，但 ValueError 可能是参数校验错误（应 422）或状态错误（应 409）
  - 建议：自定义 `NotFoundError` / `ValidationError` / `StateError` 异常类，分别映射 404/422/409

- **ISS-094（P3）** — `admin.py:73-86, 101-117, 146-156` upsert 端点无幂等键
  - 证据：`POST /api/v1/admin/templates` 等端点无 `Idempotency-Key` header 校验，重复请求会创建重复记录
  - 建议：支持 `Idempotency-Key` header，Redis 缓存 24 小时

---

## 6. 业务流闭环验证（计划三.2.2）

> 计划三.2.2 建议重点审查业务流

### 6.1 用户提交评估 → 后端计算风险 → 生成报告/预警 → 咨询师处理

**走查结果**：⚠️ 部分通过

**验证步骤**：
1. ✅ 用户提交结构化/文本评估 → 后端 `model_predict.py:save_assessment_result` 接收
2. ✅ 后端调用 `RiskAssessmentService.calculate_risk()` 生成 risk_level
3. ⚠️ 高危风险自动触发干预计划：`risk_service._auto_generate_intervention` 缺 `with_for_update`（ISS-014 P1），并发可能产生重复干预计划
4. ✅ 高危风险自动生成预警通知 → `WarningNotification` 表
5. ⚠️ 咨询师处理预警：缺失"升级"动作（ISS-058 P1），无法将高危预警升级到管理员
6. ⚠️ 危机关键词检测：文本预测分支未弹危机对话框（ISS-042 P2）

**关联问题**：ISS-014 / ISS-042 / ISS-058

### 6.2 管理员配置模板 → 用户/咨询师可见内容更新

**走查结果**：✅ 通过（新发现 ISS-076 P2）

**验证步骤**：
1. ✅ 管理员 `POST /api/v1/admin/templates` 创建模板 → `InterventionTemplate` 表
2. ⚠️ upsert_template 未写 OperationLog（ISS-076 P2，含 upsert_threshold / upsert_config 同类问题）
3. ✅ 用户端 `GET /api/v1/user/intervention/templates` 拉取最新模板
4. ✅ 咨询师端 `GET /api/v1/counselor/templates` 拉取最新模板

**关联问题**：ISS-076

### 6.3 告警产生 → 静默规则匹配 → 告警生命周期更新

**走查结果**：⚠️ 部分通过（ISS-035 P2 阻塞可追溯性）

**验证步骤**：
1. ✅ Prometheus / Alertmanager Webhook → `alerts.py:alertmanager_webhook` 接收
2. ✅ 静默规则匹配 → `SilenceRule` 表查询匹配项
3. ⚠️ 告警生命周期更新：`_transition_history` 仅内存存储（ISS-035 P2），重启丢失
4. ⚠️ 静默规则无法编辑/启停（ISS-073 P0），错误规则只能等过期
5. ⚠️ 告警状态机两套机制并存（ISS-088 P2），来源不明确

**关联问题**：ISS-035 / ISS-073 / ISS-088

### 6.4 GDPR 数据导出/删除 → 审计记录生成

**走查结果**：❌ 不通过（ISS-013 P1 阻塞，运行时必崩）

**验证步骤**：
1. ❌ 用户 `POST /api/v1/gdpr/export` 触发导出 → `gdpr.py:186` 缺 `ok` 导入，运行时 500（ISS-013 P1）
2. ⚠️ 即使修复 ISS-013，`anonymize_user` 未覆盖所有 PII 表（ISS-091 P2）
3. ⚠️ GDPR 端点仅支持用户本人操作，管理员无法代为处理（ISS-079 P1）
4. ⚠️ AdminSettingsPage 无 GDPR 区块（ISS-074 P0），管理员无 UI 入口
5. ✅ OperationLog 审计记录生成逻辑正确

**关联问题**：ISS-013 / ISS-074 / ISS-079 / ISS-091

### 6.5 模型训练任务 → 任务状态 → 结果展示

**走查结果**：✅ 通过

**验证步骤**：
1. ✅ 管理员 `POST /api/v1/admin/model/retrain` 触发 Celery 任务
2. ✅ 任务状态写入 `ModelTrainingJob` 表
3. ⚠️ 用户端 `UserModelTrainingPage` 训练按钮对 user 角色必 403（ISS-041 P1）
4. ⚠️ 训练日志仅前端 push 的本地日志（ISS-053 P3），未拉取后端真实日志
5. ✅ 模型训练完成后，风险评估接口自动加载新模型

**关联问题**：ISS-041 / ISS-053

---

## 7. Phase 3 闭环检查 (Gate Checklist)

- [x] 6 个角色走查全部完成（admin / dr_wang / dr_chen / user_none / user_moderate / user_high）
- [x] 通用功能检查表（计划二.1）全部覆盖（14 项 × 前后端对照）
- [x] 用户端 / 咨询师端 / 管理端 / 后端 API 检查表全部覆盖（8 + 6 + 8 + 13 模块）
- [x] 5 条业务流闭环验证全部完成（C.1 部分通过 / C.2 通过 / C.3 部分通过 / C.4 不通过 / C.5 通过）
- [x] 发现的问题已全部记录至 `05-audit-issues.md`（ISS-041 ~ ISS-094，共 54 个）
- [x] 同类问题已横向排查（Iron Rule #9）
  - 横向排查 1：异步按钮 loading/disabled 状态不统一 → 合并为 ISS-045
  - 横向排查 2：upsert 端点未写 OperationLog → 合并为 ISS-076（含子代理 4 的 C.2-1）
  - 横向排查 3：预警状态机过于简单 → ISS-068
  - 横向排查 4：withMockFallback 生产环境误导 → ISS-067
  - 横向排查 5：缺 with_for_update 并发问题 → 与 Phase 2 的 ISS-014/034/036 同类，新增 ISS-061（复核任务领取）

### Phase 3 关键成果

- **3 个 P0 阻塞问题**：ISS-072（危机事件状态流转缺失）/ ISS-073（静默规则编辑缺失）/ ISS-074（AdminSettings GDPR 区块缺失）
- **12 个 P1 高优问题**：含 ISS-041（用户端训练 403）/ ISS-057-060（咨询师端 4 个功能缺失）/ ISS-061（复核任务领取竞态）/ ISS-075-080（管理端 6 个功能缺失）
- **GDPR 业务流完全不通过**：ISS-013 + ISS-074 + ISS-079 + ISS-091 四个问题叠加，GDPR 模块从 UI 到后端均有阻塞
- **管理端功能缺失严重**：20 个新问题中含 3 P0 + 6 P1，多个计划二.4 要求的模块未实现

### Phase 3 统计

| 来源 | 新发现问题数 | P0 | P1 | P2 | P3 | P4 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| 子代理 1（用户端） | 16 | 0 | 1 | 4 | 9 | 2 |
| 子代理 2（咨询师端） | 15 | 0 | 5 | 7 | 3 | 0 |
| 子代理 3（管理端） | 20 | 3 | 6 | 11 | 0 | 0 |
| 子代理 4（通用+API+业务流） | 3 | 0 | 0 | 0 | 3 | 0 |
| **合计** | **54** | **3** | **12** | **22** | **15** | **2** |
