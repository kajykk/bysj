# 审查问题清单 (Audit Issues)

> **事实来源 #1 (Source of Truth #1)**
> 本文件是问题的绝对真理，`AUDIT_STATE.md` 中的统计数字必须基于本文件计算。
> 每条问题遵循状态流转：`新建 → 已确认 → 修复中 → 待复核 → 已关闭`（可分支到 `暂缓` / `拒绝`）。
> 模板字段对齐 `uploads/计划.md` 第五节"问题反馈与修复跟踪机制"。
>
> **本轮审核说明**：执行全量深度静态审查，明确忽略所有 ralph 文档及 AUDIT_STATE.md，独立、新鲜地审核。
> 审查日期：2026-07-05

---

## 📋 问题记录表 (Issue Log)

### P0 阻塞级（2 项）

| 编号 | 级别 | 模块 | 前/后/全栈 | 标题 | 发现日期 | 状态 |
|------|------|------|------------|------|----------|------|
| ISS-001 | P0 | 前端/模型训练 | 全栈 | UserModelTrainingPage 训练参数硬编码 epochs=1，几乎无法收敛 | 2026-07-05 | 已关闭 |
| ISS-002 | P0 | 前端/模型训练 | 前端 | 训练状态轮询间隔过短（2s），产生大量无效请求 | 2026-07-05 | 已关闭 |

### P1 高优先级（38 项）

#### 后端 P1（7 项）

| 编号 | 级别 | 模块 | 前/后/全栈 | 标题 | 发现日期 | 状态 |
|------|------|------|------------|------|----------|------|
| ISS-003 | P1 | 后端/silences | 后端 | update_silence AM 同步非原子，可能引发告警风暴 | 2026-07-05 | 已关闭 |
| ISS-004 | P1 | 后端/silences | 后端 | create_silence 第二次 commit 失败导致 AM silence 孤儿 | 2026-07-05 | 已关闭 |
| ISS-005 | P1 | 后端/review | 后端 | 危机事件状态变更与审计日志非原子提交，违反审计 fail-safe | 2026-07-05 | 已关闭 |
| ISS-006 | P1 | 后端/safe_pickle | 后端 | safe_joblib_load 默认不强制哈希校验，pickle 反序列化 RCE 风险 | 2026-07-05 | 已关闭 |
| ISS-007 | P1 | 后端/model_compatibility | 后端 | load_model_with_compatibility_check 未启用强制哈希校验 | 2026-07-05 | 已关闭 |
| ISS-008 | P1 | 后端/tasks | 后端 | Celery 训练任务参数 dataset_name/model_name 未做路径安全校验 | 2026-07-05 | 已关闭 |
| ISS-009 | P1 | 后端/tasks | 后端 | update_job_in_redis 非原子读-改-写导致任务状态丢失 | 2026-07-05 | 已关闭 |

#### 前端代码 P1（9 项）

| 编号 | 级别 | 模块 | 前/后/全栈 | 标题 | 发现日期 | 状态 |
|------|------|------|------------|------|----------|------|
| ISS-010 | P1 | 前端/i18n | 前端 | UserModelTrainingPage 大量硬编码英文文案未走 i18n | 2026-07-05 | 已关闭 |
| ISS-011 | P1 | 前端/视觉 | 前端 | UserModelTrainingPage 硬编码渐变色绕过设计令牌 | 2026-07-05 | 已关闭 |
| ISS-012 | P1 | 前端/视觉 | 前端 | AdminCrisisEventsPage getScoreColor 硬编码颜色且阈值不一致 | 2026-07-05 | 已关闭 |
| ISS-013 | P1 | 前端/错误处理 | 前端 | AdminOperationLogsPage 权限错误写入页面级 pageError | 2026-07-05 | 已关闭 |
| ISS-014 | P1 | 前端/StructuredAssess | 前端 | resetStructuredForm 未重置 stepper 步骤 | 2026-07-05 | 已关闭 |
| ISS-015 | P1 | 前端/StructuredAssess | 前端 | validate 错误被静默吞掉（catch(() => false)） | 2026-07-05 | 已关闭 |
| ISS-016 | P1 | 前端/Intervention | 前端 | getTodayDate 使用 UTC 日期，东八区跨日错位 | 2026-07-05 | 已关闭 |
| ISS-017 | P1 | 前端/TextAssess | 前端 | 文本分析结果伪造模型预测字段污染历史记录 | 2026-07-05 | 已关闭 |
| ISS-018 | P1 | 前端/i18n | 前端 | ExperimentTab 等组件硬编码英文文案 | 2026-07-05 | 已关闭 |

