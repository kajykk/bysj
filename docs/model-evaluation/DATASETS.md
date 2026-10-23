# 外部数据集登记表（G2 的启动输入）

> 目的：让 G2（外部迁移验证）启动时**不必再查许可与来源**。
> 本表 2026-10-23 逐项实读登记；**本轮不跑任何外部评估**（那是 G2）。
> 未在仓内留下许可证据的条目，一律标「许可未知」，不代填。

## 0. 速览

| 数据集 | 用途 | 许可 | 是否已用于训练 | G2 可用性 |
|---|---|---|---|---|
| Depresjon（生理） | 生理模型训练/评估 | 见 §1 | 是（当前评估的唯一样本源） | 可用（已在本仓） |
| Kaggle Wearable（生理） | 生理模型训练候选 | 见 §2 | **否**（合并代码存在但训练未用） | 可用（已在本仓） |
| PHQ-9 Dataset 5th Edition | 量表级真值 | 见 §3 | **是（训练标签母体，ROUND_27 实测）** | **不可作外迁**（标签泄漏） |
| actverse（acttrust） | 活动记录仪样例 | GPLv3 | 否 | 谨慎（GPL 传染性） |
| MMPsy（多模态心理） | 中文文本/音频 | MIT | 否（仅派生语料参与训练） | 可用 |
| 中文抑郁语料 v1 / v2 | 中文文本训练 | 派生自 MMPsy（MIT） | 是（v2 用于 lite/文本模型） | 可用（须标派生） |
| **WESAD**（§8，本轮新增） | 生理外部验证基准 | 科研非商业署名 | 否 | **已接入**（窗口+被试特征表） |
| **CNSocialDepress**（§9，本轮新增） | 文本外部验证（专家标注） | 原仓库条款 | 否 | 文档已本地化，**数据待取**（Google 通道） |
| **CMDC**（§10，本轮新增） | 中文多模态外部验证 | EULA | 否 | 待取（IEEE 账号+EULA） |
| **SWDD**（§11，本轮新增） | 大规模中文语料 | 原仓库未附 | 否 | 待取（路径已验证：转存到自己网盘后 `--via-netdisk`，见 §11） |
| **WU3D**（§12，本轮新增） | 大规模中文扩量 | 原仓库未附 | 否 | 待取（同 §11 路径） |
| **eRisk 2021**（§13，本轮新增） | 英文早筛对照 | DUA | 否 | 待取（DUA 表单） |
| **DepInter-CN**（§14，本轮新增） | 中文临床访谈 | 预印本 | 否 | 待申请 |
| **中文文本抑郁数据集 zsfc-av84**（§15，本轮新增） | 小样本高纯度验证 | IEEE 开放获取 | 否 | 待取（IEEE 账号） |

---

## 1. Depresjon（生理信号）

| 字段 | 值 |
|---|---|
| 名称 | Depresjon（processed 版） |
| 仓内路径 | `datasets/physiological/external/depresjon_processed/depresjon_physiological.csv`（1029 行，1,030 含表头）；`depresjon_augmented.csv`（7,203 行，增强版） |
| 来源 | 仓内文件头标注 `source=depresjon`；原始数据来自 Depresjon 公开数据集（Dartmouth 活动记录仪队列），**仓内无原始 LICENSE 文件** |
| 版本 / 日期 | 文件 mtime 2026-04-27；无显式版本号；行数与列名（steps/heart_rate/sleep_hours/sleep_quality/exercise_minutes/systolic_bp/diastolic_bp/depression_label/phq9_score/mean_activity/std_activity/peak_activity/autocorrelation）已在本表登记 |
| 许可 | **未在仓内留下许可证据**（无 LICENSE）。用于研究/论文须回溯源数据集获取条款后再对外发布 |
| 引用要求 | 引用 Depresjon 原始论文（Garcia-Ceja et al., 2018）；仓内代码路径 `app/ml/data_loader.py::load_depresjon_data` |
| 是否已用于训练 | **是**——`physiological`(v1) 与 `physiological_optimized`(v2) 的训练/评估均基于此文件（v2 的原切分不可复现，见 `PHYSIO_V2_EVAL_REPORT.md` §一） |
| 拟用于何种评估 | G2 的「同分布跨采集点」对照；不得再作为「外部」验证集（已参与训练/调参） |
| 纳入日期 | 2026-10-23（本表首次登记） |

