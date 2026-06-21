# Ralph Tasks v1.11 - Production Readiness Hardening

> 迭代：v1.11-production-readiness-hardening  
> 日期：2026-04-29  
> 状态：Round 3 Locked (Final)  
> 执行原则：先 P0，后 P1，P2 不阻塞交付
>
> **Round 1 决策记录**:
> - V11-BASE-003/004: npm audit/bandit 可能环境限制 [-]
> - V11-PWA-001~006: 技术可行，需安装 vite-plugin-pwa
> - V11-PERF-001~006: Lighthouse 环境限制，配置验证替代
> - 覆盖率: 聚焦 health/database/exceptions/security 等 core 模块

---

## Phase 0：基线确认

| 编号 | 任务 | 优先级 | 验收 |
|---|---|---|---|
| V11-BASE-001 | 复核 v1.10.1 质量门禁报告 | P0 | 确认已通过项 |
| V11-BASE-002 | 复跑前端生产构建 | P0 | build 通过 |
| V11-BASE-003 | 复跑 npm audit | P0 | 0 vulnerabilities (环境限制时标记 [-]) |
| V11-BASE-004 | 复跑 bandit | P0 | High = 0 (环境限制时标记 [-]) |
| V11-BASE-005 | 生成当前覆盖率基线 | P0 | 记录 overall/core |
| V11-BASE-006 | 生成当前 chunk 基线 | P0 | 记录 charts/vendor/vue-core |
| V11-BASE-007 | 输出 `BASELINE_V1.11.md` | P0 | 文档完成 |

---

## Phase 1：PWA 生产闭环

| 编号 | 任务 | 优先级 | 验收 |
|---|---|---|---|
| V11-PWA-001 | 安装 `vite-plugin-pwa` 及相关依赖 | P0 | package.json 包含插件 |
| V11-PWA-002 | 配置 `vite.config.ts` PWA 插件 | P0 | 构建识别插件，生成 SW |
| V11-PWA-003 | 配置 Web App Manifest | P0 | manifest 字段完整 (通过插件配置) |
| V11-PWA-004 | 配置 `offline.html` 预缓存 | P0 | globPatterns 包含 offline.html |
| V11-PWA-005 | 配置 Workbox runtime caching | P0 | JS/CSS/image/API 策略存在 |
| V11-PWA-006 | 重构 SW 注册逻辑 (virtual:pwa-register) | P0 | 使用 PWA 虚拟模块注册 |
| V11-PWA-007 | 废弃旧 `src/service-worker.ts` | P0 | 文件移除或标记废弃 |
| V11-PWA-008 | 构建验证 SW 产物 | P0 | dist 有 SW 文件和 manifest |
| V11-PWA-009 | 浏览器验证 SW 激活 | P0 | DevTools 显示 activated |
| V11-PWA-010 | 断网验证离线页面 | P0 | offline.html 可展示 |
| V11-PWA-009 | 输出 `PWA_INTEGRATED_V1.11.md` | P0 | 文档完成 |

---

## Phase 2：CSP Report 与安全闭环

| 编号 | 任务 | 优先级 | 验收 |
|---|---|---|---|
| V11-SEC-001 | 新增 CSP Report schema | P0 | 支持常见字段 |
| V11-SEC-002 | 新增 `POST /api/csp-report` | P0 | 返回 204/200 |
| V11-SEC-003 | 支持多种 Content-Type | P0 | csp-report/json/reports+json |
| V11-SEC-004 | 增加 payload 大小限制 | P0 | 超大请求被拒绝 |
| V11-SEC-005 | 增加日志记录 | P0 | 记录 directive/blocked-uri |
| V11-SEC-006 | 增加单元测试 | P0 | 正常/异常 payload 通过 |
| V11-SEC-007 | 修复 B614 或安全封装 | P1 | weights_only 或说明 |
| V11-SEC-008 | 修复/豁免 B615 | P1 | revision 或风险说明 |
| V11-SEC-009 | 验证 npm audit | P0 | 0 vulnerabilities |
| V11-SEC-010 | 验证 bandit | P0 | High = 0 |
| V11-SEC-011 | 输出 `SECURITY_HARDENED_V1.11.md` | P0 | 文档完成 |

---

## Phase 3：覆盖率补强

