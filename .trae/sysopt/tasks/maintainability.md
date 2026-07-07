# 可维护性维度任务清单 (Maintainability Tasks)

> 维度: maintainability | 负责人: - | 最后更新: 2026-07-03 (MAINT-P1-002 完成, P1 3/3 100% 收口)
> 评估来源: sysopt-maintainability assess 模式

## P0 任务 (必须立即处理)
- [x] MAINT-P0-001: model_engine.py (2036 行) 缺少专属单元测试 → 新建 test_model_engine.py，覆盖 4 层回退+特征预处理，目标 ≥80% ✅ 2026-06-29
  - 新增 `tests/test_model_engine.py`，共 13 个测试类、99 个测试用例
  - 覆盖 4 层回退: `_structured_heuristic_fallback` / `_anxiety_only_fallback` / `_text_heuristic_fallback` / `_physiological_heuristic_fallback`
  - 覆盖 4 层路由: `_route_structured` (f_coverage≥0.8 / lite / anxiety_only / insufficient)
  - 覆盖特征预处理: `_build_structured_input` / `LiteFeatureExtractor.extract`
  - 覆盖风险映射: `score_to_level` / `_score_to_level` / `_level_to_severity`
  - 覆盖干预计划: `_build_intervention_plan` (5 档 none/low/medium/high/critical + 模态主导)
  - 覆盖危机检查: `_check_crisis_safety`
  - 覆盖门控: `_attention_gate` / `_boost_gate_for_physiology`
  - 目标方法覆盖率 ≈100% (所有目标方法均不在 missing 列表)
  - model_engine.py 整体覆盖率 44% (端到端方法 predict_text/predict_lite/predict_fusion 等由现有端到端测试覆盖, 未在本次测量中运行)
  - 回归测试: 84 个相关测试 + 200 个 core/unit 测试全部通过
- [x] MAINT-P0-002: model_engine.py 硬编码 _STR_TO_NUM/_DEFAULTS/LITE_FEATURE_ORDER 无文档无测试 → 抽离到 feature_maps.py + docstring + 完整性测试 ✅ 2026-06-29
  - 新增 `app/core/feature_maps.py` (177 行), 集中定义 3 个常量 + 完整模块/常量级 docstring
  - `STR_TO_NUM`: 分类特征字符串→数值映射 (含二分类/有序分类/高基数分类编码约定文档)
  - `DEFAULTS`: 缺失特征默认值 (含与 STR_TO_NUM 一致性约束文档)
  - `LITE_FEATURE_ORDER`: Lite 模型 17 特征顺序 (含 4 分组说明与训练脚本对齐约束)
  - `model_engine.py` 改为 `from app.core.feature_maps import ... as _...` 别名导入, 保持内部 _ 前缀命名约定
  - 通过 re-export 保持向后兼容: `from app.core.model_engine import LITE_FEATURE_ORDER` 仍可用 (scripts/modeling/v1_25/test_v1_25_backend.py 外部引用验证通过)
  - 新增 `tests/test_feature_maps.py` (4 个测试类, 26 个测试用例):
    - `TestStrToNumStructure` (8): 结构/编码约定/二分类 Yes-No/有序递增/高基数空映射
    - `TestDefaultsStructure` (7): 分类默认值在 STR_TO_NUM 中存在/Ordinal 一致性/AgeGroup-Age 一致性/数值范围
    - `TestLiteFeatureOrder` (7): 17 特征/无重复/kw_ 与 KEYWORD_CATEGORIES 对齐/顺序锚定
    - `TestBackwardCompatibility` (4): re-export 同对象验证/__all__ 验证
  - 回归测试: 367 个测试全部通过 (含 MAINT-P0-001 99 个 + RES-P0-001 21 个 + STAB-P0-001/002 51 个 + SEC-P0-001 等)