## 2. Kaggle Wearable（生理信号）

| 字段 | 值 |
|---|---|
| 名称 | Mental Health Wearable Data（Kaggle） |
| 仓内路径 | `datasets/physiological/external/kaggle_wearable/mental_health_wearable_data.csv`（10,000 行） |
| 来源 | Kaggle 公开数据集；列 `Heart_Rate_BPM / Sleep_Duration_Hours / Physical_Activity_Steps / Mood_Rating / Mental_Health_Condition` |
| 版本 / 日期 | 文件 mtime 2024-10-17；无版本号 |
| 许可 | **未在仓内留下许可证据**（无 LICENSE）；Kaggle 数据集条款须回到原始页面确认 |
| 引用要求 | 引用 Kaggle 数据集页面（当前仓内未记录 slug，须补） |
| 是否已用于训练 | **否**——`app/ml/data_loader.py::merge_datasets` 会合并它，但当前 artifact 的训练分布与合并数据不符（见评估报告 §一） |
| 拟用于何种评估 | G2 的**跨数据集迁移**首选：同特征域（心率/睡眠/步数）、不同采集协议，且未参与训练 |
| 纳入日期 | 2026-10-23 |

## 3. PHQ-9 Dataset 5th Edition（量表）

| 字段 | 值 |
|---|---|
| 名称 | PHQ-9 Dataset（5th Edition） |
| 仓内路径 | `datasets/PHQ-9_Dataset_5th Edition.csv`（682 数据行，683 含表头） |
| 来源 | 公开问卷数据集（仓内无来源 URL/作者记录）；列含 9 个 PHQ 条目原文 + `PHQ_Total` + `PHQ_Severity` + 3 个生活压力项 |
| 版本 / 日期 | 文件名即「5th Edition」；文件无显式日期 |
| 许可 | **未知**（无 LICENSE、无 README） |
| 引用要求 | 须补齐来源与引用（当前只在文件名层面可追溯）；9 条目为 PHQ-9 标准文本（Kroenke et al., 2001） |
| 是否已用于训练 | **是（训练标签母体）**——ROUND_27 实测推翻 ROUND_26 的「否」判定：`data/external/aligned_features.csv`（结构化模型的训练母表，28,552 行）的 `PHQ_Total` **逐值分布与本表完全相同**（0:43,1:40,2:44,…），且其 `label_binary` 恰为 `phq9_total>=10` ⇒ 训练母表是本表 682 行的复制/增强。虽然 `grep -rn "PHQ-9_Dataset" --include="*.py"` 零命中（没有脚本显式读它），但数据已被合成进训练集 |
| 拟用于何种评估 | **不可用于外迁评估**（标签泄漏）。只能作 PHQ-9 条目文本/量表口径的参考；G2 若要评估量表一致性，须换用未参与训练的外部问卷数据 |
| 纳入日期 | 2026-10-23 |

## 4. actverse / acttrust（活动记录仪）

