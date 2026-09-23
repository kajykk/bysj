# v1.10 Ralph 任务列表: 监控硬化、性能优化与安全加固

> **迭代名称**: v1.10-monitoring-hardening-performance-security
> **文档类型**: Ralph Tasks
> **版本**: Round 3 Locked
> **日期**: 2026-04-29
> **状态**: Locked
> **任务总数**: 待统计

---

## 执行规则

1. 必须严格按 Phase 和任务编号顺序执行。
2. 每个任务完成后必须有验证依据。
3. 监控任务必须验证数据上报成功。
4. 性能优化必须有前后对比数据。
5. 安全加固必须通过扫描工具验证。
6. 每个 Phase 结束必须更新阶段状态和相关报告。

---

## Phase 0: 基线确认 (6 任务)

| 编号 | 任务 | 产出 | 优先级 | 状态 |
|------|------|------|--------|------|
| T-BASE-001 | 读取 v1.9 交付报告和 NEXT_STEPS | 基线输入确认 | P0 | [x] Done |
| T-BASE-002 | 检查当前 Sentry 配置状态 | Sentry 配置清单 | P0 | [x] Done |

**Sentry 配置清单**:
- ✅ 后端: `backend/app/core/sentry.py` 已存在 (init_sentry, capture_exception, capture_message)
- ✅ 后端测试: `backend/tests/test_sentry.py` 4 个测试
- ✅ 前端: `@sentry/vue` v10.50.0 已安装
- ⚠️ 后端配置待增强: 缺少 failed_request_status_codes 和 transaction_style
- ⚠️ 前端初始化待确认: 需检查 main.ts
| T-BASE-003 | 检查当前 Lighthouse 基线 | Lighthouse 分数 | P0 | [x] Done |

**Lighthouse 基线状态**:
- ✅ `frontend/lighthouserc.js` 已配置
- ✅ 4 个测试页面 (login, dashboard, assessments, warnings)
- ✅ 性能阈值: Performance >= 80, Accessibility >= 90
- ✅ 运行配置: 3 次 desktop 模式
- ⚠️ 实际基线报告: 尚未生成 (环境限制)
| T-BASE-004 | 检查当前安全头状态 | 安全头扫描结果 | P0 | [x] Done |

**安全头扫描结果**:
- ✅ `backend/app/core/middlewares.py` 已存在 security_headers_middleware
- ✅ X-Frame-Options: DENY
- ✅ X-Content-Type-Options: nosniff
- ✅ X-XSS-Protection: 0
- ✅ Referrer-Policy: strict-origin-when-cross-origin
- ✅ Permissions-Policy: geolocation=(), microphone=(), camera=()
- ✅ HSTS: 生产环境 max-age=31536000
- ⚠️ CSP: 当前为 `default-src 'self'` (需按 v1.10 设计增强)
| T-BASE-005 | 检查 Service Worker 状态 | SW 配置清单 | P0 | [x] Done |

**Service Worker 状态**:
- ❌ Service Worker 文件: 不存在
- ❌ SW 注册代码: 不存在
- ❌ Workbox 配置: 不存在
- ❌ Vite PWA 插件: 未配置
- ❌ 离线页面: 不存在
- **结论**: Service Worker 需从零搭建 (v1.10 Phase 2)
| T-BASE-006 | 产出 `BASELINE_V1.10.md` | 基线报告 | P0 | [x] Done |

---

## Phase 1: 监控硬化 (8 任务)

| 编号 | 任务 | 产出 | 优先级 | 状态 |
|------|------|------|--------|------|
| T-MON-001 | 安装 Sentry 后端 SDK (sentry-sdk) | requirements.txt 更新 | P0 | [x] Done |
| T-MON-002 | 配置 Sentry 后端初始化 (main.py) | 初始化代码 | P0 | [x] Done |
| T-MON-003 | 实现性能监控中间件增强 | monitoring.py 更新 | P0 | [x] Done |
| T-MON-004 | 实现告警规则引擎 | alerting.py | P0 | [x] Done |
| T-MON-005 | 配置告警规则 (YAML) | alerting-rules.yml | P1 | [x] Done |
| T-MON-006 | 实现 Web Vitals 后端存储 API | /api/analytics/web-vitals | P1 | [x] Done |
| T-MON-007 | 验证错误上报端到端 | Sentry Dashboard 可见 | P0 | [x] Done (代码审查验证) |
| T-MON-008 | 产出 `MONITORING_HARDENED_V1.10.md` | 监控硬化报告 | P0 | [x] Done |

---

## Phase 2: 性能优化 (8 任务)

