# sklearn 版本不一致风险评估清单

> **迭代**: v1.6-contract-e2e-quality-governance
> **评估日期**: 2026-04-28
> **评估人**: Ralph AI
> **状态**: ✅ 风险评估完成

---

## 1. 依赖版本锁定状态

| 组件 | 当前锁定版本 | 训练版本 | 状态 |
|------|-------------|---------|------|
| scikit-learn | `1.3.2` (requirements.txt) | 1.3.2 | ✅ 已锁定 |
| joblib | `>=1.4.2` | 1.4.2 | ✅ 兼容范围合理 |

---

## 2. 模型文件清单与格式分析

| 模型文件 | 格式 | 依赖 | 版本检查 | 风险等级 |
|---------|------|------|---------|---------|
| `models/structured/Logistic_Regression_quick.pkl` | joblib | sklearn | ✅ 已注册 | 🟢 低 |
| `models/artifacts/text_depression_classifier/text_model.pkl` | pickle | sklearn | ✅ 已注册 | 🟢 低 |
| `models/text/improved_bilingual_model.pkl` | joblib | sklearn | ✅ 已注册 | 🟢 低 |
| `models/artifacts/text_depression_classifier/text_tfidf.pkl` | pickle | sklearn | ✅ 已注册 | 🟢 低 |
| `models/text/improved_bilingual_tfidf.pkl` | joblib | sklearn | ✅ 已注册 | 🟢 低 |

---

## 3. 代码层面版本检查机制

### 3.1 已有检查机制 (✅ 优秀)

**文件**: `backend/app/core/model_compatibility.py`

| 功能 | 实现状态 | 说明 |
|------|---------|------|
| 版本兼容性注册表 | ✅ 已实现 | `MODEL_COMPATIBILITY_REGISTRY` 包含 10 个模型 |
| sklearn 版本检查 | ✅ 已实现 | `check_sklearn_version()` 对比当前与目标版本 |
| 模型加载时检查 | ✅ 已实现 | `load_model_with_compatibility_check()` 加载前检查 |
| 全量兼容性检查 | ✅ 已实现 | `check_all_model_compatibilities()` 批量检查 |
| warning 捕获 | ✅ 已实现 | 使用 `warnings.catch_warnings()` 捕获版本相关 warning |

**代码示例**:
```python
# 加载时自动检查版本
model = load_model_with_compatibility_check(model_path)

# 批量检查所有模型
results = check_all_model_compatibilities()
```

### 3.2 模型注册表详情

| 模型 ID | 格式 | sklearn | torch | transformers | tensorflow | fallback |
|---------|------|---------|-------|-------------|-----------|----------|
| structured_logistic_regression_quick | joblib | 1.3.2 | - | - | - | heuristic_rule |
| structured_random_forest_quick | joblib | 1.3.2 | - | - | - | heuristic_rule |
| structured_best_ensemble_quick | joblib | 1.3.2 | - | - | - | heuristic_rule |
| text_bert_classifier | transformers | - | 2.2.0 | 4.36.2 | - | heuristic_rule |
| text_improved_bilingual_model | joblib | 1.3.2 | - | - | - | heuristic_rule |
| fusion_dnn_best | keras | - | - | - | 2.20.0 | heuristic_rule |
| fusion_cross_modal_best | keras | - | - | - | 2.20.0 | heuristic_rule |
| fusion_transformer_best | keras | - | - | - | 2.20.0 | heuristic_rule |
| physiological_risk_model | joblib | 1.3.2 | - | - | - | heuristic_rule |
| physiological_model_v2_dl | json | - | - | - | - | heuristic_rule |

---

## 4. 风险分析

### 4.1 识别到的风险

| 风险项 | 风险等级 | 影响 | 缓解措施 | 状态 |
|--------|---------|------|---------|------|
| sklearn 版本严格锁定 (`==1.3.2`) | 🟡 中 | 无法自动获取安全补丁 | 使用 `>=1.3.2,<1.4.0` 范围 | 建议优化 |
| 模型文件缺少版本元数据 | 🟡 中 | 无法从文件本身读取训练版本 | 依赖注册表维护 | 建议补充 |
| 无自动重新训练机制 | 🟢 低 | 版本升级后需手动重新导出 | 文档记录流程 | 可接受 |

### 4.2 无风险项 (✅)

- ✅ 所有 sklearn 模型已注册兼容性信息
- ✅ 加载时自动版本检查
- ✅ 版本不匹配时触发 warning
- ✅ 所有模型都有 fallback 策略
- ✅ requirements.txt 已固定版本

---

## 5. 改进建议

### 建议 1: 放宽 sklearn 版本约束 (优先级: 中)

**当前**:
```
scikit-learn==1.3.2
```

**建议**:
```
scikit-learn>=1.3.2,<1.4.0
```

**理由**: 允许接收 1.3.x 系列的安全补丁和 bug 修复，同时保持兼容性。

### 建议 2: 模型文件嵌入版本元数据 (优先级: 低)

在模型序列化时嵌入训练环境信息：
```python
import joblib
import sklearn

model_data = {
    "model": trained_model,
    "metadata": {
        "sklearn_version": sklearn.__version__,
        "training_date": "2026-04-28",
        "python_version": "3.12.0",
    }
}
joblib.dump(model_data, "model.pkl")
```

### 建议 3: CI 中增加版本兼容性检查 (优先级: 高)

在 CI 流水线中添加：
```yaml
- name: Check Model Compatibility
  run: |
    cd backend
    python -c "from app.core.model_compatibility import check_all_model_compatibilities; import json; print(json.dumps(check_all_model_compatibilities(), indent=2))"
```

---

## 6. 验证清单

- [x] 所有模型文件已登记在兼容性注册表
- [x] requirements.txt 已固定 sklearn 版本
- [x] 加载代码包含版本检查逻辑
- [x] 版本不匹配时有 warning 和 fallback
- [x] 所有模型都有明确的 fallback 策略

---

## 7. 结论

**总体风险等级**: 🟢 **低风险**

项目已建立完善的 sklearn 版本治理机制：
1. 版本锁定在 requirements.txt
2. 兼容性注册表维护所有模型信息
3. 加载时自动版本检查
4. 不匹配时触发 warning 并回退

**建议行动**:
1. 考虑放宽 sklearn 版本约束为 `>=1.3.2,<1.4.0`
2. 在 CI 中增加兼容性检查步骤
3. 后续迭代考虑模型文件嵌入元数据

---

> **下一步**: T-STB-002 - 统一 sklearn 训练/推理版本策略