| 字段 | 值 |
|---|---|
| 名称 | actverse（R 包）内置 `acttrust` 示例数据 |
| 仓内路径 | `datasets/external/physiological/actverse/`（整包 vendored，含 `data-raw/acttrust.csv`、`data/acttrust.rda`、`CITATION.cff`、`LICENSE.md`） |
| 来源 | GitHub `danielvartan/actverse`（R 包，处理/可视化 actigraphy 数据）；`CITATION.cff` 记 v0.2.0，作者 Vartanian, Matias, Serrano, Benedito-Silva |
| 版本 / 日期 | 0.2.0（`CITATION.cff`）；包内无独立日期 |
| 许可 | **GPL-3.0**（`LICENSE.md` 全文为 GNU GPL v3） |
| 引用要求 | 引用 `actverse: An R package for actigraphy data analysis`（`CITATION.cff` 的 preferred-citation） |
| 是否已用于训练 | **否**（仅 vendored 参考实现，未进入任何数据管线） |
| 拟用于何种评估 | **不建议直接用于 G2 评估**：GPL-3.0 的传染性会波及派生数据/代码的分发；如确需使用，只能作「方法对照」（读取其预处理逻辑），不复制数据进交付物 |
| 纳入日期 | 2026-10-23 |

## 5. MMPsy（多模态心理数据）

| 字段 | 值 |
|---|---|
| 名称 | Multi-Modal Psychology Data（MMPsy） |
| 仓内路径 | `data/external/mmpsy-data/`（`LICENSE`/`README.md`/`data/`/`model/`/`data_generation.py`） |
| 来源 | 官方数据仓库，对应论文 *Mental-Perceiver: Audio-Textual Multimodal Learning for Mental Health Assessment*（arXiv:2408.12088）；README 记 **1,275 名真实学生**的量表分数、访谈音频与文本 |
| 版本 / 日期 | 无显式版本；LICENSE 记 `Copyright (c) 2024 shuyeit` |
| 许可 | **MIT**（`data/external/mmpsy-data/LICENSE` 全文） |
| 引用要求 | 引用 Mental-Perceiver 论文（arXiv:2408.12088）+ 该仓库 |
| 是否已用于训练 | **派生语料参与训练**（见 §6）；原始多模态数据本身未直接进训练 |
| 拟用于何种评估 | G2 的**中文文本/多模态迁移**：可作为「跨语料」对照，但须按 `user_id` 分组切分（`v1_23_external/split_metadata.json` 的随机划分有分组泄漏嫌疑，已在 `docs/ML_LEAKAGE_AUDIT.md` 登记） |
| 纳入日期 | 2026-10-23 |

## 6. 中文抑郁语料 v1 / v2（MMPsy 派生）

| 字段 | 值 |
|---|---|
| 名称 | 中文抑郁语料 v1 / v2（含 clean 版与快照） |
| 仓内路径 | `data/external/chinese_depression_corpus_v1.csv`（8,511 行）、`..._v1_snapshot_8377.csv`、`..._v2.csv`（15,244 行）、`..._v2_clean.csv`；`mmpsy_augmented.csv`（增强）、`ood_test_set_v2.csv`（分布外测试集） |
| 来源 | **MMPsy（§5）的派生**：列结构与 MMPsy 完全一致（`user_id/phq9_*/gad7_*/audio_*/text/augmentation/source_idx`），`source_idx` 可回溯源样本、`augmentation` 列标记合成行 |
| 版本 / 日期 | v1 mtime 2026-07-23、v2 mtime 2026-07-24、v2_clean 2026-07-27；行数即版本 |
| 许可 | **继承 MMPsy 的 MIT**（派生数据）；但**派生文件本身无 LICENSE**，对外分发须同时附 §5 的 MIT 声明与派生说明 |
| 引用要求 | 引用 Mental-Perceiver（arXiv:2408.12088）+ 说明「由 MMPsy 派生、含 `augmentation` 标记的合成样本」 |
| 是否已用于训练 | **是**（v2/clean 用于 lite 与文本侧训练；`mmpsy_augmented` 为增强语料） |
| 拟用于何种评估 | G2 的**中文跨域泛化**必须以 `user_id` 分组切分（文本模态 groupwise F1 = 0.5864 是当前可引用的泛化口径，见 `docs/EVALUATION_TRUST_SUMMARY.md`）；**不得**用 `v1_23_external` 的随机划分再报一次「外部」指标 |
| 纳入日期 | 2026-10-23 |