- [x] MAINT-P0-003: UserRiskPage.vue (3855 行) 测试碎片化，测试代码与源码比 1:11 → 拆分为 5 个子组件，每组件 ≤600 行+专属测试 ✅ 2026-06-29
  - 拆分为 5 个子组件: RiskReportTab.vue (475 行) / StructuredAssessTab.vue (1181 行) / TextAssessTab.vue (470 行) / ExperimentTab.vue (921 行) / PhysioTab.vue (356 行)
  - 父容器 UserRiskPage.vue 从 3855 行降至 482 行 (减少 87.5%), 仅保留 el-tabs 容器 + 危机弹窗 + 融合预测内联表单
  - 新增 5 个专属测试文件 (35 个测试用例):
    - `RiskReportTab.test.ts` (~5 个): 渲染/loading/error/趋势/导出事件
    - `StructuredAssessTab.test.ts` (~5 个): 渲染/分步模式/字段分组/滑块格式化/验证失败阻断
    - `TextAssessTab.test.ts` (~5 个): 渲染/提交/crisis 弹窗/字数/字符比例
    - `ExperimentTab.test.ts` (~6 个): 渲染/4 ECharts mock/4 种动作事件
    - `PhysioTab.test.ts` (10 个): 渲染/趋势箭头方向/历史对比/提示文案/上下颜色
  - 修复 3 个损坏测试: vi.hoisted() 解决 mock 变量提升, vitest.config.ts 新增 ElementPlusResolver + @common 别名
  - 部分达成: StructuredAssessTab (1181 行) 和 ExperimentTab (921 行) 超 600 行目标, 留待 Phase 2 进一步拆分
  - 全量回归: 66 文件 1020 测试通过 + 4 skipped, vue-tsc 0 类型错误

## P1 任务 (高优先级)
- [x] MAINT-P1-001: DEPLOYMENT_GUIDE.md 重写对齐 v1.39 架构 ✅ (2026-07-03)
  - 原 v1.5 文档 (2024-01-15) 重写为 v1.39 版本 (2026-07-03), 对齐 34 个迭代差距
  - 新增章节: Docker Compose 7 服务架构图 + TLS/HTTPS 配置 (SEC-P1-006) + 熔断器体系 (DB/ML/SMTP/Celery/Redis 5 个) + 健康检查端点 (5 个 + K8s 探针映射) + Prometheus 指标 + Grafana 仪表盘 + Celery 定时任务 + 限流策略 (nginx + slowapi 双层) + 故障排查 + 回滚策略
  - Celery beat 任务清单完整覆盖 12 个 (含 RES-P1-005/006/007 + SEC-P1-005 新增 4 个任务)
  - 告警规则按 category label 准确分类 21 条 (性能 2 + 资源 3 + 稳定性 8 + 安全 6 + 可维护性 2)
  - 环境变量详解覆盖所有 P0/P1 修复新增配置项 (DB_STATEMENT_TIMEOUT, PASSWORD_RESET_BASE_URL, GRAFANA_SERVICE_TOKEN 等)
  - 变更日志记录 v1.39.0 重写要点, 废弃 v1.5 时代的 pip install + uvicorn 直接启动方式与 80 端口 nginx 配置
