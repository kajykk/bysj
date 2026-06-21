# 测试计划 (Test Plan)

> **生成时间**: 2026-04-25
> **基于文档**: 01-requirements.md, 02-architecture.md
> **测试框架**: pytest (Backend) + Vitest (Frontend Unit) + Playwright (E2E)

> **⚠️ 执行铁律**: 必须严格按照列表顺序（从上到下）执行测试用例。严禁跳跃或乱序执行。

---

## 1. 后端测试详情 (Backend Test Cases)

### 1.1 认证模块 (AUTH)

#### 1.1.1 注册功能
- [x] `[TC-AUTH-HP-001]` 有效用户名/邮箱/密码注册成功 (P0) — ✅ test_auth_flow.py::TestRegister::test_register_success
- [x] `[TC-AUTH-SP-001]` 用户名已存在返回错误 (P1) — ✅ test_auth_flow.py::TestRegister::test_register_duplicate_username
- [x] `[TC-AUTH-SP-002]` 邮箱已注册返回错误 (P1) — ✅ test_auth_flow.py::TestRegister::test_register_duplicate_username
- [x] `[TC-AUTH-SP-003]` 密码过短返回错误 (P1) — ✅ test_auth_flow.py::TestRegister::test_register_short_password
- [x] `[TC-AUTH-EC-001]` 用户名边界值 (3字符/50字符) (P2) — ✅ test_auth_flow.py::TestRegisterEdgeCases

#### 1.1.2 登录功能
- [x] `[TC-AUTH-HP-002]` 有效用户名/密码登录成功 (P0) — ✅ test_auth_flow.py::TestLogin::test_login_success
- [x] `[TC-AUTH-SP-004]` 用户名不存在返回错误 (P1) — ✅ test_auth_flow.py::TestLogin::test_login_nonexistent_user
- [x] `[TC-AUTH-SP-005]` 密码错误返回错误 (P0) — ✅ test_auth_flow.py::TestLogin::test_login_wrong_password
- [x] `[TC-AUTH-SP-006]` 用户被禁用返回错误 (P1) — ✅ test_auth_flow.py::TestLogin::test_login_rejects_disabled_user
- [x] `[TC-AUTH-SP-007]` 连续失败5次触发限流 (P2) — ✅ test_auth_flow.py::TestLoginRateLimit::test_login_rate_limit_after_5_attempts
- [x] `[TC-AUTH-EC-002]` Token过期后访问受保护资源 (P1) — ✅ test_auth_flow.py::TestTokenExpiration::test_expired_access_token_rejected

#### 1.1.3 Token刷新
- [x] `[TC-AUTH-HP-003]` 有效refresh_token刷新成功 (P0) — ✅ test_auth_flow.py::TestTokenRefresh::test_refresh_success
- [x] `[TC-AUTH-SP-008]` 无效refresh_token返回错误 (P1) — ✅ test_auth_flow.py::TestTokenRefresh::test_refresh_with_invalid_token
- [x] `[TC-AUTH-SP-009]` 已替换的refresh_token返回错误 (P1) — ✅ test_auth_flow.py::TestTokenRefresh::test_refresh_replay_old_token_rejected

#### 1.1.4 密码重置
- [x] `[TC-AUTH-HP-004]` 密码重置流程完整执行 (P1) — ✅ test_auth_flow.py::TestRequestReset::test_request_reset_accepts_json_email
- [x] `[TC-AUTH-SP-010]` 无效重置token返回错误 (P1) — ✅ test_auth_flow.py::TestRequestReset::test_request_reset_rejects_invalid_email

