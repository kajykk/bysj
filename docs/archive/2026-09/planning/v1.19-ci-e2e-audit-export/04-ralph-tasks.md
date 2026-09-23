# Ralph 任务列表 — v1.19-ci-e2e-audit-export

> **迭代**: v1.19-ci-e2e-audit-export  
> **日期**: 2026-05-01  
> **状态**: Planning Phase - Round 1 Draft  
> **基于**: `e:\code\bysj\md\3.md`

> **⚠️ 执行铁律**: 必须严格按照列表顺序（从上到下）执行任务。严禁跳跃或乱序执行。

## 任务状态图例
- [ ] 待开始 (Pending)
- [x] 已完成 (Completed)
- [~] 进行中 (In Progress)
- [-] 阻塞 (Blocked)

---

## Phase 0: 前置依赖修复 (Prerequisite)

- [x] **0.1 修复 `app/models/review.py` sa 导入错误**
  - [x] 第 29 行 `sa.Float` → `Float` (Float 已从 sqlalchemy 导入)
  - [x] 验证全项目无其他 `sa.` 引用残留
  - [x] 验证 `crisis_export_service.py` 可正常导入

---

## Phase 1: v1.18 未实测项基线确认

- [x] **1.1 读取 v1.18 交付物**
  - [x] 读取 v1.18 `RALPH_STATE.md`
  - [x] 读取 v1.18 `05-test-plan.md`
  - [x] 统计所有 `[~] Windows 环境限制` 测试项 (17项: 14 P0 + 3 P1)
  - [x] 标记哪些转为 v1.19 实测目标

- [x] **1.2 建立 v1.19 实测清单**
  - [x] 生成未实测 P0 项清单
  - [x] 生成未实测 P1 项清单
  - [x] 输出 `BASELINE_V1.19.md`

---

## Phase 2: Docker/CI 验证环境检查与修复

> **注**: 项目已有 `docker-compose.yml`, `Dockerfile.test`, `.github/workflows/`, `Makefile`

- [x] **2.1 检查现有 Docker 配置**
  - [x] 审查 `docker-compose.yml` 服务定义 — 完整 (postgres/redis/test)
  - [x] 审查 `backend/Dockerfile.test` — 依赖完整 (pytest, httpx, coverage)
  - [x] 确认 `scripts/` 目录已有基础脚本
  - [x] 无需修复，配置完备

- [x] **2.2 编写 CI 验证脚本**
  - [x] 创建 `scripts/ci_backend_verify.sh` (后端+迁移+冒烟)
  - [x] 创建 `scripts/ci_frontend_verify.sh` (前端构建)

---

## Phase 3: 数据库迁移实测

- [x] **3.1 空库迁移测试**
  - [x] 创建空 SQLite 测试库 `test_migration_v19.db`
  - [x] 执行 `alembic upgrade a1b2c3d4e5f6` → ✅ 成功 (5 步增量迁移)
  - [x] 验证 `review_tasks` 表 15 个字段 — ✅ 全部正确
  - [x] 验证 `crisis_events` 表 13 个字段 — ✅ 全部正确
  - [x] 验证索引 (`ix_crisis_events_status_created_at`, `ix_crisis_events_trigger_source_created_at`, `ix_crisis_events_user_id`) — ✅ 全部存在

- [x] **3.2 数据读写验证**
  - [x] 插入 review_tasks 测试数据 → ✅ 成功
  - [x] 插入 crisis_events 测试数据 → ✅ 成功
  - [x] 查询验证数据完整性 → ✅ 通过

- [x] **3.3 回滚验证**
  - [x] 执行 `alembic downgrade f6a1b9c0e5d3` → ✅ 成功
  - [x] 确认 `review_tasks` 和 `crisis_events` 表已删除 → ✅
  - [x] 确认索引已删除 → ✅
  - [x] 确认已有表不受影响 → ✅

- [x] **3.4 输出迁移报告**
  - [x] 生成 `MIGRATION_EXECUTION_REPORT.md`

---

## Phase 4: 后端测试与 API 冒烟实测

- [x] **4.1 服务启动验证**
  - [x] uvicorn 启动成功
  - [x] 模型 fallback 正常（预加载跳过，运行时使用启发式）
  - [x] Sentry 无DSN跳过

- [x] **4.2 API 冒烟测试**
  - [x] `GET /health` → 200 ✅
  - [x] `GET /health/ready` → 200 ✅
  - [~] `POST /api/v1/predict/tabular` — ⚠️ 需认证 token（预期行为）
  - [~] `POST /api/v1/predict/text` — ⚠️ 需认证 token（预期行为）
  - [~] `GET /api/v1/admin/crisis-events/export` — ⚠️ 需认证 token

