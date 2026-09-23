# v1.28-final-delivery — 任务列表

> **迭代**: v1.28-final-delivery
> **基于**: 01-requirements.md
> **创建日期**: 2026-05-02
> **执行顺序**: 按物理顺序从上到下执行

---

## Phase 0: Git 工作区清理 (P0)

- [x] T-GIT-001 — 更新 .gitignore 覆盖所有测试产物和运行时文件
- [x] T-GIT-002 — 清理不必要的临时文件和测试产物
- [x] T-GIT-003 — 验证 git status 干净可交付

## Phase 1: 版本标识暴露 (P1)

- [x] T-VER-001 — 后端暴露 /api/v1/version 端点
- [x] T-VER-002 — 前端显示版本号

## Phase 2: 最终验收回归 (P0)

- [x] T-ACC-001 — 后端服务启动验证
- [x] T-ACC-002 — 前端构建 + 启动验证
- [x] T-ACC-003 — 核心 API 验证（风险评估、summary、snapshot）
- [x] T-ACC-004 — 四条路由验证（structured/lite/anxiety_only/insufficient）
- [x] T-ACC-005 — Crisis Override 验证

## Phase 3: 封版 Checklist (P0)

- [x] T-CHK-001 — 创建 FINAL_RELEASE_CHECKLIST.md

## Phase 4: 答辩/验收材料 (P1)

- [x] T-DEF-001 — 一页式项目总结
- [x] T-DEF-002 — 5 分钟演示脚本
- [x] T-DEF-003 — 常见答辩问答准备

## Phase 5: 封版标签 (P0)

- [x] T-TAG-001 — Git commit + 打 tag v1.28-final

## Phase 6: 状态更新 (P0)

- [x] T-STA-001 — 更新根 RALPH_STATE.md 到 v1.28
