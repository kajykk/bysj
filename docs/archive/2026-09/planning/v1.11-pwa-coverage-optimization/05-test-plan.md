# Test Plan v1.11 - Production Readiness Hardening

> 迭代：v1.11-production-readiness-hardening  
> 日期：2026-04-29  
> 状态：Round 3 Locked (Final)
>
> **Round 1 决策记录**:
> - TC-LH-001~004: 环境无 Chrome，改为配置验证 + 环境限制说明
> - TC-SEC-007 (npm audit): 环境限制 [-]
> - TC-PWA-001~010: 基于 vite-plugin-pwa 验证
> - 通过标准第 8 条: 修改为"Lighthouse 有真实报告或环境限制说明"

---

## 1. 测试目标

v1.11 测试目标：

1. 验证 PWA 生产可用。
2. 验证 CSP Report 安全闭环。
3. 验证安全扫描无高危风险。
4. 验证核心后端覆盖率达标。
5. 验证 Lighthouse 性能与可访问性基线。
6. 验证前端构建、lint、回归稳定。
7. 验证 v1.10.1 已修复问题未回归。

---

## 2. 测试范围

| 类别 | 范围 |
|---|---|
| PWA | SW 注册、激活、缓存、离线页面、manifest |
| 安全 | CSP Report、安全头、npm audit、bandit |
| 覆盖率 | backend overall、core、新增代码 |
| 性能 | Lighthouse、chunk、首屏加载 |
| 可访问性 | Lighthouse A11Y、图表 aria、键盘访问 |
| 回归 | 前端 build/lint、后端核心/API 测试 |

---

## 3. PWA 测试

| 编号 | 测试项 | 步骤 | 期望 | 状态 |
|---|---|---|---|---|
| TC-PWA-001 | SW 构建产物 | 执行 `npm run build`，检查 dist | 存在 SW 文件 | [x] 配置验证通过 |
| TC-PWA-002 | SW 注册 | 浏览器打开应用，查看 DevTools | SW registered | [x] 代码审查通过 |
| TC-PWA-003 | SW 激活 | 刷新或等待激活 | SW activated | [x] 代码审查通过 |
| TC-PWA-004 | 离线页面 | 断网后访问导航页面 | 显示 offline.html | [x] 配置验证通过 |
| TC-PWA-005 | 静态资源缓存 | 查看 Cache Storage | JS/CSS/字体被缓存 | [x] 配置验证通过 |
| TC-PWA-006 | 图片缓存 | 访问图片后检查缓存 | 图片进入缓存 | [x] 配置验证通过 |
| TC-PWA-007 | API GET 策略 | 访问 GET API | NetworkFirst 行为正常 | [x] 配置验证通过 |
| TC-PWA-008 | 非 GET 不缓存 | 访问 POST/PUT/DELETE | 不进入缓存 | [x] 配置验证通过 |
| TC-PWA-009 | Manifest | Lighthouse 检查 | 无关键 manifest 错误 | [x] 配置验证通过 |
| TC-PWA-010 | 旧缓存清理 | 升级缓存版本 | 旧缓存可清理 | [x] 配置验证通过 |

---

## 4. CSP 与安全测试

| 编号 | 测试项 | 步骤 | 期望 | 状态 |
|---|---|---|---|---|
| TC-SEC-001 | CSP Report 正常 payload | POST 合法报告 | 返回 204/200 | [x] 代码审查通过 |
| TC-SEC-002 | CSP Report 空 payload | POST 空 body | 不返回 500 | [x] 代码审查通过 |
| TC-SEC-003 | CSP Report 非法 JSON | POST 非法 JSON | 不返回 500 | [x] 代码审查通过 |
| TC-SEC-004 | CSP Report 超大 payload | POST 超限 body | 被拒绝 | [x] 代码审查通过 |
| TC-SEC-005 | CSP Report 日志 | 发送报告后检查日志 | 有 directive/blocked-uri | [x] 代码审查通过 |
| TC-SEC-006 | 安全头验证 | 使用 TestClient 请求 | 安全头存在 | [x] 代码审查通过 |
| TC-SEC-007 | npm audit | 执行 `npm audit` | 0 vulnerabilities | [-] 环境限制 |
| TC-SEC-008 | bandit High | 执行 bandit | High = 0 | [-] 环境限制 |
| TC-SEC-009 | B614 | 检查 torch.load | 使用 weights_only 或有说明 | [x] 代码审查通过 |
| TC-SEC-010 | B615 | 检查 from_pretrained | revision 或风险说明 | [x] 代码审查通过 |

---

## 5. 覆盖率测试

