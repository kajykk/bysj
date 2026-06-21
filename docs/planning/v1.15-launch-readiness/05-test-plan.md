# 05-测试计划: v1.15 上线就绪

> **迭代名称**: v1.15-launch-readiness  
> **目标**: 用最小但有效的测试证明系统可上线  
> **日期**: 2026-05-01  
> **状态**: Draft

---

## 1. 测试策略

v1.15 测试策略以“上线风险”为核心，而不是单纯追求覆盖率数字。

测试优先级：

1. P0: 核心功能、部署启动、冒烟验证。
2. P1: CI/Docker 关键测试、关键模块测试。
3. P2: 覆盖率提升、完整 E2E、性能专项。

---

## 2. P0 上线准入测试

### 2.1 前端构建测试

| 编号 | 测试项 | 通过标准 | 状态 | 备注 |
|---|---|---|---|---|
| FE-P0-001 | 前端依赖安装 | 依赖安装成功 | ⚠️ 环境限制 | Windows 本地 exit -1073741510，CI 已配置 `npm ci` |
| FE-P0-002 | 前端生产构建 | 构建命令成功退出 | ⚠️ 环境限制 | Windows 本地 exit -1073741510，CI 已补充 `frontend-build` 任务 |
| FE-P0-003 | 首页访问 | 页面无白屏、无阻塞错误 | ⏳ 待测 | 需 CI/Docker 环境验证 |
| FE-P0-004 | 核心页面访问 | 核心业务页面可打开 | ⏳ 待测 | 需 CI/Docker 环境验证 |
| FE-P0-005 | API 错误提示 | 后端不可用时前端有合理提示 | ✅ 代码审查通过 | httpError + httpFeedback 机制完整 |

### 2.2 后端启动测试

| 编号 | 测试项 | 通过标准 | 状态 | 备注 |
|---|---|---|---|---|
| BE-P0-001 | 后端依赖安装 | 依赖安装成功 | ⚠️ 环境限制 | Windows 本地 exit -1073741510，CI 已配置 `pip install` |
| BE-P0-002 | 后端服务启动 | 服务正常监听端口 | ⚠️ 环境限制 | Windows 本地受限，CI/Docker 已配置启动命令 |
| BE-P0-003 | 健康检查 | 健康检查接口返回成功 | ✅ 代码审查通过 | `/health`, `/health/ready`, `/health/seed` 已配置 |
| BE-P0-004 | 启动日志 | 无 P0 级别启动错误 | ✅ 代码审查通过 | lifespan 中异常已捕获并记录 |

### 2.3 核心 API 测试

| 编号 | 测试项 | 通过标准 | 状态 | 备注 |
|---|---|---|---|---|
| API-P0-001 | 核心 API 成功路径 | 返回 2xx 和预期结构 | ✅ 代码审查通过 | auth, user_risk, counselor, admin 端点完整 |
| API-P0-002 | 核心 API 参数错误 | 返回 4xx 和结构化错误 | ✅ 代码审查通过 | 全局异常处理已安装 |
| API-P0-003 | 认证/权限路径 | 返回符合预期的认证结果 | ✅ 代码审查通过 | JWT + role/permission 验证完整 |
| API-P0-004 | 前后端联调 | 前端可成功消费后端响应 | ⏳ 待测 | 需 CI/E2E 环境验证 |

### 2.4 数据库测试

| 编号 | 测试项 | 通过标准 | 状态 | 备注 |
|---|---|---|---|---|
| DB-P0-001 | 数据库连接 | 后端可连接数据库 | ✅ 代码审查通过 | SQLite 默认，PostgreSQL 生产配置完整 |
| DB-P0-002 | 数据初始化/迁移 | 必要表结构可用 | ✅ 代码审查通过 | Alembic migration + SQLAlchemy create_all |
| DB-P0-003 | 核心数据写入 | 核心数据可创建 | ✅ 代码审查通过 | 模型层和 service 层已验证 |
| DB-P0-004 | 核心数据读取 | 核心数据可查询 | ✅ 代码审查通过 | 模型层和 service 层已验证 |

### 2.5 模型/算法测试

| 编号 | 测试项 | 通过标准 | 状态 | 备注 |
|---|---|---|---|---|
| ML-P0-001 | 模型/算法依赖 | 目标环境可加载必要依赖 | ✅ 实测通过 | 模型相关测试整体可运行，PyTorch/sklearn 可加载或有 fallback |
| ML-P0-002 | 典型输入执行 | 返回可展示结果 | ✅ 实测通过 | 已补齐 artifact，并将生理模型专用阈值校准为 35/55/75/90；模型测试通过 |
| ML-P0-003 | 异常输入执行 | 返回可理解错误，不崩溃 | ✅ 实测通过 | 模型相关测试 112 passed，异常/缺失路径与风险预期对比测试通过 |

---

## 3. P1 支撑测试

### 3.1 CI/Docker 测试

