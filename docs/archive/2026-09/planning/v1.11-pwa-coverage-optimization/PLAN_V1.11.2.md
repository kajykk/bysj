# Plan v1.11.2 - Security & Test Closure

> **迭代**: v1.11.2-security-test-closure  
> **日期**: 2026-04-30  
> **状态**: Ready to Start  
> **基线报告**: `E:\code\bysj\VERIFICATION_REPORT_v1.11.1.md`  
> **目标**: 修复 v1.11.1 验证中发现的安全与测试阻塞项，使 v1.11 能进入生产候选状态

---

## 1. 背景

v1.11 已完成 PWA、CSP Report、测试补强、图表可访问性、chunk 拆分策略等实现工作。v1.11.1 验证报告进一步确认：

- 前端依赖可安装。
- 前端生产构建通过。
- PWA 产物已生成。
- PWA 图标已补齐。
- pytest 可收集 1397 个测试。
- bandit 无 High。
- CSP Report 路径已统一为 `/api/v1/csp-report`。

但仍存在生产放行阻塞项：

1. `npm audit` 存在 4 个 high 漏洞。
2. pytest 全量测试存在 214 个失败。
3. 覆盖率为 33%，未达到 v1.11 原目标 40%。
4. bandit 仍有 9 个 Medium B615。
5. Lighthouse 与 PWA 浏览器行为仍需补充记录。

因此，v1.11.2 的定位是安全与测试收口，不新增业务功能。

---

## 2. 迭代定位

v1.11.2 是一个修复收口迭代：

```text
v1.11.1 验证发现阻塞项
    ↓
v1.11.2 修复安全漏洞、分类失败测试、建立 release gate
    ↓
质量门禁通过后，v1.11 可归档为生产候选
```

---

## 3. 总目标

| 编号 | 目标 | 优先级 |
|---|---|---|
| G1 | 修复或规避 `npm audit` 4 个 high 漏洞 | P0 |
| G2 | 将 214 个失败测试完成分类并收敛 P0 测试集 | P0 |
| G3 | 建立最小生产放行 release gate 测试集 | P0 |
| G4 | 明确测试环境依赖配置 | P0 |
| G5 | 保持 `bandit High = 0` | P0 |
| G6 | 确认 CSP Report 路径 `/api/v1/csp-report` 一致 | P0 |
| G7 | 覆盖率提升到 40%，或形成明确延期说明 | P1 |
| G8 | 收敛 B615 Medium 风险或形成风险接受说明 | P1 |
| G9 | 补充 PWA 浏览器验证与 Lighthouse 记录 | P1 |
| G10 | 输出 v1.11.2 质量门禁与最终报告 | P0 |

---

## 4. 非目标

v1.11.2 不包含：

1. 新业务功能开发。
2. 完整 CI/CD 自动部署。
3. 覆盖率提升到 60%。
4. Playwright 全量 E2E。
5. CSP Enforcement。
6. 离线写入与后台同步。
7. services 层全面重构。
8. BERT 模型体系重构。

---

## 5. P0 任务

### 5.1 前端安全漏洞修复

| 编号 | 任务 | 验收 |
|---|---|---|
| V112-SEC-FE-001 | 升级 `vite-plugin-pwa` 到安全版本 | `npm audit` high/critical 为 0 |
| V112-SEC-FE-002 | 如上游未修复，使用 `overrides` 约束 `serialize-javascript` | `npm audit` high/critical 为 0 |
| V112-SEC-FE-003 | 修复后执行前端构建 | `npm run build` 通过 |
| V112-SEC-FE-004 | 验证 PWA 产物仍存在 | `sw.js`、manifest、offline.html 存在 |

### 5.2 测试失败分类与 release gate

| 编号 | 任务 | 验收 |
|---|---|---|
| V112-TEST-001 | 对 214 个失败测试按原因分类 | 输出 `TEST_FAILURE_TRIAGE_V1.11.2.md` |
| V112-TEST-002 | 区分环境依赖、测试数据、业务逻辑、历史过期测试 | 每类有处理策略 |
| V112-TEST-003 | 建立 release gate 测试集 | P0 测试命令明确 |
| V112-TEST-004 | release gate 测试集通过 | 100% passed |
| V112-TEST-005 | 解决 import mismatch / 环境污染类错误 | 不再出现同类错误 |

### 5.3 测试环境依赖配置

