# P2-1 评估结果：句向量 vs TF-IDF（同口径 A/B）

> **2026-10-05 结论修正：由「换」反转为「不换」。**
> 2026-10-04 的 A/B 把 TF-IDF 基线**做差了**（用了 TfidfVectorizer 默认 analyzer，
> 中文不分词；生产用的是 jieba 分词），且阈值协议与生产不同。
> 用生产同款配置重测后：**MiniLM F1 0.5075 / AUC 0.7568 低于生产基线 0.5864 / 0.8437 → 不换**。
> 10-04 的原始记录保留在 §4，作为「怎样把对照实验做错」的样本。
> 最新数据：`p2_1_fixed_threshold_eval.json`

## 1. 最终结论：不换（2026-10-05）

### 1.1 与生产同口径的对照（固定阈值 0.3）

生产 bilingual_v2 的口径（已入库 `backend_text_bilingual_v2_metrics.json`）：
**固定阈值 0.3**、groupwise CV、n=8,379、正例率 0.2163。下表为同一口径重测：

| 组 | 特征 | 维 | F1 | AUC |
|---|---|---|---|---|
| A | TF-IDF（默认 analyzer，中文不分词） | 89,988 | 0.4338 | 0.6929 |
| C | TF-IDF + SVD | 300 | 0.3446 | 0.5604 |
| **D** | **TF-IDF + `zh_bilingual_tokenize`（jieba，生产同款）** | 103,028 | **0.5709** | **0.8420** |
| B | MiniLM 句向量 | 384 | 0.5075 | 0.7568 |
| — | **生产基线（入库 metrics）** | 120,000 | **0.5864** | **0.8437** |

**D 组复现了生产基线**：F1 0.5709 vs 0.5864（差 0.015）、AUC 0.8420 vs 0.8437（差 0.0017）。
协议可信度由此得到验证（差异来自 `max_features` 103,028 vs 120,000 等细节）。

**判定：不换。** MiniLM 相对生产基线 ΔF1 = **−0.0634**、ΔAUC = **−0.0852**，两个指标都更低。

### 1.2 为什么会得出相反的结论（10-04 的两个错误）

| # | 错误 | 后果 |
|---|---|---|
| 1 | **基线没用生产配置**：生产 TF-IDF 用 `zh_bilingual_tokenize`（jieba 中文分词），我用了默认 analyzer（中文不分词） | TF-IDF 基线被低估：0.4338 vs 真实 0.5864，凭空"让出" 0.15 |
| 2 | **阈值协议不同**：生产用固定 0.3，我用「每折训练折内选最佳 F1 阈值」 | 后者在分布漂移折上把阈值推向极端并全判负（多折 F1=0），让基线更难看 |

两个错误**同向叠加**，于是 MiniLM 看起来"涨了 0.22"。
**教训：A/B 的基线必须是生产同款配置的复现，而不是自己随手搭一个"TF-IDF"。**
否则比较的是"候选方案 vs 被削弱的自己"，结论必然偏乐观。

### 1.3 句向量路线是否就此否定

不否定路线，只否定**这一个模型**。`paraphrase-multilingual-MiniLM-L12-v2` 是 2023 年的小模型；
若下一轮要试，门槛必须重设为 **超过生产基线 0.5864**（不是超过我搭的基线），候选建议
`BAAI/bge-m3`、`intfloat/multilingual-e5-*` 之类更新的多语模型，且同样要用 D 组口径测。

---

## 4. 2026-10-04 原始记录（保留作反面样本，勿直接引用其结论）

| 固定项 | 值 |
|---|---|
| 语料 | `data/external/chinese_depression_corpus_v1.csv`（8,379 行，1,275 组，正例率 21.6%） |
| 标签 | `phq9_binary` |
| 分组 | `m2_group_cv_eval.build_group_ids`（原始样本与其增强变体同组，防泄露） |
| 分类器 | `LogisticRegression(C=1.0, class_weight="balanced", max_iter=3000)` |
| CV | `GroupKFold(n_splits=5)`，阈值在**训练折内**按最佳 F1 选 |
| 实现 | `t1_group_cv_tool.evaluate_group_cv`（与项目既有评估同一实现） |

| 组 | 特征 | 维度 |
|---|---|---|
| A | TF-IDF(1-2gram, min_df=2, sublinear_tf) | 89,988 |
| **C** | **A → TruncatedSVD(300)**（解释方差 0.246） | 300 |
| B | MiniLM `paraphrase-multilingual-MiniLM-L12-v2`（mean pooling, L2 norm） | 384 |

## 2. 结果

