# Ralph 任务列表 (Implementation Plan)

> **版本**: v3.1.0
> **迭代**: v1.0-comprehensive-test
> **日期**: 2026-04-25

> **⚠️ 执行铁律**: 必须严格按照列表顺序（从上到下）执行任务。严禁跳跃或乱序执行。

## 任务状态图例
- [ ] 待开始 (Pending)
- [x] 已完成 (Completed)
- [~] 进行中 (In Progress)

---

## Phase 1: 基础设施与核心配置

### 1.1 项目初始化
- [x] **1.1.1 后端项目结构**
    - [x] 创建 app/ 目录结构 (api, core, models, schemas, services)
    - [x] 配置 main.py FastAPI应用入口
    - [x] 配置 lifespan (初始化/关闭)
- [x] **1.1.2 前端项目结构**
    - [x] 创建 Vue 3 + Vite 项目
    - [x] 配置 Element Plus UI库
    - [x] 配置 Pinia 状态管理
    - [x] 配置 Vue Router

### 1.2 数据库与ORM
- [x] **1.2.1 数据库配置**
    - [x] 配置 SQLAlchemy 2.0 AsyncEngine
    - [x] 配置 AsyncSessionLocal
    - [x] 数据库连接池配置 (生产环境)
- [x] **1.2.2 基础模型**
    - [x] 创建 Base 基类
    - [x] 实现 User 模型 (含CheckConstraint)
    - [x] 实现 UserProfile 模型
    - [x] 实现 EmergencyContact 模型
    - [x] 实现 UserCounselorBinding 模型
- [x] **1.2.3 业务模型**
    - [x] 实现 RiskAssessment 模型
    - [x] 实现 WarningNotification 模型
    - [x] 实现 WarningSetting 模型
    - [x] 实现 InterventionPlan 模型
    - [x] 实现 InterventionTask 模型
    - [x] 实现 InterventionTemplate 模型
    - [x] 实现 TaskExecution 模型
    - [x] 实现 StructuredAssessment 模型
    - [x] 实现 TextEntry 模型
    - [x] 实现 PhysiologicalRecord 模型
    - [x] 实现 CounselorProfile / ConsultationAppointment / ConsultationRecord 模型
    - [x] 实现 ClientGroup / ClientGroupMember 模型
    - [x] 实现 EducationContent / ContentViewHistory / UserFavorite / MeditationLog 模型
    - [x] 实现 OperationLog / SystemConfig / WarningThreshold / ModelRegistry / ModelFeedback 模型
    - [x] 实现 RefreshTokenSession 模型
    - [x] 实现 DataDraft 模型

### 1.3 核心中间件与安全
- [x] **1.3.1 安全配置**
    - [x] 实现 JWT工具 (create_access_token, create_refresh_token, decode_token)
    - [x] 实现 bcrypt密码工具 (verify_password, get_password_hash)
    - [x] 配置 CORS中间件
    - [x] 配置 安全响应头中间件
- [x] **1.3.2 请求处理**
    - [x] 实现 request_id中间件 (全链路追踪)
    - [x] 实现 限流中间件 (slowapi)
    - [x] 实现 全局异常处理
    - [x] 实现 统一响应格式 (ok/error)

---

## Phase 2: 认证授权模块

### 2.1 认证服务
- [x] **2.1.1 注册功能**
    - [x] 实现 AuthService.register (含唯一性校验)
    - [x] 注册时自动创建UserProfile
    - [x] 编写注册单元测试
- [x] **2.1.2 登录功能**
    - [x] 实现 AuthService.login (密码验证+状态检查)
    - [x] 生成access_token + refresh_token
    - [x] 记录RefreshTokenSession
    - [x] 编写登录单元测试
- [x] **2.1.3 Token刷新**
    - [x] 实现 refresh_token接口
    - [x] 验证token类型和过期状态
    - [x] 标记旧token为replaced
    - [x] 编写刷新单元测试
- [x] **2.1.4 密码重置**
    - [x] 实现密码重置token生成
    - [x] 实现重置邮件发送 (含SMTP回退)
    - [x] 编写密码重置单元测试

### 2.2 权限控制
- [x] **2.2.1 依赖注入**
    - [x] 实现 get_current_user (JWT解码+用户查询)
    - [x] 实现 require_role (角色校验)
    - [x] 实现 require_permission (权限矩阵校验)
- [x] **2.2.2 角色层级**
    - [x] 配置 ROLE_HIERARCHY
    - [x] 配置 PERMISSION_MATRIX
    - [x] 编写权限单元测试

---

## Phase 3: 用户数据模块