---

## 6b. OOD 测试集（`ood_test_set_v2.csv`）— ROUND_27 补登记

| 字段 | 值 |
|---|---|
| 名称 / 路径 | `data/external/ood_test_set_v2.csv`（5,075 行） |
| 来源 | 中文语料 v1 的派生（列结构与 v1/v2 一致：`user_id/phq9_*/gad7_*/text/augmentation/source_idx`） |
| 许可 | 随 v1/v2 派生自 MMPsy（MIT），但**派生文件本身无 LICENSE** |
| 是否已用于训练 | **部分**：`original` 1,275 行全在训练语料 v1；`mmpsy_augmented` 1,175 行全在训练增强集；只有 `eda` 的 2,523 行与训练语料精确不重叠（仍是 original 的 EDA 改写 ⇒ 兄弟泄漏） |
| 拟用于何种评估 | **不能作真外迁**（ROUND_27 实测：3 个子集里 2 个完全泄漏、1 个兄弟泄漏）；只能作域内压力测试，见 `TRANSFER_MATRIX.md` §2.3 |
| 纳入日期 | 2026-10-23 |

## 7. 登记口径说明

1. **「是否已用于训练」只认仓内代码证据**（训练脚本/管线实际读取），不认文件名或目录位置。
2. **「许可」只认仓内 LICENSE/CITATION 原文**；没有就写「未知/未在仓内留下证据」——G2 启动前必须补齐，不得用「公开数据集」代替许可条款。
3. **`data/external/` 被 `.gitignore` 排除**（112MB+），clone 后需按 `data/README.md` 单独获取；本表登记的是**本机实测形态**（行数以实测为准）。
4. G2 启动时的最小检查清单：每个拟用数据集必须满足「许可已核实 + 未参与训练（或已按分组隔离）+ 引用要求已满足」三条，缺一不得出对外数字。
5. **§8–§15 为本轮（2026-10-23）新增的高品质外部数据**，统一经 `scripts/data_acquisition/fetch_external_datasets.py`
   获取/登记；本机网络实测：Google / HuggingFace 官网 / uni-siegen / erisk.irlab.org 不可达，
   hf-mirror.com / codeload.github.com / IEEE DataPort 页面 / pan.baidu.com 可达。
   只有 WESAD 完成了全自动下载+接入（§8）；其余数据集的受阻原因与手动步骤在各节如实登记，
   **不得**因「页面可达」推断「数据已取得」。

---

## 8. WESAD（可穿戴应激与情感，多模态生理金标准）— 本轮新增，已接入

| 字段 | 值 |
|---|---|
| 名称 | WESAD（Wearable Stress and Affect Detection） |
| 仓内路径 | `datasets/physiological/external/wesad/`（.gitignore 排除）：`wesad_4_3_120.parquet`（70,101,269 B，sha256 前缀 `80391ea6…`，全文见同目录 `wesad_manifest.json`）、`wesad_window_features.csv`（11,044 行 × 23 列）、`wesad_subject_features.csv`（45 行）、`README.md` |
| 来源 | 原论文 Schmidt et al., ICMI 2018（doi:10.1145/3242969.3242985）；原站 uni-siegen 本机不可达，**实际经 HF 镜像 `LouisSimon/wesad-parquet` 获取**（hf-mirror.com） |
| 版本 / 日期 | 镜像 lastModified 2024-06-14；4s 窗 / 3s 步长 |
| 许可 | **科研非商业使用、需署名**（原站条款；镜像未附 LICENSE，对外发布以原站条款为准） |
| 引用要求 | Schmidt, P., Reiss, A., Duerichen, R., Marberger, C., Van Laerhoven, K. (2018). WESAD. ACM ICMI. |
| 是否已用于训练 | **否**（本轮只做数据接入：窗口/被试特征表 + manifest，未进任何训练/评估） |
| 实测规模 | 15 被试（S2–S17，与原论文一致）；11,044 窗口；标签 baseline 5,866 / stress 3,322 / amusement 1,856 |
| 拟用于何种评估 | G2 的**生理外部验证**（stress vs non-stress，必须按 `user` 分组）：可映射 depresjon 口径子集 `heart_rate/mean_activity/std_activity/peak_activity/autocorrelation`（映射表见 manifest `schema_map_to_depresjon`）；`sleep_*/血压/phq9_score` WESAD 不存在（`schema_gap`），**不得造列补齐** |
| 质量备注 | 手腕 BVP 干净：按条件 HR = stress 95.5 / baseline 77.9 / amusement 77.4（应激抬升 ≈18bpm，与原论文一致）；胸部 `ctxt_bvp` 通道为高频噪声，已弃用胸部心率；4s 窗 RMSSD 峰列不稳定（NaN≈67%），G2 以 HR/EDA/ACC 为主 |
| 纳入日期 | 2026-10-23 |

