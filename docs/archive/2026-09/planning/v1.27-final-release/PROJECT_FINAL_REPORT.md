# PROJECT_FINAL_REPORT — 大学生心理健康风险评估系统

> **项目终期报告**
> **版本**: v1.27 Final Release
> **日期**: 2026-05-02
> **覆盖迭代**: v1.20 → v1.26

---

## 一、项目背景

大学生群体面临日益严重的心理健康挑战，焦虑、抑郁等问题呈上升趋势。本项目旨在构建一个**多模型、路由式**的心理健康风险评估系统，支持从结构化问卷数据到自由文本的多模态输入，实现分层级、可解释的风险评估。

---

## 二、问题定义

1. **核心问题**: 如何根据用户可用数据量，自动选择最优评估模型？
2. **安全问题**: 如何确保危机表述不被遗漏，始终触发人工复核？
3. **工程问题**: 如何在多模型并存的情况下，保持系统可维护、可观测、可回滚？

---

## 三、数据来源

| 数据源 | 样本量 | 用途 |
|:---|:--:|:---|
| Synthetic (结构化) | 10,000 | v1.20 基线训练 |
| Real (student_mental_health) | 1,000 | v1.21 真实数据验证 |
| External (Kaggle+Mendeley) | 19,916 | v1.23 外部临床标签 |
| mmpsy (GAD-7+文本) | 1,275 | v1.25 轻特征模型 |

---

## 四、模型演进路线

```
v1.20 结构化基线 (synthetic, 12特征, LR balanced)
    │
    ├─ v1.21 真实数据探索 (binary LR/RF + multiclass LR/RF)
    │   → binary 效果有限, multiclass 表现差 → 弃用/禁用
    │
    ├─ v1.22 风险评估方案审计
    │   → 明确数据分层与标签定义
    │
    ├─ v1.23 外部临床标签模型 (19,916 external, LR)
    │   → AUC=0.91, 外部验证通过 → experimental
    │
    ├─ v1.24 分数迁移治理 (ScoreAdapter, piecewise_monotonic)
    │   → 控制 v1.23→v1.20 迁移漂移 → limited_active
    │
    ├─ v1.25 轻特征模型 (17特征, Calibrated LR, mmpsy数据)
    │   → 仅需 GAD-7+文本 → limited_active
    │
    └─ v1.26 召回优化与安全治理
        → threshold=0.40, AUC=0.938
        → Crisis override + 监控面板
        → GO — 建议封版
```

---

## 五、最终系统架构

### 5.1 路由式多模型体系

系统根据输入特征完整度自动选择评估路径：

| 路由 | 触发条件 | 模型 | Lifecycle | 置信度 |
|:---|:---|:---|:---|:--:|
| structured | 特征覆盖率 ≥ 80% | v1.20 LR | default | high/medium |
| lite | GAD-7 + text ≥ 20 chars | v1.25 Calibrated LR | limited_active | medium |
| anxiety_only | 仅 GAD-7 | 启发式规则 | fallback | low |
| insufficient | 无有效输入 | — | fallback | — |

### 5.2 安全 Override 机制

- 10 个中文危机关键词检测
- 纯字符串匹配，不依赖任何模型状态
- `risk_level` 只升不降（至少设为 3）
- 前端 `el-alert type="warning"` 醒目提醒人工复核

---

## 六、实验结果对比

### 6.1 v1.20 结构化基线

| 指标 | 值 |
|:---|---:|
| Accuracy | 0.9833 |
| F1 | 0.9875 |
| ROC-AUC | 0.9991 |

*(注: synthetic 数据，指标偏高，但作为工程基线可用)*

### 6.2 v1.23 外部临床标签模型

| 指标 | 值 |
|:---|---:|
| AUC | 0.9131 |
| F1 | 0.8589 |
| Recall | 0.8733 |
| PHQ-9 Pearson r | 0.6826 |

### 6.3 v1.25 Lite + v1.26 Threshold

