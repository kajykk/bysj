# v1.16-coverage-80 开发任务列表

> **迭代名称**: v1.16-coverage-80
> **上一迭代**: v1.15-launch-readiness
> **目标**: 将测试覆盖率提升至 80%，完善测试体系
> **创建日期**: 2026-05-01

---

## 1. 任务总览

| 阶段 | 任务数 | 优先级 |
|---|---|---|
| Phase 1: 测试基础设施 | 5 | P0 |
| Phase 2: 后端单元测试 | 8 | P0 |
| Phase 3: 后端集成测试 | 5 | P0 |
| Phase 4: 前端单元测试 | 6 | P1 |
| Phase 5: E2E 测试 | 4 | P1 |
| Phase 6: CI/CD 集成 | 3 | P0 |

**总计**: 31 个任务

---

## 2. Phase 1: 测试基础设施

### T-INFRA-001: 创建后端测试目录结构
- **描述**: 按照架构文档创建 backend/tests/ 目录结构
- **文件**:
  - `backend/tests/unit/__init__.py`
  - `backend/tests/unit/api/__init__.py`
  - `backend/tests/unit/services/__init__.py`
  - `backend/tests/unit/repositories/__init__.py`
  - `backend/tests/unit/core/__init__.py`
  - `backend/tests/integration/__init__.py`
  - `backend/tests/fixtures/__init__.py`
- **验收标准**: 目录结构完整，pytest 可以识别
- **状态**: [ ]

### T-INFRA-002: 配置后端测试依赖
- **描述**: 在 requirements.txt 或 requirements-dev.txt 中添加测试依赖
- **依赖**:
  - pytest
  - pytest-cov
  - pytest-asyncio
  - factory-boy
  - freezegun
  - pyfakefs
- **验收标准**: `pip install -r requirements-dev.txt` 成功
- **状态**: [ ]

### T-INFRA-003: 创建测试基类和 Fixtures
- **描述**: 创建 BaseTestCase 和共享 fixtures
- **文件**:
  - `backend/tests/base.py`
  - `backend/tests/conftest.py`
  - `backend/tests/fixtures/users.py`
  - `backend/tests/fixtures/assessments.py`
- **验收标准**: 所有测试可以继承基类并使用 fixtures
- **状态**: [ ]

### T-INFRA-004: 配置前端测试环境
- **描述**: 配置 Vitest 和测试工具
- **文件**:
  - `frontend/vitest.config.ts`
  - `frontend/src/__tests__/setup.ts`
- **依赖**:
  - vitest
  - @vue/test-utils
  - jsdom
  - @testing-library/vue
- **验收标准**: `npm run test:unit` 可以执行
- **状态**: [ ]

### T-INFRA-005: 配置 Playwright E2E 测试
- **描述**: 配置 Playwright 测试环境
- **文件**:
  - `frontend/playwright.config.ts`
  - `frontend/src/__tests__/e2e/.gitignore`
- **依赖**:
  - @playwright/test
- **验收标准**: `npx playwright test` 可以执行
- **状态**: [ ]

---

## 3. Phase 2: 后端单元测试

### T-BE-UNIT-001: Auth API 单元测试
- **描述**: 测试认证相关 API
- **文件**: `backend/tests/unit/api/test_auth.py`
- **覆盖**:
  - 登录成功/失败
  - 注册成功/失败
  - Token 刷新
  - 密码重置
- **目标覆盖率**: 90%
- **状态**: [ ]

### T-BE-UNIT-002: User Risk API 单元测试
- **描述**: 测试用户风险评估 API
- **文件**: `backend/tests/unit/api/test_user_risk.py`
- **覆盖**:
  - 风险评估提交
  - 评估历史查询
  - 预警查看
- **目标覆盖率**: 85%
- **状态**: [ ]

### T-BE-UNIT-003: Counselor API 单元测试
- **描述**: 测试咨询师相关 API
- **文件**: `backend/tests/unit/api/test_counselor.py`
- **覆盖**:
  - 用户管理
  - 预警处理
  - 干预计划
- **目标覆盖率**: 85%
- **状态**: [ ]

### T-BE-UNIT-004: Auth Service 单元测试
- **描述**: 测试认证服务层
- **文件**: `backend/tests/unit/services/test_auth_service.py`
- **覆盖**:
  - 密码哈希验证
  - Token 生成/验证
  - 权限检查
- **目标覆盖率**: 90%
- **状态**: [ ]

### T-BE-UNIT-005: Risk Service 单元测试
- **描述**: 测试风险评估服务层
- **文件**: `backend/tests/unit/services/test_risk_service.py`
- **覆盖**:
  - 风险等级计算
  - 预警生成逻辑
  - 评估结果存储
- **目标覆盖率**: 85%
- **状态**: [ ]

### T-BE-UNIT-006: Model Service 单元测试
- **描述**: 测试模型服务层
- **文件**: `backend/tests/unit/services/test_model_service.py`
- **覆盖**:
  - 模型加载
  - 预测执行
  - 结果格式化
  - Fallback 机制
- **目标覆盖率**: 80%
- **状态**: [ ]