### 3.1 数据收集
- [x] **3.1.1 结构化数据**
    - [x] 实现 StructuredCollectRequest Schema
    - [x] 实现 collect_structured_data API
    - [x] 数据归一化 (is_student处理)
    - [x] 编写结构化数据单元测试
- [x] **3.1.2 文本数据**
    - [x] 实现 TextAnalyzeRequest Schema
    - [x] 实现 text_analyze API
    - [x] 调用模型进行情感分析
    - [x] 编写文本分析单元测试
- [x] **3.1.3 生理数据**
    - [x] 实现 PhysiologicalRecordRequest Schema
    - [x] 实现 record_physiological API
    - [x] 字段安全过滤
    - [x] 编写生理数据单元测试
- [x] **3.1.4 草稿管理**
    - [x] 实现 DraftUpsertRequest Schema
    - [x] 实现 upsert_draft / get_draft API
    - [x] 编写草稿单元测试

---

## Phase 4: 风险评估模块

### 4.1 模型引擎
- [x] **4.1.1 模型注册**
    - [x] 实现 MODEL_PATHS 配置
    - [x] 实现模型加载器 (joblib/pickle/keras)
    - [x] 实现模型预热 (preload)
- [x] **4.1.2 预测接口**
    - [x] 实现 predict_structured (结构化数据预测)
    - [x] 实现 predict_text (文本情感预测)
    - [x] 实现 predict_physiological (生理数据预测)
    - [x] 实现 predict_fusion (融合预测)
    - [x] 实现 explain_prediction (特征重要性)
    - [x] 编写模型引擎单元测试

### 4.2 风险服务
- [x] **4.2.1 评估核心**
    - [x] 实现 assess_structured (含启发式回退)
    - [x] 实现 _calculate_heuristic_score
    - [x] 实现 _score_to_level / _level_to_severity
    - [x] 编写评估核心单元测试
- [x] **4.2.2 报告生成**
    - [x] 实现 get_risk_report (最新评估+趋势)
    - [x] 实现 get_risk_trend (历史趋势)
    - [x] 实现 export_risk (CSV/JSON/PDF导出)
    - [x] 实现 PDF异步生成 (reportlab+线程池)
    - [x] 编写报告单元测试
- [x] **4.2.3 预警触发**
    - [x] 实现 _check_warning_trigger
    - [x] 实现 _auto_generate_intervention
    - [x] 实现 _create_plan_from_template
    - [x] 编写预警触发单元测试

---

## Phase 5: 预警与干预模块

### 5.1 预警服务
- [x] **5.1.1 用户预警**
    - [x] 实现 WarningService.list_warnings
    - [x] 实现 WarningService.mark_read / mark_all_read
    - [x] 实现 WarningService.get_setting / update_setting
    - [x] 编写用户预警单元测试
- [x] **5.1.2 咨询师预警**
    - [x] 实现 CounselorService.list_warnings
    - [x] 实现 CounselorService.handle_warning
    - [x] 记录操作日志
    - [x] 编写咨询师预警单元测试

### 5.2 干预服务
- [x] **5.2.1 计划管理**
    - [x] 实现干预模板CRUD (AdminService)
    - [x] 实现计划生成逻辑
    - [x] 实现任务列表生成
    - [x] 编写计划管理单元测试
- [x] **5.2.2 任务执行**
    - [x] 实现任务完成/跳过
    - [x] 实现反馈记录
    - [x] 编写任务执行单元测试

---

## Phase 6: 咨询管理模块

### 6.1 咨询师服务
- [x] **6.1.1 用户绑定**
    - [x] 实现绑定码生成
    - [x] 实现用户-咨询师绑定
    - [x] 编写绑定单元测试
- [x] **6.1.2 咨询记录**
    - [x] 实现 ConsultationRecord CRUD
    - [x] 实现 Appointment 管理
    - [x] 编写咨询记录单元测试
- [x] **6.1.3 客户分组**
    - [x] 实现 ClientGroup CRUD
    - [x] 实现 ClientGroupMember 管理
    - [x] 编写客户分组单元测试

---

## Phase 7: 内容与管理模块

### 7.1 内容服务
- [x] **7.1.1 教育内容**
    - [x] 实现 ContentService.list_contents (含搜索/筛选)
    - [x] 实现 ContentService.get_content_detail
    - [x] 实现收藏/浏览历史
    - [x] 编写内容服务单元测试

### 7.2 管理服务
- [x] **7.2.1 仪表盘**
    - [x] 实现 AdminService.get_stats
    - [x] 编写仪表盘单元测试
