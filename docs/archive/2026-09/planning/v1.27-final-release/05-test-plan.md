# v1.27 测试计划

> **迭代编号**: v1.27-final-release-and-project-closure
> **状态**: ✅ ALL COMPLETE
> **创建日期**: 2026-05-02

---

## Test Suite 1: 资产完整性测试

### TEST-AST-001: 模型文件存在性
- [x] 所有核心模型文件存在于预期路径
- [x] 伴随文件 (scaler, feature_names) 完整
- [x] 模型文件可成功加载 (不报错)

### TEST-AST-002: 配置文件一致性
- [x] config.py 含 lite_decision_threshold=0.40
- [x] config.py 含 crisis_keywords 列表
- [x] model_registry.py 含全部 7 个模型注册
- [x] 前端 modelApi.ts 类型与后端 Schema 一致

---

## Test Suite 2: 端到端路由测试

### TEST-E2E-001: Structured 路由
- [x] 输入完整结构化字段 → routing_info.model_family = "structured"
- [x] risk_score 在 [0,1] 范围内
- [x] requires_human_review = false (无危机词)

### TEST-E2E-002: Lite 路由
- [x] 输入 GAD-7 + 文本 → routing_info.model_family = "lite"
- [x] 阈值 0.40 生效
- [x] 响应含 routing_reason

### TEST-E2E-003: Anxiety-Only 路由
- [x] 仅输入 GAD-7 分数 → routing_info.model_family = "anxiety_only"
- [x] fallback 标记正确

### TEST-E2E-004: Insufficient 路由
- [x] 空输入/严重缺失 → routing_info.model_family = "insufficient"
- [x] 返回友好提示信息

### TEST-E2E-005: Crisis Override
- [x] 文本含"我想死" → safety_flags 含 "crisis_keyword_detected"
- [x] requires_human_review = true
- [x] risk_level ≥ 3
- [x] crisis_override_count 递增

### TEST-E2E-006: Fallback 容错
- [x] 模拟模型缺失 → 不崩溃，走 fallback
- [x] fallback_count 递增

---

## Test Suite 3: 前端测试

### TEST-FE-001: 构建验证
- [x] `npm run build` exit code = 0
- [x] 无 TypeScript 错误

### TEST-FE-002: 风险页展示
- [x] risk_score 数值展示
- [x] 危机提示可见 (requires_human_review=true 时)
- [x] 路由信息可读

---

## Test Suite 4: 监控 API 测试

### TEST-MON-001: Engine Snapshot
- [x] `GET /api/v1/monitoring/engine-snapshot` 返回 200
- [x] 响应含 routing_stats
- [x] 响应含 fallback_count
- [x] 响应含 crisis_override_count

### TEST-MON-002: Dashboard Summary
- [x] `GET /api/v1/monitoring/dashboard-summary` 返回 200
- [x] 模型 lifecycle 过滤正确

---

## Test Suite 5: 清理验证

### TEST-CLN-001: Git 状态检查
- [x] 无意外未跟踪文件
- [x] .gitignore 覆盖临时产物目录
- [x] playwright-report/, test-results/ 已加入 gitignore

---

> **测试总计**: 5 Suites / 11 Tests
> **最终状态**: ✅ **ALL PASS (11/11)** — 2026-05-02