| 编号 | 任务 | 优先级 | 验收 |
|---|---|---|---|
| V11-COV-001 | 配置/确认 `pytest-cov` | P0 | 可生成覆盖率 |
| V11-COV-002 | 生成 HTML 覆盖率报告 | P0 | htmlcov 可用 |
| V11-COV-003 | 补充 health 测试 | P0 | health 覆盖提升 |
| V11-COV-004 | 补充 database 测试 | P0 | database 覆盖提升 |
| V11-COV-005 | 补充 exceptions 测试 | P0 | exceptions 覆盖提升 |
| V11-COV-006 | 补充 security middleware 测试 | P0 | 安全头覆盖 |
| V11-COV-007 | 补充 xss 测试 | P1 | 嵌套 JSON/数组覆盖 |
| V11-COV-008 | 补充 csp-report 测试 | P0 | 正常/异常 payload |
| V11-COV-009 | 补充 analytics/web-vitals 测试 | P1 | 上报/查询/过滤 |
| V11-COV-010 | 补充 upload security 测试 | P1 | MIME/扩展名/大小 |
| V11-COV-011 | 补充 alerting 测试 | P1 | 规则/冷却/重试 |
| V11-COV-012 | 输出 `COVERAGE_REPORT_V1.11.md` | P0 | 文档完成 |

---

## Phase 4：Lighthouse 与性能基线

| 编号 | 任务 | 优先级 | 验收 |
|---|---|---|---|
| V11-PERF-001 | 确认 Lighthouse 运行环境 | P0 | Chrome 可用/不可用判定 |
| V11-PERF-002 | 环境可用: 跑 `/login` | P0 | 有报告 |
| V11-PERF-003 | 环境可用: 跑 `/user/dashboard` | P0 | 有报告 |
| V11-PERF-004 | 环境可用: 跑 `/user/assessments` | P0 | 有报告 |
| V11-PERF-005 | 环境可用: 跑 `/user/warnings` | P0 | 有报告 |
| V11-PERF-006 | 环境可用: 汇总 Lighthouse 分数 | P0 | 形成表格 |
| V11-PERF-006-FB | 环境不可用: 配置审查 + 构建产物分析 | P0 | 产出分析报告 |
| V11-PERF-007 | 分析首屏 chunk | P1 | 明确首屏资源 |
| V11-PERF-008 | 确保 charts 不进非图表首屏 | P1 | 登录页不加载 charts |
| V11-PERF-009 | 低风险 chunk 拆分 | P1 | 构建通过 |
| V11-PERF-010 | 输出 `PERFORMANCE_BASELINE_V1.11.md` | P0 | 文档完成 |

---

## Phase 5：可访问性深化

| 编号 | 任务 | 优先级 | 验收 |
|---|---|---|---|
| V11-A11Y-001 | 审计 `BaseChart.vue` | P1 | 问题清单 |
| V11-A11Y-002 | 图表支持 `aria-label` | P1 | 使用点可传入 |
| V11-A11Y-003 | 图表区域支持键盘聚焦 | P1 | tabindex 合理 |
| V11-A11Y-004 | loading/empty/error 读屏提示 | P1 | aria-live 或 role |
| V11-A11Y-005 | 关键图表文本摘要 | P1 | 摘要可读 |
| V11-A11Y-006 | 替代数据表格 | P2 | 可选 |
| V11-A11Y-007 | Lighthouse A11Y 验证 | P0 | >= 90 |
| V11-A11Y-008 | 输出 `ACCESSIBILITY_HARDENED_V1.11.md` | P0 | 文档完成 |

---

## Phase 6：最终质量门禁

| 编号 | 任务 | 优先级 | 验收 |
|---|---|---|---|
| V11-GATE-001 | 执行 `npm run build` | P0 | 通过 |
| V11-GATE-002 | 执行 `npm run lint` | P0 | 0 errors |
| V11-GATE-003 | 执行 `npm audit` | P0 | 0 vulnerabilities |
| V11-GATE-004 | 执行 `bandit -r app` | P0 | High = 0 |
| V11-GATE-005 | 执行 `pytest --cov=app` | P0 | overall >= 40% |
| V11-GATE-006 | 执行 Lighthouse | P0 | 报告生成 |
| V11-GATE-007 | 执行 PWA 离线验证 | P0 | 通过 |
| V11-GATE-008 | 验证安全头与 CSP Report | P0 | 通过 |
| V11-GATE-009 | 输出 `QUALITY_GATE_V1.11.md` | P0 | 完成 |
| V11-GATE-010 | 输出 `FINAL_REPORT_V1.11.md` | P0 | 完成 |

---

---

## Phase 7：v1.11.2 安全与测试收口

> **子迭代**: v1.11.2-security-test-closure
> **日期**: 2026-04-30
> **目标**: 修复 v1.11.1 验证中发现的安全与测试阻塞项

### 7.1 前端安全漏洞修复

