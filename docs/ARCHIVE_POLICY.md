# 文档分层归档政策（P2）

> 现状：docs/ 约 520 个 md，大量过程性计划/审计/总结文档，与现状脱节风险高。

## 两层结构

- **现状层**（根保留）：README、CHANGELOG、`docs/architecture.md`、部署与告警运维指南、
  `backend/models/MODEL_REGISTRY.md`（模型世系）、`docs/COVERAGE_ROADMAP.md`（质量门禁）、
  `docs/DEMO_CHECKLIST.md`（演示）、论文第 4 章相关实验文档。现状层文档必须与代码一致，
  版本数字一律引用 SSOT（`backend/app/core/config.py`），不得独立维护。
- **归档层**（`docs/archive/`）：过程性计划、审计、总结、已关闭的优化方案
  （如 Phase 5 UI 信息架构重组、physiological-multimodal Idea 遗留决策）。
  归档文档头部必须标注 `> 归档：内容反映撰写时状态，不再更新。`

## 执行步骤

1. 新建 `docs/archive/`，按季度分子目录。
2. 首批归档：已完成的里程碑计划/审计/总结类文档（保留现状层索引链接，避免断链）。
3. README 修正：测试量“约 2000 条”→以后端 `pytest --collect-only` 与前端 vitest 实测为准；
   数据表 39→以 models 声明与生产库实测为准（当前 39/40，需注明口径差 1 为历史视图/遗留表）。
