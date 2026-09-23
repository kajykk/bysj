# 产品需求文档 (PRD)

> **项目名称**: 抑郁症预警系统 (Depression Warning System)
> **版本**: v3.1.0
> **迭代**: v1.0-comprehensive-test
> **日期**: 2026-04-25

## 1. 项目概述

### 1.1 背景
基于多模态数据（结构化问卷、文本、生理信号）的抑郁症风险评估与预警系统，为用户提供心理健康监测、风险预警、干预计划及咨询师对接服务。

### 1.2 目标用户
- **普通用户 (user)**: 进行自评、查看风险报告、接收预警、执行干预任务
- **咨询师 (counselor)**: 管理绑定用户、处理预警、记录咨询、分配干预计划
- **管理员 (admin)**: 系统配置、内容管理、模型管理、审计日志

### 1.3 核心功能模块

| 模块 | 说明 | 角色 |
|------|------|------|
| 认证授权 | 注册/登录/Token刷新/密码重置/RBAC权限控制 | 全部 |
| 用户数据 | 结构化评估/文本分析/生理数据记录/草稿保存 | user |
| 风险评估 | 结构化模型预测/文本情感分析/生理风险计算/融合预测 | user |
| 预警通知 | 风险等级变化触发预警/咨询师推送/用户设置阈值 | user/counselor |
| 干预计划 | 模板管理/计划生成/任务执行/进度跟踪 | user/counselor |
| 咨询管理 | 用户-咨询师绑定/预约/咨询记录/客户分组 | counselor |
| 内容管理 | 教育内容/冥想资源/收藏/浏览历史 | user |
| 管理后台 | 仪表盘/模板管理/模型注册/阈值配置/操作日志 | admin |

## 2. 功能需求详解

### 2.1 认证授权模块 (Auth)

#### 2.1.1 用户注册
- **字段**: username (3-50字符), email (唯一), password (加密存储), role (user/counselor)
- **校验**: 用户名/邮箱唯一性校验
- **流程**: 注册 -> 创建用户 -> 创建默认Profile -> 返回用户信息

#### 2.1.2 用户登录
- **字段**: username, password
- **校验**: 密码bcrypt验证, 用户状态active
- **流程**: 登录 -> 生成access_token + refresh_token -> 记录refresh_session -> 返回token+用户信息
- **安全**: 密码截断72字符, 登录限流5次/分钟

#### 2.1.3 Token刷新
- **输入**: refresh_token
- **校验**: JWT解码, type=refresh, 未过期, 未revoke
- **流程**: 验证 -> 生成新access_token + 新refresh_token -> 标记旧token为replaced

#### 2.1.4 密码重置
- **流程**: 请求重置 -> 生成reset_token -> 发送邮件(链接) -> 验证token -> 更新密码
- **备用**: SMTP未配置时日志输出重置链接

#### 2.1.5 RBAC权限
- **角色层级**: admin, counselor, user
- **权限矩阵**: 细粒度权限控制 (PERMISSION_MATRIX)
- **依赖**: require_role / require_permission

### 2.2 用户数据模块 (User Data)

#### 2.2.1 结构化数据收集
- **字段**: age, gender, study_year, cgpa, stress_level, sleep_duration, social_support, financial_pressure, family_history, academic_pressure, exercise_frequency, anxiety, panic_attack, treatment_seeking
- **处理**: 根据identity_type自动归一化(is_student)
- **存储**: StructuredAssessment表

#### 2.2.2 文本分析
- **输入**: entry_type, content, emotion_tags, mood_score
- **处理**: 调用text模型进行情感分析 -> sentiment_score, sentiment_label
- **存储**: TextEntry表

#### 2.2.3 生理数据记录
- **字段**: sleep_hours, sleep_quality, exercise_minutes, heart_rate, systolic_bp, diastolic_bp, steps
- **存储**: PhysiologicalRecord表

#### 2.2.4 草稿保存
- **功能**: 按draft_type保存/读取数据草稿
- **存储**: DataDraft表 (user_id + draft_type唯一约束)

### 2.3 风险评估模块 (Risk Assessment)