| 编号 | 测试项 | 通过标准 | 状态 | 备注 |
|---|---|---|---|---|
| CI-P1-001 | Docker/Linux 后端关键测试 | 关键测试通过 | ✅ 已配置 | `docker-compose.yml` + `Dockerfile.test` 已配置 |
| CI-P1-002 | CI 前端构建 | CI 中前端构建通过 | ✅ 已配置 | `pr-quality-gates.yml` 已补充 `frontend-build` |
| CI-P1-003 | CI 后端关键测试 | CI 中后端关键测试通过 | ✅ 已配置 | `pr-quality-gates.yml` 已有 unit/integration/contract 测试 |
| CI-P1-004 | 覆盖率报告 | 可生成则记录，不阻塞上线 | ✅ 已配置 | `coverage-check` job 已配置，阈值 40% |

### 3.2 sklearn 版本兼容性测试 (Phase 6 新增)

| 编号 | 测试项 | 通过标准 | 状态 | 备注 |
|---|---|---|---|---|
| SKL-P1-001 | sklearn 版本范围检查 | 当前版本在 >=1.3.2,<1.4.0 | ✅ 已配置 | `check_compatibility.py` + CI job |
| SKL-P1-002 | 模型文件存在性检查 | 6 个核心模型文件存在 | ✅ 已配置 | `check_compatibility.py` 自动验证 |
| SKL-P1-003 | 模型兼容性注册表检查 | 所有注册模型环境兼容 | ✅ 已配置 | `check_all_model_compatibilities()` |
| SKL-P1-004 | SimpleImputer fill_dtype 补丁 | 基于 sklearn 版本判断，容错安全 | ✅ 代码审查通过 | model_engine.py `_patch_simple_imputer` |

### 3.3 CI E2E 闭环测试 (Phase 6 新增)

| 编号 | 测试项 | 通过标准 | 状态 | 备注 |
|---|---|---|---|---|
| E2E-P1-001 | 后端启动健康检查 (CI) | curl /health 返回 ok，30s 内 | ✅ 已配置 | `e2e-tests.yml` 健康轮询 |
| E2E-P1-002 | 核心 API 验证 (CI) | /health, /health/ready, /health/seed 均 200 | ✅ 已配置 | `e2e-tests.yml` Verify core API 步骤 |
| E2E-P1-003 | 前端生产构建 + 服务 (CI) | `npm run build` 成功，`serve dist -l 5173` 可访问 | ✅ 已配置 | `e2e-tests.yml` production mode |
| E2E-P1-004 | E2E 全栈测试 (CI) | Playwright 对真实后端运行核心流程测试 | ✅ 已配置 | `e2e-tests.yml` Run E2E tests |
| E2E-P1-005 | PR 门禁 E2E Smoke | Mock API 模式 E2E smoke 通过 | ✅ 已配置 | `pr-quality-gates.yml` e2e-smoke job |

### 3.4 后端关键模块测试

| 编号 | 测试项 | 通过标准 | 状态 |
|---|---|---|---|
| BE-P1-001 | config 测试 | 配置加载符合预期 | ⏳ 待测 |
| BE-P1-002 | database 测试 | 数据库会话生命周期可用 | ⏳ 待测 |
| BE-P1-003 | security 测试 | Token 和认证逻辑符合预期 | ⏳ 待测 |
| BE-P1-004 | middleware 测试 | 请求 ID、安全头、CORS 符合预期 | ⏳ 待测 |

### 3.5 GDPR / PII 加密测试 (Phase 7 新增)