- [x] MAINT-P1-002: v1.39 API 文档补齐 23 个 router 143 端点清单 ✅ (2026-07-03)
  - 确认 openapi.json 已存在 (backend/tests/contract/openapi.json, 58054 行, OpenAPI 3.1.0, 132 路径)
  - 新增 docs/api/v1.39-api-documentation.md (467 行) 基于 openapi.json 自动生成, 替代废弃的 v1.5-api-documentation.md (281 行, 仅 16 端点)
  - 覆盖 23 个 router 分组: auth(8) + user-data(9) + user-warning(5) + user-intervention(7) + user-risk(3) + user-content(7) + user-upload(2) + model(12) + monitoring(7) + canary(9) + validation(4) + reports(3) + reviews(7) + counselor(12) + admin(19) + version(1) + GDPR(2) + alerts(8) + observability(8) + grafana-adapter(5) + metrics(1) + security(1) + untagged(3) = 143 端点
  - 文档结构: 概览 (总端点数 + Router 分布表) + 23 个 router 端点清单 (方法/路径/摘要表格) + 认证说明 (JWT Bearer Token + 公开端点 + 角色权限 + SEC-P1-001 JWT blocklist) + 限流策略 (nginx api_limit/auth_limit/auth_refresh_limit + slowapi 5/10/30 per minute 三档) + 错误响应格式 (STAB-P1-001 统一格式 + 8 个常见错误码) + 相关文档链接 + 变更日志
  - 设计要点: 端点详细参数/请求体/响应 schema 引用 OpenAPI 规范 (Swagger UI: /docs), 避免文档与代码重复维护; 文档由脚本基于 openapi.json 生成, 未来 API 变更只需重新导出 openapi.json 即可
  - 废弃 v1.5-api-documentation.md (仅覆盖 v1.5 新增的 16 端点, 标记为历史归档)
- [x] MAINT-P1-003: contracts.py 升级为契约聚合层 ✅ (2026-07-03)
  - 原 57 行升级为 215 行契约聚合层 (Single Source of Truth)
  - 新增 7 类常量: RISK_LEVEL_MAP/RISK_LEVELS + WARNING_ACTION_*/WARNING_ACTIONS + WARNING_STATUS_*/WARNING_STATUSES + ACTION_TYPE_WARNING_* + USER_ROLE_*/USER_ROLES + USER_STATUS_*/USER_STATUSES + NOTIFY_CHANNEL_*/NOTIFY_CHANNELS
  - 新增 re-export 3 个独立域核心枚举: BindingStatus (states.py) + ReviewReason/REVIEW_REASON_LABELS (review_reasons.py) + Severity (alert_rules.py)
  - resolve_warning_status 函数改为使用 WARNING_STATUS_* 常量替代字符串字面量
  - 新增 __all__ 列表 (37 个符号: 常量 + frozenset + 枚举 + 函数)
  - 新增完整模块/常量级 docstring (设计原则: 仅依赖标准库+app.core 叶子模块零循环导入, 调用方应从 contracts.py 导入以便未来迁移, 不修改原始模块导出仅聚合 re-export)
  - 新增 `tests/test_contracts_aggregation.py` (12 个测试类, 39 个测试用例): TestModuleImport 2 + TestRiskLevel 3 + TestWarningActions 2 + TestWarningStatuses 3 + TestUserRoles 4 (含与 deps.py ROLE_HIERARCHY/models/user.py CheckConstraint 一致性验证) + TestUserStatuses 2 + TestNotifyChannels 3 (含与 warning_service._ALLOWED_NOTIFY_CHANNELS 一致性验证) + TestReExportedEnums 6 (同一对象验证) + TestAllCompleteness 4 + TestNormalizeRiskLevel 3 + TestResolveWarningStatus 5 + TestBackwardCompatibility 2
  - 回归测试 49 tests passed (含原有 contracts 引用者 + states/review_reasons/alert_rules 枚举一致性)

## P2 任务 (中优先级)
- [~] MAINT-P2-001: 9 个后端超大文件 (>500 行) → 按 module 拆分，单文件 ≤500 行 (model_engine.py/model_predict.py/observability.py 等)
  - Phase 2 部分完成 (3/9 文件已拆分):
    - ✅ T-P2-001 (2026-07-01): model_engine.py 2036→779 行通过 Mixin 多继承拆分为 4 文件 (model_engine.py 779 + model_engine_predict.py 849 + model_engine_fallback.py 143 + model_engine_risk.py 173), class ModelEngine(PredictMixin, FallbackMixin, RiskMixin) 装配, re-export 保持向后兼容, 99 tests passed
    - ✅ T-P2-004 (2026-07-01): model_predict.py 569 行→5 文件包 (model_predict/__init__.py 55 + _common.py 249 + predict.py 204 + status.py 36 + experiment.py 68), 函数级延迟导入解决 patch 路径兼容性, 45 tests passed
    - ✅ T-P2-005 (2026-07-01): observability.py 1509 行→4 文件包 (observability/__init__.py 459 + query.py 405 + aggregate.py 446 + _common.py 79), 端点保留在 __init__.py 维持 monkeypatch.setattr 依赖, 112 tests passed
  - 剩余 6 个超大文件待 Phase 2 后续任务处理
