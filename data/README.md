# data/ 数据说明（P1 可复现性配套）

> 本目录被 `.gitignore` 排除（112MB+），clone 后需单独获取。
> 最小可运行集：`processed/` 全部（<1MB）+ 按需获取 `external/` 训练语料。

## processed/（特征与评估集，随代码逻辑版本化，体积小）

| 文件 | 说明 |
|---|---|
| `lite_features.csv`（89KB） | 轻特征模型输入特征 |
| `mmpsy_structured_features.csv`（191KB） | 结构化特征 |
| `v1_23_external/` | v1.23 外部验证相关产物 |

## external/（原始/第三方语料，体积大，按需获取）

| 文件 | 体积 | 说明 |
|---|---|---|
| `aligned_features.csv` | 2MB | 对齐后特征 |
| `mmpsy_scores.csv` | 1.3MB | MMPsy 评分 |
| `ood_test_set_v2.csv` | 10MB | 分布外测试集 |
| `mmpsy_augmented.csv` | 17MB | 增强语料 |
| `chinese_depression_corpus_v1.csv` | 19MB | 中文抑郁语料 v1 |
| `chinese_depression_corpus_v1_snapshot_8377.csv` | 19MB | v1 快照（8377 条） |
| `chinese_depression_corpus_v2.csv` | 33MB | 中文抑郁语料 v2 |
| `chinese_depression_corpus_v2_clean.csv` | 10MB | v2 清洗版 |
| `mmpsy-data/`、`student-depression/`、`student-depression-dataset/` | — | 第三方数据集目录（注意数据许可，仅限研究使用） |

获取方式：与模型产物一并发布（见 `scripts/artifacts.manifest.json` 的生成方式，
`python scripts/generate_manifest.py` 可扩展覆盖本目录）。
论文引用口径以 `backend/models/MODEL_REGISTRY.md` 为准。