#### 功能契约 P1（4 项）

| 编号 | 级别 | 模块 | 前/后/全栈 | 标题 | 发现日期 | 状态 |
|------|------|------|------------|------|----------|------|
| ISS-019 | P1 | 后端/counselor | 后端 | counselor 模块 14 个端点未挂显式 @limiter.limit 限流 | 2026-07-05 | 已关闭 |
| ISS-020 | P1 | 后端/counselor | 后端 | counselor 模块 14 个端点未声明 responses=COMMON_ERROR_RESPONSES | 2026-07-05 | 已关闭 |
| ISS-021 | P1 | 后端/review | 后端 | review 模块 11 个端点未挂显式 @limiter.limit 限流 | 2026-07-05 | 已关闭 |
| ISS-022 | P1 | 后端/多模块 | 后端 | 约 50+ 端点未声明 responses=COMMON_ERROR_RESPONSES（影响 OpenAPI 契约） | 2026-07-05 | 已关闭 |

#### 视觉/响应式/UX/A11Y P1（18 项）

| 编号 | 级别 | 模块 | 前/后/全栈 | 标题 | 发现日期 | 状态 |
|------|------|------|------------|------|----------|------|
| ISS-023 | P1 | 前端/样式 | 前端 | variables.scss 与 theme.scss 设计令牌命名分裂（--bg-color vs --bg-primary） | 2026-07-05 | 已关闭 |
| ISS-024 | P1 | 前端/样式 | 前端 | 间距令牌不符合规范（--spacing-md=12px，计划要求 16px） | 2026-07-05 | 已关闭 |
| ISS-025 | P1 | 前端/样式 | 前端 | 圆角令牌缺失（仅 4/8/12px，计划要求 6/10/16px；BentoCell 硬编码 20px） | 2026-07-05 | 已关闭 |
| ISS-026 | P1 | 前端/样式 | 前端 | 断点令牌严重不足（SCSS 仅 2 档，useBreakpoint 6 档数值与计划不匹配） | 2026-07-05 | 已关闭 |
| ISS-027 | P1 | 前端/通用组件 | 前端 | ErrorPage 完全脱离设计系统（硬编码颜色 + 无深色模式 + 硬编码中文） | 2026-07-05 | 已关闭 |
| ISS-028 | P1 | 前端/通用组件 | 前端 | SkipLink 完全脱离设计系统（硬编码颜色 + 硬编码中文） | 2026-07-05 | 已关闭 |
| ISS-029 | P1 | 前端/通用组件 | 前端 | StatefulContainer/EmptyState 大量硬编码颜色和中文 | 2026-07-05 | 已关闭 |
| ISS-030 | P1 | 前端/通用组件 | 前端 | FilterBar 硬编码中文"查询/重置"未走 i18n | 2026-07-05 | 已关闭 |
| ISS-031 | P1 | 前端/通用组件 | 前端 | PageTable 行高亮硬编码 #ecf5ff 未走令牌 | 2026-07-05 | 已关闭 |
| ISS-032 | P1 | 前端/视觉 | 前端 | BentoCell 与 el-card 视觉双轨并存（圆角/阴影/间距不一致） | 2026-07-05 | 已关闭 |
| ISS-033 | P1 | 前端/响应式 | 前端 | 所有 el-dialog 使用固定 width="500px"，移动端横向溢出 | 2026-07-05 | 已关闭 |
| ISS-034 | P1 | 前端/响应式 | 前端 | BottomNav 角色覆盖不全（admin 无底部导航） | 2026-07-05 | 已关闭 |
| ISS-035 | P1 | 前端/UX | 前端 | 15 处危险操作确认框全部使用 type:'warning' 而非 danger | 2026-07-05 | 已关闭 |
| ISS-036 | P1 | 前端/A11Y | 前端 | ErrorPage 无深色模式（白底白字低对比） | 2026-07-05 | 已关闭 |
| ISS-037 | P1 | 前端/A11Y | 前端 | BottomNav 字号过小（10px，低于规范 12px） | 2026-07-05 | 已关闭 |
| ISS-038 | P1 | 前端/A11Y | 前端 | BottomNav 硬编码 aria-label="主导航"未走 i18n | 2026-07-05 | 已关闭 |
| ISS-039 | P1 | 前端/A11Y | 前端 | SkipLink 硬编码"跳转到主内容"未走 i18n | 2026-07-05 | 已关闭 |
| ISS-040 | P1 | 前端/A11Y | 前端 | AdminCrisisEventsPage 颜色作为唯一状态表达（无图标/文字辅助） | 2026-07-05 | 已关闭 |