### T-BE-UNIT-007: User Repository 单元测试
- **描述**: 测试用户数据访问层
- **文件**: `backend/tests/unit/repositories/test_user_repo.py`
- **覆盖**:
  - CRUD 操作
  - 查询优化
  - 事务管理
- **目标覆盖率**: 85%
- **状态**: [ ]

### T-BE-UNIT-008: Core 模块单元测试
- **描述**: 测试核心模块
- **文件**:
  - `backend/tests/unit/core/test_config.py`
  - `backend/tests/unit/core/test_security.py`
  - `backend/tests/unit/core/test_model_engine.py`
- **覆盖**:
  - 配置加载
  - 安全工具
  - 模型引擎
- **目标覆盖率**: 80%
- **状态**: [ ]

---

## 4. Phase 3: 后端集成测试

### T-BE-INT-001: Auth 流程集成测试
- **描述**: 测试完整认证流程
- **文件**: `backend/tests/integration/test_auth_flow.py`
- **覆盖**:
  - 注册 -> 登录 -> 访问资源
  - Token 过期 -> 刷新 -> 继续访问
  - 权限不足 -> 403 响应
- **目标覆盖率**: 90%
- **状态**: [ ]

### T-BE-INT-002: Risk 流程集成测试
- **描述**: 测试风险评估完整流程
- **文件**: `backend/tests/integration/test_risk_flow.py`
- **覆盖**:
  - 提交评估 -> 模型预测 -> 结果存储
  - 查看历史 -> 详情展示
  - 预警生成 -> 通知发送
- **目标覆盖率**: 85%
- **状态**: [ ]

### T-BE-INT-003: Model 流程集成测试
- **描述**: 测试模型相关流程
- **文件**: `backend/tests/integration/test_model_flow.py`
- **覆盖**:
  - 模型加载 -> 预测 -> 结果返回
  - 模型失败 -> Fallback -> 启发式规则
  - 批量预测 -> 结果聚合
- **目标覆盖率**: 80%
- **状态**: [ ]

### T-BE-INT-004: Database 集成测试
- **描述**: 测试数据库操作
- **文件**: `backend/tests/integration/test_database.py`
- **覆盖**:
  - 连接池管理
  - 事务回滚
  - 迁移执行
- **目标覆盖率**: 80%
- **状态**: [ ]

### T-BE-INT-005: Error Handling 集成测试
- **描述**: 测试错误处理
- **文件**: `backend/tests/integration/test_errors.py`
- **覆盖**:
  - 404 处理
  - 422 验证错误
  - 500 内部错误
  - 全局异常处理
- **目标覆盖率**: 85%
- **状态**: [ ]

---

## 5. Phase 4: 前端单元测试

### T-FE-UNIT-001: LoginForm 组件测试
- **描述**: 测试登录表单组件
- **文件**: `frontend/src/__tests__/unit/components/LoginForm.test.ts`
- **覆盖**:
  - 表单验证
  - 错误提示
  - 提交事件
- **目标覆盖率**: 80%
- **状态**: [ ]

### T-FE-UNIT-002: RiskAssessment 组件测试
- **描述**: 测试风险评估组件
- **文件**: `frontend/src/__tests__/unit/components/RiskAssessment.test.ts`
- **覆盖**:
  - 问卷交互
  - 提交逻辑
  - 结果展示
- **目标覆盖率**: 75%
- **状态**: [ ]

### T-FE-UNIT-003: WarningList 组件测试
- **描述**: 测试预警列表组件
- **文件**: `frontend/src/__tests__/unit/components/WarningList.test.ts`
- **覆盖**:
  - 列表渲染
  - 状态更新
  - 详情查看
- **目标覆盖率**: 75%
- **状态**: [ ]

### T-FE-UNIT-004: useAuth Composable 测试
- **描述**: 测试认证组合式函数
- **文件**: `frontend/src/__tests__/unit/composables/useAuth.test.ts`
- **覆盖**:
  - 登录状态管理
  - Token 存储
  - 权限检查
- **目标覆盖率**: 85%
- **状态**: [ ]

### T-FE-UNIT-005: useApi Composable 测试
- **描述**: 测试 API 组合式函数
- **文件**: `frontend/src/__tests__/unit/composables/useApi.test.ts`
- **覆盖**:
  - 请求拦截
  - 错误处理
  - 重试逻辑
- **目标覆盖率**: 80%
- **状态**: [ ]

### T-FE-UNIT-006: Utils 函数测试
- **描述**: 测试工具函数
- **文件**:
  - `frontend/src/__tests__/unit/utils/httpError.test.ts`
  - `frontend/src/__tests__/unit/utils/validators.test.ts`
- **覆盖**:
  - HTTP 错误处理
  - 表单验证
  - 数据格式化
- **目标覆盖率**: 90%
- **状态**: [ ]

---

## 6. Phase 5: E2E 测试

### T-E2E-001: Auth 流程 E2E 测试
- **描述**: 测试认证用户流程
- **文件**: `frontend/src/__tests__/e2e/auth.spec.ts`
- **覆盖**:
  - 注册 -> 登录 -> 首页
  - 登录失败 -> 错误提示
  - 登出 -> 跳转登录页