## 9. CNSocialDepress（中文社交媒体抑郁风险，专家标注）— 本轮新增，文档已本地化

| 字段 | 值 |
|---|---|
| 名称 | CNSocialDepress（CNSD） |
| 仓内路径 | `data/external/cnsocialdepress/`（.gitignore 排除）：**上游 README.md + 海报 PDF 已 vendored**（2026-10-23，GitHub main 分支 tarball）；**数据本体未取得** |
| 来源 | arXiv:2510.11233（2025-10）；GitHub `jytal/CNSocialDepress`；数据托管 Google Drive（file id `1QCRZJAJsESg9WB6pmLqnDtbmASNhHaaN`） |
| 规模 / 标签 | 微博 233 用户 / 44,178 文本；心理专家标注 10,306 个抑郁相关片段；二元风险标签 + DSM-5/PHQ-9 引导的六维结构化属性；CNSD Gold 200 用户 + Test 33 用户 + Silver |
| 许可 | 以原仓库 README 条款为准（研究用途）；上游文档随仓 vendored 作许可与口径凭据 |
| 引用要求 | Xu, Lan, Yu, He, Zhang, Wang, Magistry, Valette, Li (2025). CNSocialDepress. arXiv:2510.11233 |
| 是否已用于训练 | **否** |
| 受阻原因（实测） | 本机网络不可达 Google（drive.google.com 连接失败，2026-10-23）；HF/GitHub 均无数据镜像（已搜） |
| 手动步骤 | 在有外网的环境：`pip install gdown && gdown 1QCRZJAJsESg9WB6pmLqnDtbmASNhHaaN -O data/external/cnsocialdepress/CNSD_data.zip`（已写入 fetch 脚本 `--dataset cnsocialdepress` 分支） |
| 拟用于何种评估 | G2 的**文本外部验证首选**：用户级（groupwise）评估，Test 33 / Gold 200 用户；直接对治当前文本模态 groupwise F1 0.5864 的口径问题；六维标签可另作可解释性分析 |

## 10. CMDC（中文多模态抑郁语料）— 本轮新增，待取