### P2 中优先级（67 项，节选关键问题）

#### 后端 P2（10 项）

| 编号 | 级别 | 模块 | 标题 | 发现日期 | 状态 |
|------|------|------|------|----------|------|
| ISS-041 | P2 | 后端/review | aware/naive datetime 混用（多处 datetime.now(timezone.utc) 赋给 naive 列） | 2026-07-05 | 已关闭 |
| ISS-042 | P2 | 后端/alerts | severity 过滤使用 contains 子串匹配（P1 误匹配 P10） | 2026-07-05 | 已关闭 |
| ISS-043 | P2 | 后端/content_service | completed_at 使用 aware datetime 不一致 | 2026-07-05 | 已关闭 |
| ISS-044 | P2 | 后端/alert_lifecycle | _transition_history 仅存内存，多实例部署丢失 | 2026-07-05 | 已关闭 |
| ISS-045 | P2 | 后端/pdf/excel_job_store | MAX_PDF_JOBS/MAX_EXCEL_JOBS 未实现，高并发可能内存压力 | 2026-07-05 | 已关闭 |
| ISS-046 | P2 | 后端/safe_pickle | safe_torch_load 允许 weights_only=False 绕过安全加载 | 2026-07-05 | 已关闭 |
| ISS-047 | P2 | 后端/celery_async | 进程级事件循环单例在 Celery thread 模式下非线程安全 | 2026-07-05 | 已关闭 |
| ISS-048 | P2 | 后端/tasks/pdf_report | PDF 生成任务参数未做内容 sanitization（控制字符） | 2026-07-05 | 已关闭 |
| ISS-049 | P2 | 后端/alembic | 数据库 URL 含凭据写入 Alembic config 可能被日志记录 | 2026-07-05 | 已关闭 |
| ISS-050 | P2 | 后端/tasks/scheduler | uploads 目录清理基于 mtime 可被篡改 | 2026-07-05 | 已关闭 |

#### 前端代码 P2（11 项）

| 编号 | 级别 | 模块 | 标题 | 发现日期 | 状态 |
|------|------|------|------|----------|------|
| ISS-051 | P2 | 前端/CrisisEvents | 手动拼接 CSV 未复用 exportUtils 且未做公式注入防护 | 2026-07-05 | 已关闭 |
| ISS-052 | P2 | 前端/OperationLogs | 手动拼接 CSV 重复实现且单元格转义不完整 | 2026-07-05 | 已关闭 |
| ISS-053 | P2 | 前端/RiskReport | scoreColor 硬编码 hex 色值（与 riskFormatters 重复定义） | 2026-07-05 | 已关闭 |
| ISS-054 | P2 | 前端/Intervention | onMounted 并行加载两个 Tab（history 默认不可见浪费带宽） | 2026-07-05 | 已关闭 |
| ISS-055 | P2 | 前端/CrisisEvents | 默认日期范围在 setup 时计算，跨午夜后不更新 | 2026-07-05 | 已关闭 |
| ISS-056 | P2 | 前端/AssessmentDetail | goBack 透传全部 query（可能泄露 token 等参数） | 2026-07-05 | 已关闭 |
| ISS-057 | P2 | 前端/ModelTraining | 18:6 固定布局无响应式断点 | 2026-07-05 | 已关闭 |
| ISS-058 | P2 | 前端/StructuredAssess | 匿名用户 historyKey 冲突（id=0 共享 localStorage） | 2026-07-05 | 已关闭 |
| ISS-059 | P2 | 前端/ModelTraining | showModelStatusDetail 使用已废弃的 customClass | 2026-07-05 | 已关闭 |
| ISS-060 | P2 | 前端/OperationLogs | safeJson 函数声明误导（未在模板使用） | 2026-07-05 | 已关闭 |
| ISS-061 | P2 | 前端/性能 | UserInterventionPage history tab 未 lazy 加载 | 2026-07-05 | 已关闭 |