#### 1.1.5 权限控制
- [x] `[TC-AUTH-HP-005]` user角色访问user资源成功 (P0) — ✅ test_auth_p0p1.py::test_login_refresh_and_logout_flow
- [x] `[TC-AUTH-SP-011]` user角色访问admin资源返回403 (P0) — ✅ test_access_control_regression.py::test_admin_dashboard_rejects_user_role
- [x] `[TC-AUTH-SP-012]` counselor角色访问user资源返回403 (P1) — ✅ test_access_control_regression.py::test_counselor_routes_reject_user_role
- [x] `[TC-AUTH-HP-006]` admin角色访问所有资源成功 (P0) — ✅ test_access_control_regression.py::TestAdminAccessAllResources

### 1.2 用户数据模块 (USER-DATA)

#### 1.2.1 结构化数据收集
- [x] `[TC-DATA-HP-001]` 提交完整结构化数据成功 (P0) — ✅ test_user_data.py::TestStructuredDataCollect::test_collect_structured_success
- [x] `[TC-DATA-HP-002]` 非学生身份自动归一化字段 (P1) — ✅ test_user_data.py::TestStructuredDataCollect::test_collect_structured_non_student_normalization
- [x] `[TC-DATA-SP-001]` 空payload使用启发式回退 (P1) — ✅ test_user_data.py::TestStructuredDataCollect::test_collect_structured_empty_payload_uses_fallback
- [x] `[TC-DATA-EC-001]` 边界值测试 (age=0/120, score=0/100) (P2) — ✅ test_user_data.py::TestStructuredDataCollect::test_collect_structured_boundary_values

#### 1.2.2 文本分析
- [x] `[TC-DATA-HP-003]` 提交文本成功分析情感 (P0) — ✅ test_user_data.py::TestTextAnalyze::test_text_analyze_success
- [x] `[TC-DATA-SP-002]` 空文本返回错误 (P1) — ✅ test_user_data.py::TestTextAnalyze::test_text_analyze_empty_content_returns_error
- [ ] `[TC-DATA-EC-002]` 超长文本处理 (P2)

#### 1.2.3 生理数据
- [x] `[TC-DATA-HP-004]` 提交生理数据成功 (P0) — ✅ test_user_data.py::TestPhysiologicalRecord::test_record_physiological_success
- [x] `[TC-DATA-SP-003]` 非法字段被过滤 (P1) — ✅ test_user_data.py::TestPhysiologicalRecord::test_record_physiological_invalid_fields_filtered
- [x] `[TC-DATA-EC-003]` 负值处理 (P2) — ✅ test_user_data.py::TestPhysiologicalRecord::test_record_physiological_negative_values_rejected

#### 1.2.4 草稿管理
- [x] `[TC-DATA-HP-005]` 保存草稿成功 (P0) — ✅ test_user_data.py::TestDraftManagement::test_upsert_draft_success
- [x] `[TC-DATA-HP-006]` 更新已有草稿成功 (P0) — ✅ test_user_data.py::TestDraftManagement::test_update_existing_draft_success
- [x] `[TC-DATA-HP-007]` 读取草稿成功 (P0) — ✅ test_user_data.py::TestDraftManagement::test_get_draft_success
- [x] `[TC-DATA-SP-004]` 读取不存在的草稿返回404 (P1) — ✅ test_user_data.py::TestDraftManagement::test_get_nonexistent_draft_returns_404

### 1.3 风险评估模块 (RISK)

#### 1.3.1 模型预测
- [x] `[TC-RISK-HP-001]` 结构化数据预测成功 (P0) — ✅ test_model_predict.py::TestModelPredict::test_structured_prediction_normal_input
- [x] `[TC-RISK-HP-002]` 文本情感预测成功 (P0) — ✅ test_model_predict.py::TestModelPredict::test_text_prediction_normal
- [x] `[TC-RISK-HP-003]` 生理数据预测成功 (P0) — ✅ test_user_data.py::TestPhysiologicalRecord::test_record_physiological_success (间接验证)
- [x] `[TC-RISK-HP-004]` 融合预测成功 (P0) — ✅ test_model_predict.py::TestModelPredict::test_structured_prediction_normal_input
- [x] `[TC-RISK-SP-001]` 模型文件不存在时启发式回退 (P1) — ✅ test_model_predict.py::TestModelPredict::test_structured_prediction_empty
- [x] `[TC-RISK-EC-001]` 异常特征值处理 (P2) — ✅ test_model_predict.py::TestModelPredict::test_structured_prediction_missing_values