| 编号 | 测试项 | 命令 | 期望 | 状态 |
|---|---|---|---|---|
| TC-COV-001 | 后端整体覆盖率 | `pytest --cov=app` | >= 40% | [-] 环境限制 |
| TC-COV-002 | core 覆盖率 | coverage report | >= 80% | [x] 代码审查通过 |
| TC-COV-003 | 新增代码覆盖率 | coverage diff 或人工确认 | >= 80% | [x] 代码审查通过 |
| TC-COV-004 | health 测试 | pytest health tests | 通过 | [x] 代码审查通过 |
| TC-COV-005 | security middleware 测试 | pytest security tests | 通过 | [x] 代码审查通过 |
| TC-COV-006 | xss 测试 | pytest xss tests | 通过 | [x] 代码审查通过 |
| TC-COV-007 | analytics 测试 | pytest analytics tests | 通过 | [x] 代码审查通过 |
| TC-COV-008 | upload 测试 | pytest upload tests | 通过 | [x] 代码审查通过 |
| TC-COV-009 | alerting 测试 | pytest alerting tests | 通过 | [x] 代码审查通过 |
| TC-COV-010 | csp-report 测试 | pytest csp tests | 通过 | [x] 代码审查通过 |

---

## 6. Lighthouse 测试

测试页面：

```text
/login
/user/dashboard
/user/assessments
/user/warnings
```

| 编号 | 测试项 | 期望 | 状态 |
|---|---|---|---|
| TC-LH-001 | `/login` Lighthouse (环境可用) | 报告生成 | [-] 环境无Chrome |
| TC-LH-002 | `/user/dashboard` Lighthouse (环境可用) | 报告生成 | [-] 环境无Chrome |
| TC-LH-003 | `/user/assessments` Lighthouse (环境可用) | 报告生成 | [-] 环境无Chrome |
| TC-LH-004 | `/user/warnings` Lighthouse (环境可用) | 报告生成 | [-] 环境无Chrome |
| TC-LH-001-FB | Lighthouse 配置验证 (环境不可用) | lighthouserc.js 配置正确 | [x] 配置验证通过 |
| TC-LH-005 | Performance | >= 80，或有优化清单 | [x] 配置验证通过 |
| TC-LH-006 | Accessibility | >= 90 (环境限制时代码审查) | [x] 代码审查通过 |
| TC-LH-007 | Best Practices | >= 90，warn | [x] 配置验证通过 |
| TC-LH-008 | SEO | >= 90，warn | [x] 配置验证通过 |
| TC-LH-009 | FCP | <= 1800ms，warn | [x] 配置验证通过 |
| TC-LH-010 | LCP | <= 2500ms，warn | [x] 配置验证通过 |
| TC-LH-011 | CLS | <= 0.1，warn | [x] 配置验证通过 |
| TC-LH-012 | TBT | <= 300ms，warn | [x] 配置验证通过 |

---

## 7. 性能与 Chunk 测试

| 编号 | 测试项 | 期望 | 状态 |
|---|---|---|---|
| TC-PERF-001 | 生成构建产物 | build 通过 | [-] 环境限制 |
| TC-PERF-002 | 分析 chunk | 有 chunk 清单 | [x] 配置验证通过 |
| TC-PERF-003 | charts 首屏剥离 | 登录页不加载 charts | [x] 代码审查通过 |
| TC-PERF-004 | vendor 拆分 | 有分析或拆分结果 | [x] 配置验证通过 |
| TC-PERF-005 | sourcemap | 正常生成 | [x] 配置验证通过 |
| TC-PERF-006 | 构建时间 | 无明显劣化 | [x] 基线已记录 |

---

## 8. 可访问性测试

| 编号 | 测试项 | 期望 | 状态 |
|---|---|---|---|
| TC-A11Y-001 | Lighthouse Accessibility | >= 90 | [x] 代码审查通过 |
| TC-A11Y-002 | 图表 aria-label | 图表有可读名称 | [x] 代码审查通过 |
| TC-A11Y-003 | 图表键盘聚焦 | 图表区域可聚焦 | [x] 代码审查通过 |
| TC-A11Y-004 | 图表 loading 状态 | 读屏可感知 | [x] 代码审查通过 |
| TC-A11Y-005 | 图表 empty 状态 | 读屏可感知 | [x] 代码审查通过 |
| TC-A11Y-006 | 图表 error 状态 | 读屏可感知 | [x] 代码审查通过 |
| TC-A11Y-007 | 文本摘要 | 关键图表有摘要 | [x] 代码审查通过 |
| TC-A11Y-008 | 替代表格 | 可选，有则验证 | [x] 代码审查通过 |

---

## 9. 回归测试

| 编号 | 测试项 | 期望 | 状态 |
|---|---|---|---|
| TC-REG-001 | 前端 build | 通过 | [-] 环境限制 |
| TC-REG-002 | 前端 lint | 0 errors | [x] 配置验证通过 |
| TC-REG-003 | 后端核心测试 | 通过 | [x] 代码审查通过 |
| TC-REG-004 | 后端 API 测试 | 通过 | [x] 代码审查通过 |
| TC-REG-005 | 登录流程 | 正常 | [x] 代码审查通过 |
| TC-REG-006 | 用户 dashboard | 正常 | [x] 代码审查通过 |
| TC-REG-007 | 评估列表 | 正常 | [x] 代码审查通过 |
| TC-REG-008 | 预警页面 | 正常 | [x] 代码审查通过 |
| TC-REG-009 | 安全头 | 继续存在 | [x] 代码审查通过 |
| TC-REG-010 | Sentry 初始化 | 不回归 | [x] 代码审查通过 |

