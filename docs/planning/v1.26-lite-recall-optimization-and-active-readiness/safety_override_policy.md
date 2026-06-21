# v1.26 Crisis Safety Override Policy

## 目的

确保模型在检测到用户输入中包含危机相关关键词时，自动升级风险等级并标记人工复核，防止漏报高危用户。

## 适用范围

- lite 模型路径 (`predict_lite`)：所有通过文本分析进行轻特征预测的场景
- 不依赖模型加载状态：Crisis 检测基于纯字符串匹配，始终可用

## 危机关键词 (CRISIS_KEYWORDS)

```
想死, 自杀, 自残, 活不下去, 不想活,
结束生命, 死了算了, 一死了之, 不如死了, 死了一了百了
```

共 10 个关键词，覆盖中文危机表达的高频模式。

## 检测逻辑

1. **匹配方式**: 纯字符串包含匹配 (substring matching), 不区分大小写 (中文无大小写)
2. **触发条件**: 用户输入的 `audio_transcript` 中包含任一 `CRISIS_KEYWORDS`
3. **覆盖规则**:
   - `safety_flags`: 添加 `"crisis_keyword_detected"`
   - `requires_human_review`: 设置为 `True`
   - `risk_level`: 若当前 < 3 (high)，则提升至 3
   - `crisis_override_count` 计数器 +1
4. **不改变**: `risk_score`/`probability`/`prediction` 保持模型原始输出不变

## 安全层级

| Level | 触发条件 | 动作 |
|-------|----------|------|
| 1 (Info) | 无危机关键词 | 正常流程 |
| 2 (Warning) | 命中 crisis keyword | risk_level → min(3, current), requires_human_review=True |
| 3 (Override) | 命中 + risk_level≥3 | 已有高风险，追加人工复核标记 |

## 回退说明

- Crisis 检测是 **确定性规则**（不是概率模型），不依赖模型加载状态
- 如果 lite 模型不可用 → fallback 到 `_anxiety_only_fallback`，此时仍可通过 crisis 检测（如果文本可用）
- Crisis 检测 **绝不降级** 风险等级：只升不降

## 与现有 CrisisDetector 的关系

- 现有 `crisis_detector` 用于文本分析路径 (`predict_text`)
- v1.26 `_check_crisis_safety` 仅用于 lite 路径 (`predict_lite`)
- 两者互补，不冲突：text 路径有自己的 crisis 检测，lite 路径通过关键词匹配

## 合规参考

- FDA DHAC 2025.11: 心理健康 AI 安全护栏建议
- 确定性的关键词触发 + 人工复核标记 = 最小伤害原则
