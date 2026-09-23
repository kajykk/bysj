# v1.22 模型选择报告 (MODEL_SELECTION_REPORT)

> **日期**: 2026-05-01  
> **迭代**: v1.22-risk-model-scheme  
> **报告类型**: 方案选择版

---

## 一、候选方案

v1.22 比较的不是单纯模型分数，而是可上线、可解释、可回滚的整体方案。

| 方案 | 说明 | 结论 |
|------|------|------|
| A. 继续使用 v1.20 Synthetic LR | 保持当前默认模型 | 推荐作为默认稳定路径 |
| B. 启用 v1.21 Real Binary LR | 真实数据训练，高召回但低精度 | 推荐作为实验参考 |
| C. 启用 v1.21 Real Binary RF | 精度较高但召回不足 | 不推荐 |
| D. 启用独立五级模型 | v1.21 已验证失败 | 不推荐 |
| E. 二分类概率 + 五级阈值分档 | 用概率生成展示等级 | 推荐作为 v1.22 主方案 |
| F. Heuristic fallback | 规则兜底 | 必须保留 |

---

## 二、关键指标对比

| 模型 | F1 | Recall | ROC-AUC | 主要问题 | v1.22 定位 |
|------|----|--------|---------|----------|------------|
| v1.20 Synthetic LR | 0.9875 | ~0.99 | 0.9991 | 学到合成规则，不代表真实诊断 | 默认稳定模型 |
| v1.21 Real LR | 0.6000 | 0.9130 | 0.9401 | 精度低，概率需校准 | 实验参考模型 |
| v1.21 Real RF | 0.6829 | 0.6087 | 0.8956 | 漏报率高 | 不推荐 |
| v1.21 Multiclass LR | 0.1365 Macro | 0.6154 High/Critical | — | 总体不可用 | 禁用 |
| v1.21 Multiclass RF | 0.1921 Macro | 0.1154 High/Critical | — | Critical 识别失败 | 禁用 |

---

## 三、v1.22 推荐架构

```text
默认路径：
结构化输入 → v1.20 Synthetic LR / Heuristic fallback → risk_score → risk_level

实验路径：
结构化输入 → v1.21 Real Binary LR → calibrated probability → experimental risk_score

展示路径：
主风险等级 = 默认路径输出
实验参考 = v1.21 Real LR 输出，仅后台/研究可见
```

---

## 四、选择理由

### 4.1 为什么不直接替换 v1.20

- v1.21 Real LR 的 F1 未达标；
- 真实数据样本量不足；
- 概率校准不充分；
- 替换后可能导致误报激增；
- 目前缺少线上真实反馈闭环。

### 4.2 为什么仍保留 v1.21 Real LR

- 它是目前唯一基于真实 Depression 标签训练的结构化模型；
- Recall 高，适合作为安全侧参考；
- ROC-AUC 高，说明排序能力有效；
- 可以作为未来真实数据扩充后的基线。

### 4.3 为什么禁用五级独立模型

- Accuracy 和 F1 Macro 均不可接受；
- High/Critical 召回不稳定；
- 标签派生导致泄漏与解释风险；
- 五级输出可以通过概率分档更稳定地实现。

---

## 五、v1.22 最终模型选择

| 功能 | 推荐方案 |
|------|----------|
| 默认线上结构化模型 | v1.20 Synthetic LR 或 heuristic fallback |
| 真实数据参考模型 | v1.21 Real Binary LR |
| 五级风险输出 | 二分类概率/风险分数阈值分档 |
| 独立五级模型 | 禁用 |
| RF 模型 | 不作为主路径 |
| 模型回滚 | 必须保留 fallback |

---

## 六、配置建议

```text
STRUCTURED_MODEL_VERSION=v1.20_synthetic_lr
STRUCTURED_MODEL_MODE=primary
ENABLE_REAL_BINARY_EXPERIMENT=true
REAL_BINARY_MODEL_VERSION=v1.21_real_binary_lr
ENABLE_MULTICLASS_MODEL=false
ENABLE_HEURISTIC_FALLBACK=true
```

如果需要灰度开启真实模型，可采用：

```text
STRUCTURED_MODEL_VERSION=v1.21_real_binary_lr
STRUCTURED_MODEL_MODE=experimental
```

但不建议在没有人工复核和监控的生产环境中直接切换。

---

## 七、Go / No-Go 判定

| 项目 | 判定 |
|------|------|
| v1.20 默认路径 | Go |
| v1.21 Real Binary LR 实验路径 | Conditional Go |
| v1.21 Real RF | No-Go |
| 独立五级模型 | No-Go |
| 概率分档五级风险 | Go |
| fallback 兜底 | Go |

---

## 八、结论

v1.22 的模型选择结论是：

> **不以真实模型直接替换默认模型，而是采用“稳定默认模型 + 真实 LR 实验参考 + 概率分档五级风险 + fallback 兜底”的组合方案。**

该方案承认 v1.21 暴露出的真实数据限制，同时保留了后续升级空间。
