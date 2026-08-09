# 新数据探针报告 (combined_data.csv, 从未参与训练/验证)

- 生成时间: 2026-08-09T15:38:29.780467+00:00
- 数据源: `datasets/combined/combined_data.csv` (53,043 行 → 清洗后 ≥5 字符 52,625)

## 主二分类 (Depression + Suicidal vs Normal)

| 模型 | N | Pos率 | Acc | BalAcc | Prec | Recall | Spec | F1 | AUC | Brier | 误判数 |
|------|---|-------|-----|--------|------|--------|------|-----|-----|-------|--------|
| text_depression_classifier | 42343 | 61.5% | 0.8405 | 0.8030 | 0.8111 | 0.9657 | 0.6403 | 0.8817 | 0.9403 | 0.1136 | 6753 |
| text_improved_bilingual | 42343 | 61.5% | 0.9109 | 0.9016 | 0.9157 | 0.9420 | 0.8613 | 0.9287 | 0.9659 | 0.0779 | 3771 |

## 中间症状类判阳率 (行为观测, 不计入指标)

| 类 | text_depression_classifier | text_improved_bilingual |
|---|---|---|
| Anxiety | 90.9% | 84.7% |
| Bipolar | 98.6% | 97.0% |
| Stress | 94.7% | 95.2% |
| Personality disorder | 97.4% | 92.3% |

## 误判样例 (各模型 Top-5 低概率错报)

### text_depression_classifier
- [Depression label=1 prob=0.0006] [ webshealth.com
- [Suicidal label=1 prob=0.005] omg the cringe i cant
- [Depression label=1 prob=0.0068] comence terapia e [opcionyo.com]( cambio la vida... terapia es la solucin
- [Depression label=1 prob=0.0144] os ltimos trs dias eu ando sentindo uma bad to profunda e eu no entendo, eu no tenho motivos pra estar triste eu deveria estar sorrindo mas no estou e isso me deixa mais triste. eu sinto um vazio to g
- [Suicidal label=1 prob=0.0167] 37.795120 -122.44502037.794440 -122.43321037.793690 -122.404460
### text_improved_bilingual
- [Depression label=1 prob=0.0312] [ webshealth.com
- [Depression label=1 prob=0.0479] ughhhhhhhhhh ughhhh ugh ughhhhhh ugh ugh ugh ugh ughhhhhhhhhhhhhhhhhhhhhhhhhhhh ughhhhhhhhhhhh
- [Suicidal label=1 prob=0.0759] today is finally the day today!
- [Suicidal label=1 prob=0.0816] omg the cringe i cant
- [Suicidal label=1 prob=0.0876] yep. tonight. tonight