| 指标 | 值 | 要求 | 状态 |
|:---|---:|----:|:--:|
| AUC | 0.9380 | ≥ 0.88 | ✅ |
| Recall | 0.7692 | ≥ 0.75 | ✅ |
| Specificity | 0.9542 | ≥ 0.65 | ✅ |
| F1 | 0.7895 | — | ✅ |
| Brier Score | 0.0710 | ≤ 0.12 | ✅ |

### 6.4 关键改进：Recall 从 0.6667 → 0.7692

通过 v1.26 决策阈值优化（0.50 → 0.40），Recall 提升 15.4%，且 Specificity 保持在 0.9542。

---

## 七、安全策略

1. **Crisis Override**: 确定性规则，不依赖模型
2. **只升不降**: 安全标记只能提升风险等级
3. **人工复核提醒**: 前端 el-alert 醒目展示
4. **审计计数**: `_crisis_override_count` 可追溯
5. **Fallback 链路**: 5 级容错，系统不崩溃

---

## 八、监控与生命周期

### 8.1 监控能力

- Engine Snapshot API (routing_stats, fallback_count, crisis_count)
- Dashboard Summary API
- 模型加载状态与路径检查

### 8.2 模型生命周期治理

| Lifecycle | 数量 | 说明 |
|:---|---:|:---|
| default | 1 | v1.20 全局兜底 |
| limited_active | 3 | v1.24 adapter, v1.25 lite |
| experimental | 1 | v1.23 外部模型 |
| deprecated | 2 | v1.21 binary |
| disabled | 2 | v1.21 multiclass |

### 8.3 活跃模型过滤

```python
ACTIVE_LIFECYCLES = frozenset({"default", "limited_active"})
# get_active_models() 仅返回这两个状态的模型
```

---

## 九、技术实现

| 层 | 技术选择 |
|:---|:---|
| 后端框架 | FastAPI (Python), async/await |
| ML 框架 | scikit-learn (LogisticRegression, CalibratedClassifierCV) |
| 深度学习 (备选) | TensorFlow / PyTorch (optional, 已回退) |
| 前端 | Vue 3 + TypeScript + Element Plus + Vite |
| 数据库 | SQLite (dev) / PostgreSQL (prod) |
| 容器化 | Docker + docker-compose |

---

## 十、局限性

1. **结构化模型基于合成数据**: v1.20 在 synthetic 数据上训练，真实场景性能待外部验证
2. **Lite 模型样本量有限**: mmpsy 仅 1,275 样本，正样本比例 20.2%
3. **文本特征为浅层**: 基于关键词匹配和统计特征，未使用 BERT/embedding
4. **无多模态融合**: 结构化+文本+生理的多模态融合 (fusion) 因 Keras 模型缺失当前不可用
5. **未进行临床验证**: 所有评估指标基于统计测试集，未经临床医生独立评价

---

## 十一、后续展望

1. **数据扩展**: 收集更多真实标注数据，尤其增加高风险样本
2. **文本深度化**: 引入预训练语言模型 (BERT/RoBERTa) 进行语义级风险评估
3. **临床验证**: 与学校心理中心合作，进行临床效果评估
4. **移动端**: 开发微信小程序或移动 App
5. **持续监控**: 建立生产环境下的模型漂移检测与自动重训机制

---

## 十二、交付清单

| 类别 | 文件 | 状态 |
|:---|:---|:--:|
| 资产检查 | `FINAL_ASSET_CHECK.md` | ✅ |
| E2E 测试 | `FINAL_E2E_TEST_REPORT.md` | ✅ |
| 前端验收 | `FINAL_FRONTEND_REVIEW.md` | ✅ |
| 模型卡 | `FINAL_MODEL_CARD.md` | ✅ |
| 架构说明 | `FINAL_SYSTEM_ARCHITECTURE.md` | ✅ |
| 总报告 | `PROJECT_FINAL_REPORT.md` | ✅ |
| 封版决策 | `FINAL_GO_NO_GO.md` | ✅ FINAL-GO |

---

> **项目终期结论**: 系统已建成**路由式多模型风险评估体系**，核心指标全面达标，安全治理完善，具备交付条件。建议 **FINAL-GO 封版**。
