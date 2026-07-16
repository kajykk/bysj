---
name: sys-security-hardening
description: >-
  This skill should be used when improving security posture — "漏洞扫描",
  "修高危漏洞", "权限审计", "数据脱敏", "敏感数据加密", "安全审计".
  It implements §4.4 of the optimization plan.
agent_created: true
---

# sys-security-hardening

## 用途
体系化治理漏洞、访问控制、数据保护与审计，使安全可防护、可审计、可合规。

## 何时使用
- WF-0 安全扫描、WF-1 修高危漏洞、WF-3 固化安全 SLA。
- 用户要求「扫漏洞」「做权限审计」「日志脱敏」。

## 执行流程
1. **漏洞扫描**：
   - Python 依赖/代码：`trivy fs`、`bandit`。
   - 前端依赖：`npm audit`（frontend）。
   - 镜像：`trivy image`（项目已有 `.trivyignore`）。
2. **优先级修复**：高危 24–72h、中危 7d；第三方组件版本管理。
3. **访问控制**：最小权限、角色分层（RBAC）；API 鉴权与权限校验统一；高权限操作二次确认 + 审计。
4. **数据保护**：敏感数据加密存储/传输；日志脱敏；导出权限控制；备份加密。
5. **审计**：登录/操作审计、异常访问检测、风险操作告警、应急响应机制。
6. **回归**：安全回归测试 + 权限变更审计；生产最小权限。

## 工具与脚本
- 扫描：`trivy`、`bandit`、`npm audit`、`pip-audit`。
- 审计：Sentry（已有 `@sentry/vue`）、结构化日志 + 脱敏中间件。
- 加密：密钥管理（`backend/.pii_key` 已存在，须规范使用）。

## 验收与 KPI（§3 / §9）
- 高危漏洞清零、中危按时效修复。
- 100% 关键接口鉴权与审计、敏感数据加密 100%、日志脱敏 100%。

## 与本工程栈的对应
- 后端鉴权在 `backend/app/api/v1/auth` 或 `app/core/security`。
- 前端 Sentry：`@sentry/vue`（frontend/package.json）。
- 隐私密钥：`backend/.pii_key`；PII 处理须脱敏。

## 注意事项
- 修复漏洞时防兼容/权限回归，需双人复核 + 安全回归测试。
- 密钥与 PII 严禁入库或打日志明文。
