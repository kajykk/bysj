# P2-2 评估结果：DeepSeek 第二意见 —— 不做

> 执行：2026-10-05 03:00–03:15｜脚本 `scripts/llm_judge_evaluate.py`（可复现）
> 原始数据：`llm_judge_results.csv`、`llm_judge_eval_report.json`、`llm_judge_ablation.json`
> 供应商：DeepSeek `deepseek-flash`（非思考模式）

## 1. 结论：**不做**

用**只传脱敏结构化特征**（合规路径，2026-10-04 选定）时，DeepSeek 对「中度及以上抑郁」
**没有独立判别能力**。三臂消融（每臂 100 条，成本合计 ¥0.045）：

| 臂 | 给 LLM 的字段 | Cohen's kappa | 一致率 |
|---|---|---|---|
| A | 完整（含模型概率与判定阈值） | **0.9800** | 0.99 |
| **B** | **中性字段（抽掉一切模型判断）** | **0.0000** | **0.50（=随机）** |
| C | 不经 LLM，模型自身判断 | 0.9800 | 0.99 |

**判读**：

1. **A 与 C 完全相同（kappa 0.98）** —— LLM 拿到模型概率和阈值后，几乎逐条复述了模型结论。
   它测的是「LLM 是否忠实转述模型」，**不是**「LLM 有临床价值」。
2. **B 掉到 0.00（一致率 0.50 = 抛硬币）** —— 抽掉模型判断后，只给 GAD-7（焦虑量表，与抑郁是
   不同构念）和 `audio_count`，LLM 对抑郁诊断**没有任何判别力**。

按既定规则（kappa < 0.6 → 不做，不放宽传原文），**结论是放弃 LLM 第二意见**。
若不是为了确认这件事，代价是一次「看起来 kappa 0.98、其实毫无增量」的绿灯。

## 2. ⚠️ 一个必须防止的误读：C 臂的 0.98 不是泛化性能

C 臂 kappa 0.98 看着像「模型已经很准，LLM 没必要」，但**不能这么读**：

- `improved_bilingual_model.pkl` 是**用全量语料训练**的，而这些样本**在训练集内** →
  C 臂是**样本内（in-sample）**一致性；
- 真正的泛化性能是 P2-1 测出的 **groupwise CV F1 = 0.5864**（同一份 metrics 里
  `full_model_eval_on_zh` F1 = 0.9972 也是样本内，两者相差 0.41）。

所以 A == C 只能说明「**LLM 忠实复述了模型的样本内判断**」，不能推出「模型泛化已经很准」。

## 3. 成本（顺带得到的确切数字）

| 项 | 值 |
|---|---|
| A+B 两臂 token | in 46,077 / out 9,183 |
| 合计成本 | **¥0.0447**（flash off-peak，汇率假设 7.2） |
| 单次 | 约 ¥0.00024 —— 远低于 ¥0.01 门槛 |

即：**成本从来不是瓶颈，判别力才是。**

## 4. 若将来还要重启这条线，前置条件是什么

按本次实测，需要先满足其一，否则重复实验没有意义：

1. **让 LLM 看到文本**（改变合规路径，需重新评估数据出境风险）—— 但那正是 10-04 决定
   排除的方案；
2. **换成对结构化特征真正有用的信息** —— 例如增加行为/生理指标、量表子项分数；
3. **换一个确实能读结构化数据的任务** —— 例如让 LLM 判断「需不需要人工复核」（流程性判断，
   而非临床诊断），那与它的能力匹配。

在现有合规路径下，本实验已经证明：**这条路的信息量不足，再跑一次也是同样结果。**

## 5. 过程中的两个坑（复用价值高）

1. **DeepSeek V4 系列默认开 thinking 模式**：最终答案在 `content`，思维链在
   `reasoning_content`，若 thinking 未结束 `content` 会是**空字符串** → 解析不到 judgement
   （表现为「没有有效判断」）。需显式传 `{"thinking": {"type": "disabled"}}`；
   且 thinking 模式下 `temperature` 不生效。
2. **语料按 `source_idx` 去重是必须的**：同一 group 有「原文 + 若干增强变体」多行
   （8,379 行只有 **1,244** 个唯一 group），直接 merge 会把每个样本复制成多份
   —— 实测 `--limit 5` 拿到的全是同一个 `J0001`。

## 6. 复现

```powershell
cd E:\code\bysj\backend
# key 放 backend/.env 一行: DEEPSEEK_API_KEY=sk-xxx（已 gitignore）
.venv/Scripts/python.exe ../scripts/llm_judge_evaluate.py --limit 100            # 单臂
.venv/Scripts/python.exe ../scripts/llm_judge_evaluate.py --limit 100 --ablation  # 三臂消融
```