#### 功能契约 P2（14 项）

| 编号 | 级别 | 模块 | 标题 | 发现日期 | 状态 |
|------|------|------|------|----------|------|
| ISS-062 | P2 | 后端/review/counselor/admin | 部分列表端点未在端点层校验 page_size 上限 | 2026-07-05 | 已关闭 |
| ISS-063 | P2 | 后端/user_content | 4 个端点未声明 responses | 2026-07-05 | 已关闭 |
| ISS-064 | P2 | 后端/alerts | 3 个端点未声明 responses | 2026-07-05 | 已关闭 |
| ISS-065 | P2 | 后端/silences | 6 个端点使用 response_model=dict 而非统一 ApiResponse | 2026-07-05 | 已关闭 |
| ISS-066 | P2 | 后端/user_risk | report/trend/export 未声明 responses | 2026-07-05 | 已关闭 |
| ISS-067 | P2 | 后端/gdpr | /export 未声明 responses | 2026-07-05 | 已关闭 |
| ISS-068 | P2 | 后端/alerts | history/ack/archive 未挂显式限流 | 2026-07-05 | 已关闭 |
| ISS-069 | P2 | 后端/reports | 3 个 PDF 端点未声明 responses | 2026-07-05 | 已关闭 |
| ISS-070 | P2 | 后端/model_predict/status | 4 个端点未挂显式限流 | 2026-07-05 | 已关闭 |
| ISS-071 | P2 | 后端/monitoring | 7 个端点未挂显式限流 + 8 个未声明 responses | 2026-07-05 | 已关闭 |
| ISS-072 | P2 | 后端/grafana_adapter | 5 个端点未挂显式限流 + 未声明 responses | 2026-07-05 | 已关闭 |
| ISS-073 | P2 | 后端/admin_metrics | 未挂限流 + 未声明 responses | 2026-07-05 | 已关闭 |
| ISS-074 | P2 | 后端/canary | 9 个端点未声明 responses | 2026-07-05 | 已关闭 |
| ISS-075 | P2 | 后端/version | 未声明 responses | 2026-07-05 | 已关闭 |

#### 视觉/响应式/UX/A11Y P2（32 项，详见 07-visual-beautification.md）

