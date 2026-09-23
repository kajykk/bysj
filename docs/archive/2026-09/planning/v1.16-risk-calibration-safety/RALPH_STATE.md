# Ralph 项目状态: v1.16-risk-calibration-safety

<!--
AI 指令:
1. 本文件是 v1.16-risk-calibration-safety 的唯一事实来源。
2. 当前迭代目标是提升各模型预测风险等级与业务预期的一致性，并补充危机识别和人工复核机制。
3. 执行阶段必须按 `04-ralph-tasks.md` 顺序推进。
4. 测试阶段必须按 `05-test-plan.md` 顺序推进。
5. 每次任务完成后必须同步更新本文件。
-->

> **当前上下文**: v1.16-risk-calibration-safety - 已完成
> **迭代名称**: v1.16-risk-calibration-safety
> **上一迭代**: v1.15-launch-readiness
> **当前阶段**: 交付阶段 (Delivery) - 全部完成
> **当前任务**: 所有 24 个任务已完成
> **主引用文档**: `docs/planning/v1.16-risk-calibration-safety/04-ralph-tasks.md`

---

## 1. 迭代定位

v1.16 基于 `md/1.md` 中的优化建议，聚焦风险校准与上线安全。

优先级：

1. 文本危机表达强规则 (P0)
2. 融合模型人工复核标记 (P0)
3. 补齐结构化/文本/生理/融合的预期风险样本测试 (P0)
4. 结构化模型和文本模型阈值校准 (P1)
5. 模型解释能力 (P1)

---

## 2. 规划阶段

| 文档 | 状态 |
|---|---|
| `01-requirements.md` | 已完成 |
| `02-architecture.md` | 已完成 |
| `03-design.md` | 已完成 |
| `04-ralph-tasks.md` | 已完成 |
| `05-test-plan.md` | 已完成 |

### 当前规划状态

| 轮次 (Round) | 步骤 1: 草稿 (Draft) | 步骤 2: 自查 (Critique) | 步骤 3: 调研 (Research) | 步骤 4: 推演 (Simulation) | 步骤 5: 锁定 (Lock) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Round 1** (基线) | 完成 | 完成 | 完成 | 完成 | 完成 |

---

## 3. 开发/修复阶段

> **目标**: 按顺序实现危机检测、阈值校准、融合优先级规则、预期样本测试。

- **状态**: 已完成 (Completed)
- **进度**: 24 / 24 任务完成
- **引用**: `docs/planning/v1.16-risk-calibration-safety/04-ralph-tasks.md`

| Phase | 名称 | 状态 |
|---|---|---|
| Phase 1 | 危机检测与文本分析 | 已完成 |
| Phase 2 | 阈值校准与结构化模型增强 | 已完成 |
| Phase 3 | 生理模型增强 | 已完成 |
| Phase 4 | 融合模型优先级规则 | 已完成 |
| Phase 5 | 预期风险样本测试 | 已完成 |
| Phase 6 | API 与集成测试 | 已完成 |
| Phase 7 | 前端适配 | 已完成 |
| Phase 8 | 文档与交付 | 已完成 |

---

## 4. 测试阶段

> **目标**: 使用测试计划验证功能。

- **状态**: 已完成 (Completed)
- **进度**: 70 / 70 测试通过
- **引用**: `docs/planning/v1.16-risk-calibration-safety/05-test-plan.md`

| 类别 | 总数 | P0 | 已完成 |
| :--- | :--- | :--- | :--- |
| 单元测试 | 35 | 25 | 35 |
| 预期样本测试 | 22 | 22 | 22 |
| API 集成测试 | 9 | 9 | 9 |
| 回归测试 | 4 | 4 | 4 |

---

## 5. 项目交付

- **最终审查**: [x] 已完成
- **用户验收**: [ ] 待用户确认

---

## 6. 与历史迭代关系

### v1.15-launch-readiness

- **状态**: 条件完成 (Conditional Go)
- **结论**: 核心功能完整，可继续推进风险校准迭代

### v1.16-risk-calibration-safety

- **状态**: 已完成
- **结论**: 风险校准完成，危机检测和人工复核机制已落地，70个测试全部通过

---

## 7. 下一步

v1.16-risk-calibration-safety 迭代已全部完成。建议用户：

1. **审核交付物**: 查看 `DELIVERY_REPORT.md` 和 `CALIBRATION_REPORT.md`
2. **选择下一步方向**: 参考 `NEXT_STEPS.md` 中的建议
   - 推荐: v1.17-model-upgrade (BERT 模型升级)
   - 备选: v1.17-launch-readiness (上线准备)
3. **确认验收**: 确认 v1.16 迭代完成，开始规划 v1.17

---

> **文档版本**: v1.2-Completed
> **最后更新**: 2026-05-01