- **状态**: [ ]

### T-E2E-002: Risk Assessment 流程 E2E 测试
- **描述**: 测试风险评估流程
- **文件**: `frontend/src/__tests__/e2e/risk.spec.ts`
- **覆盖**:
  - 填写问卷 -> 提交 -> 查看结果
  - 查看历史评估
  - 预警信息查看
- **状态**: [ ]

### T-E2E-003: Counselor 流程 E2E 测试
- **描述**: 测试咨询师流程
- **文件**: `frontend/src/__tests__/e2e/counselor.spec.ts`
- **覆盖**:
  - 查看用户列表
  - 处理预警
  - 查看干预计划
- **状态**: [ ]

### T-E2E-004: Admin 流程 E2E 测试
- **描述**: 测试管理员流程
- **文件**: `frontend/src/__tests__/e2e/admin.spec.ts`
- **覆盖**:
  - 系统设置
  - 模板管理
  - 操作日志查看
- **状态**: [ ]

---

## 7. Phase 6: CI/CD 集成

### T-CI-001: 创建 v1.16 覆盖率工作流
- **描述**: 创建 GitHub Actions 工作流
- **文件**: `.github/workflows/v1.16-coverage.yml`
- **覆盖**:
  - 后端单元测试
  - 后端集成测试
  - 前端单元测试
  - E2E 测试
- **验收标准**: PR 自动触发测试
- **状态**: [ ]

### T-CI-002: 配置覆盖率报告上传
- **描述**: 配置 Codecov 或类似服务
- **文件**:
  - `.github/workflows/v1.16-coverage.yml` (更新)
  - `codecov.yml`
- **覆盖**:
  - 覆盖率报告生成
  - 覆盖率上传
  - PR 覆盖率检查
- **验收标准**: PR 显示覆盖率变化
- **状态**: [ ]

### T-CI-003: 配置覆盖率门禁
- **描述**: 配置覆盖率下降告警
- **文件**:
  - `.github/workflows/v1.16-coverage.yml` (更新)
- **覆盖**:
  - 覆盖率下降阻止合并
  - 覆盖率目标检查
- **验收标准**: 覆盖率低于 80% 时 PR 失败
- **状态**: [ ]

---

## 8. 任务依赖关系

```
Phase 1: 基础设施
  ├── T-INFRA-001 (目录结构)
  ├── T-INFRA-002 (测试依赖)
  ├── T-INFRA-003 (测试基类)
  ├── T-INFRA-004 (前端测试环境)
  └── T-INFRA-005 (Playwright 配置)
       │
       v
Phase 2: 后端单元测试
  ├── T-BE-UNIT-001 (Auth API)
  ├── T-BE-UNIT-002 (User Risk API)
  ├── T-BE-UNIT-003 (Counselor API)
  ├── T-BE-UNIT-004 (Auth Service)
  ├── T-BE-UNIT-005 (Risk Service)
  ├── T-BE-UNIT-006 (Model Service)
  ├── T-BE-UNIT-007 (User Repository)
  └── T-BE-UNIT-008 (Core 模块)
       │
       v
Phase 3: 后端集成测试
  ├── T-BE-INT-001 (Auth 流程)
  ├── T-BE-INT-002 (Risk 流程)
  ├── T-BE-INT-003 (Model 流程)
  ├── T-BE-INT-004 (Database)
  └── T-BE-INT-005 (Error Handling)
       │
       v
Phase 4: 前端单元测试 (可与 Phase 2/3 并行)
  ├── T-FE-UNIT-001 (LoginForm)
  ├── T-FE-UNIT-002 (RiskAssessment)
  ├── T-FE-UNIT-003 (WarningList)
  ├── T-FE-UNIT-004 (useAuth)
  ├── T-FE-UNIT-005 (useApi)
  └── T-FE-UNIT-006 (Utils)
       │
       v
Phase 5: E2E 测试
  ├── T-E2E-001 (Auth 流程)
  ├── T-E2E-002 (Risk 流程)
  ├── T-E2E-003 (Counselor 流程)
  └── T-E2E-004 (Admin 流程)
       │
       v
Phase 6: CI/CD 集成
  ├── T-CI-001 (工作流创建)
  ├── T-CI-002 (覆盖率上传)
  └── T-CI-003 (覆盖率门禁)
```

---

## 9. 验收标准

### 9.1 覆盖率目标

| 模块 | 目标覆盖率 | 测量方式 |
|---|---|---|
| 后端单元测试 | >= 80% | pytest-cov |
| 后端集成测试 | >= 80% | pytest-cov |
| 前端单元测试 | >= 80% | c8 |
| E2E 测试 | 核心流程覆盖 | Playwright |

### 9.2 质量标准

- [ ] 所有 P0 功能有对应的单元测试
- [ ] 所有 API 有对应的集成测试
- [ ] 核心用户流程有对应的 E2E 测试
- [ ] 测试通过率 100%
- [ ] 无 flaky 测试
- [ ] CI 中自动运行所有测试
- [ ] 覆盖率报告自动生成

---

> **文档版本**: v1.0
> **最后更新**: 2026-05-01
