---
name: sysopt-security
description: "Security optimizer for vulnerability remediation, access control, data protection, and security audit. Invoke during system optimization when handling security vulnerabilities, permission risks, sensitive data encryption, log masking, or compliance issues."
---

# Skill: sysopt-security (安全性维度)

## 📋 技能描述 (Description)

这是系统优化的 **安全性维度专家**。
你的职责是处理漏洞修复、访问控制、数据保护、安全审计等安全相关问题。

## 使用场景 (Usage)

- 发现安全漏洞 (SQL 注入、XSS、CSRF、路径遍历等) 时。
- 权限边界不清、访问控制缺失时。
- 敏感数据未加密、日志未脱敏时。
- 依赖库存在已知漏洞时。
- 需要建立安全审计与应急响应机制时。
- 被 `sysopt-orchestrator` 以指定 mode 调用时。

## 工作模式 (Modes)

### Mode 1: assess (基线评估 - Phase 0)

**目标**：全面安全评估，识别安全风险。

**执行步骤**：
1. **漏洞扫描**：
   - 静态代码扫描 (Bandit/Semgrep/CodeQL)。
   - 依赖漏洞扫描 (pip-audit/safety/npm audit)。
   - 动态扫描 (OWASP ZAP/Burp)。
   - 按严重程度分级 (Critical/High/Medium/Low)。
2. **访问控制审计**：
   - 检查 API 鉴权覆盖率 (哪些接口未鉴权)。
   - 审计权限边界 (最小权限原则)。
   - 检查角色权限分层是否合理。
   - 检查管理端高权限操作是否有二次确认。
3. **数据保护评估**：
   - 识别敏感数据字段 (PII/PHI/财务数据)。
   - 检查传输加密 (HTTPS/TLS)。
   - 检查存储加密 (静态数据加密)。
   - 检查日志脱敏覆盖率。
4. **依赖安全**：
   - 梳理第三方依赖清单 (SBOM)。
   - 扫描已知漏洞 (CVE)。
   - 检查依赖版本是否过时。
5. **审计日志**：
   - 检查登录与操作审计完整性。
   - 检查异常访问检测能力。
   - 检查风险操作告警机制。

**输出**：
- 将问题写入 `.trae/sysopt/problem-inventory.md` (维度=security)。
- 将基线数据写入 `.trae/sysopt/kpi-baseline.md` 的安全分区。
- 生成 `.trae/sysopt/tasks/security.md` 任务清单。

---

### Mode 2: quickfix (快速止血 - Phase 1)

**目标**：修复高危漏洞，消除 immediate 安全风险。

**处理范围**：
- P0: 高危安全漏洞 (SQL 注入、RCE、认证绕过、敏感数据泄露)。
- P1: 高风险权限缺失、关键接口未鉴权。

**优化策略**：

#### 1) 漏洞修复
- **SQL 注入**：参数化查询/ORM，禁止字符串拼接 SQL。
- **XSS**：输出转义/CSP 策略/输入校验。
- **CSRF**：Token 验证/SameSite Cookie。
- **路径遍历**：拦截 null 字节、`..`、Windows 保留名 (CON/AUX/PRN)。
- **RCE**：禁止 eval/exec 用户输入，命令白名单。
- **依赖漏洞**：升级到安全版本，无法升级则打补丁。

#### 2) 访问控制加固
- 最小权限原则 (仅授予必要权限)。
- 角色权限分层 (RBAC)。
- API 鉴权统一 (中间件/装饰器)。
- 管理端高权限操作二次确认与审计。
- 敏感操作强制重新认证 (MFA)。

#### 3) 数据保护
- 敏感数据加密存储 (AES-256) + 密钥管理 (KMS/环境变量)。
- 传输加密 (HTTPS + TLS 1.2+)。
- 日志脱敏 (手机号/身份证/银行卡/邮箱)。
- 数据导出权限控制 + 水印。
- PII 加密密钥轮转机制。

---

### Mode 3: structural (结构性优化 - Phase 2)

**目标**：构建系统化安全架构。

**优化策略**：
1. **统一鉴权架构**：
   - 统一身份认证 (SSO/OAuth2/JWT)。
   - 统一权限中心 (RBAC/ABAC)。
   - API 网关统一鉴权。
2. **数据安全架构**：
   - 字段级加密 (敏感字段独立加密)。
   - 密钥管理系统 (KMS)。
   - 数据分类分级 (按敏感度分级保护)。
3. **安全隔离**：
   - 网络隔离 (VPC/安全组)。
   - 服务隔离 (服务网格 mTLS)。
   - 数据隔离 (多租户数据隔离)。

---

### Mode 4: governance (体系化治理 - Phase 3)

**目标**：建立安全治理机制。

**治理内容**：
1. 建立安全扫描与漏洞修复 SLA：
   - 高危：24~72 小时内修复。
   - 中危：7 天内修复。
   - 低危：30 天内修复。
2. 建立安全审计机制：
   - 登录与操作审计 100% 覆盖。
   - 异常访问检测 (行为分析)。
   - 风险操作告警。
3. 建立安全事件应急响应机制 (IRP)。
4. 定期安全培训与渗透测试。
5. 依赖安全持续监控 (Dependabot/Snyk)。

## KPI 目标 (KPI Targets)

| KPI | 目标 |
|-----|------|
| 高危漏洞修复时效 | 24~72 小时内 |
| 中危漏洞修复时效 | 7 天内 |
| 关键接口鉴权与访问审计 | 100% |
| 敏感数据加密覆盖率 | 100% |
| 关键日志脱敏覆盖率 | 100% |

## 🛡️ 铁律与约束 (Iron Rules & Constraints)

1. **安全优先**：高危漏洞必须 P0 处理，禁止以业务理由拖延。
2. **最小权限**：默认拒绝，仅授予必要权限。
3. **纵深防御**：多层安全防护，禁止单点依赖。
4. **可审计**：所有敏感操作必须有审计日志。
5. **密钥安全**：密钥禁止硬编码，必须使用 KMS/环境变量。
6. **双人复核**：高风险安全变更必须双人复核。

## 📂 关联资产 (Related Assets)

- `.trae/sysopt/tasks/security.md` (任务清单)
- `.trae/sysopt/kpi-baseline.md` (基线数据)
- `.trae/sysopt/problem-inventory.md` (问题清单)
- `sysopt-orchestrator/SKILL.md` (编排器)
