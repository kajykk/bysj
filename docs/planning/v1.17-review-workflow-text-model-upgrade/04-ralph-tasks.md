# Ralph 任务列表 — v1.17-review-workflow-text-model-upgrade

<!--
AI 指令:
1. 任务必须原子化 (1-4小时粒度)。
2. 必须遵循 Infrastructure -> Backend -> Frontend -> QA 的依赖顺序。
3. 执行阶段：每完成一个任务，必须立即更新此文件。只有当代码已实现且经过验证后，才能将 "[ ]" 改为 "[x]"。
4. 顺序强制: 必须严格按照列表顺序（从上到下）执行任务。严禁跳跃或乱序执行。
-->

> **⚠️ 执行铁律**: 必须严格按照列表顺序（从上到下）执行任务。严禁跳跃或乱序执行。

## 任务状态图例
- [ ] 待开始 (Pending)
- [x] 已完成 (Completed)
- [~] 进行中 (In Progress)

---

## Phase 1: 上线环境验证与基线冻结

### 1.1 前端构建验证
- [x] **T-BASE-001** 前端生产构建验证
  - 运行 `npm run build`
  - 确认无构建错误
  - 确认输出目录正确

### 1.2 后端启动验证
- [x] **T-BASE-002** 后端启动验证
  - 确认后端正常启动
  - 确认数据库连接正常
  - 确认模型加载正常

### 1.3 健康检查验证
- [x] **T-BASE-003** 健康检查验证
  - 测试 `/health` 端点
  - 测试 `/health/ready` 端点
  - 确认返回状态正确

### 1.4 API 冒烟测试
- [x] **T-BASE-004** 模型 API 冒烟测试
  - 测试 `/model/predict/text` 正常文本
  - 测试 `/model/predict/text` 危机文本
  - 测试 `/model/predict/fusion` 正常请求
  - 测试 `/model/predict/fusion` 危机请求
  - 确认 v1.16 核心能力正常

### 1.5 基线文档
- [x] **T-BASE-005** 生成 `BASELINE_V1.17.md`
  - 记录环境验证结果
  - 记录基线版本信息

---

## Phase 2: 复核工作流后端

### 2.1 数据模型
- [x] **T-REVIEW-001** 设计 review 数据模型
  - 创建 `ReviewTask` SQLAlchemy model
  - 创建 `ReviewStatus` enum
  - 创建 `ReviewPriority` enum
  - 创建 Alembic migration

- [x] **T-REVIEW-002** 创建 review schema
  - 创建 `ReviewTaskCreate` schema
  - 创建 `ReviewTaskResponse` schema
  - 创建 `ReviewTaskUpdate` schema

### 2.2 服务层
- [x] **T-REVIEW-003** 创建 review service
  - 实现 `create_review_task()`
  - 实现 `get_reviews()` 支持筛选和分页
  - 实现 `assign_review()`
  - 实现 `resolve_review()`
  - 实现 `escalate_review()`
  - 实现 `get_review_stats()`

### 2.3 API 层
- [x] **T-REVIEW-004** 创建 review API
  - `GET /reviews`
  - `GET /reviews/{id}`
  - `POST /reviews/{id}/assign`
  - `POST /reviews/{id}/resolve`
  - `POST /reviews/{id}/escalate`
  - `GET /reviews/stats`

### 2.4 集成
- [x] **T-REVIEW-005** 集成风险预测触发 review task
  - 修改 `model_engine.py` 的 `predict_fusion()`
  - 当 `review_required=True` 或 `crisis_override=True` 时自动创建复核任务
  - 确保异步处理，不阻塞预测响应

### 2.5 测试
- [x] **T-REVIEW-006** 编写 review service 单元测试
  - 测试创建复核任务
  - 测试状态流转
  - 测试筛选查询
  - 测试权限控制

- [x] **T-REVIEW-007** 编写 review API 集成测试
  - 测试各端点正常流程
  - 测试权限验证
  - 测试错误处理

---

## Phase 3: 危机审计日志