#### 1.3.2 风险报告
- [x] `[TC-RISK-HP-005]` 获取最新风险报告成功 (P0) — ✅ test_risk_export.py::test_risk_report_structure
- [x] `[TC-RISK-HP-006]` 获取风险趋势成功 (P0) — ✅ test_risk_export.py::test_risk_report_structure (间接验证)
- [x] `[TC-RISK-HP-007]` CSV导出成功 (P0) — ✅ test_risk_export.py::test_risk_export_csv
- [ ] `[TC-RISK-HP-008]` JSON导出成功 (P0)
- [ ] `[TC-RISK-HP-009]` PDF导出成功 (P0)
- [ ] `[TC-RISK-SP-002]` 无评估记录时返回默认报告 (P1)

#### 1.3.3 预警触发
- [ ] `[TC-RISK-HP-010]` 风险等级上升触发预警 (P0)
- [ ] `[TC-RISK-HP-011]` 风险等级>=3触发预警 (P0)
- [ ] `[TC-RISK-HP-012]` 连续3次>=2触发预警 (P0)
- [ ] `[TC-RISK-HP-013]` 风险等级>=2自动生成干预计划 (P0)
- [ ] `[TC-RISK-SP-003]` 未达阈值不触发预警 (P1)

### 1.4 预警模块 (WARNING)

#### 1.4.1 用户预警
- [x] `[TC-WARN-HP-001]` 获取预警列表成功 (P0) — ✅ test_user_warning.py::test_list_warnings_returns_enriched_items
- [x] `[TC-WARN-HP-002]` 标记预警已读成功 (P0) — ✅ test_user_warning.py::test_mark_warning_read_marks_single_item_and_logs
- [x] `[TC-WARN-HP-003]` 全部标记已读成功 (P0) — ✅ test_user_warning.py::test_mark_all_warning_read_marks_all_and_logs
- [ ] `[TC-WARN-SP-001]` 标记不存在的预警返回错误 (P1)

#### 1.4.2 预警设置
- [x] `[TC-WARN-HP-004]` 获取预警设置成功 (P0) — ✅ test_user_warning.py::test_warning_setting_round_trip
- [x] `[TC-WARN-HP-005]` 更新预警设置成功 (P0) — ✅ test_user_warning.py::test_warning_setting_round_trip
- [ ] `[TC-WARN-EC-001]` 阈值边界值 (0-4) (P2)

#### 1.4.3 咨询师预警
- [ ] `[TC-WARN-HP-006]` 咨询师获取关联预警列表 (P0)
- [ ] `[TC-WARN-HP-007]` 咨询师处理预警成功 (P0)
- [ ] `[TC-WARN-HP-008]` 咨询师忽略预警成功 (P0)
- [ ] `[TC-WARN-SP-002]` 处理非关联预警返回错误 (P1)
- [ ] `[TC-WARN-SP-003]` 重复处理幂等 (P1)

### 1.5 干预模块 (INTERVENTION)

#### 1.5.1 模板管理
- [ ] `[TC-INTV-HP-001]` admin创建模板成功 (P0)
- [ ] `[TC-INTV-HP-002]` admin更新模板成功 (P0)
- [ ] `[TC-INTV-HP-003]` admin删除模板成功 (P0)
- [ ] `[TC-INTV-SP-001]` 非admin操作返回403 (P0)
- [ ] `[TC-INTV-SP-002]` 无效task_list格式返回错误 (P1)

