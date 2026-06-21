# 关键路径测试清单

## 1. 模型加载 (Model Loading)

| 测试 ID | 测试项 | 测试文件 | 优先级 | 状态 |
|---------|--------|----------|--------|------|
| CP-ML-001 | 模型文件存在时正确加载 | `tests/test_ml_model.py` | P0 | [x] |
| CP-ML-002 | 模型文件不存在时返回 False | `tests/test_ml_model.py` | P0 | [x] |
| CP-ML-003 | 模型版本不匹配时触发警告 | `tests/test_ml_model.py` | P1 | [ ] |
| CP-ML-004 | 损坏的模型文件优雅处理 | `tests/test_ml_model.py` | P1 | [ ] |
| CP-ML-005 | 多模型并行加载 | `tests/test_ml_model.py` | P2 | [ ] |

## 2. 回退机制 (Fallback Mechanism)

| 测试 ID | 测试项 | 测试文件 | 优先级 | 状态 |
|---------|--------|----------|--------|------|
| CP-FB-001 | 模型不可用时触发规则回退 | `tests/degradation/test_model_fallback.py` | P0 | [x] |
| CP-FB-002 | 特征缺失时触发规则回退 | `tests/degradation/test_model_fallback.py` | P0 | [x] |
| CP-FB-003 | 低质量输入时触发规则回退 | `tests/degradation/test_model_fallback.py` | P1 | [ ] |
| CP-FB-004 | 超时情况下触发规则回退 | `tests/degradation/test_model_fallback.py` | P1 | [ ] |
| CP-FB-005 | 回退结果格式与正常结果一致 | `tests/degradation/test_model_fallback.py` | P0 | [ ] |

## 3. 报告导出 (Report Export)

| 测试 ID | 测试项 | 测试文件 | 优先级 | 状态 |
|---------|--------|----------|--------|------|
| CP-RPT-001 | PDF 报告生成成功 | `tests/api/test_reports_api.py` | P0 | [x] |
| CP-RPT-002 | Excel 报告生成成功 | `tests/api/test_reports_api.py` | P0 | [x] |
| CP-RPT-003 | 大数据量报告生成不超时 | `tests/performance/test_api_latency.py` | P1 | [ ] |
| CP-RPT-004 | 报告模板渲染正确 | `tests/api/test_reports_api.py` | P1 | [ ] |
| CP-RPT-005 | 批量导出功能正常 | `tests/api/test_reports_api_extended.py` | P1 | [x] |

## 4. 漂移检测 (Drift Detection)

| 测试 ID | 测试项 | 测试文件 | 优先级 | 状态 |
|---------|--------|----------|--------|------|
| CP-DRF-001 | PSI 计算正确 | `tests/test_ml_model.py` | P1 | [ ] |
| CP-DRF-002 | 输入分布漂移触发告警 | `tests/api/test_monitoring_api.py` | P1 | [ ] |
| CP-DRF-003 | 概念漂移检测 | `tests/test_ml_model.py` | P2 | [ ] |
| CP-DRF-004 | 漂移告警通知发送 | `tests/api/test_monitoring_api.py` | P2 | [ ] |

## 5. 路由懒加载 (Route Lazy Loading)

| 测试 ID | 测试项 | 测试文件 | 优先级 | 状态 |
|---------|--------|----------|--------|------|
| CP-RT-001 | 路由按需加载 | `frontend/src/router/*.test.ts` | P1 | [ ] |
| CP-RT-002 | 路由预加载策略 | `frontend/src/router/*.test.ts` | P2 | [ ] |
| CP-RT-003 | 404 页面正确显示 | `frontend/src/views/common/NotFoundPage.test.ts` | P1 | [ ] |
| CP-RT-004 | 权限路由守卫 | `frontend/src/router/*.test.ts` | P0 | [ ] |

## 6. 图表交互 (Chart Interaction)

| 测试 ID | 测试项 | 测试文件 | 优先级 | 状态 |
|---------|--------|----------|--------|------|
| CP-CHT-001 | 图表数据正确渲染 | `frontend/src/composables/useECharts.test.ts` | P1 | [x] |
| CP-CHT-002 | 图表缩放和拖拽 | `frontend/src/composables/useECharts.test.ts` | P2 | [ ] |
| CP-CHT-003 | 图表数据更新 | `frontend/src/composables/useECharts.test.ts` | P1 | [ ] |
| CP-CHT-004 | 图表响应式适配 | `frontend/src/composables/useECharts.test.ts` | P1 | [ ] |

