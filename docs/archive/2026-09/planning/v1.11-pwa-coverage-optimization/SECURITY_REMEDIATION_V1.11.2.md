# Security Remediation v1.11.2

> **迭代**: v1.11.2-security-test-closure  
> **日期**: 2026-04-30  
> **状态**: Ready for Remediation  
> **目标**: 修复 v1.11.1 中发现的前端 high 漏洞，并收敛后端 bandit Medium 风险

---

## 1. 当前安全状态

| 项目 | v1.11.1 状态 | v1.11.2 目标 |
|---|---|---|
| npm audit high | 4 | 0 |
| npm audit critical | 0 | 0 |
| bandit High | 0 | 0 |
| bandit Medium | 9 B615 | <= 5 或有风险接受说明 |
| CSP Report 路径 | 已统一为 `/api/v1/csp-report` | 保持一致 |

---

## 2. 前端 high 漏洞

### 2.1 已知链路

v1.11.1 报告指出 high 漏洞来自：

```text
vite-plugin-pwa@0.21.1/0.21.2
  -> workbox-build
  -> @rollup/plugin-terser
  -> serialize-javascript <=7.0.4
```

涉及 GHSA：

- GHSA-5c6j-r48x-rmvq
- GHSA-qj8w-gfj5-8c6v

---

## 3. 修复策略

### 3.1 首选：升级 vite-plugin-pwa

```bash
cd frontend
npm install vite-plugin-pwa@latest
npm audit
npm run build
```

验收：

| 检查项 | 标准 |
|---|---|
| npm audit | 0 high / critical |
| build | 成功 |
| PWA 产物 | `sw.js`、manifest、offline.html 存在 |

---

### 3.2 备选：使用 npm overrides

如果上游依赖暂未完全修复，可在 `frontend/package.json` 中增加：

```json
{
  "overrides": {
    "serialize-javascript": "^7.0.0"
  }
}
```

然后执行：

```bash
cd frontend
npm install
npm audit
npm run build
```

注意：使用 overrides 后必须验证 Workbox/PWA 构建没有回归。

---

### 3.3 不推荐：风险接受 high 漏洞

high 漏洞不建议风险接受。除非满足以下全部条件，否则不能放行：

1. 漏洞仅影响构建期工具，不进入运行时包。
2. 有明确 CVE/GHSA 影响分析。
3. 有短期升级计划。
4. 项目负责人明确批准。

默认策略：

```text
high / critical 必须修复或规避，不能无说明放行。
```

---

## 4. 后端 bandit Medium B615

### 4.1 问题

当前存在 9 个 B615：

```text
HuggingFace from_pretrained() 未固定 revision
```

### 4.2 处理策略

| 场景 | 处理 |
|---|---|
| 远程 Hub 模型 | 增加固定 `revision` |
| 本地模型路径 | 确认路径来自受控目录，并增加说明 |
| 测试模型 | 使用 fixture 路径或 dummy model |
| 暂无法修复 | `# nosec B615` + 风险接受说明 |

---

## 5. B615 登记表

| ID | 文件 | 行号 | 模型来源 | 处理方式 | 状态 |
|---|---|---:|---|---|---|
| B615-001 | TBD | TBD | TBD | TBD | 待处理 |
| B615-002 | TBD | TBD | TBD | TBD | 待处理 |
| B615-003 | TBD | TBD | TBD | TBD | 待处理 |
| B615-004 | TBD | TBD | TBD | TBD | 待处理 |
| B615-005 | TBD | TBD | TBD | TBD | 待处理 |
| B615-006 | TBD | TBD | TBD | TBD | 待处理 |
| B615-007 | TBD | TBD | TBD | TBD | 待处理 |
| B615-008 | TBD | TBD | TBD | TBD | 待处理 |
| B615-009 | TBD | TBD | TBD | TBD | 待处理 |

---

## 6. CSP Report 路径确认

v1.11.2 必须保持：

```text
/api/v1/csp-report
```

一致性检查：

| 位置 | 期望 |
|---|---|
| FastAPI 路由 | `/api/v1/csp-report` |
| CSP Header `report-uri` | `/api/v1/csp-report` |
| 测试用例 | `/api/v1/csp-report` |
| 文档 | `/api/v1/csp-report` |

---

## 7. 安全验证命令

```bash
cd frontend
npm audit
npm run build

cd ../backend
bandit -r app
pytest tests/api/test_csp_report.py -v
```

---

## 8. 验收标准

| 类别 | 标准 |
|---|---|
| npm audit | 0 high / critical |
| npm audit critical | 0 |
| 前端构建 | 通过 |
| PWA 产物 | 未回归 |
| bandit High | 0 |
| bandit Medium | <= 5 或有明确风险接受说明 |
| CSP Report | 路径一致，测试通过 |
| 文档 | 修复结果写入本文件和质量门禁报告 |

---

## 9. 修复记录

> 完成修复后填写。

| 项目 | 修复前 | 修复后 | 证据 |
|---|---|---|---|
| npm audit high | 4 | TBD | TBD |
| vite-plugin-pwa | TBD | TBD | TBD |
| serialize-javascript | <=7.0.4 | TBD | TBD |
| bandit High | 0 | 0 | TBD |
| bandit Medium | 9 | TBD | TBD |

---

## 10. 结论模板

```text
前端 high 漏洞：已修复 / 未修复
npm audit：通过 / 未通过
bandit High：通过 / 未通过
bandit Medium：已收敛 / 风险接受 / 延期
CSP Report 路径：一致 / 不一致
是否允许进入 v1.11.2 质量门禁：是 / 否
```
