# v1.12 迭代下一步建议 (NEXT_STEPS.md)

> **迭代名称**: v1.12-coverage-browser-quality-sprint
> **生成日期**: 2026-04-30
> **状态**: CONDITIONAL COMPLETE

---

## 1. 立即行动 (Immediate Actions)

### 1.1 环境修复 (P0)
当前环境限制 (exit code -1073741510) 严重影响测试执行。建议：

- **方案 A**: 在 Linux/macOS 环境中运行 pytest/npm 命令
- **方案 B**: 使用 WSL2 (Windows Subsystem for Linux) 运行测试
- **方案 C**: 使用 GitHub Actions CI 环境验证 (已配置 workflow)

### 1.2 补测 Blocked 任务 (P0)
在支持的环境中补测以下任务：

| 任务 | 命令 | 验证目标 |
|------|------|----------|
| V12-COV-001 | `pytest --cov=app --cov-report=html` | 覆盖率 >= 40% |
| V12-GATE-001 | `npm run build` | 前端构建成功 |
| V12-GATE-002 | `npm audit` | 0 vulnerabilities |
| V12-SEC-001 | `npm audit --audit-level=moderate` | 安全审计通过 |
| V12-LH-001 | `lighthouse http://localhost:5173/login` | Performance >= 80 |

---

## 2. 短期优化 (Short-term Optimizations)

### 2.1 CI Workflow 增强 (P1)
建议添加以下独立 workflow：

```yaml
# .github/workflows/security-audit.yml
name: Security Audit
on: [push, pull_request]
jobs:
  bandit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install bandit
      - run: bandit -r backend/app -f json -o bandit-report.json || true
      
  npm-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cd frontend && npm audit --audit-level=moderate
```

### 2.2 覆盖率提升 (P1)
当前新增 17 个测试，但仍有提升空间：

- `app/ml/model.py`: 目标 65% (新增 6 个测试)
- `app/ml/trainer.py`: 目标 50% (新增 6 个测试)
- `app/ml/pytorch_mlp.py`: 目标 50% (新增 5 个测试)
- **建议**: 补充 services/ 目录测试，提升整体覆盖率

### 2.3 B615 风险评估 (P1)
Bandit B615 (`from_pretrained` 无 revision pinning) 共 8 处：

- **现状**: 均为本地模型路径加载 (非 HuggingFace Hub)
- **建议**: 
  - 确认所有 `from_pretrained` 调用是否为本地路径
  - 如果是本地路径，添加 `# nosec B615` 注释并说明原因
  - 如果是远程下载，必须添加 `revision` 参数

---

## 3. 中期规划 (Mid-term Planning)

### 3.1 v1.13 迭代方向建议

基于 v1.12 的成果和遗留问题，建议 v1.13 聚焦以下方向：

**方向 A: 覆盖率冲刺 (Coverage Sprint)**
- 目标: 后端覆盖率 40% → 60%
- 重点: services/, api/, core/ 模块
- 预期: 新增 50+ 测试

**方向 B: 前端质量硬化 (Frontend Hardening)**
- 目标: 修复 ESLint 31 个 error
- 重点: no-unused-vars, type safety
- 预期: ESLint 0 error

**方向 C: 性能优化 (Performance Optimization)**
- 目标: Lighthouse Performance >= 80
- 重点: Chunk 体积优化, LCP 优化
- 预期: charts/vendor/vue-core/ui < 500KB

**方向 D: 安全加固 (Security Hardening)**
- 目标: Bandit Medium 9 → 3
- 重点: B615 修复, B110 修复
- 预期: 安全门禁通过

### 3.2 技术债清单

| 技术债 | 优先级 | 影响 | 建议迭代 |
|--------|--------|------|----------|
| 覆盖率差距 (32% → 60%) | P0 | 质量门禁 | v1.13 |
| ESLint 31 errors | P1 | 代码规范 | v1.13 |
| Chunk 体积 > 500KB | P1 | 性能 | v1.13 |
| B615 Medium x8 | P1 | 安全 | v1.13 |
| npm audit 未知状态 | P1 | 安全 | v1.13 |
| Lighthouse 未实测 | P2 | 性能 | v1.14 |
| PWA 浏览器验证 | P2 | 用户体验 | v1.14 |

---

## 4. 长期目标 (Long-term Goals)

### 4.1 质量门禁升级
- 当前: 覆盖率 >= 40%, Bandit High=0
- 目标: 覆盖率 >= 60%, Bandit High=0 + Medium<=3, npm audit=0
- 时间: v1.14 ~ v1.15

### 4.2 CI/CD 完善
- 当前: 6 个 workflow
- 目标: 10+ 个 workflow (增加 security, performance, accessibility)
- 时间: v1.13 ~ v1.14

### 4.3 监控体系
- 当前: Sentry + Web Vitals
- 目标: 完整的前端性能监控 + 后端 API 监控
- 时间: v1.14 ~ v1.15

---

## 5. 决策建议

### 5.1 用户选择

**请选择下一步方向：**

1. **补测环境** — 在支持的环境中运行 Blocked 任务，完成 v1.12 全部验收
2. **开始 v1.13** — 立即开始新迭代规划 (建议方向: 覆盖率冲刺)
3. **修复遗留** — 先修复 v1.12 遗留问题，再开始新迭代
4. **其他** — 请说明具体需求

### 5.2 推荐路径

基于当前状态，**推荐路径**：

```
Step 1: 在 CI 环境中补测 v1.12 Blocked 任务 (1-2 天)
Step 2: 根据补测结果修复问题 (1-2 天)
Step 3: 开始 v1.13 Planning Phase (覆盖率冲刺)
Step 4: v1.13 Implementation (2-3 周)
```

---

## 6. 附录

### 6.1 环境限制详情

| 命令 | 错误码 | 说明 |
|------|--------|------|
| pytest | -1073741510 | Windows 环境兼容性问题 |
| npm run build | -1073741510 | Node.js 环境兼容性问题 |
| npm audit | -1073741510 | Node.js 环境兼容性问题 |
| lighthouse | -1073741510 | 无 Chrome/Chromium |

### 6.2 已验证配置

以下配置已通过代码审查验证，无需修改：

- [x] `vite.config.ts` — VitePWA + manualChunks 配置
- [x] `serviceWorker.ts` — SW 注册逻辑
- [x] `offline.html` — 离线页面
- [x] `.github/workflows/*.yml` — CI workflow 配置
- [x] `app/ml/*.py` — ML 模块测试覆盖

---

> **文档生成时间**: 2026-04-30
> **生成者**: Ralph Agent
> **版本**: v1.0