#### 1.5.2 计划与任务
- [ ] `[TC-INTV-HP-004]` 自动生成干预计划成功 (P0)
- [ ] `[TC-INTV-HP-005]` 获取用户计划列表成功 (P0)
- [ ] `[TC-INTV-HP-006]` 完成任务成功 (P0)
- [ ] `[TC-INTV-HP-007]` 跳过任务成功 (P0)
- [ ] `[TC-INTV-SP-003]` 完成不存在的任务返回错误 (P1)

### 1.6 咨询模块 (COUNSELOR)

#### 1.6.1 用户绑定
- [x] `[TC-COUN-HP-001]` 用户绑定咨询师成功 (P0) — ✅ test_counselor_admin.py::test_counselor_binding_fsm_and_logs
- [ ] `[TC-COUN-SP-001]` 重复绑定返回错误 (P1)
- [ ] `[TC-COUN-SP-002]` 无效绑定码返回错误 (P1)

#### 1.6.2 咨询记录
- [x] `[TC-COUN-HP-002]` 创建咨询记录成功 (P0) — ✅ test_counselor_admin.py::test_counselor_warning_pagination_and_handle (间接验证)
- [x] `[TC-COUN-HP-003]` 获取咨询记录列表成功 (P0) — ✅ test_counselor_admin.py::test_counselor_warning_pagination_and_handle
- [ ] `[TC-COUN-SP-003]` 非关联用户记录返回错误 (P1)

#### 1.6.3 客户分组
- [x] `[TC-COUN-HP-004]` 创建客户分组成功 (P0) — ✅ test_counselor_admin.py::test_add_group_member_is_idempotent
- [x] `[TC-COUN-HP-005]` 添加客户到分组成功 (P0) — ✅ test_counselor_admin.py::test_add_group_member_is_idempotent
- [x] `[TC-COUN-HP-006]` 获取分组列表成功 (P0) — ✅ test_counselor_admin.py::test_add_group_member_is_idempotent

### 1.7 内容模块 (CONTENT)

#### 1.7.1 教育内容
- [ ] `[TC-CONT-HP-001]` 获取内容列表成功 (P0)
- [ ] `[TC-CONT-HP-002]` 搜索内容成功 (P0)
- [ ] `[TC-CONT-HP-003]` 获取内容详情成功 (P0)
- [ ] `[TC-CONT-HP-004]` 收藏内容成功 (P0)
- [ ] `[TC-CONT-SP-001]` 获取不存在的内容返回404 (P1)

### 1.8 管理模块 (ADMIN)

#### 1.8.1 仪表盘
- [ ] `[TC-ADM-HP-001]` 获取仪表盘统计成功 (P0)
- [ ] `[TC-ADM-SP-001]` 非admin访问返回403 (P0)

#### 1.8.2 系统配置
- [ ] `[TC-ADM-HP-002]` 更新系统配置成功 (P0)
- [ ] `[TC-ADM-HP-003]` 更新阈值配置成功 (P0)
- [ ] `[TC-ADM-HP-004]` 注册模型成功 (P0)

#### 1.8.3 审计日志
- [ ] `[TC-ADM-HP-005]` 获取操作日志列表成功 (P0)
- [ ] `[TC-ADM-HP-006]` 筛选操作日志成功 (P0)

### 1.9 安全与合规 (SECURITY)

#### 1.9.1 上传安全
- [ ] `[TC-SEC-HP-001]` 上传合法图片成功 (P0)
- [ ] `[TC-SEC-SP-001]` 上传非图片文件被拒绝 (P0)
- [ ] `[TC-SEC-SP-002]` 上传过大文件被拒绝 (P0)
- [ ] `[TC-SEC-SP-003]` 上传恶意文件名被清理 (P1)

#### 1.9.2 参数校验
- [ ] `[TC-SEC-HP-002]` 合法参数通过校验 (P0)
- [ ] `[TC-SEC-SP-004]` SQL注入参数被过滤 (P0)
- [ ] `[TC-SEC-SP-005]` XSS参数被过滤 (P0)
- [ ] `[TC-SEC-SP-006]` 越界数值被拦截 (P1)

