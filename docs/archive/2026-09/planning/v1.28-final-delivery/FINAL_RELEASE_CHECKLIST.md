# FINAL_RELEASE_CHECKLIST — v1.28-final

> **版本**: v1.28-final
> **发布日期**: 2026-05-02
> **状态**: FINAL-GO

---

## 1. 后端启动

- [x] uvicorn 启动成功
- [x] /health 端点返回 `{"status":"ok"}`
- [x] /api/v1/version 返回 `v1.28-final`

## 2. 前端构建

- [x] `npm run build` 成功
- [x] 侧边栏底部显示 `v1.28-final`
- [x] 新页面组件编译通过（AdminCrisisEventsPage, CounselorReviewDetailPage, CounselorReviewListPage）

## 3. 核心 API

- [x] /api/v1/model/predict/fusion — 风险评估正常（普通文本→risk_level 1, 危机文本→risk_level 4）
- [x] /api/v1/monitoring/dashboard-summary — 监控面板正常
- [x] /api/v1/monitoring/engine-snapshot — 引擎快照正常（10 个模型已加载）
- [x] /api/v1/auth/login — 认证正常（admin/user/counselor 均可登录）

## 4. Crisis Override

- [x] 输入危机文本后风险等级升至 4 (critical)
- [x] 干预等级为 critical
- [x] 触发紧急预警动作

## 5. 文档齐全

- [x] `PROJECT_FINAL_REPORT.md` — 项目总报告（v1.27）
- [x] `FINAL_MODEL_CARD.md` — 模型卡
- [x] `FINAL_SYSTEM_ARCHITECTURE.md` — 系统架构
- [x] `FINAL_GO_NO_GO.md` — GO/NO-GO 决策
- [x] `FINAL_E2E_TEST_REPORT.md` — E2E 测试报告
- [x] `FINAL_FRONTEND_REVIEW.md` — 前端审查
- [x] `FINAL_ASSET_CHECK.md` — 资产检查
- [x] 答辩/验收材料（一页总结 + 演示脚本 + 问答）

## 6. 模型资产

- [x] `backend/models/artifacts/` — 生产推理所需资产完整
- [x] 10 个模型在 engine-snapshot 中均有加载记录
- [x] 历史模型文件（v1.23/v1.24/v1.25）已纳入版本控制

## 7. Git 工作区

- [x] .gitignore 覆盖测试产物、数据库、日志、临时脚本
- [x] 所有源代码文件已 staged
- [x] 历史规划文档各迭代已纳入版本控制
- [x] 无敏感文件泄漏

## 8. Git Tag

- [ ] 已打 tag `v1.28-final`

---

## 结论

| 检查项 | 状态 |
|:---|:--:|
| 后端启动 | ✅ |
| 前端构建 | ✅ |
| 核心 API | ✅ |
| Crisis Override | ✅ |
| 文档齐全 | ✅ |
| 模型资产 | ✅ |
| 工作区清洁 | ✅ |
| Git Tag | ⏳ |

**总体判断**: ✅ GO — 可交付，待打 tag 完成最终封版。