#### 2.3.1 结构化评估
- **模型**: structured_logistic_regression_quick / structured_random_forest_quick / structured_best_ensemble_quick
- **回退**: 模型加载失败时使用启发式算法
- **输出**: risk_score (0-100), risk_level (0-4), risk_factors

#### 2.3.2 文本评估
- **模型**: text_bert_classifier / text_improved_bilingual_model
- **输出**: sentiment_score, sentiment_label

#### 2.3.3 生理评估
- **模型**: physiological_risk_model
- **输出**: physiological_score

#### 2.3.4 融合预测
- **模型**: fusion_dnn_best / fusion_cross_modal_best / fusion_transformer_best
- **输入**: 结构化 + 文本 + 生理特征
- **输出**: 综合风险分数

#### 2.3.5 风险报告
- **功能**: 最新风险评估/趋势分析/历史记录导出(CSV/JSON/PDF)
- **PDF生成**: reportlab异步生成

### 2.4 预警通知模块 (Warning)

#### 2.4.1 触发条件
- 风险等级上升
- 风险等级>=3
- 连续3次评估风险等级>=2

#### 2.4.2 通知流程
- 生成WarningNotification
- 自动关联绑定咨询师
- 用户可设置阈值/通知渠道/免打扰时段

#### 2.4.3 处理流程
- 用户查看/标记已读
- 咨询师处理/忽略/记录处理备注

### 2.5 干预计划模块 (Intervention)

#### 2.5.1 模板管理
- **字段**: template_name, applicable_levels, task_list, estimated_weeks, status
- **权限**: admin管理, counselor查看

#### 2.5.2 计划生成
- **触发**: 风险等级>=2时自动生成
- **逻辑**: 按风险等级匹配模板 -> 创建计划 -> 创建任务列表
- **关联**: 自动关联绑定咨询师

#### 2.5.3 任务执行
- **字段**: task_name, task_type, schedule, duration_minutes
- **状态**: pending -> completed / skipped
- **反馈**: feedback_score (1-5), feedback_note

### 2.6 咨询管理模块 (Counselor)

#### 2.6.1 用户绑定
- **方式**: 绑定码(bind_code) / 管理员分配
- **状态**: active / inactive

#### 2.6.2 预警处理
- **列表**: 查看关联用户的预警
- **操作**: handle / ignore / 记录备注
- **审计**: 记录OperationLog

#### 2.6.3 咨询记录
- **字段**: main_topics, client_status, interventions, next_plan, notes
- **关联**: appointment / warning

#### 2.6.4 客户分组
- **功能**: 创建分组 / 添加成员 / 按分组查看

### 2.7 内容管理模块 (Content)

#### 2.7.1 教育内容
- **字段**: title, content_type, category, summary, cover_image_url, duration_minutes, difficulty
- **功能**: 列表/搜索/详情/收藏/浏览历史

#### 2.7.2 冥想日志
- **字段**: content_id, duration, completion_status

### 2.8 管理后台模块 (Admin)

#### 2.8.1 仪表盘
- **统计**: 用户数/咨询师数/预警数/评估数/模型状态

#### 2.8.2 模板管理
- **CRUD**: 干预模板的增删改查

#### 2.8.3 模型注册
- **字段**: model_id, model_name, model_type, file_path, version, accuracy, f1_score, latency_ms
- **功能**: 注册/更新/切换状态

#### 2.8.4 阈值配置
- **功能**: 调整风险等级阈值

#### 2.8.5 操作日志
- **字段**: operator_id, action_type, target_type, target_id, detail, ip_address, request_id
- **功能**: 查看/筛选/审计

## 3. 非功能需求

### 3.1 性能
- API响应时间 < 500ms (P95)
- 风险评估异步执行
- PDF生成使用线程池

### 3.2 安全
- JWT认证, 密钥生产环境强制检查
- 密码bcrypt加密, 截断72字符
- CORS配置
- 限流保护
- 操作审计日志

### 3.3 可靠性
- 模型加载失败时启发式回退
- 数据库连接池自动回收
- 健康检查端点

### 3.4 可维护性
- 结构化日志 (request_id追踪)
- 统一响应格式
- 异常处理中间件