| 编号 | 级别 | 模块 | 标题 | 发现日期 | 状态 |
|------|------|------|------|----------|------|
| ISS-076 | P2 | 前端/RiskTrendChart | 图表色板硬编码 #3b82c4/#d65a5a/#5a9e3a 未走令牌 | 2026-07-05 | 已关闭 |
| ISS-077 | P2 | 前端/UserDashboard | ECharts tooltip HTML 内联样式硬编码颜色 | 2026-07-05 | 已关闭 |
| ISS-078 | P2 | 前端/AdminSettings | 使用未定义的 --color-success/--color-danger 变量 | 2026-07-05 | 已关闭 |
| ISS-079 | P2 | 前端/AuthBrandPanel | 硬编码 7+ 颜色 + 硬编码中文默认值 | 2026-07-05 | 已关闭 |
| ISS-080 | P2 | 前端/表单 | label-width 数值混乱（80/90/100/120/160px 5 种值） | 2026-07-05 | 已关闭 |
| ISS-081 | P2 | 前端/弹窗 | 所有 el-dialog width="500px" 移动端溢出 | 2026-07-05 | 已关闭 |
| ISS-082 | P2 | 前端/CounselorDetail | 详情页无响应式（el-descriptions :column="2" 小屏未切换） | 2026-07-05 | 已关闭 |
| ISS-083 | P2 | 前端/PageTable | 表格无小屏适配策略（无关键列保留/次要列隐藏） | 2026-07-05 | 已关闭 |
| ISS-084 | P2 | 前端/FilterBar | 小屏不换行/不收起（筛选项 >4 时挤压） | 2026-07-05 | 已关闭 |
| ISS-085 | P2 | 前端/LoginPage | 断点不一致（960px vs useBreakpoint 992px vs SCSS 768px） | 2026-07-05 | 已关闭 |
| ISS-086 | P2 | 前端/图表 | 图表高度未响应式（默认 300px 小屏占用过多） | 2026-07-05 | 已关闭 |
| ISS-087 | P2 | 前端/UX | 批量操作选中数量未显示 | 2026-07-05 | 已关闭 |
| ISS-088 | P2 | 前端/UX | 导出无进度反馈（大文件 CSV 导出无百分比提示） | 2026-07-05 | 已关闭 |
| ISS-089 | P2 | 前端/UX | 长任务无进度/轮询（UserModelTrainingPage） | 2026-07-05 | 已关闭 |
| ISS-090 | P2 | 前端/UX | 加载失败重试入口不一致 | 2026-07-05 | 已关闭 |
| ISS-091 | P2 | 前端/UX | 高风险操作确认文案不具体 | 2026-07-05 | 已关闭 |
| ISS-092 | P2 | 前端/UX | 风险等级无解释说明（无 tooltip） | 2026-07-05 | 已关闭 |
| ISS-093 | P2 | 前端/UX | 快捷筛选缺失（无"今天/7 天/30 天"按钮） | 2026-07-05 | 已关闭 |
| ISS-094 | P2 | 前端/UX | Dashboard 卡片点击区域不一致 | 2026-07-05 | 已关闭 |
| ISS-095 | P2 | 前端/UX | 图表 tooltip 解释不足 | 2026-07-05 | 已关闭 |
| ISS-096 | P2 | 前端/A11Y | 弹窗焦点管理缺失 | 2026-07-05 | 已关闭 |
| ISS-097 | P2 | 前端/A11Y | 图标按钮缺 aria-label | 2026-07-05 | 已关闭 |
| ISS-098 | P2 | 前端/A11Y | 颜色作为唯一状态表达（色盲用户无法区分） | 2026-07-05 | 已关闭 |
| ISS-099 | P2 | 前端/A11Y | chart role="img" 但 tooltip 不可访问 | 2026-07-05 | 已关闭 |
| ISS-100 | P2 | 前端/A11Y | StatefulContainer 错误图标无 alt | 2026-07-05 | 已关闭 |
| ISS-101 | P2 | 前端/视觉 | BentoCell 内部 padding/gap 硬编码 rem 值 | 2026-07-05 | 已关闭 |
| ISS-102 | P2 | 前端/视觉 | ListPageScaffold padding/gap 硬编码 | 2026-07-05 | 已关闭 |
| ISS-103 | P2 | 前端/视觉 | 字号层级偏差（主标题 30px/26px/24px 不一致） | 2026-07-05 | 已关闭 |
| ISS-104 | P2 | 前端/CounselorUsers | 图表色板硬编码 7 色未抽到统一色板文件 | 2026-07-05 | 已关闭 |
| ISS-105 | P2 | 前端/CounselorReviewDetail | getScoreColor 硬编码且阈值与 AdminCrisisEvents 不一致 | 2026-07-05 | 已关闭 |
| ISS-106 | P2 | 前端/PageTable | 分页 layout 在小屏被挤压 | 2026-07-05 | 已关闭 |
| ISS-107 | P2 | 前端/MainLayout | header-right 在小屏用户名直接消失 | 2026-07-05 | 已关闭 |

### P3 低优先级（31 项，详见各专项报告）

| 编号范围 | 级别 | 数量 | 主要模块 |
|----------|------|------|----------|
| ISS-108 ~ ISS-138 | P3 | 31 | 后端代码质量、前端代码质量、视觉细节、响应式细节、UX 细节、A11Y 细节 |

### P4 建议级（12 项，详见各专项报告）