| 编号 | 测试项 | 通过标准 | 状态 | 备注 |
|---|---|---|---|---|
| GDPR-P1-001 | PII 加密 roundtrip | 加密后能正确解密回原文 | ✅ 通过 | `test_encrypt_decrypt_roundtrip` |
| GDPR-P1-002 | 字段级密钥隔离 | 同明文不同字段密文不同 | ✅ 通过 | `test_different_fields_have_different_keys` |
| GDPR-P1-003 | 空值/None 透传 | 不加密，直接返回 | ✅ 通过 | `test_empty_value_passthrough` |
| GDPR-P1-004 | 防止重复加密 | 已加密密文二次加密不改变 | ✅ 通过 | `test_double_encryption_prevented` |
| GDPR-P1-005 | 明文解密向后兼容 | 未加密的明文可"解密" | ✅ 通过 | `test_plaintext_passthrough_on_decrypt` |
| GDPR-P1-006 | mask_pii 完全脱敏 | 全部替换为 `*` | ✅ 通过 | `test_mask_pii_full` |
| GDPR-P1-007 | mask_pii 保留末尾 N 位 | 末尾 N 位保留 | ✅ 通过 | `test_mask_pii_keep_last` |
| GDPR-P1-008 | EncryptedString TypeDecorator | ORM 读写加解密正确 | ✅ 通过 | `test_encrypted_string_type_decorator` |
| GDPR-P1-009 | dev 环境密钥自动生成 | 缺失密钥时生成临时密钥 | ✅ 通过 | `test_ensure_pii_key_in_dev_generates` |
| GDPR-P1-010 | prod 环境密钥缺失抛错 | 缺失时抛 RuntimeError | ✅ 通过 | `test_ensure_pii_key_in_prod_raises` |
| GDPR-P1-011 | export 完整结构 | 返回所有 12 个数据集合 | ✅ 通过 | `test_export_returns_full_structure` |
| GDPR-P1-012 | export 缺失用户抛错 | ValueError "用户不存在" | ✅ 通过 | `test_export_raises_for_missing_user` |
| GDPR-P1-013 | anonymize 错误密码拒绝 | ValueError "密码错误" | ✅ 通过 | `test_anonymize_requires_password` |
| GDPR-P1-014 | anonymize 已删除用户拒绝 | ValueError "已被删除" | ✅ 通过 | `test_anonymize_already_deleted_raises` |
| GDPR-P1-015 | anonymize 正确密码完整流程 | username/email/phone 替换 + OperationLog + commit | ✅ 通过 | `test_anonymize_succeeds_with_correct_password` |
| GDPR-P1-016 | API export 未登录 401 | 返回 401/403 | ✅ 通过 | `test_export_endpoint_requires_auth` |
| GDPR-P1-017 | API delete 未登录 401 | 返回 401/403 | ✅ 通过 | `test_delete_endpoint_requires_auth` |
| GDPR-P1-018 | API delete 未二次确认 400 | confirm=false 返回 400 | ✅ 通过 | `test_delete_endpoint_requires_confirm` |

**汇总**: 18/18 通过 (`pytest tests/test_gdpr_pii.py`)

### 3.6 v1.15 遗留问题回归测试 (Phase 8 新增)

| 编号 | 测试项 | 通过标准 | 状态 | 备注 |
|---|---|---|---|---|
| BE-P8-001 | `test_gdpr_pii.py` 全套 | 18/18 通过 | ✅ 通过 | Phase 7 回归 |
| BE-P8-002 | `test_auth_p0p1.py::test_login_refresh_and_logout_flow` | 通过 | ✅ 通过 | 登录刷新登出流程 |
| BE-P8-003 | `test_auth_p0p1.py::test_profile_update_and_change_password` | 旧密码错误返回 400 + message | ✅ 通过 | 适配新 error 响应格式 |
| BE-P8-004 | `test_csp_report_smoke.py` 全套 | 9/9 通过 | ✅ 通过 | 重命名后无冲突 |
| BE-P8-005 | `test_data_loader_smoke.py` 全套 | 8/8 通过 | ✅ 通过 | 重命名后无冲突 |
| BE-P8-006 | `test_experiment_metrics_smoke.py` 全套 | 8/8 通过 | ✅ 通过 | 重命名后无冲突 |
| BE-P8-007 | `pytest --collect-only` 无收集错误 | 0 错误 | ✅ 通过 | 5 个冲突文件已修复 |
| FE-P8-001 | `npm run typecheck` | 0 错误 | ✅ 通过 | 25+ 类型错误已全部修复 |
| FE-P8-002 | Service Worker 类型 | 不在 include 中 | ✅ 通过 | 已从 tsconfig.app.json 排除 |
| FE-P8-003 | web-vitals 类型 | 类型声明可用 | ✅ 通过 | `src/types/web-vitals.d.ts` 已创建 |

**汇总**: 9/9 通过,`pytest` 5 套文件合计 45/45 通过,`npm run typecheck` 0 错误

---

## 4. P2 后置测试

以下测试不阻塞 v1.15 上线：

- 后端整体覆盖率达到 80%。
- 完整 E2E 自动化测试。
- Lighthouse 性能评分。
- 大规模兼容性测试。
- Windows 本地完整 pytest 稳定性验证。

---

## 5. 测试执行顺序

必须按以下顺序执行：

1. 前端生产构建。
2. 后端启动与健康检查。
3. 数据库连接与初始化。
4. 模型/算法典型输入验证。
5. 核心 API 成功路径。
6. 核心 API 失败路径。
7. 前后端核心流程手动验收。
8. Docker/Linux/CI 关键测试。
9. 上线阻塞清单复核。
10. Go/No-Go 决策。

---

## 6. 测试通过定义

### 6.1 可以上线

- 所有 P0 测试通过。
- 无 P0 上线阻塞项。
- P1 风险已记录且有后续计划。
- 回滚方案存在且可执行。

### 6.2 禁止上线

出现以下任一情况，判定 No-Go：

- 前端无法构建。
- 后端无法启动。
- 健康检查失败。
- 核心 API 失败。
- 核心数据无法读写。
- 核心模型/算法无法返回结果。
- 无法回滚。

---

> **文档版本**: v1.0-Draft  
> **最后更新**: 2026-05-01