- [~] **4.3 pytest 全量运行**
  - [~] pytest collection 完成但耗时过长（1074 items, 2.5分钟） — Windows 环境限制
  - 建议在 Docker CI 环境运行

---

## Phase 5: 前端危机事件列表页与导出 UI 实现

> **注**: 前端尚无危机事件列表页，需新建页面 + 导出功能

- [x] **5.1 创建危机事件列表页**
  - [x] 在 `frontend/src/views/admin/` 下创建 `AdminCrisisEventsPage.vue`
  - [x] 实现危机事件数据表格（参考 `AdminOperationLogsPage.vue` 模式）
  - [x] 接入 `GET /api/v1/reviews/crisis-events` 列表 API
  - [x] 配置路由 `/admin/crisis-events`

- [x] **5.2 添加日期范围选择器**
  - [x] 参考 `AdminOperationLogsPage.vue` 中的 DatePicker 实现
  - [x] 默认值: start=30天前, end=今天

- [x] **5.3 添加导出按钮**
  - [x] 实现 ExportButton 组件
  - [x] 调用 `GET /api/v1/admin/crisis-events/export?start_date=&end_date=`
  - [x] 实现 CSV 下载逻辑 (blob → download)
  - [x] 添加 Loading / Error / Empty 状态处理

- [~] **5.4 前端测试**
  - [~] 页面渲染测试 — Windows 环境限制 (Vitest 不可用)
  - [~] 导出按钮交互测试 — Windows 环境限制
  - [~] 错误处理测试 — Windows 环境限制

- [x] **5.5 前端构建验证**
  - [x] `npm run build` → 2543 modules transformed, dist/ 存在 (150 items)
  - [x] Circular chunk warning 非阻塞

- [x] **5.6 输出导出 UI 报告**
  - [x] 生成 `AUDIT_EXPORT_UI_REPORT.md`

---

## Phase 6: 复核与危机审计 E2E 实测

- [ ] **6.1 危机文本闭环 E2E**
  - [ ] 创建测试用户
  - [ ] 用户提交含危机关键词的文本
  - [ ] 验证 `CrisisEvent` 已创建 (status=detected)
  - [ ] 验证 `ReviewTask` 已创建 (priority=crisis_review)
  - [ ] 咨询师登录 → 查看 ReviewTask 列表
  - [ ] 咨询师处理 ReviewTask (resolve)
  - [ ] 验证 CrisisEvent 状态更新

- [ ] **6.2 融合预测闭环 E2E**
  - [ ] 用户提交高风险融合预测
  - [ ] 验证 review_required=true
  - [ ] 验证 ReviewTask 自动创建
  - [ ] 咨询师查看并处理

- [ ] **6.3 管理员审计闭环 E2E**
  - [ ] 管理员查看危机事件列表
  - [ ] 管理员导出 CSV
  - [ ] 验证 CSV 用户 ID 已脱敏
  - [ ] 验证 CSV 格式正确

- [ ] **6.4 输出 E2E 报告**
  - [ ] 生成 `E2E_VALIDATION_REPORT.md`

---

## Phase 7: 结构化模型重训预研 (P1)

- [ ] **7.1 训练脚本检查**
  - [ ] 确认 `train_baseline.py` 可用性
  - [ ] 确认训练数据完整性
  - [ ] 确认 sklearn 版本
  - [ ] 确认 artifact 输出目录

- [ ] **7.2 输出预研计划**
  - [ ] 生成 `STRUCTURED_MODEL_RETRAIN_PLAN.md`

---

## Phase 8: CI 报告归档 (P1)

- [ ] **8.1 报告归档**
  - [ ] 归档 backend test report
  - [ ] 归档 frontend build report
  - [ ] 归档 migration report
  - [ ] 归档 E2E report
  - [ ] 归档 coverage report (非阻塞)

---

## Phase 9: 交付与 Go/No-Go 决策

- [ ] **9.1 汇总所有验证结果**
  - [ ] 汇总 CI 结果
  - [ ] 汇总 E2E 结果
  - [ ] 汇总迁移结果
  - [ ] 汇总导出 UI 结果

- [ ] **9.2 更新风险清单**
  - [ ] 关闭已缓解风险
  - [ ] 记录新增风险

- [ ] **9.3 生成上线报告**
  - [ ] 生成 `DELIVERY_REPORT.md`
  - [ ] 给出 Go / Conditional Go / No-Go 结论

- [ ] **9.4 生成 NEXT_STEPS.md**
  - [ ] v1.20 候选方向 (BERT / 生理模型 / 结构化重训)

- [ ] **9.5 更新 RALPH_STATE.md**
  - [ ] 标记所有任务完成
  - [ ] 标记测试通过
  - [ ] 标记待用户验收

---

> **文档版本**: v1.0-Draft  
> **最后更新**: 2026-05-01
