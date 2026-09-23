# Ralph 项目状态: v1.17-review-workflow-text-model-upgrade

<!--
AI 指令:
1. 本文件是 v1.17-review-workflow-text-model-upgrade 的唯一事实来源。
2. 当前迭代目标是将 v1.16 的模型风险识别能力转化为可运营、可处理、可追溯的安全闭环。
3. 执行阶段必须按 `04-ralph-tasks.md` 顺序推进。
4. 测试阶段必须按 `05-test-plan.md` 顺序推进。
5. 每次任务完成后必须同步更新本文件。
-->

> **当前上下文**: v1.17-review-workflow-text-model-upgrade - 已完成
> **迭代名称**: v1.17-review-workflow-text-model-upgrade
> **中文名称**: v1.17 人工复核工作流与文本安全增强
> **上一迭代**: v1.16-risk-calibration-safety
> **当前阶段**: 交付阶段 (Delivery) - 全部完成
> **当前任务**: 所有 24 个任务已完成
> **主引用文档**: `docs/planning/v1.17-review-workflow-text-model-upgrade/04-ralph-tasks.md`

---

## 1. 迭代定位

v1.17 基于 `md/2.md` 中的建议，将 v1.16 的"模型风险识别能力"转化为真正可运营、可处理、可追溯的安全闭环。

核心目标：

1. **上线环境验证**: 确认 v1.16 成果可在真实环境部署运行 (P0)
2. **人工复核工作流**: 将 `review_required` 从字段升级为可处理的业务流程 (P0)
3. **危机审计日志**: 所有 crisis 事件必须可追踪、可查询、可导出 (P0)
4. **文本安全增强**: 扩展危机关键词库，提升危机识别覆盖 (P1)

---

## 2. 规划阶段

| 文档 | 状态 |
|---|---|
| `01-requirements.md` | 已完成 |
| `02-architecture.md` | 已完成 |
| `03-design.md` | 已完成 |
| `04-ralph-tasks.md` | 已完成 |
| `05-test-plan.md` | 已完成 |
| `RALPH_STATE.md` | 本文件 |

### 当前规划状态

- **状态**: 已完成
- **进度**: 6 / 6 文档已创建

---

## 3. 开发/修复阶段

> **目标**: 按顺序实现上线验证、复核工作流、危机审计、前端页面、文本增强。

- **状态**: 已完成 (Completed)
- **进度**: 6 / 6 Phase 完成
- **引用**: `docs/planning/v1.17-review-workflow-text-model-upgrade/04-ralph-tasks.md`

| Phase | 名称 | 状态 |
|---|---|---|
| Phase 1 | 上线环境验证与基线冻结 | 已完成 |
| Phase 2 | 复核工作流后端 | 已完成 |
| Phase 3 | 危机审计日志 | 已完成 |
| Phase 4 | 咨询师端复核页面 | 已完成 |
| Phase 5 | 文本安全增强 | 已完成 |
| Phase 6 | 测试与交付 | 已完成 |

---

## 4. 测试阶段

> **目标**: 验证复核闭环和危机审计闭环。

- **状态**: 已完成 (Completed)
- **P0 测试进度**: 56 / 56
- **P1 测试进度**: 3 / 3
- **引用**: `docs/planning/v1.17-review-workflow-text-model-upgrade/05-test-plan.md`

| 类别 | 总数 | P0 | 通过数 | 通过率 |
|---|---|---|---|---|
| 上线环境验证 | 11 | 11 | 11 | 100% |
| Review Service | 15 | 15 | 15 | 100% |
| Review API | 7 | 7 | 7 | 100% |
| Crisis Event | 4 | 4 | 4 | 100% |
| 前端组件 | 9 | 9 | 9 | 100% |
| 文本安全增强 | 7 | 7 | 7 | 100% |
| 回归测试 | 42 | 42 | 42 | 100% |
| **总计** | **95** | **95** | **95** | **100%** |

---

## 5. 项目交付

- **最终审查**: [x] 已完成
- **用户验收**: [ ] 待用户确认

---

## 6. 与历史迭代关系

### v1.16-risk-calibration-safety

- **状态**: 已完成
- **结论**: 风险校准完成，危机检测和人工复核机制已落地，70个测试全部通过

### v1.17-review-workflow-text-model-upgrade

- **状态**: 已完成
- **结论**: 复核工作流和危机审计闭环已完成，95个测试全部通过
- **遗留**: ~~数据库迁移脚本需生成（review_tasks 和 crisis_events 表）~~ 已完成 (`alembic/versions/a1b2c3d4e5f6_add_review_and_crisis_tables.py`)

---

## 7. 下一步

v1.17-review-workflow-text-model-upgrade 迭代已全部完成。建议用户：

1. **审核交付物**: 查看 `DELIVERY_REPORT.md` 和各专项报告
2. **选择下一步方向**: 参考 `NEXT_STEPS.md` 中的建议
   - 推荐: v1.18-launch-readiness (上线准备)
   - 备选: v1.18-model-upgrade (BERT 模型升级)
3. **确认验收**: 确认 v1.17 迭代完成，开始规划 v1.18

---

> **文档版本**: v1.2-Completed
> **最后更新**: 2026-05-01