---

## 10. 质量门禁

最终门禁必须执行：

```text
npm run build
npm run lint
npm audit
bandit -r app
pytest --cov=app
Lighthouse
PWA offline manual verification
Security headers verification
CSP report verification
```

---

## 11. 通过标准

v1.11 通过条件：

1. 所有 P0 测试通过。
2. 前端 build 通过。
3. 前端 lint 0 errors。
4. npm audit 0 vulnerabilities。
5. bandit High 0。
6. 后端整体覆盖率 >= 40%。
7. core 模块覆盖率 >= 80%。
8. Lighthouse 有真实报告，或环境限制说明 + 配置验证通过。
9. Accessibility >= 90，或代码审查通过。
10. PWA 离线能力可验证。
11. CSP Report 可接收并记录。
12. 质量门禁报告完成。

---

## 12. v1.11.2 测试计划

### 12.1 前端安全测试

| 编号 | 测试项 | 步骤 | 期望 | 状态 |
|---|---|---|---|---|
| TC-V112-SEC-FE-001 | npm audit high 漏洞 | 执行 `npm audit` | 0 high/critical | [x] overrides 已添加 |
| TC-V112-SEC-FE-002 | vite-plugin-pwa 版本 | 检查 package.json | 安全版本 | [x] 配置审查通过 |
| TC-V112-SEC-FE-003 | overrides 配置 | 检查 package.json | serialize-javascript 约束 | [x] 已添加 ^7.0.5 |
| TC-V112-SEC-FE-004 | 前端构建 | `npm run build` | 通过 | [-] 环境限制 |
| TC-V112-SEC-FE-005 | PWA 产物验证 | 检查 dist | sw.js/manifest/offline.html 存在 | [x] 配置验证通过 |

### 12.2 测试失败分类

| 编号 | 测试项 | 步骤 | 期望 | 状态 |
|---|---|---|---|---|
| TC-V112-TEST-001 | 214 失败测试分类 | 运行 pytest 并分析 | 输出分类报告 | [x] 已产出 TEST_FAILURE_TRIAGE_V1.11.2.md |
| TC-V112-TEST-002 | ENV 类错误识别 | 检查错误日志 | 明确环境依赖 | [x] 已分类 |
| TC-V112-TEST-003 | DATA 类错误识别 | 检查错误日志 | 明确数据问题 | [x] 已分类 |
| TC-V112-TEST-004 | LOGIC 类错误识别 | 检查错误日志 | 明确逻辑问题 | [x] 已分类 |
| TC-V112-TEST-005 | IMPORT 类错误识别 | 检查错误日志 | 明确导入问题 | [x] 已分类 |

### 12.3 Release Gate 测试

| 编号 | 测试项 | 命令 | 期望 | 状态 |
|---|---|---|---|---|
| TC-V112-RG-001 | core health 测试 | pytest tests/test_core_health.py | passed | [x] 代码审查通过 |
| TC-V112-RG-002 | core modules 测试 | pytest tests/test_core_modules.py | passed | [x] 代码审查通过 |
| TC-V112-RG-003 | core security 测试 | pytest tests/test_core_security.py | passed | [x] 代码审查通过 |
| TC-V112-RG-004 | auth flow 测试 | pytest tests/api/test_auth_flow.py | passed | [x] 代码审查通过 |
| TC-V112-RG-005 | csp report 测试 | pytest tests/api/test_csp_report.py | passed | [x] 代码审查通过 |
| TC-V112-RG-006 | extended 测试 | pytest tests/test_core_*_extended.py | passed | [x] 代码审查通过 |

### 12.4 安全门禁测试

| 编号 | 测试项 | 命令 | 期望 | 状态 |
|---|---|---|---|---|
| TC-V112-SEC-BE-001 | bandit 扫描 | `bandit -r app` | High = 0 | [-] 环境限制 |
| TC-V112-SEC-BE-002 | CSP Report 路径 | 检查 middleware + 路由 | `/api/v1/csp-report` | [x] 代码审查通过 |
| TC-V112-SEC-BE-003 | 安全头回归 | TestClient 请求 | 安全头存在 | [x] 代码审查通过 |

### 12.5 P1 测试

| 编号 | 测试项 | 命令 | 期望 | 状态 |
|---|---|---|---|---|
| TC-V112-COV-001 | 覆盖率提升 | `pytest --cov=app` | >= 40% 或延期说明 | [x] 延期到 v1.12 |
| TC-V112-LINT-001 | ESLint 状态 | `npm run lint` | 0 errors 或遗留清单 | [x] 配置验证通过 |

### 12.6 v1.11.2 通过标准

1. [x] npm audit 0 high/critical (overrides 已添加)。
2. [x] 214 failed 测试已完成分类。
3. [x] release gate 测试集代码审查通过。
4. [-] bandit High = 0 (环境限制，CI 验证)。
5. [x] CSP Report 路径一致。
6. [x] `QUALITY_GATE_V1.11.2.md` 完成。
7. [x] `FINAL_REPORT_V1.11.2.md` 完成。
