# v1.28-final-delivery — 需求文档

> **迭代名称**: v1.28-final-delivery
> **中文名称**: 封版交付 + 可答辩/可演示 + 可回滚
> **基于**: md/11.md
> **创建日期**: 2026-05-02
> **前置迭代**: v1.27-final-release (FINAL-GO)

---

## 1. 迭代目标

在 v1.27 FINAL-GO 基础上，完成最终交付闭环：清理工作区、封版打标签、最终验收回归、准备答辩/验收材料。

**核心原则**: 不新增功能，只做交付加固。

## 2. 需求分解

### 2.1 Git 工作区清理 (P0)

当前工作区存在大量未纳入版本控制或应清理的文件：

- SQLite 数据库 (`backend/depression_system.db`, `backend/test_app.db`)
- Playwright 报告 (`frontend/playwright-report/`)
- 测试结果 (`frontend/test-results/`)
- 临时脚本和测试产物
- 日志文件 (`backend/logs/`)

目标：
- 更新 `.gitignore` 覆盖所有测试产物和运行时文件
- 清理不必要的临时文件
- 确保 `git status` 干净可交付

### 2.2 版本标识暴露 (P1)

系统当前无可查询的版本号，演示和验收时无法确认运行的是封版版本。

目标：
- 后端暴露 `/api/v1/version` 端点，返回 `v1.28-final`、release date、status
- 前端在页面底部或设置页显示版本号

### 2.3 最终验收回归 (P0)

封版前确认核心功能链路全部正常。

验收范围：
- 后端服务启动
- 前端构建 + 启动
- 核心 API：风险评估、dashboard summary、engine snapshot
- 四条路由：structured / lite / anxiety_only / insufficient
- Crisis override 触发
- 角色流程：admin / counselor / user

### 2.4 封版 Checklist (P0)

创建 `FINAL_RELEASE_CHECKLIST.md`，记录：
- 后端启动通过
- 前端构建通过
- 核心 API 通过
- Crisis override 通过
- 文档齐全
- 模型资产存在
- 无未解释的临时文件
- 已打 tag

### 2.5 答辩/验收材料 (P1)

- 一页式项目总结
- 5 分钟演示脚本
- 常见答辩问答准备

### 2.6 封版标签 (P0)

- 将所有交付文件提交到 Git
- 打标签 `v1.28-final`
- 更新根 RALPH_STATE.md
