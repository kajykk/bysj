# v1.28-final-delivery — 测试计划

> **迭代**: v1.28-final-delivery
> **基于**: 04-ralph-tasks.md
> **创建日期**: 2026-05-02

---

## Suite 0: Git 清理验证

- [x] TEST-GIT-001 — .gitignore 规则覆盖验证
- [x] TEST-GIT-002 — 临时文件已清理
- [x] TEST-GIT-003 — git status 仅含预期的交付文件

## Suite 1: 版本端点验证

- [x] TEST-VER-001 — /api/v1/version 返回正确版本信息
- [x] TEST-VER-002 — 前端可见版本号

## Suite 2: 验收回归

- [x] TEST-ACC-001 — 后端启动成功 (uvicorn)
- [x] TEST-ACC-002 — 前端构建成功 (npm run build)
- [x] TEST-ACC-003 — /api/v1/predict 接口正常
- [x] TEST-ACC-004 — /api/v1/monitor/summary 接口正常
- [x] TEST-ACC-005 — /api/v1/monitor/engine-snapshot 接口正常
- [x] TEST-ACC-006 — Structured 路由可触发
- [x] TEST-ACC-007 — Lite 路由可触发
- [x] TEST-ACC-008 — Anxiety-Only 路由可触发
- [x] TEST-ACC-009 — Insufficient 路由可触发
- [x] TEST-ACC-010 — Crisis Override 可触发（风险等级>=3）
- [x] TEST-DEF-001 — 答辩材料文件存在
- [x] TEST-CHK-001 — FINAL_RELEASE_CHECKLIST 所有项通过
- [x] TEST-TAG-001 — Git tag v1.28-final 存在
