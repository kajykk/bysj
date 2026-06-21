# v1.27 任务列表

> **迭代编号**: v1.27-final-release-and-project-closure
> **状态**: ✅ ALL COMPLETE (FINAL-GO)
> **前置**: [01-requirements.md](file:///e:/code/bysj/docs/planning/v1.27-final-release/01-requirements.md)
> **执行铁律**: 必须按物理顺序执行，每完成一项立即更新状态

---

## Phase 0: 最终资产盘点

### T-AST-001: 模型文件资产检查
- [x] 检查所有模型文件 (.pkl/.pth/.joblib) 存在且可加载
- [x] 检查 v1.20 structured 模型文件
- [x] 检查 v1.23 external 模型文件
- [x] 检查 v1.24 adapter 模型文件
- [x] 检查 v1.25 lite 模型文件
- [x] 检查 v1.21 binary/multiclass 模型文件状态
- [x] 检查 scaler/feature_names 伴随文件完整
- [x] 输出 `FINAL_ASSET_CHECK.md`

### T-AST-002: 配置文件资产检查
- [x] 检查 `backend/app/core/config.py` 所有配置项完整
- [x] 检查 `model_registry.py` 注册表完整
- [x] 检查 threshold 配置 (lite_decision_threshold=0.40)
- [x] 检查 crisis_keywords 配置
- [x] 检查 lifecycle 状态正确
- [x] 检查前端 API 类型定义与后端一致
- [x] 追加到 `FINAL_ASSET_CHECK.md`

---

## Phase 1: 端到端功能验收

### T-E2E-001: 后端服务启动验证
- [x] 启动后端服务 (uvicorn)
- [x] 验证健康检查端点 `/health` 返回 200
- [x] 验证模型加载状态正常
- [x] 验证 engine-snapshot 端点 `/api/v1/monitoring/engine-snapshot` 可访问

### T-E2E-002: 6 条路由链路验收
- [x] structured 完整输入 → 走 structured 路由
- [x] lite 输入 (GAD-7+文本) → 走 lite 路由
- [x] anxiety_only 输入 (仅GAD-7) → 走 anxiety_only
- [x] insufficient 空输入 → 返回信息不足
- [x] crisis 输入 (含"我想死") → 触发人工复核
- [x] fallback 模型缺失/异常 → 不崩溃
- [x] 输出 `FINAL_E2E_TEST_REPORT.md`

### T-E2E-003: 前端构建验证
- [x] 前端 `npm run build` 成功
- [x] 无构建错误
- [x] 追加到 `FINAL_E2E_TEST_REPORT.md`

---

## Phase 2: 前端展示验收

### T-FE-001: 用户风险页验收
- [x] risk_score 展示正常
- [x] risk_level 展示正常
- [x] limited_active 模型标注清楚
- [x] 危机提示 (el-alert) 醒目可见
- [x] routing_reason 可读
- [x] 信息不足提示友好
- [x] 输出 `FINAL_FRONTEND_REVIEW.md`

### T-FE-002: 管理端验收
- [x] 模型 lifecycle 状态正确过滤 (deprecated/disabled)
- [x] dashboard-summary API 返回正常
- [x] 追加到 `FINAL_FRONTEND_REVIEW.md`

---

## Phase 3: 最终模型卡

### T-MC-001: 模型卡整理
- [x] 汇总全部模型: v1.20, v1.21 binary, v1.21 multiclass, v1.23, v1.24, v1.25
- [x] 标注 lifecycle: default/experimental/limited_active/deprecated/disabled
- [x] 标注用途与路由场景
- [x] 标注训练数据与特征维度
- [x] 输出 `FINAL_MODEL_CARD.md`

---

## Phase 4: 最终系统架构说明

### T-ARC-001: 架构文档
- [x] 描述多模型路由体系
- [x] 描述安全 override 机制
- [x] 描述监控与生命周期治理
- [x] 描述 fallback 层级
- [x] 输出 `FINAL_SYSTEM_ARCHITECTURE.md`

---

## Phase 5: 最终总报告

### T-RPT-001: 项目总报告
- [x] 项目背景与问题定义
- [x] 数据来源说明
- [x] 模型演进路线 (v1.20 → v1.26)
- [x] v1.20 基线说明
- [x] v1.23 外部模型提升
- [x] v1.24 分数迁移治理
- [x] v1.25 轻特征模型
- [x] v1.26 召回优化与安全治理
- [x] 最终系统架构
- [x] 实验结果对比表
- [x] 安全策略说明
- [x] 监控与生命周期
- [x] 局限性与后续展望
- [x] 输出 `PROJECT_FINAL_REPORT.md`

---

## Phase 6: 临时产物清理

### T-CLN-001: 临时文件清理
- [x] 扫描 `frontend/playwright-report/`
- [x] 扫描 `frontend/test-results/`
- [x] 扫描其他临时产物
- [x] 更新 `.gitignore`
- [x] 确认 git status 干净

---

## Phase 7: 最终封版决策

### T-GNG-001: FINAL GO/NO-GO
- [x] 汇总 Phase 0-6 产出
- [x] 与封版条件逐条比对
- [x] 全部条件通过 → FINAL-GO
- [x] 输出 `FINAL_GO_NO_GO.md`

---

> **任务总计**: 7 Phases / 12 Tasks
> **最终状态**: ✅ **ALL COMPLETE (FINAL-GO)** — 12/12 任务完成 | 2026-05-02