| 编号 | 任务 | 验收 |
|---|---|---|
| V112-ENV-001 | 记录 Redis 依赖与启动方式 | 文档明确 |
| V112-ENV-002 | 记录 Celery eager/mock 策略 | 文档明确 |
| V112-ENV-003 | 记录 Postgres/测试数据库配置 | 文档明确 |
| V112-ENV-004 | 记录 BERT/模型 fixture 策略 | 文档明确 |
| V112-ENV-005 | 输出 `TEST_ENV_SETUP_V1.11.2.md` | 文档完成 |

### 5.4 安全门禁确认

| 编号 | 任务 | 验收 |
|---|---|---|
| V112-SEC-BE-001 | 执行 bandit | High = 0 |
| V112-SEC-BE-002 | 确认 CSP Report 路径一致 | header 与路由均为 `/api/v1/csp-report` |
| V112-SEC-BE-003 | 确认安全头未回归 | TestClient 或集成测试通过 |

---

## 6. P1 任务

| 编号 | 任务 | 验收 |
|---|---|---|
| V112-COV-001 | 覆盖率从 33% 提升到 40% | `pytest --cov=app` >= 40%，或形成延期说明 |
| V112-COV-002 | 优先补 `health`、`database`、`csp_report`、`xss` 测试 | 新增测试通过 |
| V112-SEC-B615-001 | 处理 B615 `from_pretrained` revision 风险 | Medium 数下降或有豁免说明 |
| V112-PWA-001 | 浏览器验证 SW registered/activated | 验证记录完成 |
| V112-LH-001 | Lighthouse 实跑 | Performance/A11Y/PWA 结果记录 |
| V112-LINT-001 | 确认 ESLint 状态 | 0 errors 或明确遗留清单 |

---

## 7. P2 延后任务

| 任务 | 建议版本 |
|---|---|
| 全量 1397 测试全部通过 | v1.12 测试专项 |
| 覆盖率达到 60% | v1.12 |
| Playwright 关键路径 E2E | v1.12 |
| CSP Enforcement | v1.12 |
| 离线写入同步 | v1.12 |
| Web Vitals 持久化 | v1.12 |

---

## 8. Release Gate 测试集

在全量测试完全收敛前，v1.11.2 采用最小生产放行测试集：

```bash
cd backend
pytest tests/test_core_health.py \
       tests/test_core_modules.py \
       tests/test_core_security.py \
       tests/api/test_auth_flow.py \
       tests/api/test_csp_report.py \
       tests/test_core_*_extended.py \
       -v
```

通过标准：

1. 所有 release gate 测试 100% passed。
2. 不出现 import mismatch。
3. 不依赖 Redis/Celery/BERT/Postgres 外部不可控服务。
4. CSP Report 测试全部通过。
5. core/security/auth 关键路径通过。

---

## 9. 验收标准

### P0 必须满足

| 类别 | 标准 |
|---|---|
| 前端构建 | `npm run build` 通过 |
| 前端安全 | `npm audit` 无 high / critical |
| PWA 产物 | `sw.js`、manifest、offline.html 存在 |
| 后端安全 | `bandit High = 0` |
| 测试 | release gate 测试集 100% 通过 |
| 测试 | 214 failed 已完成分类 |
| CSP | `/api/v1/csp-report` 路径一致 |
| 文档 | `QUALITY_GATE_V1.11.2.md` 完成 |

### P1 建议满足

| 类别 | 标准 |
|---|---|
| 覆盖率 | overall >= 40%，或有延期说明 |
| core 覆盖率 | >= 80% |
| Lighthouse | Performance >= 80 或有优化清单 |
| A11Y | Accessibility >= 90 |
| bandit Medium | <= 5 或有风险接受说明 |
| ESLint | 0 errors 或明确遗留清单 |

---

## 10. 交付物

v1.11.2 至少需要产出：

```text
PLAN_V1.11.2.md
TEST_FAILURE_TRIAGE_V1.11.2.md
TEST_ENV_SETUP_V1.11.2.md
SECURITY_REMEDIATION_V1.11.2.md
PWA_LIGHTHOUSE_VERIFICATION_V1.11.2.md
QUALITY_GATE_V1.11.2.md
FINAL_REPORT_V1.11.2.md
```

---

## 11. 启动条件

v1.11.2 可在以下条件满足后启动：

1. 已确认 `VERIFICATION_REPORT_v1.11.1.md` 为基线。
2. 已接受本计划中的 P0/P1/P2 划分。
3. 已明确 high 漏洞不得风险接受，必须修复或规避。
4. 已明确 release gate 测试集作为 v1.11.2 最小放行门槛。

---

## 12. 结论

v1.11.2 的核心目标是：

```text
修复 high 安全漏洞；
收敛测试失败；
建立最小生产放行测试集；
补齐验证记录；
让 v1.11 从“实现完成”进入“生产候选”。
```
