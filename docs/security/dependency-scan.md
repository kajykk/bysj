# 依赖项安全扫描 (SEC-A Dependency SCA)

> **关联任务**: SEC-A 依赖项 SCA 扫描
> **创建日期**: 2026-07-03
> **基线文档**: [SYSTEM_OPTIMIZATION_FOLLOWUP_PLAN.md](../SYSTEM_OPTIMIZATION_FOLLOWUP_PLAN.md)

---

## 1. 概述

本项目所有 Python 第三方依赖 (200+ 包) 必须通过 SCA (Software Composition Analysis) 扫描, 确保:
- 无 HIGH/CRITICAL 等级已知漏洞进入生产环境
- CI 每次构建自动扫描, 每周一定时全量复查
- 双重扫描 (pip-audit + safety) 交叉验证, 降低误报率

---

## 2. 工具选型

| 工具 | 数据源 | 用途 | 触发条件 |
|------|--------|------|---------|
| `pip-audit` | PyPI Advisory Database (官方) | 主扫描器, 阻塞合并 | PR / 每周一 |
| `safety` | Safety DB (商业数据库) | 交叉验证, 兜底 | PR / 每周一 |

**选择理由**:
- `pip-audit` 由 PyPA (Python Packaging Authority) 维护, 数据源为 PyPI 官方 Advisory, 无商业授权风险
- `safety` 数据库与 pip-audit 互补, 部分 0-day 漏洞 safety 收录更快
- 两者均为 CLI 工具, 无需外部服务依赖, 适合 CI 集成

---

## 3. CI 集成

### 3.1 主扫描 workflow

文件: [.github/workflows/dependency-scan.yml](../../.github/workflows/dependency-scan.yml)

触发条件:
- **Pull Request**: 当 `backend/requirements.txt` 或 `backend/requirements-dev.txt` 变更时触发
- **定时**: 每周一 02:00 UTC (北京时间 10:00) 全量扫描所有依赖
- **手动**: 通过 GitHub Actions UI 触发 (workflow_dispatch)

扫描流程:
1. `pip-audit` 扫描 `requirements.txt` + `requirements-dev.txt`, 输出 JSON 报告
2. `safety` 扫描 `requirements.txt`, 输出 JSON 报告 (兜底)
3. 任何 HIGH/CRITICAL 漏洞均使 CI 失败, 阻塞 PR 合并
4. 报告作为 artifact 上传, 保留 30 天

### 3.2 PR Quality Gates 集成

文件: [.github/workflows/pr-quality-gates.yml](../../.github/workflows/pr-quality-gates.yml)

新增 `dependency-scan` job:
- 仅在依赖文件变更时运行 (避免无依赖变更的 PR 浪费 CI 资源)
- `quality-gate-summary.needs` 加入 `dependency-scan`, 失败阻塞 PR 合并
- `skipped` 状态视为通过 (无依赖变更时)

---

## 4. 漏洞处理流程

### 4.1 漏洞分级

| 等级 | 处理时限 | 处理方式 |
|------|---------|---------|
| CRITICAL | 24 小时内 | 立即升级到修复版本; 无修复版本时紧急评估替代方案 |
| HIGH | 3 个工作日内 | 升级到修复版本; 评估影响范围 |
| MEDIUM | 1 个迭代内 | 记录到 [known-vulnerabilities.md](./known-vulnerabilities.md), 排期修复 |
| LOW | 持续跟踪 | 记录到 known-vulnerabilities.md, 随依赖升级修复 |

### 4.2 例外 (Ignore) 流程

当某漏洞无法立即修复时 (例如上游无修复版本), 可添加 `--ignore-vuln` 例外:

**步骤**:
1. 在 `docs/security/known-vulnerabilities.md` 中记录例外理由
2. 修改 `.github/workflows/dependency-scan.yml`, 添加 `--ignore-vuln <CVE-ID>` 参数
3. **必须**经安全负责人审批 (PR 评论中 @reviewer)
4. 设置例外有效期 (最长 90 天), 到期后必须重新评估

**例外条目必须包含**:
- CVE ID
- 受影响包与版本
- 例外理由 (上游无修复 / 影响范围有限 / 已通过 WAF 缓解 等)
- 例外有效期
- 审批人

---

## 5. 已知漏洞跟踪

文件: [known-vulnerabilities.md](./known-vulnerabilities.md)

记录所有未修复的 MEDIUM/LOW 漏洞与例外条目, 包含:
- CVE ID / GHSA ID
- 受影响包与版本
- 漏洞描述
- 影响评估 (是否可利用 / 影响范围)
- 处理状态 (待修复 / 已例外 / 已修复)
- 跟踪链接 (上游 issue / PR)

---

## 6. 验收清单

- [x] `pip-audit` 在 CI 中成功运行, 输出 JSON 报告
- [x] `safety` 作为交叉验证扫描器运行
- [x] HIGH/CRITICAL 漏洞阻塞 PR 合并 (通过 `--strict` 标志)
- [x] 每周一定时全量扫描, 报告归档 30 天 (artifact retention-days=30)
- [x] 文档说明扫描策略与例外流程 (本文档)
- [x] `backend/requirements-dev.txt` 添加 `pip-audit>=2.7.0` 与 `safety>=3.2.0`

---

## 7. 相关命令 (本地运行)

```bash
# 本地运行 pip-audit (推荐提交前自检)
cd backend
pip-audit --requirement requirements.txt --requirement requirements-dev.txt

# 输出 JSON 报告
pip-audit --requirement requirements.txt --format json --output report.json

# 跳过特定 CVE (与 CI 配置一致)
pip-audit --requirement requirements.txt --ignore-vuln CVE-XXXX-XXXXX

# safety 扫描
safety scan --file requirements.txt --output json
```

---

## 8. 变更日志

| 日期 | 变更内容 | 作者 |
|------|---------|------|
| 2026-07-03 | 初始版本, 创建 SEC-A SCA 扫描文档 | 系统优化团队 |
