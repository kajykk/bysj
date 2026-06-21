# Learnings v1.11 - Production Readiness Hardening

> 迭代：v1.11-production-readiness-hardening  
> 日期：2026-04-29  
> 状态：Final Draft  
> 用途：沉淀 v1.10 / v1.10.1 经验，并指导 v1.11 执行

---

## 1. v1.10 / v1.10.1 成功经验

| 经验 | 效果 | v1.11 延续方式 |
|---|---|---|
| Sentry 延迟导入 | 避免环境兼容问题 | 可选依赖继续使用延迟导入 |
| TestClient 验证安全头 | 无需真实部署即可验证中间件 | CSP Report、安全头继续用 TestClient |
| 质量门禁收口 | 发现 SW 未编译问题 | v1.11 每个 Phase 后运行小门禁 |
| Vite 6 升级 | 修复前端依赖漏洞且构建稳定 | v1.11 保持依赖升级后必跑 build |
| bandit + npm audit | 清除 High 和 moderate 漏洞 | v1.11 纳入质量门禁 |
| 文档化交付 | 交付结果清晰可追踪 | v1.11 继续产出阶段报告 |

---

## 2. v1.10 / v1.10.1 教训

| 问题 | 原因 | v1.11 改进 |
|---|---|---|
| Service Worker 未编译 | 只有源码，缺少构建集成 | v1.11 优先配置 vite-plugin-pwa |
| Lighthouse 未实跑 | 缺少 Chrome 环境 | v1.11 必须在可运行环境中执行 |
| 覆盖率只有 28% | 历史迭代测试不足 | v1.11 核心覆盖率设为 P0 |
| MD5 进入生产代码 | 安全扫描前置不足 | v1.11 每轮运行 bandit |
| CSP 有 report-uri 但无端点 | 响应头配置与后端能力未闭环 | v1.11 实现 `/api/csp-report` |
| CSP unsafe-inline | 为框架兼容保守配置 | v1.11 Report-Only，v1.12 Enforcement |
| Chunk 体积偏大 | 图表/UI 库未充分拆分 | v1.11 控制首屏加载 |
| 图表 A11Y 不足 | 基础组件修复优先于数据可访问性 | v1.11 聚焦 BaseChart |

---

## 3. v1.11 决策记录

| 决策 | 选项 | 最终选择 | 理由 |
|---|---|---|---|
| PWA 工具 | vite-plugin-pwa / workbox-cli / 手写 SW | vite-plugin-pwa | 与 Vite 集成最好 |
| Workbox 模式 | generateSW / injectManifest | generateSW | v1.11 先保证生产可用 |
| 覆盖率目标 | 40% / 60% / 80% | v1.11 40%，v1.12 60% | 从 28% 直接到 60% 风险高 |
| CSP 策略 | 立即 Enforcement / Report-Only | Report-Only | 降低误阻断风险 |
| CSP unsafe-inline | 立即移除 / 分阶段移除 | 分阶段 | Vue/样式兼容性需验证 |
| Chunk 目标 | 全部 < 300KB / 首屏优先 | 首屏优先 | 更符合用户体验 |
| 离线能力 | 只读离线 / 离线写入同步 | v1.11 只做基础离线 | 离线写入复杂度高 |
| CI/CD | 完整流水线 / 质量门禁脚本 | 质量门禁优先 | 控制范围 |

---

## 4. v1.11 风险预判

| 风险 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|
| vite-plugin-pwa 与 Vite 6 兼容问题 | 中 | 高 | 先最小配置验证 |
| SW 缓存导致旧资源不更新 | 中 | 高 | 开启 cleanupOutdatedCaches，版本化缓存 |
| API 被错误缓存 | 低 | 高 | 只缓存 GET，排除认证接口 |
| Lighthouse 环境不稳定 | 中 | 中 | 跑 3 次取中位数 |
| 覆盖率提升耗时过长 | 高 | 中 | 优先 core 和新增模块 |
| bandit Medium 修复影响 ML | 中 | 中 | 优先低风险修复，必要时豁免 |
| CSP Report 被刷日志 | 中 | 中 | payload 限制、速率限制、采样 |
| A11Y 改动影响图表布局 | 低 | 中 | 保持视觉不变，增强语义 |
| chunk 拆分引发懒加载问题 | 中 | 中 | 每次拆分后 build 和回归 |

---

## 5. v1.11 执行原则

1. P0 优先，不被 P2 功能拖慢。
2. 每完成一个 Phase，立即做小范围验证。
3. 不为覆盖率写低价值测试。
4. 所有安全降级或豁免必须写入报告。
5. Lighthouse 不达标时，先形成瓶颈清单，再决定是否优化。
6. PWA 先保证可注册、可离线，不立即做复杂离线写入。
7. CSP 先 Report-Only，不直接生产 Enforcement。
8. 图表 A11Y 优先增强语义，不破坏现有视觉。
9. 最终结论必须基于验证结果，不凭代码审查判断完成。

---

## 6. v1.12 延续方向

v1.11 完成后，v1.12 建议继续：

| 方向 | 内容 |
|---|---|
| 覆盖率 | 后端整体覆盖率提升到 60% |
| PWA | IndexedDB、离线写入、后台同步 |
| CSP | 生产 Enforcement，移除 unsafe-inline |
| 性能 | 更细粒度 chunk 拆分 |
| 监控 | Web Vitals 持久化 |
| 告警 | 接入企业微信/钉钉/邮件 |
| CI/CD | 完整自动化部署流水线 |
| 安全 | bandit Medium 全部清理或正式豁免 |