### 3.1 数据模型
- [x] **T-AUDIT-001** 设计 crisis_event 数据模型
  - 创建 `CrisisEvent` SQLAlchemy model
  - 创建 `CrisisStatus` enum
  - 创建 Alembic migration

### 3.2 服务层
- [x] **T-AUDIT-002** 创建 crisis_event service
  - 实现 `record_crisis_event()`
  - 实现 `get_crisis_events()` 支持筛选和分页
  - 实现 `handle_crisis_event()`
  - 实现 `export_crisis_events()`

### 3.3 API 层
- [x] **T-AUDIT-003** 创建 crisis_event API
  - `GET /crisis-events` (管理员权限)
  - `GET /crisis-events/stats`
  - `GET /crisis-events/export`

### 3.4 集成
- [x] **T-AUDIT-004** 集成危机检测事件记录
  - 修改 `predict_text` API
  - 检测到危机时自动记录审计日志
  - 关联 review_task_id

### 3.5 测试
- [x] **T-AUDIT-005** 编写 crisis_event 测试
  - 测试记录危机事件
  - 测试查询和筛选
  - 测试导出功能
  - 测试权限控制

---

## Phase 4: 咨询师端复核页面

### 4.1 路由和布局
- [x] **T-FE-REVIEW-001** 创建咨询师端路由和布局
  - 添加 `/counselor/reviews` 路由
  - 添加 `/counselor/reviews/:id` 路由
  - 创建咨询师端布局组件

### 4.2 复核列表页
- [x] **T-FE-REVIEW-002** 创建复核任务列表页
  - 实现列表展示
  - 实现状态筛选
  - 实现优先级筛选
  - 实现分页
  - 实现刷新

### 4.3 复核详情页
- [x] **T-FE-REVIEW-003** 创建复核详情页
  - 展示用户信息
  - 展示模型预测结果
  - 展示风险因素和保护因素
  - 展示历史风险记录

### 4.4 处理功能
- [x] **T-FE-REVIEW-004** 添加处理动作
  - 实现标记已处理
  - 实现升级危机事件
  - 实现填写处理备注
  - 实现表单验证

### 4.5 危机警示
- [x] **T-FE-REVIEW-005** 添加危机事件明显警示
  - 危机任务红色高亮
  - 危机详情页警告横幅
  - 紧急处理提示

---

## Phase 5: 文本安全增强

### 5.1 关键词库扩展
- [x] **T-CRISIS-101** 扩展危机关键词库
  - 增加网络用语（emo、破防、一了百了）
  - 增加计划性表达（准备好了、今晚就结束、留下遗书）
  - 增加求助表达（救救我、控制不住、怕伤害自己）

- [x] **T-CRISIS-102** 增加误报过滤规则
  - 过滤 "笑死了"
  - 过滤 "气死了"
  - 过滤 "社死了"
  - 过滤 "尴尬死了"

### 5.2 测试
- [x] **T-CRISIS-103** 扩展文本样本测试
  - 新增 30+ 文本测试样本
  - 覆盖网络用语
  - 覆盖计划性表达
  - 覆盖求助表达
  - 覆盖误报场景

---

## Phase 6: 测试与交付

### 6.1 回归测试
- [x] **T-REG-001** v1.16 核心能力回归测试
  - 危机检测测试
  - 阈值校准测试
  - 融合优先级测试
  - 预期风险样本测试

### 6.2 集成测试
- [x] **T-REG-002** 端到端流程测试
  - 文本预测 -> 创建复核任务 -> 咨询师处理
  - 融合预测 -> 记录危机事件 -> 管理员查看

### 6.3 文档
- [x] **T-DOC-001** 生成 `REVIEW_WORKFLOW_REPORT.md`
- [x] **T-DOC-002** 生成 `CRISIS_AUDIT_REPORT.md`
- [x] **T-DOC-003** 生成 `CRISIS_KEYWORD_REPORT.md`
- [x] **T-DELIVER-001** 生成 `DELIVERY_REPORT.md`
- [x] **T-DELIVER-002** 生成 `NEXT_STEPS.md`

---

> **文档版本**: v1.0
> **生成时间**: 2026-05-01
> **迭代**: v1.17-review-workflow-text-model-upgrade