| 组 | F1 mean | AUC mean |
|---|---|---|
| A TF-IDF(89,988) | 0.0544 | 0.6929 |
| **C TF-IDF+SVD(300)** | 0.2452 | 0.5604 |
| **B MiniLM(384)** | **0.4692** | **0.7568** |

- **ΔF1 (B−C) = +0.2240**、**ΔAUC (B−C) = +0.1963**，CI95 不重叠 → **达到预设门槛**
- ΔF1 (B−A) = +0.4148，但 A 是**坏基线**（89,988 维配 6,703 训练样本 = 维度诅咒，多折 F1=0），只能作对照说明，**不能当决策依据**

### 一个值得记的反转

降维（SVD 300）把 TF-IDF 的 **AUC 从 0.6929 打到 0.5604**（丢掉 75% 方差），F1 却升到 0.2452。
这说明：**B 的优势不是「维度低」也不是「概率校准好」**——若只是维度/校准优势，C 组（同为 300 维稠密）应当与 B 接近，但 C 的 AUC 只有 0.56。
**B 的增益来自语义表征本身**，这是本次评估最硬的一条证据。

## 3. 必须同时声明的限定（不要只引用第 2 节）

| # | 限定 | 影响 |
|---|---|---|
| 1 | **CI95 不可信**：`GroupKFold` 是确定性的（sklearn 不支持 shuffle），`SEEDS` 循环只重排 fold 顺序 → 15 次评估实为 5 折重复，CI 按 n=15 计算偏窄。**只看点估计** | 门槛判断仍成立（ΔF1 0.224 远大于 0.02），但不要引用 CI 数字 |
| 2 | **绝对 F1 0.469 未达项目自设目标**（`m2_group_cv_eval` 写的目标是 ≥0.65） | MiniLM 优于 TF-IDF，但**没有达标** |
| 3 | **单一语料、单一标签**：仅中文 corpus v1 + `phq9_binary`；生产主路径是**双语**模型 | 外部效度未验证，不能直接外推到生产 |
| 4 | **成本未核算**：权重 470MB（现有 `improved_bilingual_model.pkl` 约 1.3MB，**约 360 倍**）；编码 8.7 条/秒（单条约 115ms CPU） | 上线前必须做体积/延迟核算 |
| 5 | **计划里的 0.586 基线无法溯源**（见 `P2_NEXT_RELEASE_PROPOSALS.md`） | 本结果是**自建口径**，不可与 0.586/0.536 并列引用 |

## 4. 结论（分档，不是一句「换」）

**判定：换 —— 但只到「进入下一轮正式评估」这一档，不足以直接替换生产模型。**

已满足：预设门槛（ΔF1 +0.224 ≥ +0.02，公平对照下 CI 不重叠）、机制合理（语义表征增益可解释）。

未满足，投产前必须补：

1. **在双语生产语料上复测**（本轮仅中文；生产主路径为 `text_improved_bilingual_*`）；
2. **补齐 F1 到 ≥0.65 目标**（当前 0.469；可试更强的 pooling/微调/更合适的分类器，但不得为凑达标而调评估口径）；
3. **成本核算**（470MB 权重 vs 现有 1.3MB；CPU 推理延迟对实时链路的影响）；
4. **修评估器**：去掉 `SEEDS` 冗余循环（或改用真正支持 shuffle 的 `StratifiedGroupKFold`），并考虑阈值选取策略——多折 F1=0 说明「训练折最优阈值」在分布漂移折上不可靠（两组同等受影响，故相对比较仍有效，但绝对值别当真）。

## 5. 复现方式

```bash
cd backend
# 权重（470MB，本机 hf 直连不通，见 scripts/fetch_hf_model_via_mirror.sh）
bash ../scripts/fetch_hf_model_via_mirror.sh \
     sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 ../models/_cache/minilm-l12
# 三组一起跑（约 30 分钟，B 组编码占 16 分钟）
.venv/Scripts/python.exe ../scripts/t1_sentence_embedding_eval.py
# 只重跑某组
.venv/Scripts/python.exe ../scripts/t1_sentence_embedding_eval.py --only-groups C
```

依赖说明：`sentence-transformers 6.1.0` 在本环境**不可用**（其 `AutoProcessor` 调用是 transformers 5.x 新增，而该模型仓库无 processor 配置 → `ValueError`）。评估脚本改为**手工 `AutoTokenizer` + `AutoModel` + mean pooling**（与 `1_Pooling/config.json` 的 `pooling_mode_mean_tokens=true` 等价），权重完整性已核验（`missing_keys=0`、`mismatched_keys=0`）。
