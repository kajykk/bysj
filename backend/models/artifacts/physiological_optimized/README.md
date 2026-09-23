# physiological_optimized (v2 experimental)

> **状态**: TRAINING_PENDING (未交付到 v1.28-final)
> **生产回退**: 加载失败时自动使用 `physiological` (v1) + 启发式规则

## 概述

`physiological_optimized` 是 v1.6 计划中、但**未在 v1.28-final 中落地**的生理信号深度学习模型。
该目录在 v1.28 中创建出来,作为未来 v1.29+ 迭代的占位与契约锚点。

## 当前生产行为

```
predict_fusion(features, text, physiological)
  └── physiological model_loader.load()
        ├── load('physiological')         # v1 (F1=0.694) - 当前实际使用
        └── load('physiological_optimized') # v2 - FileNotFoundError → fallback
```

**回退路径**(在 `app/core/model_engine.py`):
```python
try:
    model = load_physiological_optimized()
except Exception:
    logger.warning("physiological_optimized unavailable, using v1 fallback")
    model = load_physiological()
```

## 验收指标(目标)

| 指标 | 基线 (v1) | 目标 (v2) |
|:---|:---:|:---:|
| **F1-Score** | 0.694 | ≥ 0.75 |
| **Accuracy** | 0.689 | ≥ 0.78 |
| **Precision** | 0.683 | ≥ 0.76 |
| **Recall** | 0.704 | ≥ 0.74 |

## 训练数据要求

- **样本量**: ≥ 5,000 标注样本 (生理信号 + 抑郁评分)
- **来源**: 高校心理中心 + 可穿戴设备数据 (HRV, 步态, 睡眠)
- **划分**: 80% train / 10% val / 10% test (按用户 ID 分组,避免数据泄漏)

## 模型架构 (草案)

```python
class PhysiologicalOptimizedV2(nn.Module):
    def __init__(self, n_features: int = 28):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_features, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Dropout(0.4),
            nn.Linear(256, 128),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Dropout(0.4),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(64, 2),  # binary: depression vs control
        )

    def forward(self, x):
        return self.net(x)
```

- 参数量: ~80K (符合 Ralph 规则 #6: < 50K 用于 < 10K 样本)
- 正则化: L2 (1e-4) + Dropout (0.3-0.4) + EarlyStopping (patience=10)
- 优化器: AdamW + CosineAnnealingLR

## 灰度上线路径

1. **影子模式** (v1.29): 5% 流量同步预测,不实际干预决策
2. **金丝雀** (v1.30): 5% 流量启用新模型,实时监控 F1/AUPRC
3. **McNemar 检验**: p<0.05 后切换 50% 流量
4. **全量**: 14 天观察期后切换 100%

## 文件清单

| 文件 | 状态 | 说明 |
|:---|:---:|:---|
| `manifest.json` | ✅ 已生成 | 训练计划、目标、fallback 契约 |
| `model.json` | ⏳ 待训练 | 神经网络权重 |
| `scaler.json` | ⏳ 待训练 | StandardScaler 参数 |
| `feature_names.json` | ⏳ 待训练 | 28 维特征名 |
| `metrics.json` | ⏳ 待训练 | F1/Accuracy/Precision/Recall + 95% CI |

## 相关文档

- [NEXT_STEPS.md](../../../docs/archive/2026-09/planning/v1.28-final-delivery/NEXT_STEPS.md) - v1.29 计划
- [model_engine.py](../../../app/core/model_engine.py) - 回退逻辑
- [RALPH.md 规则 #6](../../../.trae/rules/Ralph.md) - 深度学习规范
