# 05-测试计划 (Test Plan)

> **迭代名称**: v1.13-coverage-sprint-40to60
> **日期**: 2026-04-30
> **状态**: Draft (Round 1)

---

## 1. 测试策略

### 1.1 测试类型

| 类型 | 范围 | 目标 | 工具 |
|------|------|------|------|
| 单元测试 | core/, services/ | >= 55% / >= 50% | pytest, mock |
| API 测试 | api/ | >= 45% | TestClient |
| 集成测试 | services + api | >= 40% | pytest, SQLite |

### 1.2 测试优先级

- **P0**: core/config, core/security, services/physiological, services/assessment, api/physiological, api/assessment
- **P1**: services/warning, services/user, services/auth, api/warning, api/user, api/auth
- **P2**: core/exceptions, 其他辅助模块

---

## 2. 测试用例清单

### 2.1 core/ 模块测试

#### TC-CORE-CONFIG-001: 配置加载测试
- **前置条件**: 存在 .env 文件
- **步骤**: 加载配置
- **预期结果**: 配置值正确加载

#### TC-CORE-CONFIG-002: 环境变量覆盖测试
- **前置条件**: 设置环境变量
- **步骤**: 加载配置
- **预期结果**: 环境变量覆盖默认值

#### TC-CORE-CONFIG-003: 默认值测试
- **前置条件**: 无环境变量
- **步骤**: 加载配置
- **预期结果**: 使用默认值

#### TC-CORE-SEC-001: 密码哈希测试
- **前置条件**: 明文密码
- **步骤**: 调用 hash_password
- **预期结果**: 返回哈希值，可验证

#### TC-CORE-SEC-002: JWT 生成测试
- **前置条件**: 用户数据
- **步骤**: 调用 create_access_token
- **预期结果**: 返回有效 JWT

#### TC-CORE-SEC-003: JWT 验证测试
- **前置条件**: 有效 JWT
- **步骤**: 调用 verify_token
- **预期结果**: 返回用户数据

#### TC-CORE-SEC-004: 无效 JWT 测试
- **前置条件**: 无效/过期 JWT
- **步骤**: 调用 verify_token
- **预期结果**: 抛出异常

#### TC-CORE-EXC-001: 自定义异常测试
- **前置条件**: 触发业务异常
- **步骤**: 抛出自定义异常
- **预期结果**: 异常信息正确

---

### 2.2 services/ 模块测试

#### TC-SVC-PHY-001: 生理数据获取测试
- **前置条件**: 用户存在
- **步骤**: 调用 get_physiological_data
- **预期结果**: 返回数据列表

#### TC-SVC-PHY-002: 生理数据处理测试
- **前置条件**: 原始数据
- **步骤**: 调用 process_physiological_data
- **预期结果**: 返回处理后的数据

#### TC-SVC-PHY-003: 生理数据异常测试
- **前置条件**: 无效用户 ID
- **步骤**: 调用 get_physiological_data
- **预期结果**: 抛出 NotFoundError

#### TC-SVC-AST-001: 评估创建测试
- **前置条件**: 用户存在，数据有效
- **步骤**: 调用 create_assessment
- **预期结果**: 返回评估对象

#### TC-SVC-AST-002: 评估查询测试
- **前置条件**: 评估存在
- **步骤**: 调用 get_assessment
- **预期结果**: 返回评估详情

#### TC-SVC-AST-003: 评估更新测试
- **前置条件**: 评估存在
- **步骤**: 调用 update_assessment
- **预期结果**: 数据已更新

#### TC-SVC-WRN-001: 警告生成测试
- **前置条件**: 异常生理数据
- **步骤**: 调用 generate_warning
- **预期结果**: 返回警告对象

#### TC-SVC-WRN-002: 警告查询测试
- **前置条件**: 警告存在
- **步骤**: 调用 get_warnings
- **预期结果**: 返回警告列表

#### TC-SVC-USR-001: 用户创建测试
- **前置条件**: 新用户信息
- **步骤**: 调用 create_user
- **预期结果**: 返回用户对象

#### TC-SVC-AUTH-001: 登录验证测试
- **前置条件**: 用户存在
- **步骤**: 调用 authenticate_user
- **预期结果**: 返回用户对象

#### TC-SVC-AUTH-002: 无效登录测试
- **前置条件**: 错误密码
- **步骤**: 调用 authenticate_user
- **预期结果**: 返回 None

---

### 2.3 api/ 模块测试

#### TC-API-PHY-001: GET /physiological 测试
- **前置条件**: 用户已认证
- **步骤**: 发送 GET 请求
- **预期结果**: 200 OK，返回数据

#### TC-API-PHY-002: POST /physiological 测试
- **前置条件**: 用户已认证，数据有效
- **步骤**: 发送 POST 请求
- **预期结果**: 201 Created

#### TC-API-AST-001: GET /assessment 测试
- **前置条件**: 用户已认证
- **步骤**: 发送 GET 请求
- **预期结果**: 200 OK

#### TC-API-AST-002: POST /assessment 测试
- **前置条件**: 用户已认证
- **步骤**: 发送 POST 请求
- **预期结果**: 201 Created

#### TC-API-WRN-001: GET /warning 测试
- **前置条件**: 用户已认证
- **步骤**: 发送 GET 请求
- **预期结果**: 200 OK

#### TC-API-WRN-002: PUT /warning/{id} 测试
- **前置条件**: 用户已认证，警告存在
- **步骤**: 发送 PUT 请求
- **预期结果**: 200 OK

#### TC-API-USR-001: GET /user 测试
- **前置条件**: 用户已认证
- **步骤**: 发送 GET 请求
- **预期结果**: 200 OK

#### TC-API-AUTH-001: POST /auth/login 测试
- **前置条件**: 用户存在
- **步骤**: 发送 POST 请求
- **预期结果**: 200 OK，返回 Token

#### TC-API-AUTH-002: POST /auth/register 测试
- **前置条件**: 新用户信息
- **步骤**: 发送 POST 请求
- **预期结果**: 201 Created

---

## 3. 覆盖率目标

| 模块 | 当前 | 目标 | 差距 |
|------|------|------|------|
| 整体 | 40% | 60% | +20% |
| core/ | ?% | 55% | ?% |
| services/ | ?% | 50% | ?% |
| api/ | ?% | 45% | ?% |

---

## 4. 验收标准

- [ ] 所有 P0 测试通过
- [ ] 整体覆盖率 >= 60%
- [ ] 无回归测试失败
- [ ] CI workflow 通过

---

> **文档版本**: v1.0-Draft
> **最后更新**: 2026-04-30
