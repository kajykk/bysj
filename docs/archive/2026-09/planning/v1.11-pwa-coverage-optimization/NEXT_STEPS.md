# Next Steps v1.11

> **迭代**: v1.11-production-readiness-hardening
> **日期**: 2026-04-29
> **状态**: Implementation Phase 完成，待验证

---

## 1. 立即行动 (P0)

### 1.1 CI 环境验证

在支持 npm/python 的 CI 环境中执行：

```bash
# 前端
cd frontend
npm install
npm run build
npm audit

# 后端
cd backend
pytest tests/api/test_csp_report.py -v
pytest tests/test_core_*_extended.py -v
pytest --cov=app --cov-report=term-missing
bandit -r app
```

### 1.2 PWA 图标

添加 PWA 图标到 `frontend/public/`：
- `icon-192x192.png`
- `icon-512x512.png`

### 1.3 CSP Report URI 配置

在 `backend/app/core/middlewares.py` 中确认 `report-uri /api/csp-report` 已配置。

---

## 2. 短期优化 (P1)

### 2.1 覆盖率验证

运行完整测试套件，确认覆盖率目标：
- 整体 >= 40%
- core 模块 >= 80%

### 2.2 Chunk 体积验证

构建后检查 chunk 体积：
- charts < 500KB
- vendor < 500KB
- vue-core < 500KB

### 2.3 Lighthouse 运行

在 Chrome 环境中运行 Lighthouse：
```bash
npx lighthouse http://localhost:5173/login --output=json
```

---

## 3. 中期规划 (P2)

### 3.1 v1.12 迭代建议

| 方向 | 内容 |
|------|------|
| 覆盖率 | 整体 40% -> 60%，auth/user/prediction 模块 |
| Lighthouse | Performance >= 80，Accessibility >= 90 |
| E2E | Playwright 关键路径回归 |
| 监控 | Sentry 错误追踪调优 |

### 3.2 技术债

- [ ] 前端 ESLint 31 个错误
- [ ] TypeScript strict 模式启用
- [ ] 后端 async session 模式统一

---

## 4. 决策点

请选择下一步方向：

1. **修复/优化**: 在当前环境尝试修复 Blocked 任务（需用户确认环境变化）
2. **新迭代**: 开始 v1.12 Planning Phase
3. **验证**: 等待 CI 环境验证结果

---

> **产出日期**: 2026-04-29
> **报告状态**: 已归档
