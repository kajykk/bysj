# EATD-Corpus 外部锁定测试 · 预注册协议（PRE-REGISTRATION）

> 纪律：本协议在**查看 EATD 任何评分分布或模型在该集上的任何指标之前**写定并提交。
> 一旦提交，切点、样本定义、预处理、指标、成功判据**均不得因看到结果而更改**。
> 若执行后方发现协议有缺陷，只能作废并**另立 v2 预注册**重跑，不得就地改切点重报。

## 0. 目的与角色

- 角色：EATD 是文本模态的**外部锁定测试集**（从未参与任何训练/调参/阈值选择）。
- 它回答的问题：MMPsy 学生书面语上训练的文本模型，迁移到**独立人群（心理咨询志愿者）、
  口语访谈转录**上，真实判别力是多少？——即论文《结果》章的「跨人群/跨语域」外推证据。
- 它与现有 groupwise（同人群换被试 F1 0.5864）互补：groupwise 答"换人"，EATD 答"换人群+换语域"。

## 1. 数据来源（可复现获取）

- 来源：EATD-Corpus（ICASSP 2022, arXiv:2202.08210）官方 OneDrive
  `https://1drv.ms/u/s!AsGVGqImbOwYhHUHcodFC3xmKZKK?e=mCT5oN`，解压密码 `Ymj26Uv5`。
- 仓库代码：`speechandlanguageprocessing/ICASSP2022-Depression`（仅代码，无数据）。
- 落地路径（本机）：`data/external/eatd/`（受 .gitignore 排除，不入库；只登记形态）。
- 引用义务：Shen, Yang, Lin. *Automatic Depression Detection: An Emotional Audio-Textual
  Corpus and a GRU/BiLSTM-based Model.* ICASSP 2022.

## 2. 样本定义（一条样本 = 一个志愿者的文本）

- 每个志愿者文件夹含 `positive.txt / negative.txt / neutral.txt` 三段访谈转录。
- **样本单位 = 志愿者（subject）**，不是段落；与 groupwise 的"按人分组"哲学一致。
- 文本拼接规则（开发前定死）：三段按 `positive → negative → neutral` 顺序以换行拼接，
  空/缺失段跳过。**不做**任何增强、不改写、不翻译。
- 标签：每志愿者一个 SDS 分。用 `new_label.txt`（标准化 = 原始 SDS × 1.25）。

## 3. 二分类切点（开发前定死，核心）

- **阳性（疑似抑郁）= new_label ≥ 53；阴性 = new_label < 53。**
- 理由：Zung SDS 标准分（×1.25）常用临床切点，53 为中国常模「轻度抑郁及以上」界值；
  与 EATD 论文报告的抑郁比例（训练 19/83≈23%、验证 11/79≈14%）量级一致。
- **不**根据本数据集分布调切点；**不**尝试多个切点择优。
- 敏感性（仅报告，不择优）：另附 ≥60（中重度界）的读数，作为"更严切点下"的描述，
  但**主结果只认 ≥53**。

## 4. 预处理（复用生产链路，不得为 EATD 特调）

- 文本：与生产文本模型完全一致的分词/向量化（`zh_bilingual_tokenize` + 已训练
  TF-IDF 词表 + 已训练 LR）。**只做 transform，不 refit**——这是"外部测试"的定义。
- 不针对 EATD 调阈值：**判定阈值固定 0.5**（与生产、与 groupwise 一致）。

## 5. 指标与成功判据

- 主指标：F1、ROC AUC、Recall、Precision、混淆矩阵，**均附 95% CI**。
- CI 方法：**按 subject 分组 bootstrap**（抽志愿者，非抽段），B=10000 seed=42
  （与 ROUND_30 groupwise 同一方法学）。
- 样本量诚实声明：EATD 仅 162 人、阳性约 30 人 ⇒ CI 必然宽；**宽区间如实报告**，
  不得只报点估计。
- 成功判据（开发前定义，避免事后叙事）：
  - "有真实跨域信号"= AUC 的 95% CI 下界 > 0.5；
  - "可作辅助初筛"需 Recall CI 下界与 Precision 同时达到可讨论水平，否则只报"信号存在但弱"。
- **任何结果都报**：即便 AUC 跌破 0.5（完全不可迁移），也如实写为负结果——
  与 ROUND_27 生理迁移 AUC 0.512 同等对待。

## 6. 污染检查（跑前必做）

- 用 v1_27 去重逻辑核验：EATD 文本与 MMPsy 派生训练语料（v1/v2/clean/mmpsy_augmented）
  的重叠率；若存在显著重叠（按理不应有，人群/来源不同），在报告中声明并剔除重叠段落。
- 核验 EATD 从未被任何训练/调参脚本读取（`git grep` 证据留档）。

## 7. 执行顺序（不可颠倒）

1. [本文件] 预注册协议提交入库；【检查点】此时不得看过 EATD 评分分布/任何指标。
2. 用户手动下载 + 解压 EATD 到 `data/external/eatd/`。
3. 跑「污染检查 + 结构校验」脚本（只验结构/重叠，不报指标）。
4. 跑「一次性锁定评估」：transform-only + 阈值 0.5 + 分组 bootstrap CI，落盘逐样本预测 + json。
5. 结果进台账（新编号）+ 章节 §4ter + 闸门；无论好坏。

## 8. 不可做清单

- 不得为提升 EATD 读数而重训/微调模型、改切点、改阈值、挑段落。
- 不得把 EATD 结果与泄漏口径（0.99）混谈。
- 不得因结果差而隐瞒——负结果同样入库。