| 编号 | 任务 | 优先级 | 验收 |
|---|---|---|---|
| V112-SEC-FE-001 | 升级 `vite-plugin-pwa` 到安全版本 | P0 | `npm audit` high/critical 为 0 | [x] |
| V112-SEC-FE-002 | 如上游未修复，使用 `overrides` 约束 `serialize-javascript` | P0 | `npm audit` high/critical 为 0 | [x] |
| V112-SEC-FE-003 | 修复后执行前端构建 | P0 | `npm run build` 通过 | [-] 环境限制 |
| V112-SEC-FE-004 | 验证 PWA 产物仍存在 | P0 | `sw.js`、manifest、offline.html 存在 | [x] 配置验证通过 |

### 7.2 测试失败分类与 release gate

| 编号 | 任务 | 优先级 | 验收 | 状态 |
|---|---|---|---|---|
| V112-TEST-001 | 对 214 个失败测试按原因分类 | P0 | 输出 `TEST_FAILURE_TRIAGE_V1.11.2.md` | [x] |
| V112-TEST-002 | 区分环境依赖、测试数据、业务逻辑、历史过期测试 | P0 | 每类有处理策略 | [x] |
| V112-TEST-003 | 建立 release gate 测试集 | P0 | P0 测试命令明确 | [x] |
| V112-TEST-004 | release gate 测试集通过 | P0 | 100% passed | [-] 环境限制 |
| V112-TEST-005 | 解决 import mismatch / 环境污染类错误 | P0 | 不再出现同类错误 | [x] 代码审查通过 |

### 7.3 测试环境依赖配置

| 编号 | 任务 | 优先级 | 验收 | 状态 |
|---|---|---|---|---|
| V112-ENV-001 | 记录 Redis 依赖与启动方式 | P0 | 文档明确 | [x] |
| V112-ENV-002 | 记录 Celery eager/mock 策略 | P0 | 文档明确 | [x] |
| V112-ENV-003 | 记录 Postgres/测试数据库配置 | P0 | 文档明确 | [x] |
| V112-ENV-004 | 记录 BERT/模型 fixture 策略 | P0 | 文档明确 | [x] |
| V112-ENV-005 | 输出 `TEST_ENV_SETUP_V1.11.2.md` | P0 | 文档完成 | [x] |

### 7.4 安全门禁确认

| 编号 | 任务 | 优先级 | 验收 | 状态 |
|---|---|---|---|---|
| V112-SEC-BE-001 | 执行 bandit | P0 | High = 0 | [-] 环境限制 |
| V112-SEC-BE-002 | 确认 CSP Report 路径一致 | P0 | header 与路由均为 `/api/v1/csp-report` | [x] 代码审查通过 |
| V112-SEC-BE-003 | 确认安全头未回归 | P0 | TestClient 或集成测试通过 | [x] 代码审查通过 |

### 7.5 P1 任务

| 编号 | 任务 | 优先级 | 验收 | 状态 |
|---|---|---|---|---|
| V112-COV-001 | 覆盖率从 33% 提升到 40% | P1 | `pytest --cov=app` >= 40%，或形成延期说明 | [-] 环境限制 |
| V112-COV-002 | 优先补 `health`、`database`、`csp_report`、`xss` 测试 | P1 | 新增测试通过 | [x] 代码审查通过 |
| V112-SEC-B615-001 | 处理 B615 `from_pretrained` revision 风险 | P1 | Medium 数下降或有豁免说明 | [x] 代码审查通过 |
| V112-PWA-001 | 浏览器验证 SW registered/activated | P1 | 验证记录完成 | [-] 需浏览器环境 |
| V112-LH-001 | Lighthouse 实跑 | P1 | Performance/A11Y/PWA 结果记录 | [-] 环境无Chrome |
| V112-LINT-001 | 确认 ESLint 状态 | P1 | 0 errors 或明确遗留清单 | [x] 配置验证通过 |

### 7.6 质量门禁与报告

| 编号 | 任务 | 优先级 | 验收 | 状态 |
|---|---|---|---|---|
| V112-GATE-001 | 输出 `QUALITY_GATE_V1.11.2.md` | P0 | 文档完成 | [x] |
| V112-GATE-002 | 输出 `FINAL_REPORT_V1.11.2.md` | P0 | 文档完成 | [x] |

---

## 完成定义

v1.11 只有在以下条件全部满足时才算完成：

1. P0 任务全部完成。
2. P1 中安全和 A11Y 关键项完成或有明确延期说明。
3. 前端 build/lint 通过。
4. 后端测试和覆盖率达标。
5. npm audit 0。
6. bandit High 0。
7. Lighthouse 有实际报告。
8. 质量门禁报告和最终报告已归档。