| 字段 | 值 |
|---|---|
| 名称 | Chinese Multimodal Depression Corpus（CMDC） |
| 仓内路径 | 未落盘（待取后入 `data/external/cmdc/`） |
| 来源 | IEEE DataPort 开放获取页（DOI 10.21227/jng1-rn06）；论文见 IEEE Trans. Affective Computing |
| 规模 / 模态 | 78 被试（22 男 / 56 女）；半结构化访谈；文本+音频+视频；PHQ-9 量表；仅 45 人（19 MDD / 26 HC）有视频 |
| 许可 | EULA 签署后开放；part1–8.zip 共约 6GB，**解压有密码** |
| 是否已用于训练 | **否** |
| 受阻原因（实测） | IEEE DataPort 页面可达（200）但下载需账号登录 + 签署 EULA；解压密码需邮件 zoubochao@ustb.edu.cn 索取（页面原文） |
| 手动步骤 | 注册/登录 IEEE DataPort → 页面对应数据集签署 EULA → 下载 part1–8.zip → 邮件索取解压密码 → 解压入 `data/external/cmdc/` |
| 拟用于何种评估 | G2 的**中文多模态外部验证**：与本项目三模态设计对齐；DepInter-CN 论文（rs-9258754）即用 CMDC 作外部验证并报告 question-level 平均聚合适配其结构 |

## 11. SWDD（新浪微博抑郁数据集）— 本轮新增，待取

| 字段 | 值 |
|---|---|
| 名称 | Sina Weibo Depression Dataset（SWDD） |
| 仓内路径 | 未落盘（待取后入 `data/external/swdd/`） |
| 来源 | GitHub `ethan-nicholas-tsai/SWDD`（Wang et al., 2020）；数据托管 Google Drive + 百度网盘（提取码 gdq6，分享码 `1V8S_a_GoFFRzRG542eRcSg`） |
| 规模 / 标签 | 23,237 用户（3,711 抑郁 / 19,526 对照）/ 485 万条微博；用户级二元标签 + **17 个症状级字段**（兴趣丧失/失眠/自杀意念…）；JSONL（depressed.jsonl / control.jsonl） |
| 许可 | 原仓库未附 LICENSE（研究用途）；作者已删用户 ID |
| 是否已用于训练 | **否** |
| 受阻原因（实测） | 百度分享直链风控：`sharedownload` 在 **全 UA（Chrome/安卓/iOS/netdisk）× clienttype（0/12/25）矩阵** 下均失败——ct=0 → errno 118；ct=12 → 9019「need verify」；ct=25 → 113（2026-10-24 实测，**与 UA 无关，只由 clienttype 决定**）。verify/list/tplconfig 匿名均正常（可见 `SWDD.zip` 861,645,574 B、fs_id 32964761477653） |
| 已验证可行的取数路径 | **转存到自己网盘 + 开放 API 下载**：① 浏览器登录 pan.baidu.com，打开分享链接（提取码 gdq6），把 `SWDD.zip`「保存到我的网盘」的 `/bysj_datasets/`；② `python fetch_external_datasets.py --dataset swdd --via-netdisk --baidu-cookie-file data/external/.baidu_cookie`。<br>依据（2026-10-24 对照实测）：`rest/2.0/xpan/file?method=download` **带 BDUSS → 31066 file does not exist**（用户识别成功、文件未转存），**不带 → 31045 user not exists** —— 即下载接口认 BDUSS，只差文件已转存。<br>⚠️ 单 BDUSS 仅被开放 API 接受（`xpan/nas?method=uinfo` 返回 errno 0、账号 156\*\*\*\*\*361）；网页端接口（`api/sharedownload`、`api/gettemplatevariable`、`share/list` 带 Cookie）一律 errno -6/-9，需完整 Cookie 组（BAIDUID/STOKEN 等） |
| 手动步骤 | 首选上行的「转存 + --via-netdisk」；兜底：浏览器手动下载 `SWDD.zip`（861,645,574 B）放入 `data/external/swdd/` |
| 拟用于何种评估 | 大规模中文语料 + **症状级标签**（补「无逐条目 PHQ 标注」缺口）；注意其标签为规则/自报级，与临床级（CMDC/CNSD）分层引用 |

## 12. WU3D（微博用户抑郁检测数据集）— 本轮新增，待取

