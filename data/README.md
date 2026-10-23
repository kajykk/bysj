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

## external/ 本轮新增（2026-10-23，高品质外部数据）

统一获取工具：`python scripts/data_acquisition/fetch_external_datasets.py --list|--all|--verify`

| 目录 | 数据集 | 状态（本机实测） | 受阻时的手动步骤 |
|---|---|---|---|
| `../datasets/physiological/external/wesad/` | WESAD（ICMI 2018，15 被试多模态生理） | **已下载并接入**（4s 窗 parquet + 窗口/被试特征表 + manifest） | — |
| `cnsocialdepress/` | CNSocialDepress（专家标注中文文本） | 上游 README/海报已本地化；**数据待取** | 外网环境 `gdown 1QCRZJAJsESg9WB6pmLqnDtbmASNhHaaN` |
| `swdd/` | SWDD（微博 23,237 用户） | **待取**：百度 anonymous 直链被风控（errno 118/9019） | fetch 脚本 `--baidu-cookie` 或浏览器手动下载 |
| `wu3d/` | WU3D（微博 10K+ 抑郁用户） | **待取**：同上 | 同上 |
| `cmdc/` | CMDC（中文多模态，78 人 PHQ-9） | **待取**：IEEE DataPort 需账号+EULA，解压密码邮件索取 | 见 DATASETS.md §10 |
| `erisk2021/` | eRisk 2021（Reddit BDI-II） | **待取**：DUA 表单 + 域名不可达 | 见 DATASETS.md §13 |
| `depinter-cn/` | DepInter-CN（临床访谈 50 人） | **待取**：预印本未公开托管 | 见 DATASETS.md §14 |
| `zsfc-av84/` | 中文文本抑郁数据集（31+33） | **待取**：IEEE 账号 | 见 DATASETS.md §15 |

许可、规模、质量分层与 G2 用途以 `docs/model-evaluation/DATASETS.md` §8–§15 为准；
本机网络通道实测结论（Google/HF 官网/uni-siegen/erisk 不可达，hf-mirror/codeload/IEEE 页面/百度可达）
记录在该脚本 docstring。