- [x] **7.2.2 系统配置**
    - [x] 实现 SystemConfig 管理
    - [x] 实现 WarningThreshold 配置
    - [x] 实现 ModelRegistry 管理
    - [x] 编写系统配置单元测试
- [x] **7.2.3 审计日志**
    - [x] 实现 OperationLog 记录
    - [x] 实现日志查询/筛选
    - [x] 编写审计日志单元测试

---

## Phase 8: 前端开发

### 8.1 基础架构
- [x] **8.1.1 API层**
    - [x] 实现 axios封装 (含token自动刷新)
    - [x] 实现各模块API (auth, user, risk, warning, intervention, counselor, admin)
    - [x] 实现请求拦截器/响应拦截器
- [x] **8.1.2 状态管理**
    - [x] 实现 auth store (登录状态/用户信息)
    - [x] 实现 user store
    - [x] 实现 risk store

### 8.2 页面开发
- [x] **8.2.1 认证页面**
    - [x] 实现 LoginPage
    - [x] 实现 RegisterPage
    - [x] 实现 ForgotPasswordPage
- [x] **8.2.2 用户页面**
    - [x] 实现 Dashboard (用户仪表盘)
    - [x] 实现 AssessmentPage (评估页面)
    - [x] 实现 RiskReportPage (风险报告)
    - [x] 实现 WarningPage (预警列表)
    - [x] 实现 InterventionPage (干预计划)
    - [x] 实现 ProfilePage (个人资料)
- [x] **8.2.3 咨询师页面**
    - [x] 实现 CounselorDashboard
    - [x] 实现 ClientListPage
    - [x] 实现 WarningHandlePage
    - [x] 实现 ConsultationRecordPage
- [x] **8.2.4 管理页面**
    - [x] 实现 AdminDashboard
    - [x] 实现 UserManagementPage
    - [x] 实现 TemplateManagementPage
    - [x] 实现 ModelManagementPage
    - [x] 实现 OperationLogPage

---

## Phase 9: 质量保障

### 9.1 后端测试
- [x] **9.1.1 单元测试**
    - [x] 编写 auth 模块测试 (test_auth_flow, test_auth_p0p1)
    - [x] 编写 risk 模块测试 (test_risk_export)
    - [x] 编写 counselor 模块测试 (test_counselor_admin)
    - [x] 编写 model 模块测试 (test_model_predict)
    - [x] 编写 warning 模块测试 (test_user_warning)
    - [x] 编写 upload 模块测试 (test_upload_security)
    - [x] 编写 invalid params 测试 (test_invalid_params)
    - [x] 编写 request_id 审计测试 (test_request_id_audit)
    - [x] 编写 schema 约束测试 (test_schema_constraints)
    - [x] 编写 websocket 测试 (test_websocket, test_websocket_p0p1)
- [x] **9.1.2 集成测试**
    - [x] 编写 harness 核心测试 (test_harness)
    - [x] 编写 harness 集成测试 (test_harness_integration)
    - [x] 编写场景测试 (scenario_backend_smoke)

### 9.2 前端测试
- [x] **9.2.1 单元测试**
    - [x] 编写 API层测试 (domainApis.test.ts, request.test.ts)
    - [x] 编写 路由权限测试 (routeAccess.test.ts)
- [x] **9.2.2 E2E测试**
    - [x] 编写 auth 流程测试 (auth.spec.ts)
    - [x] 编写 seed 测试 (seed.spec.ts)
    - [x] 编写 用户角色测试 (role-user.spec.ts)
    - [x] 编写 咨询师角色测试 (role-counselor.spec.ts)
    - [x] 编写 管理员角色测试 (role-admin.spec.ts)
    - [x] 编写 核心流程测试 (core-flows.spec.ts)
    - [x] 编写 harness 测试 (harness.spec.ts)

---

## 进度统计

| 阶段 | 总任务 | 已完成 | 状态 |
|------|--------|--------|------|
| Phase 1: 基础设施 | 15 | 15 | ✅ 完成 |
| Phase 2: 认证授权 | 8 | 8 | ✅ 完成 |
| Phase 3: 用户数据 | 8 | 8 | ✅ 完成 |
| Phase 4: 风险评估 | 10 | 10 | ✅ 完成 |
| Phase 5: 预警干预 | 8 | 8 | ✅ 完成 |
| Phase 6: 咨询管理 | 6 | 6 | ✅ 完成 |
| Phase 7: 内容管理 | 6 | 6 | ✅ 完成 |
| Phase 8: 前端开发 | 12 | 12 | ✅ 完成 |
| Phase 9: 质量保障 | 14 | 14 | ✅ 完成 |
| **总计** | **87** | **87** | **✅ 100%** |
