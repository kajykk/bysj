# v1.8 下一步建议 (NEXT_STEPS.md)

> **日期**: 2026-04-29
> **迭代**: v1.8-coverage-sprint-and-quality-gates
> **完成度**: 90% (63/70 任务)

---

## 1. 立即行动 (Next Iteration)

### 选项 A: 修复 Blocked 任务 (建议)
在支持完整工具链的环境中运行剩余测试：

```bash
# 1. 运行 ML 测试
pytest tests/ml/ -m "not slow and not requires_ml"

# 2. 运行 Schemathesis 契约测试
schemathesis run tests/contract/openapi.json --base-url http://localhost:8000

# 3. 运行前端构建分析
npm run build
npm run preview
npx lighthouse http://localhost:4173
```

### 选项 B: 开始 v1.9 规划
基于 v1.8 成果，建议 v1.9 方向：

| 方向 | 描述 | 优先级 |
|------|------|--------|
| 覆盖率冲刺 | 后端 60% → 85% | P0 |
| 契约测试硬化 | 通过率 80% → 100% | P0 |
| E2E 测试实跑 | Playwright 端到端测试 | P1 |
| 性能优化 | Lighthouse 80+ / Chunk 优化 | P1 |
| 监控告警 | Sentry 集成 / 异常追踪 | P2 |

---

## 2. 技术债清单

| 项目 | 当前状态 | 建议处理迭代 |
|------|----------|-------------|
| 覆盖率差距 | 估算 32% → 目标 60% | v1.9 |
| ESLint no-unused-vars | 31 个警告 | v1.9 (低优先级) |
| Chunk 体积优化 | charts/vendor > 500KB | v1.9 |
| Schemathesis 实跑 | 未在 CI 中验证 | v1.9 |
| 前端测试覆盖率 | 未量化 | v1.9 |

---

## 3. 规则更新建议

根据 v1.8 经验，建议更新 Ralph.md：

1. **环境适应性**: 明确 Windows 环境限制 (exit code -1073741510) 的处理流程
2. **Blocked 任务**: 定义 Blocked 状态的标准和解除条件
3. **代码审查验证**: 当环境限制时，允许基于代码审查的验证方式

---

## 4. 关键决策点

请用户选择下一步方向：

- [ ] **A**: 在支持环境中运行 Blocked 任务 (需要 Linux/macOS 环境)
- [ ] **B**: 开始 v1.9 Planning Phase
- [ ] **C**: 修复当前代码中的已知问题 (ESLint 警告等)
- [ ] **D**: 其他 (请描述)