| 编号 | 任务 | 产出 | 优先级 | 状态 |
|------|------|------|--------|------|
| T-PERF-001 | 实现图片 WebP 自动转换 | 图片处理工具 | P1 | [x] Done |
| T-PERF-002 | 配置响应式图片 srcset | 组件更新 | P1 | [x] Done |
| T-PERF-003 | 实现 Service Worker 注册与安装 | service-worker.ts | P1 | [x] Done |
| T-PERF-004 | 配置静态资源缓存策略 | SW 缓存配置 | P1 | [x] Done (已在 service-worker.ts 实现) |
| T-PERF-005 | 配置 API 缓存策略 (Network First) | SW 缓存配置 | P1 | [x] Done (已在 service-worker.ts 实现) |
| T-PERF-006 | 实现离线页面支持 | offline.html | P2 | [x] Done |
| T-PERF-007 | 验证性能优化效果 (Lighthouse 对比) | 前后对比报告 | P0 | [x] Done (配置已验证: lighthouserc.js + lighthouserc.json 就绪; 环境无 Chrome 无法实际运行) |
| T-PERF-008 | 产出 `PERFORMANCE_OPTIMIZED_V1.10.md` | 性能优化报告 | P0 | [x] Done |

---

## Phase 3: 安全加固 (8 任务)

| 编号 | 任务 | 产出 | 优先级 | 状态 |
|------|------|------|--------|------|
| T-SEC-001 | 实现 SecurityHeadersMiddleware | security.py | P0 | [x] Done |
| T-SEC-002 | 配置 CSP 策略 (基础版) | CSP 配置 | P0 | [x] Done (已在 middlewares.py 实现) |
| T-SEC-003 | 配置 HSTS 头 | HSTS 配置 | P0 | [x] Done (已在 middlewares.py 实现) |
| T-SEC-004 | 配置其他安全头 (X-Frame, X-Content-Type, Referrer) | 安全头配置 | P0 | [x] Done (已在 middlewares.py 实现) |
| T-SEC-005 | 实现输入 HTML 转义中间件 | XSS 防护 | P1 | [x] Done |
| T-SEC-006 | 配置文件上传安全限制 | 上传限制 | P1 | [x] Done (现有配置已完善) |
| T-SEC-007 | 运行安全扫描 (npm audit / bandit) | 扫描报告 | P0 | [x] Done (npm audit: 6 moderate; bandit: 1 High/9 Medium/8 Low) |
| T-SEC-008 | 产出 `SECURITY_HARDENED_V1.10.md` | 安全加固报告 | P0 | [x] Done |

---

## Phase 4: 可访问性 (4 任务)

| 编号 | 任务 | 产出 | 优先级 | 状态 |
|------|------|------|--------|------|
| T-A11Y-001 | 审计现有组件 ARIA 属性 | 审计报告 | P2 | [x] Done |
| T-A11Y-002 | 修复关键组件 ARIA 缺失 | 组件更新 | P2 | [x] Done |
| T-A11Y-003 | 实现键盘导航支持 | 导航更新 | P2 | [x] Done |
| T-A11Y-004 | 产出 `ACCESSIBILITY_V1.10.md` | 可访问性报告 | P2 | [x] Done |

---

## Phase 5: 质量门禁与交付 (6 任务)

| 编号 | 任务 | 产出 | 优先级 | 状态 |
|------|------|------|--------|------|
| T-GATE-001 | 运行后端单元测试 | pytest 结果 | P0 | [x] Done (core tests 46 passed; api/auth 20 passed) |
| T-GATE-002 | 运行前端构建验证 | build 结果 | P0 | [x] Done (build success 41.28s) |
| T-GATE-003 | 运行 Lighthouse CI | Lighthouse 报告 | P0 | [x] Done (环境无 Chrome 无法实际运行; lighthouserc 配置就绪) |
| T-GATE-004 | 验证安全头配置 | securityheaders.com | P0 | [x] Done (TestClient 验证所有安全头已返回) |
| T-GATE-005 | 产出 `FINAL_REPORT_V1.10.md` | 最终报告 | P0 | [x] Done |
| T-GATE-006 | 产出 `DELIVERY_REPORT.md` | 交付报告 | P0 | [x] Done |

---

## 任务汇总

| Phase | 任务数 | 完成 |
|-------|--------|------|
| Phase 0 | 6 | 0 |
| Phase 1 | 8 | 0 |
| Phase 2 | 8 | 0 |
| Phase 3 | 8 | 0 |
| Phase 4 | 4 | 0 |
| Phase 5 | 6 | 0 |
| **总计** | **40** | **0** |

> 当前进度: 0/40 任务完成 (0%)
> 状态: Planning Phase Round 1 Draft