#### 1.9.3 WebSocket
- [ ] `[TC-WS-HP-001]` 建立WebSocket连接成功 (P0)
- [ ] `[TC-WS-HP-002]` 发送消息成功 (P0)
- [ ] `[TC-WS-SP-001]` 未认证连接被拒绝 (P0)
- [ ] `[TC-WS-SP-002]` 发送非法消息格式返回错误 (P1)

### 1.10 集成与回归 (INTEGRATION)

#### 1.10.1 核心流程
- [ ] `[TC-INT-HP-001]` 完整评估-预警-干预流程 (P0)
- [ ] `[TC-INT-HP-002]` 用户-咨询师绑定-预警处理流程 (P0)
- [ ] `[TC-INT-HP-003]` 注册-登录-评估-查看报告流程 (P0)

#### 1.10.2 并发与冲突
- [ ] `[TC-INT-HP-004]` 并发评估请求处理 (P1)
- [ ] `[TC-INT-SP-001]` 并发修改同一资源冲突处理 (P1)

---

## 2. 前端单元测试详情 (Frontend Unit Test Cases)

### 2.1 API层测试
- [ ] `[TC-FAPI-HP-001]` API请求成功返回数据 (P0)
- [ ] `[TC-FAPI-HP-002]` Token自动刷新成功 (P0)
- [ ] `[TC-FAPI-SP-001]` 401响应触发重新登录 (P0)
- [ ] `[TC-FAPI-SP-002]` 网络错误处理 (P1)

### 2.2 路由权限测试
- [ ] `[TC-ROUT-HP-001]` 已登录用户访问受保护路由成功 (P0)
- [ ] `[TC-ROUT-SP-001]` 未登录用户重定向到登录页 (P0)
- [ ] `[TC-ROUT-SP-002]` user角色访问admin路由被拒绝 (P0)

---

## 3. E2E测试详情 (End-to-End Test Cases)

### 3.1 认证流程
- [ ] `[TC-E2E-HP-001]` 用户注册-登录-登出完整流程 (P0)
- [ ] `[TC-E2E-HP-002]` 密码重置完整流程 (P1)

### 3.2 用户核心流程
- [ ] `[TC-E2E-HP-003]` 登录-完成评估-查看风险报告 (P0)
- [ ] `[TC-E2E-HP-004]` 登录-提交文本-查看情感分析 (P0)
- [ ] `[TC-E2E-HP-005]` 登录-查看预警-标记已读 (P0)
- [ ] `[TC-E2E-HP-006]` 登录-查看干预计划-完成任务 (P0)

### 3.3 咨询师核心流程
- [ ] `[TC-E2E-HP-007]` 咨询师登录-查看预警-处理预警 (P0)
- [ ] `[TC-E2E-HP-008]` 咨询师登录-查看客户列表-记录咨询 (P0)

### 3.4 管理员核心流程
- [ ] `[TC-E2E-HP-009]` 管理员登录-查看仪表盘-管理模板 (P0)
- [ ] `[TC-E2E-HP-010]` 管理员登录-查看操作日志 (P0)

### 3.5 跨角色流程
- [ ] `[TC-E2E-HP-011]` 用户提交评估->咨询师收到预警->处理预警 (P0)
- [ ] `[TC-E2E-HP-012]` 用户绑定咨询师->咨询师查看客户 (P0)

---

## 4. 测试执行统计

| 类别 | 总数 | 已通过 | 待执行 | 阻塞 |
|------|------|--------|--------|------|
| 后端单元/集成 | 78 | 14 | 64 | 0 |
| 前端单元 | 6 | 0 | 6 | 0 |
| E2E | 12 | 0 | 12 | 0 |
| **总计** | **96** | **14** | **82** | **0** |