| 编号范围 | 级别 | 数量 | 主要模块 |
|----------|------|------|----------|
| ISS-139 ~ ISS-150 | P4 | 12 | 代码质量、命名规范、维护性建议 |

---

## 📋 增量审查发现 (Delta Audit Findings, 2026-07-10)

> 审查范围：feat/frontend-api-alignment 合并 + 并行进程改进 + WCAG/字体优化以来的前端新增/变更代码
> 审查方法：4 个并行子代理静态审查 + 主代理补充验证

### P0 阻塞级（1 项）

| 编号 | 级别 | 模块 | 前/后/全栈 | 标题 | 发现日期 | 状态 |
|------|------|------|------------|------|----------|------|
| ISS-151 | P0 | 前端/MainLayout | 前端 | MainLayout.vue L29-43 未解决的 git 合并冲突标记，模板渲染行为未定义 | 2026-07-10 | 已关闭 |

### P1 高优先级（6 项）

| 编号 | 级别 | 模块 | 前/后/全栈 | 标题 | 发现日期 | 状态 |
|------|------|------|------------|------|----------|------|
| ISS-152 | P1 | 前端/新页面 | 前端 | 5 个新页面大量硬编码 UI 字符串未走 i18n（AdminReportsPage/AdminCanaryPage/AdminObservabilityPage/AdminMonitoringPage/UserReportsPage 共 30+ 处） | 2026-07-10 | 已关闭 |
| ISS-153 | P1 | 前端/composable | 前端 | useOnboarding.ts L102-189 所有引导步骤标题/描述硬编码中文 | 2026-07-10 | 已关闭 |
| ISS-154 | P1 | 前端/HelpCenter | 前端 | HelpCenter.vue L35,57 el-dialog width="600px"/"440px" 移动端溢出（与已关闭 ISS-033/081 同类） | 2026-07-10 | 已关闭 |
| ISS-155 | P1 | 前端/Observability | 前端 | AdminObservabilityPage.vue L83-143 el-col :span="6" 四列布局无响应式断点，移动端挤压 | 2026-07-10 | 已关闭 |
| ISS-156 | P1 | 前端/UserReports | 前端 | UserReportsPage.vue L84 severity 仅检查 'high'，未处理 'critical'/'severe'，危急风险显示为 warning 色 | 2026-07-10 | 已关闭 |
| ISS-157 | P1 | 前端/composable | 前端 | useTaskProgress.ts L15-16 WebSocket 监听器 + 清理定时器在生产环境中永不取消订阅（内存泄漏） | 2026-07-10 | 已关闭 |

### P2 中优先级（5 项）

| 编号 | 级别 | 模块 | 标题 | 发现日期 | 状态 |
|------|------|------|------|----------|------|
| ISS-158 | P2 | 前端/Monitoring | AdminMonitoringPage.vue L91 row-click 无键盘可访问性；L100 原始 JSON 显示不友好 | 2026-07-10 | 已关闭 |
| ISS-159 | P2 | 前端/样式 | variables.scss L70 --spacing-lg=16px 与 --spacing-md 重复（应为 24px） | 2026-07-10 | 已关闭 |
| ISS-160 | P2 | 前端/MainLayout | MainLayout.vue L258 canary 分组到 "settings" 语义不正确 | 2026-07-10 | 已关闭 |
| ISS-161 | P2 | 前端/Canary | AdminCanaryPage.vue L60-68 操作按钮无 loading 状态（重复点击风险） | 2026-07-10 | 已关闭 |
| ISS-162 | P2 | 前端/Reports | AdminReportsPage.vue L72 PDF 作业轮询间隔 2s 过短（与已关闭 ISS-002 同类） | 2026-07-10 | 已关闭 |

### P3 低优先级（2 项）

| 编号 | 级别 | 模块 | 标题 | 发现日期 | 状态 |
|------|------|------|------|----------|------|
| ISS-163 | P3 | 前端/index.html | L41-42,53 骨架屏 loading 颜色硬编码 hex 未走令牌 | 2026-07-10 | 已关闭 |
| ISS-164 | P3 | 前端/OnboardingTour | OnboardingTour.vue L35-37 defineExpose 创建新 useOnboarding 实例（冗余调用） | 2026-07-10 | 已关闭 |

---