## 7. 用户认证流程 (Auth Flow)

| 测试 ID | 测试项 | 测试文件 | 优先级 | 状态 |
|---------|--------|----------|--------|------|
| CP-AUTH-001 | 用户注册 | `tests/services/test_auth_service.py` | P0 | [x] |
| CP-AUTH-002 | 用户登录 | `tests/services/test_auth_service.py` | P0 | [x] |
| CP-AUTH-003 | Token 刷新 | `tests/services/test_auth_service.py` | P0 | [ ] |
| CP-AUTH-004 | 密码重置 | `tests/services/test_auth_service.py` | P1 | [x] |
| CP-AUTH-005 | 权限校验 | `tests/api/test_auth_api.py` | P0 | [x] |

## 8. 风险评估流程 (Risk Assessment)

| 测试 ID | 测试项 | 测试文件 | 优先级 | 状态 |
|---------|--------|----------|--------|------|
| CP-RISK-001 | 结构化数据评估 | `tests/services/test_risk_service.py` | P0 | [x] |
| CP-RISK-002 | 文本数据评估 | `tests/services/test_risk_service.py` | P1 | [ ] |
| CP-RISK-003 | 生理数据评估 | `tests/services/test_risk_service.py` | P1 | [ ] |
| CP-RISK-004 | 多模态融合评估 | `tests/test_fusion_engine_extended.py` | P0 | [x] |
| CP-RISK-005 | 评估结果干预推荐 | `tests/services/test_intervention_service.py` | P0 | [x] |

## 9. 数据管理 (Data Management)

| 测试 ID | 测试项 | 测试文件 | 优先级 | 状态 |
|---------|--------|----------|--------|------|
| CP-DATA-001 | 数据录入 | `tests/services/test_user_data_service.py` | P0 | [x] |
| CP-DATA-002 | 数据查询 | `tests/services/test_user_data_service.py` | P0 | [x] |
| CP-DATA-003 | 数据更新 | `tests/services/test_user_data_service.py` | P1 | [ ] |
| CP-DATA-004 | 数据删除 | `tests/services/test_user_data_service.py` | P1 | [ ] |
| CP-DATA-005 | 数据验证 | `tests/services/test_input_validator.py` | P0 | [x] |

## 10. 监控告警 (Monitoring & Alerts)

| 测试 ID | 测试项 | 测试文件 | 优先级 | 状态 |
|---------|--------|----------|--------|------|
| CP-MON-001 | 系统健康检查 | `tests/test_core_health.py` | P0 | [x] |
| CP-MON-002 | 性能指标采集 | `tests/performance/test_api_latency.py` | P1 | [x] |
| CP-MON-003 | 告警触发 | `tests/api/test_monitoring_api.py` | P1 | [ ] |
| CP-MON-004 | 告警通知 | `tests/api/test_monitoring_api.py` | P2 | [ ] |
| CP-MON-005 | 监控仪表盘数据 | `frontend/src/views/monitoring/MonitoringDashboard.test.ts` | P1 | [x] |

## 关键路径覆盖率统计

| 路径类别 | 总测试数 | 已完成 | 覆盖率 |
|---------|---------|--------|--------|
| 模型加载 | 5 | 2 | 40% |
| 回退机制 | 5 | 2 | 40% |
| 报告导出 | 5 | 3 | 60% |
| 漂移检测 | 4 | 0 | 0% |
| 路由懒加载 | 4 | 0 | 0% |
| 图表交互 | 4 | 1 | 25% |
| 用户认证 | 5 | 3 | 60% |
| 风险评估 | 5 | 3 | 60% |
| 数据管理 | 5 | 3 | 60% |
| 监控告警 | 5 | 3 | 60% |
| **总计** | **47** | **20** | **43%** |

## 执行建议

1. **P0 测试**: 必须在每次 CI 中执行，失败则阻塞合并
2. **P1 测试**: 在 PR 合并前执行，失败需要修复
3. **P2 测试**: 定期执行（每日/每周），用于发现潜在问题
