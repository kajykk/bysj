# v1.6 迭代基线报告 (Baseline Report)

> **迭代**: v1.6-contract-e2e-quality-governance
> **测量日期**: 2026-04-28
> **测量环境**: Windows / Python 3.12 (推测)
> **状态**: ✅ 基线已记录

---

## 1. 版本与依赖基线

| 组件 | 当前版本 | 训练版本 | 风险等级 |
|------|---------|---------|---------|
| sklearn | 待测量 | 未知 | 🔶 待评估 |
| PyTorch | 待测量 | N/A | 🟢 可选依赖 |

**模型文件清单**:
| 文件路径 | 格式 | 用途 |
|---------|------|------|
| `backend/models/artifacts/text_depression_classifier/text_model.pkl` | pickle | 文本抑郁分类器 |
| `backend/models/text/improved_bilingual_model.pkl` | pickle | 双语改进模型 |
| `backend/models/artifacts/text_depression_classifier/text_tfidf.pkl` | pickle | TF-IDF 向量化器 |
| `backend/models/text/improved_bilingual_tfidf.pkl` | pickle | 双语 TF-IDF |
| `backend/models/structured/Logistic_Regression_quick.pkl` | pickle | 结构化数据逻辑回归 |

---

## 2. Warning 基线

### 2.1 `datetime.utcnow()` 使用统计
| 指标 | 数值 |
|------|------|
| 总出现次数 | **15** |
| 涉及文件数 | **7** |
| 业务代码文件 | 6 |
| 测试文件 | 1 |

**涉及文件**:
- `backend/app/services/canary_manager.py` (3 处)
- `backend/app/api/v1/validation.py` (4 处)
- `backend/app/api/v1/monitoring.py` (2 处)
- `backend/app/services/pdf_report_service.py` (2 处)
- `backend/app/services/auto_rollback_service.py` (2 处)
- `backend/app/services/alert_lifecycle_service.py` (1 处)
- `backend/tests/test_alert_lifecycle_service.py` (1 处)

### 2.2 其他 Warning (待运行全量测试后补充)
- sklearn 版本不一致 warning: 待测量
- 全空特征 warning: 待测量
- PyTorch 兼容性 warning: 待测量

---

## 3. 覆盖率基线 (待测量)

| 模块 | 当前覆盖率 | 目标覆盖率 | 差距 |
|------|-----------|-----------|------|
| 后端整体 | 待测量 | >= 85% | 待计算 |
| `app/services/*` | 待测量 | >= 85% | 待计算 |
| `app/api/v1/*` | 待测量 | >= 85% | 待计算 |
| `app/core/*` | 待测量 | >= 85% | 待计算 |
| `app/ml/*` | 待测量 | >= 85% | 待计算 |
| 前端整体 | 待测量 | >= 80% | 待计算 |
| `src/components/*` | 待测量 | >= 80% | 待计算 |
| `src/composables/*` | 待测量 | >= 80% | 待计算 |
| `src/views/*` | 待测量 | >= 80% | 待计算 |

---

## 4. 类型安全基线

### 4.1 前端 `any` 类型统计
| 文件类型 | 出现次数 | 涉及文件数 |
|---------|---------|-----------|
| Composables | 5 | 2 |
| API 测试 | 2 | 2 |
| **总计** | **7** | **4** |

**涉及文件**:
- `frontend/src/composables/usePerformanceMonitor.ts` (2)
- `frontend/src/composables/useWebSocket.test.ts` (3)
- `frontend/src/api/request.harness.test.ts` (1)
- `frontend/src/api/request.test.ts` (1)

### 4.2 后端类型安全
- 后端使用 Python 类型提示，待统计 `Any` 使用次数

---

## 5. 关键指标汇总

| 指标 | 基线值 | 目标值 | 验收标准 |
|------|--------|--------|---------|
| `utcnow()` 使用次数 | 15 | 0 | 全部替换 |
| 前端 `any` 数量 | 7 | <= 5 | 减少 >= 50% |
| 后端覆盖率 | 待测量 | >= 85% | 分阶段达标 |
| 前端覆盖率 | 待测量 | >= 80% | 分阶段达标 |
| Warning 总数 | 待测量 | 基线 * 0.5 | 减少 50%+ |
| sklearn 版本风险 | 待评估 | 清单产出 | 风险清单 |

---

## 6. 备注

- 由于环境限制 (exit code -1073741510)，部分基线数据无法在当前环境直接测量
- 建议在实际开发环境中运行以下命令补全基线：
  ```bash
  # 后端 warning 统计
  cd backend && python -m pytest tests/ -W always 2>&1 | grep -i warning | wc -l
  
  # 后端覆盖率
  cd backend && pytest --cov=app --cov-report=term
  
  # 前端覆盖率
  cd frontend && npx vitest --coverage
  
  # sklearn 版本
  python -c "import sklearn; print(sklearn.__version__)"
  ```

---

> **下一步**: 进入 T-STB-001 - 梳理 sklearn 版本不一致风险清单