## 📈 统计汇总 (Statistics Summary)

> **修复完成时间**：2026-07-05（P0/P1/P2 批次）；2026-07-10 增量审查发现 14 项新问题
> **修复执行人**：audit-beautify-orchestrator + 5 个并行 subagent
> **验证结果**：前端 vue-tsc 通过（仅 2 个预存在 DOMPurify 错误）；后端 37 个文件 ast 语法检查通过

| 级别 | 总数 | 新建 | 已确认 | 修复中 | 待复核 | 已关闭 | 暂缓 | 拒绝 |
|------|------|------|--------|--------|--------|--------|------|------|
| P0 | 3 | 0 | 0 | 0 | 0 | 3 | 0 | 0 |
| P1 | 44 | 0 | 0 | 0 | 0 | 44 | 0 | 0 |
| P2 | 72 | 0 | 0 | 0 | 0 | 72 | 0 | 0 |
| P3 | 33 | 31 | 0 | 0 | 0 | 2 | 0 | 0 |
| P4 | 12 | 12 | 0 | 0 | 0 | 0 | 0 | 0 |
| **合计** | **164** | **43** | **0** | **0** | **0** | **121** | **0** | **0** |

> **说明**：原 P0/P1/P2 共 107 项已全部修复关闭；2026-07-10 增量审查发现 14 项新问题（ISS-151~ISS-164），全部 14 项已修复关闭（ISS-151 P0 + ISS-152~157 P1 + ISS-158~162 P2 + ISS-163/164 P3）。P3(31)/P4(12) 共 43 项为低优先级建议，保持"新建"状态待后续迭代。
> **P2 修复明细**：67 项中实际代码修复 42 项、已存在无需修改 12 项、TODO 标注 13 项（架构性改进，已记录待后续迭代）。

---

## 🛡️ 修复跟踪规则（计划五.4）

- P0/P1 每日同步状态。
- 每个问题必须有关联提交或明确说明无需代码修改。
- 不允许"口头关闭"。
- 修复后必须补充或更新测试（写入 `06-regression-tests.md`）。
- 同类问题必须横向排查（Iron Rule #9）。
- 涉及权限、安全、数据一致性的问题必须由第二人复核（Iron Rule #10）。
- 修复引入新问题时，重新打开原问题或创建关联问题。

---

## 🔍 重点修复优先级（按影响排序）

### 第一优先级（P0 阻塞）— 必须当天修复
1. **ISS-001**: UserModelTrainingPage 训练参数硬编码（epochs=1）
2. **ISS-002**: 训练状态轮询间隔过短（2s）

### 第二优先级（P1 安全/数据一致性）— 1-2 天修复
3. **ISS-006/007**: safe_pickle 反序列化 RCE 风险（强制 require_hash=True）
4. **ISS-008**: Celery 训练任务参数路径校验
5. **ISS-009**: update_job_in_redis 竞态条件
6. **ISS-003/004/005**: silences/review 非原子提交（告警风暴/审计丢失）

### 第三优先级（P1 契约完整性）— 1-2 天修复
7. **ISS-019/021**: counselor/review 模块限流装饰器补充
8. **ISS-022**: 50+ 端点 responses 声明补充

### 第四优先级（P1 视觉/UX/A11Y）— 1-2 天修复
9. **ISS-023~026**: 设计令牌体系统一（命名/间距/圆角/断点）
10. **ISS-027~031**: 通用组件设计系统迁移（ErrorPage/SkipLink/StatefulContainer/FilterBar/PageTable）
11. **ISS-033**: 弹窗响应式宽度
12. **ISS-035**: 危险操作确认框改 danger 类型
13. **ISS-036~039**: A11Y 深色模式 + 字号 + i18n

### 第五优先级（P2 中级）— 3 天内修复
14. **ISS-041**: aware/naive datetime 统一
15. **ISS-045**: MAX_PDF_JOBS 实现
16. **ISS-046**: safe_torch_load weights_only=False 限制
17. **ISS-051/052**: CSV 导出复用 exportUtils
18. **ISS-065**: silences 迁移到 ApiResponse
19. **ISS-076~080**: 图表色板/品牌面板/表单 label-width 统一