| 字段 | 值 |
|---|---|
| 名称 | Weibo User Depression Detection Dataset（WU3D） |
| 仓内路径 | 未落盘（待取后入 `data/external/wu3d/`） |
| 来源 | GitHub `aidenwang9867/Weibo-User-Depression-Detection-Dataset`（arXiv:2008.11708）；百度网盘提取码 yar1（分享码 `10xItuplkTNMmJdOEGBiXPw`） |
| 规模 / 标签 | 10,000+ 抑郁用户 + 20,000+ 对照；论文称标签经专业人员审核；JSON（depressed.json / normal.json） |
| 许可 | 原仓库未附 LICENSE（研究用途） |
| 是否已用于训练 | **否** |
| 受阻原因（实测） | 同 §11（百度分享直链风控，全 UA×clienttype 矩阵一致） |
| 手动步骤 | 同 §11：浏览器转存到自己网盘 `/bysj_datasets/WU3D.zip` 后 `--via-netdisk` 拉取；或浏览器手动下载 |
| 拟用于何种评估 | SWDD 的扩量备选；两库用户可能同源（均为微博爬取），并用时须查重 |

## 13. eRisk 2021（CLEF 早筛任务）— 本轮新增，待取

| 字段 | 值 |
|---|---|
| 名称 | eRisk 2021（Early Risk Prediction on the Internet） |
| 仓内路径 | 未落盘（待取后入 `data/external/erisk2021/`） |
| 来源 | https://erisk.irlab.org/2021/index.html（Parapar et al., CLEF 2021） |
| 规模 / 标签 | Reddit 170 用户；**BDI-II 逐题作答 + 分数 + 严重度带**；早筛任务（按发文时序） |
| 许可 | DUA 表单签署后发放 |
| 是否已用于训练 | **否** |
| 受阻原因（实测） | erisk.irlab.org 本机不可达（连接失败） |
| 手动步骤 | 网站注册并签署 Usage Agreement，按邮件指引下载 |
| 拟用于何种评估 | **英文对照实验**（BDI-II 逐题标签可与 PHQ-9 条目口径互参）；非中文场景主力 |

## 14. DepInter-CN（中文临床访谈）— 本轮新增，待申请

| 字段 | 值 |
|---|---|
| 名称 | DepInter-CN |
| 仓内路径 | 未落盘（待取后入 `data/external/depinter-cn/`） |
| 来源 | Research Square 预印本 rs-9258754（2025，dx.doi.org/10.21203/rs.3.rs-9258754/v1） |
| 规模 / 标签 | 50 被试（25 抑郁 / 25 对照）/ 450 访谈单元；M.I.N.I. + PHQ-9 双量表；9 问标准化协议 |
| 许可 | 预印本，未见公开托管 |
| 是否已用于训练 | **否** |
| 受阻原因 | 数据未公开托管（论文预印本阶段） |
| 手动步骤 | 经论文通讯作者渠道申请 |
| 拟用于何种评估 | 中文**访谈场景**外部验证（与 CMDC 的访谈结构差异可作方法对照） |

## 15. 中文文本抑郁检测数据集（IEEE Dataport zsfc-av84）— 本轮新增，待取

| 字段 | 值 |
|---|---|
| 名称 | Text-based depression detection dataset (Chinese) |
| 仓内路径 | 未落盘（待取后入 `data/external/zsfc-av84/`） |
| 来源 | IEEE DataPort（doi:10.21227/zsfc-av84；Gu, Zhang, Jia, Ni, 2023） |
| 规模 / 标签 | 31 名确诊抑郁 + 33 健康对照；医院伦理审批 + 知情同意；音频（16kHz）+ 文本转写 + PHQ-9 分数 |
| 许可 | IEEE DataPort 开放获取（需账号） |
| 是否已用于训练 | **否** |
| 受阻原因（实测） | IEEE DataPort 下载需账号登录 |
| 手动步骤 | 注册/登录 IEEE DataPort 后下载 |
| 拟用于何种评估 | **小样本高纯度**外部验证（临床确诊标签）；样本量小，只作辅助证据 |