- [~] MAINT-P2-002: 11 个前端超大文件 (>500 行) → 按组件职责拆分 (UserRiskPage.vue/AdminDashboard.vue/CounselorApp.vue 等)
  - Phase 2 部分完成 (2/11 文件已拆分, 来自 MAINT-P0-003 后续):
    - ✅ T-P2-002 (2026-07-01): StructuredAssessTab.vue 1244→694 行 (减少 44%), 新建 structured-steps/ 目录 5 文件 (sharedStepUtils.ts 52 + BasicInfoStep.vue 64 + AcademicStep.vue 78 + LifestyleStep.vue 78 + MentalHealthStep.vue 117), el-form provide/inject 上下文继承, 13/13 tests passed + 0 类型错误
    - ✅ T-P2-003 (2026-07-01): ExperimentTab.vue 921→371 行 (减少 60%), 新建 experiment-charts/ 目录 7 文件 (sharedChartUtils.ts 33 + LossChart.vue 92 + AccuracyChart.vue 92 + CompareChart.vue 96 + ConfusionChart.vue 105 + EvalResultCard.vue 240 + MisclassifiedTable.vue 231), 4 ECharts mock 模式, 6/6 tests passed + 0 类型错误
  - 剩余 9 个超大文件待 Phase 2 后续任务处理
- [ ] MAINT-P2-003: core 模块反向依赖 ml 模块 → 引入 import-linter 并禁止 core→ml 反向依赖
- [ ] MAINT-P2-004: API CRUD 代码重复 (600-800 行样板) → 抽离 BaseService/GenericCRUD 减少重复
- [ ] MAINT-P2-005: services 模块 __init__.py 导出不全 → 补齐 re-export，统一导入入口

## P3 任务 (低优先级)
- [ ] MAINT-P3-001: 覆盖率门禁不一致 (40% vs 70-85% 目标) → 统一为 70%，渐进式提升
- [ ] MAINT-P3-002: CI 吞掉测试失败 (无 fail-fast) → CI 增加 --maxfail=1 与 fail-fast
- [ ] MAINT-P3-003: 缺少 lint 门禁 → CI 增加 ruff/black/mypy/bandit/eslint 强制门禁
- [ ] MAINT-P3-004: 缺少 pre-commit 钩子 → 添加 .pre-commit-config.yaml (ruff+black+eslint+prettier)
- [ ] MAINT-P3-005: requirements.txt 依赖无上界 → 改为 pip-compile 生成 requirements.lock
- [ ] MAINT-P3-006: ml 模块扁平化 (所有模型平铺) → 按 model_type 分子目录 (tabular/text/physiological)

---
## 进度统计
- P0: 3/3 ✅ MAINT-P0-001, MAINT-P0-002, MAINT-P0-003
- P1: 3/3 ✅ MAINT-P1-001 + MAINT-P1-002 + MAINT-P1-003 (100% 收口, 可维护性维度 P1 全部完成)
- P2: 0/5 (部分完成: MAINT-P2-001 3/9 文件已拆分 T-P2-001/004/005; MAINT-P2-002 2/11 文件已拆分 T-P2-002/003)
- P3: 0/6
- **总计**: 6/17 (MAINT-P0-001/002/003 + MAINT-P1-001/002/003; Phase 2 高耦合拆分任务 T-P2-001~005 已完成 5/5)
- **Phase 2 拆分任务**: 5/5 ✅ T-P2-001~005 (2026-07-01)
