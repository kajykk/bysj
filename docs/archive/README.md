# 归档区（Archive）

按 `docs/ARCHIVE_POLICY.md` 收敛：过程性计划/审计/总结文档移入此处，现状文档保留在 `docs/` 顶层。

## 2026-09（第一批）

| 文件 | 归档原因 |
|---|---|
| `2026-09/SYSTEM_OPTIMIZATION_PLAN.md` | 已执行的系统优化计划，执行结果见 `SYSTEM_OPTIMIZATION_SUMMARY_REPORT.md`（同目录） |
| `2026-09/SYSTEM_OPTIMIZATION_FOLLOWUP_PLAN.md` | 同上，后续跟进计划 |
| `2026-09/SYSTEM_OPTIMIZATION_SUMMARY_REPORT.md` | 已完成总结，不再指导当前工作 |
| `2026-09/REMAINING_TASKS_PLAN_202608.md` | 2026-08 剩余任务计划，已过期 |
| `2026-09/CODE_OPTIMIZATION_PLAN_202608.md` | 2026-08 代码优化计划，已执行 |
| `2026-09/FRONTEND_OPTIMIZATION_PLAN.md` | 前端优化计划，已执行（拆分现状见 `frontend/vite.config.ts`） |
| `2026-09/DEEP_AUDIT_REPORT_202606.md` | 2026-06 深审报告，被 `docs/FULL_AUDIT_REPORT.md` 取代 |
| `2026-09/I18N_MIGRATION_PROGRESS.md` | i18n 迁移过程记录，迁移已完成 |

注意：`docs/architecture.md` 与 `docs/CAPACITY_PLANNING.md` 中指向
`SYSTEM_OPTIMIZATION_PLAN.md` 的链接已同步更新到归档路径。

## planning/ 整树归档

`2026-09/planning/` 为原 `docs/planning/` 整树（约 48 个版本迭代目录 + 顶层计划文件），
均为已执行的 sprint 计划/交付报告/复盘，不再指导当前工作。
版本内互相引用均为相对路径，随树整体搬迁，保持有效；
4 处外部引用已修复：`ADR-010`、`infra/grafana/README`、
`docs/PRODUCT_EVALUATION_REPORT.md`（3 处）、
`backend/models/artifacts/physiological_optimized/README.md`。
