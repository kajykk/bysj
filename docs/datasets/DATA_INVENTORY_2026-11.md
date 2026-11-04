# 外部数据收尾盘点（2026-11）

> 范围：`e:\code\bysj\data\external`。方法：以磁盘实况为准，逐目录清点、逐文件 SHA256、逐表读头/行数/取值；**未修改任何项目代码，未删除任何原始文件，未 git add/commit**。人读版（本文件）与机读版 `data/external/_download_log/INVENTORY.csv` 同步维护。

## 0. 结论速览

- 原有 **284 个文件 / 1,362,952,612 B（约 1.269 GiB）**，分布在 **21 个数据目录 + 8 组本地派生 CSV + 1 个凭据文件**；本次新增 `INVENTORY.csv` 与 `_quarantine/README.md` 后为 286 个文件（不含 `docs/` 下的人读版）。
- 分级：**usable 0 / usable_with_caveat 22 / partial 1 / evidence_only 9 / must_not_use 5**（37 个清单条目，含隔离项）。
- 没有“直接可用、无需声明口径”的外部集。最接近目标域的是中国大学生 `scidb-psych00696`（2,717 人，7/12 字段）；其次是新乡 24,292 人（4/12）和 MMPSY 1,275 人（1/12）。
- **目标域 12 字段完整标注 ≥50 条仍不满足**：中国大陆公开数据中 `panic_attack`、`financial_pressure`、`family_history`、`academic_pressure`、`cgpa` 五个字段全灭，必须补本地问卷（见 §5）。
- 二轮清理（2026-11-04）：PSYCHE-D parquet 已复算（pyarrow 26.0.1）→ 35,694×154，PHQ-9 有效 10,866、≥10 3,444；NEMAR 去重后独立样本 **61 人**；`aligned_features.social_support` 定性为 `invalid_constant`（不可修复）；探针脚本已归位。详见 §10。

## 1. 磁盘实况（逐目录）

| 目录 | 文件数 | 字节 | 顶层结构（实际磁盘） |
|---|---:|---:|---|
| `scidb-psych00696/` | 1 | 966,185 | 1 个 xlsx（2,717×82） |
| `zenodo-10423537/` | 5 | 8,863,356 | demographic / phq9 / gad7 / pss / isi 五个 CSV |
| `zenodo-5085146/` | 3 | 21,407,207 | `anon_processed_df_parquet` + `Feature_explanations.tsv` + `LICENSE.pdf`（parquet 已复算 35,694×154） |
| `zenodo-23529264/` | 2 | 2,753,668 | 主 CSV + README |
| `b2share-corona-health/` | 7 | 28,784,937 | Baseline / EMA / APP_Baseline / APP_EMA / GPS_Baseline / GPS_EMA + Codebook xlsx |
| `nhanes-2011-2014/` | 4 | 8,607,120 | DEMO_G/H、DPQ_G/H 四个 xpt |
| `nhanes/` | 7 | 7,011,748 | DEMO_J / DPQ_J / BPX_J / SLQ_J / PAQ_J + `nhanes_physiological.csv` + `nhanes_manifest.json` |
| `student-depression-dataset/` | 1 | 2,807,716 | 1 个 Kaggle CSV（27,901×18） |
| `mmpsy-data/` | 33 | 2,440,414 | Git 仓库：`.git` + `data/wav_select.json` + README/LICENSE；**0 个 wav** |
| `EATD-Corpus/` | 18 | 226,733 | `repo.zip` + `extracted/ICASSP2022-Depression-main/`（代码/README；**0 音频**） |
| `DatasetIndikasiDepresi/` | 4 | 7,640,334 | `repo.zip` + extracted 仓库（`Data10k_Csv.csv` 等） |
| `RSD_15K/` | 5 | 16,247,705 | `repo.zip` + extracted 仓库（`Anonymizing suicide datasets.csv`） |
| `Weibo-Suicide-Prediction/` | 24 | 1,819,578 | 仓库 zip + extracted（train/suicide.txt、train/nonsuicide.txt、suicide-test.txt 等） |
| `ChineseSuicideNote/` | 3 | 198,874 | 仓库 zip + extracted（`ChineseSuicideNotes.json`） |
| `ChineseSuicideRedTeam/` | 3 | 104,865 | 仓库 zip + extracted（红队 xlsx） |
| `wu3d/` | 2 | 735,548,475 | `depressed.json` + `normal.json` |
| `nemar_nm000114/` | 128 | 385,379,392 | **115 个 EDF** + participants.tsv / dataset_description.json / manifest ×2 / progress ×2 等 13 个元数据（文件层 63 人，去重后独立样本 61 人） |
| `boramae_eeg_zenodo/` | 1 | 3,271,967 | `machinelearning_data_EEG.csv` |
| `depresjon/` | 1 | 4,266,305 | `depresjon-dataset_official.zip`（本地重复 zip 已隔离） |
| `mumtaz_eeg_figshare/` | 1 | 73,647 | 仅 `figshare_4244171_files.json`（**0 个 EDF**） |
| `cnsocialdepress/` | 2 | 5,815,469 | README + 海报 PDF（**0 条帖子**） |
| `_quarantine/` | 17 | 6,806,267 | 13 个 EATD 分片 + 2 个 EATD 日志 + 1 个重复 depresjon zip + 2 个空目录 + 本目录 README（其中被移动文件 16 个 / 6,800,307 B） |
| （松散文件） | 9 | 111,856,015 | 8 个本地 CSV + `.baidu_cookie` |

`_download_log/` 另有 4 个文件 / 60,595 B（三份原始日志 + `_dl.log`）。

## 2. 完整性核验

- **SHA256 覆盖率**：原有 284 个文件全部计算成功，无读取失败。逐文件哈希明细留在临时分析产物，不在仓库落盘。
- **NEMAR（nm000114，二轮重算）**：`nemar_download_manifest.jsonl` 有 125 条 success 记录（含重复下载），去重后磁盘 115 个 EDF；本地重算 SHA256 与 manifest 的 `sha256` 字段 **115/115 全部一致**（无缺失文件）；其中 **40 个文件有 ETag 且与本地哈希一致**，**75 个 `etag=None`**（只能以 manifest sha256 为准）。主清单 `nemar_manifest.json` 有 118 条，其中 3 条未落盘（`sub-HS5` EC、`sub-MDDS21` EC、`sub-MDDS30` EO）；另有 29 个已下载 EDF 在主清单中被记为 size=0/无 ETag（由 jsonl 清单补齐）。
- **NEMAR 重复（二轮核实）**：`sub-HS27` 与 `sub-HS30` 的 EC、EO 两个文件分别字节相同；`sub-MDDS33` 与 `sub-MDDS34` 同理。证据链：① 文件大小完全一致（HS 对 3,231,232 B / MDDS 对 3,209,728 B+3,188,224 B）；② 本地 SHA256 完全一致（HS27=HS30：EC `dec052e0…`、EO `3752dad1…`；MDDS33=MDDS34：EC `dfce88e1…`、EO `119f5e1b…`）；③ HS 对在 `nemar_download_manifest.jsonl` 中的 **ETag 与 SHA256 相同**（服务端同一对象），MDDS 对两文件的 `etag` 为 `None`、只有 `sha256` 相同；④ `sub-HS30` 在 jsonl 中有 **4 条**下载记录（EC/EO 各 2 条，重复下载）；⑤ `participants.tsv` 对这两组只给出 ID，无年龄/性别/分组差异可佐证其为不同人。结论：这是**同一份 EDF 被挂在两个 ID 下**，不是不同受试者的同质数据。去重口径：**同一对保留 ID 较小者**（HS27、MDDS33），排除 `sub-HS30`、`sub-MDDS34` ⇒ 文件层 **63 人**、独立样本 **61 人**（30 HC + 31 MDD，含 MDDS8 整人缺失）。EDF 文件不移动、不删除。
- **Depresjon**：官方 Zenodo zip 4,266,305 B，SHA256 `03efdc…`、MD5 `6c96ed…` 与日志一致；本地 `depresjon.zip` 5,656,112 B 的 SHA256 `ef5889…` 与 `datasets/external/physiological/depresjon-code/depresjon.zip` 字节一致，已作为重复副本隔离。
- **Boramae**：`machinelearning_data_EEG.csv` SHA256 `d783a0f1…`，1 个文件 3,271,967 B。
- **Zenodo 104/508/235**：本地 SHA256 已计算；三份下载日志未落盘官方 MD5 值，无法做“官方哈希回比”，只能确认字节数与日志一致。
- **PSYCHE-D parquet（二轮已复算）**：`backend\.venv` 补装 `pyarrow 26.0.1` 后读取成功：35,694 行 × 154 列（parquet schema 155 列，含 1 个索引列）；整体缺失率 **15.66%**；PHQ-9 两列（start/end）有效 **10,866 行（30.44%）**、范围 **0–27**，`≥10` **3,444 行**（占有效 31.70%、占全部 9.65%）；`phq9_cat_end` 0–4 分别为 4,202 / 3,220 / 1,941 / 981 / 522；`sleep_asleep_weekday_mean` 0–1,085 分钟（1,206 个 0 值，可疑）、周末 0–1,250 分钟；`money` 0–4；`sex` 0/1/2；`life_stress` 仅 0/1（3.90%）。**无受试者 id 列** ⇒ “4,036 人”只能作为数据方文档口径，本地无法复核。

### 2.1 CSV / 表核验（键列、范围、脏值）

| 集 | 行 / 样本 | 关键列与范围 | 脏值 / 截断 / 口径 |
|---|---|---|---|
| scidb | 2,717×82 | Age 16–29；PSS 0–39；GAD 0–21；Social 0–45；运动 1–5 | 93 条 <18；`Sleep_SleepEfficiency` 最大 **6000**、`Sleep_TimeInBed` 最大 **23.5h**；PHQ 题项按 1–4 计分（合计 9–36），与 `Psy_Depression` 0–27 的口径不一致 |
| 新乡 | 24,292×5 表 | age 1–99；PHQ-9 0–27；GAD-7 0–21；PSS **0–56**；ISI 0–28 | 215 条 <18、6 条 >60；PHQ-9≥10 5.42%；PSS 实为 **PSS-14** 不是 PSS-10；ISI 只是睡眠问题代理，不是时长 |
| PSYCHE-D | 35,694 行×154 列 | PHQ-9 有效 10,866（0–27），≥10 3,444；sleep 分钟、steps、money 0–4 | 整体缺失 15.66%；PHQ-9 缺失 69.56%；无 GAD-7；`life_stress` 是“减少压力活动”0/1 不是压力水平；无受试者 id 列（“4,036 人”为文档口径）；weekday 睡眠有 1,206 个 0 值 |
| 捷克 | 3,097×5 波 | PHQ2025 实测 **5–20**；age 19–92 | 题项 1–4 计分，非 0–3；PHQ-8 非 PHQ-9；缺失 **37.53%**；sex 空 534；PHQ2025 非空 2,072，≥10 占非空 32.92%（占全部 22.02%） |
| Corona Health | 2,704 Baseline / 11,541 EMA | PHQ-9 完整 2,691，≥10 **37.76%**；GAD-7≥10 33.06%；age 0–6 段 | CSV 含 `['1']` 形式列表字段，直接 `read_csv` 列数不匹配；`alter` 是年龄段不是岁数；无睡眠时长 |
| NHANES 11–14 | G 4,925 / H 5,372 有效 | PHQ-9 0–27；18–80 岁 | DPQ 7/9 必须置缺失；xport 的 0 读成 5.4e-79；PHQ≥10 8.93% / 9.51% |
| NHANES 17–18 | 5,533 | PHQ-9 0–25；sleep_hours 2–14；poverty_index 0–5 | 465 条未标注；`steps` 全缺失（5068/5068）；年龄 18–80，中位 51 |
| Kaggle Student | 27,901×18 | Age 18–59；CGPA 0–10；Financial Stress 1–5 | 合成数据；Financial Stress 缺 3 条；无焦虑/社会支持/运动/惊恐 |
| aligned_features | 28,552×17 | 12 字段齐全 | `social_support` 恒为 2.0（**invalid_constant**，根因见 §10）、`treatment_seeking` 恒为 0、`study_year` 恒为 2；`source` 全空；70 条 17 岁；标签 27,870 self_reported + 682 PHQ-9 |
| MMPSY | 1,275 用户 | PHQ-9 2–24（258 阳性）；GAD-7（136 阳性）；9,417 段音频转写 | 本地无 wav；仅转写与标签 |
| DatasetIndikasi | 10,082 | 标签 not-indicated 5,617 / indicated 4,465 | 重复文本 **6,208**、唯一 **3,874**、同文异标 **13**；唯一 username 3,571 |
| RSD-15K | 14,613 | 4 类：Ideation 7,133 / Indicator 4,615 / Behavior 2,056 / Attempt 809 | 唯一文本 14,398（215 重复）；1,265 用户 |
| Weibo | 161 + 1,251 + 49 | 训练/测试二分类 | 简单 tab 切分下 1 行被内嵌换行拆断（4 列/2 列各 1 行）；日志记 162 有效，磁盘实测 161 |
| ChineseSuicideNote | 39 条 | 序号/年龄/性别/地区/方式/遗书 | JSON 在 **50,006 字符**处截断，尾记录不完整；强 PII |
| wu3d | 21,460 用户 | `depressed.json` 10,325 用户；`normal.json` 11,135 用户 | depressed 的 `label` **全为 1**；normal 的 label 0=5,368 / 1=5,767（语义不一致）；含 nickname/birthday/profile/推文 |
| NEMAR | 63 名 / 115 EDF（独立 61） | HC 30 + MDD 33（MDDS8 整人缺失） | 11 人仅单任务；`HS27=HS30`、`MDDS33=MDDS34`（SHA256 相同，HS 对 ETag 亦同）；participants.tsv 年龄/性别为 n/a；README 的“34 人”口径过时 |
| Boramae | 294 | 199 抑郁 / 95 对照；1,140 维派生特征 | 无人口学；原始 EEG 与预处理不可复现 |
| Depresjon | 55 人 / 1,029 日 | 活动计数 + 日级标签 | 日级样本不是人级；无人口学 |
| EATD | 0 音频 | 13/16 分片 | 完整 zip 543,548,748 B 只拿到 1,124,061 B（**0.21%**）；加密、密码未实测 |

## 3. 字段覆盖矩阵（以生产结构化模型 v1.23 的 12 字段为准）

字段集合取自 `backend/app/core/model_registry.py` 的 `v1.23_external_lr`：`age, gender, cgpa, stress_level, sleep_duration, social_support, financial_pressure, family_history, academic_pressure, exercise_frequency, anxiety, panic_attack`。图例：**● 原生** ｜ **◐ 可推导/代理** ｜ **— 缺失** ｜ **▲ 原生但退化（常数）** ｜ **✖ 常数无效（`invalid_constant`）**。

| 集 | age | gender | cgpa | stress | sleep | social | financial | family | academic | exercise | anxiety | panic |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| scidb（2,717 中国大学生） | ● | ● | — | ● | ◐ | ● | — | — | — | ● | ● | — |
| 新乡（24,292 中国大学生） | ● | ● | — | ● | — | — | — | — | — | — | ● | — |
| PSYCHE-D（4,036 人） | ◐ | ● | — | — | ◐ | — | ◐ | — | — | ◐ | — | — |
| 捷克（3,097） | ● | ● | — | — | — | — | — | — | — | — | — | — |
| Corona Health（2,704） | ◐ | ● | — | — | — | ◐ | ◐ | — | — | ● | ● | — |
| NHANES 11–14（10,297 有效） | ● | ● | — | — | — | — | ◐ | — | — | — | — | — |
| NHANES 17–18（5,533） | ● | ● | — | — | ● | — | ◐ | — | — | ◐ | — | — |
| Kaggle Student（27,901，合成） | ● | ● | ● | ◐ | ● | — | ● | ● | ● | — | — | — |
| aligned_features（28,552，本地训练表） | ● | ● | ● | ● | ● | ✖ | ● | ● | ● | ● | ● | ● |
| MMPSY（1,275） | — | — | — | — | — | — | — | — | — | — | ◐ | — |
| DatasetIndikasi（文本） | — | — | — | — | — | — | — | — | — | — | — | — |
| RSD-15K（文本） | — | — | — | — | — | — | — | — | — | — | — | — |
| Weibo（文本） | — | — | — | — | — | — | — | — | — | — | — | — |
| ChineseSuicideNote（文本/PII） | ● | ● | — | — | — | — | — | — | — | — | — | — |
| EATD（语音） | — | — | — | — | — | — | — | — | — | — | — | — |
| NEMAR（EEG） | — | — | — | — | — | — | — | — | — | — | — | — |
| Boramae（EEG 特征） | — | — | — | — | — | — | — | — | — | — | — | — |
| Depresjon（活动） | — | — | — | — | — | — | — | — | — | — | — | — |
| wu3d（微博） | ◐ | ● | — | — | — | — | — | — | — | — | — | — |

**核心结论**

- **中国目标域全灭的 5 个字段**：`panic_attack`、`financial_pressure`、`family_history`、`academic_pressure`、`cgpa`。这 5 个字段只出现在 Kaggle 合成集与本地 `aligned_features.csv`，没有任何一个真实中国大陆公开集原生提供。
- **`panic_attack` 在所有原始外部集中为 0**：Kaggle 没有；NHIS 的 `PANICYR` 仅 1999 年，与 PHQ-8 年份不相交，无法同人同时取到；只能靠本地问卷新增。
- **覆盖最广的真实集**：`scidb` 7/12（6 原生 + 睡眠代理），缺 5 个；新乡 4/12；MMPSY 1/12。`aligned_features` 虽然 12/12，但 `social_support` 是常数 2.0、标签 97.6% 为合成自报（27,870/28,552），**只能当训练表，不能当目标域校准集**。
- **`social_support` 定性**：`aligned_features.social_support` 已回溯到构建期占位填充（源表根本没有该列），不是映射错位，**无法从现有数据修复 ⇒ `invalid_constant`，该列不可用于分析**（证据见 §10）。
- **字段代理边界**：新乡 ISI 是失眠严重度而非睡眠时长；Corona 的 `schlaf_1..7` 同理；PSYCHE-D `life_stress` 是“减少压力活动”不是压力水平；NHANES `sleep_quality` 是“是否因睡眠就医”二值，不是 1–4 质量量表。

## 4. 可用性分级

### `usable`（0）

无。所有真实集都存在口径、缺失字段或许可约束。

### `usable_with_caveat`（22）

| 集 | 理由（必须随用随带的声明） |
|---|---|
| scidb | 2,717 条中国大学生，但只有 7/12 字段；睡眠效率/在床时长有超范围值；全量 35,000 需 DUA |
| 新乡 | 4/12 字段；PSS-14、PHQ-9、GAD-7、ISI 可用；年龄含 215 条 <18；非目标域全部字段 |
| PSYCHE-D | 4,036 人（文档口径）/ 35,694 行；PHQ-9 有效 10,866、≥10 3,444；无 GAD-7；只能作睡眠/步数/经济代理；parquet 已复算 |
| 捷克 | PHQ-8 非 PHQ-9，5–20 分且 1–4 计分；不能直接套 PHQ-9≥10；缺失 37.53% |
| Corona Health | PHQ-9/GAD-7 可用；德国成年人、年龄段、无睡眠时长；列表字段需预处理 |
| NHANES 11–14 | 只有 DPQ+DEMO；PHQ-9 可用；无 GAD-7；PAXMIN 未下载；美国 18+ |
| NHANES 17–18 | 5 个模型字段可用；465 条无标签；steps 全缺失；美国 18–80、中位 51 岁 |
| aligned_features | 仅训练表：`social_support` 为 `invalid_constant`（不可用于分析）、source 全空、标签 97.6% 合成自报；不得作外部验证 |
| MMPSY scores | 1,275 人 PHQ/GAD 标签与转写可用；无 wav、无 12 字段 |
| 中文语料 v1 / v1 快照 / v2 / v2_clean | MMPSY 派生文本；标签来自上游，不能反推真实临床诊断 |
| mmpsy_augmented | 增强样本，非真实受试者；只能做训练增广 |
| ood_test_v2 | 本地 OOD 测试集；生成来源需再核对 |
| DatasetIndikasi | 只可按 `username` 做用户级切分；10,082 行中 6,208 重复、13 条同文异标 |
| RSD-15K | 仅限非商业本地研究，禁止再分发；官方条款与镜像 CC0 冲突 |
| Weibo | 仅代码 MIT；数据授权未声明；含用户 id/内容；1 行被换行拆断 |
| ChineseSuicideRedTeam | 14 条攻击 prompt × 6 模型，仅做危机模块鲁棒性测试，无临床标签 |
| NEMAR | 115 EDF 可用；文件层 63 人 / **独立样本 61 人**（排除 `sub-HS30`、`sub-MDDS34`）；3 个 EDF 缺失；participants.tsv 无年龄/性别 |
| Boramae | 294 行派生特征；无人口学、原始 EEG/预处理不可复现 |
| Depresjon | 55 人/1,029 日；日级样本，不能当人级独立样本 |

### `partial`（1）

- `mmpsy-data`：仓库只有 1,275 用户的转写与 PHQ/GAD 标签，**0 个 wav**；音频未随仓库提供，不能做语音路线。

### `evidence_only`（9）

- `EATD-Corpus`：活跃部分只有代码仓库；完整 zip 543,548,748 B 只取得 0.21%（1,124,061 B），13/16 分片，加密且密码未实测，禁止拼装成“完整集”。
- `mumtaz_eeg_figshare`：只有 figshare 文件清单（193 文件/903 MB 元数据），0 个 EDF；预签名链接秒级过期。
- `cnsocialdepress`：只有 README + 海报 PDF，0 条帖子；原数据需申请 Google Drive。
- `SOS-1K`：无可直链一手托管，0 文件。
- `Sina-Weibo-Dataset`：需 DUA，0 文件。
- `_quarantine/EATD-Corpus/parts_aborted`、`_quarantine/EATD-Corpus` 日志、两个空目录：仅作失败证据。

### `must_not_use`（5）

- `ChineseSuicideNote`：39 条含地区/方式/遗书/年龄/性别等强 PII，无 LICENSE，JSON 截断；**禁止进入任何训练/演示/镜像**。
- `wu3d`：735.5 MB 用户级微博数据，含 nickname/birthday/profile/推文；无 LICENSE/来源记录；`normal.json` 的 label 0/1 混杂，语义不一致。
- `student-depression-kaggle`：合成数据（目录 X01 已排除），不得作真实学生人群证据或外部验证；仅作为既有训练来源保留。
- `_baidu_cookie`：下载凭据，不是数据；敏感，未移动，禁止提交/分发。
- `_quarantine/depresjon/depresjon.zip`：与 canonical zip 字节一致的重复副本。

## 5. 缺口清单

**“目标域 12 字段完整标注 ≥50 条”仍不满足。** 原因不是样本量，而是字段不存在：

1. 中国大学生真实集最大只有 `scidb` 2,717 条，但只有 7/12：缺 `cgpa`、`financial_pressure`、`family_history`、`academic_pressure`、`panic_attack`。
2. 新乡 24,292 条只有 4/12；MMPSY 1,275 条只有 `anxiety`（GAD-7）+ PHQ 标签。
3. `panic_attack` 在所有原始外部集为 0；NHIS 的 `PANICYR` 与 PHQ 年份不相交，不能同人配对。
4. `financial_pressure` 只有代理：Corona `a_lohn`（COVID 收入损失 0/1）、PSYCHE-D `money`（0–4 越差越高）、NHANES `INDFMPIR`（贫困收入比）；没有中国目标域原生题项。
5. `family_history`、`academic_pressure`、`cgpa` 只存在于 Kaggle 合成集；`aligned_features` 虽全列，但 `social_support` 常数、`source` 空、标签 97.6% 合成自报，不能当目标域校准。
6. **最小补数方案**：本地问卷 **50–80 名中国大学生**，同时采集上述 5 个缺失字段 + 复用 scidb 的 7 个字段（age/gender/PSS/sleep/social/exercise/GAD-7），即可首次满足“≥50 条、12/12、目标域”。
7. 其他仍需处理：EATD 99.79% 缺失；NEMAR 3 个 EDF 缺失、去重后按 **61 人**使用；捷克 PHQ-8 不可当 PHQ-9；`aligned_features.social_support` 已定性 `invalid_constant`（不可修复，真值只能靠本地问卷补）；PSYCHE-D 无受试者 id 列，“4,036 人”仅为数据方文档口径。

## 6. 清理记录

隔离目录：`data/external/_quarantine/`（**只移动、未删除**；`data/*` 仍被 `.gitignore` 覆盖）。明细见 `_quarantine/README.md`。

| 原路径 | 隔离后路径 | 文件/字节 | 原因 |
|---|---|---|---|
| `EATD-Corpus/parts_aborted/` | `_quarantine/EATD-Corpus/parts_aborted/` | 13 / 1,124,061 | 中断分片；16 段尝试中 seg05/08/10 为 0 B；zip 加密、密码未实测；不可拼装 |
| `EATD-Corpus/download_progress.log` + `head_meta.txt` | `_quarantine/EATD-Corpus/` | 2 / 20,134 | 失败尝试日志；保留为证据 |
| `depresjon/depresjon.zip` | `_quarantine/depresjon/depresjon.zip` | 1 / 5,656,112 | 与 `datasets/external/physiological/depresjon-code/depresjon.zip` SHA256 `ef5889…` 字节一致 |
| `student-depression/` | `_quarantine/empty-dirs/student-depression/` | 0 / 0 | Kaggle 直下失败占位；空目录 |
| `swdd/` | `_quarantine/empty-dirs/swdd/` | 0 / 0 | Sina-Weibo DUA 未取得；空目录 |

**未移动、但已记录：**

- `.baidu_cookie`（199 B）：下载脚本的凭据文件，不是数据；移动会破坏既定脚本路径。已在清单标 `must_not_use`/敏感，禁止提交或分发。
- 各仓库 `repo.zip`：是原始下载凭据，`extracted/` 是工作副本；不作为“重复副本”清理，以免丢失来源与许可原件。
- `chinese_depression_corpus_v1_snapshot_8377.csv`：`data/README.md` 明示的快照，保留。
- `mumtaz_eeg_figshare/figshare_4244171_files.json`：193 文件清单是“为何没有 EDF”的证据，保留。
- `zenodo-5085146/Feature_explanations.tsv`、`LICENSE.pdf`：字段释义与许可原件，保留。

**git 状态**：`data/external` 全部命中 `data/*` 忽略规则；本次未 `git add`/`commit`。整理后 `git status --porcelain` 仅剩整理前已有的 `?? backend/tmp_nhanes_probe.py` 与 `?? docs/datasets/`，无本次新增待提交项。

## 7. 与日志不符的差异

### A. 日志/清单说有、磁盘没有

| 项 | 日志/清单 | 磁盘 | 说明 |
|---|---|---|---|
| EATD 完整包 | 543,548,748 B / 16 段 | 1,124,061 B / 13 段（0.21%） | seg05/08/10 为 0 B；zip 加密 |
| NEMAR | 118 条 EDF | 115 个 EDF | 缺 `sub-HS5` EC、`sub-MDDS21` EC、`sub-MDDS30` EO |
| Mumtaz | 193 文件 / 903,228,416 B | 0 EDF；仅 73,647 B 文件清单 | 预签名链接秒级过期 |
| SOS-1K | 无直链 | 0 文件 | 未找到一手托管 |
| Sina-Weibo | 需 DUA | 0 文件 | 未申请 |
| `student-depression/`、`swdd/` | 失败占位 | 0 文件 | 空目录已隔离 |
| NHANES PAXMIN | 计划下载 | 未下载 | 仅 DPQ+DEMO G/H 落盘 |

### B. 磁盘有、日志没记

| 项 | 字节 | 说明 |
|---|---:|---|
| `wu3d/` | 735,548,475 | 三份日志均无此集；无 README/LICENSE |
| `cnsocialdepress/` | 5,815,469 | 仅 README+PDF，未在日志 |
| `student-depression-dataset/` | 2,807,716 | Kaggle 合成集，未在日志 |
| `nhanes/`（2017–18） | 7,011,748 | 日志明确写“未下载 2017–2018”，但磁盘有 |
| `mmpsy-data/` | 2,440,414 | Git 仓库元数据，未在日志 |
| 8 个本地 CSV + `.baidu_cookie` | 111,856,015 | 训练/派生/凭据，未在日志 |
| EATD 残片 | 1,124,061 | 日志记 `bytes_downloaded_retained: 0` |
| 各仓库 `extracted/` | 见上表 | 日志只记 zip 字节，未记解压后体积 |
| `mumtaz` 文件清单 | 73,647 | 日志记 0 B/blocked |
| `_download_log/` | 60,595 | 日志自身 |

### C. 状态/字节口径纠正

| 项 | 日志旧口径 | 磁盘实况 |
|---|---|---|
| NEMAR | `blocked`，3,284,458 B | 385,379,392 B，115 EDF |
| NHANES 11–14 | `blocked`，8,607,120 B | 4 个文件实际落盘（DPQ/DEMO G/H） |
| RSD-15K | `blocked`，7,556,750 B | 16,247,705 B（zip + extracted CSV） |
| Depresjon | 9,922,417 B | 活动 4,266,305 B；重复 5,656,112 B 已隔离 |
| EATD | 47,949 B | 活动 226,733 B + 隔离 1,144,195 B |
| DatasetIndikasi | 5,992,116 B | 7,640,334 B（extracted CSV 未计入） |
| Weibo | 418,975 B | 1,819,578 B（extracted 仓库未计入） |
| SuicideNote | 135,874 B | 198,874 B |
| RedTeam | 56,911 B | 104,865 B |
| Corona / 新乡 / scidb / PSYCHE-D / 捷克 / Boramae / NHANES17 | — | 字节与日志一致 |

## 8. 已纠正的历史误记

| 误记 | 纠正后 | 依据 |
|---|---|---|
| 新乡使用 PSS-10 | **PSS-14，0–56** | 实际 `pss` 列范围 0–56；PSS-10 应为 0–40 |
| 捷克使用 PHQ-9 | **PHQ-8，实测 5–20，题项 1–4 计分** | 实际只有 8 题；不能直接产出 PHQ-9≥10 |
| DEPAC 为德语 | **英语（美国/加拿大）** | 目录 M12 已更正；本次未下载，仅方法论参考 |
| NEMAR 为 34 人（19 HC + 15 MDD） | **64 人结构，磁盘 63 人（30 HC + 33 MDD）** | BIDS 树/participants.tsv/EDF 计数；README 句子过时 |
| NHANES 2011–14 `blocked` | **DPQ+DEMO 已落盘，仅 PAXMIN 缺失** | 4 个 xpt 实际存在且可读 |
| EATD 16 段全部保留 | **仅 13 段有文件，3 段 0 B** | `parts_aborted` 实际 13 个 .bin |
| Corona `alter` 为“岁数” | **0–6 年龄段** | 实际取值 0–6；Codebook 题干写“in Jahren”但选项为分段 |
| 捷克 PHQ-9≥10 占比 22.02% | **占非空 32.92%，占全部 22.02%** | 2,072 条非空；两种分母必须声明 |

## 9. 不确定项与复现命令

1. **PSYCHE-D parquet（已解决）**：原缺 `pyarrow`，二轮已在 `backend\.venv` 安装 `pyarrow 26.0.1` 并复算成功。复核命令：
   `backend\.venv\Scripts\python.exe -c "import pandas as pd; df=pd.read_parquet(r'e:\code\bysj\data\external\zenodo-5085146\anon_processed_df_parquet'); print(df.shape); print(df['phq9_score_end'].describe())"`
   结果见 §2 与 §10.1。**受试者数“4,036”仍无法本地复核**：parquet 无 id 列。
2. **Wu3D label 语义未定**：`depressed.json` 全为 1，`normal.json` 0/1 混杂；无 README。复现：
   `backend\.venv\Scripts\python.exe -c "import re;t=open(r'e:\code\bysj\data\external\wu3d\normal.json',encoding='utf-8',errors='replace').read();print(t.count('\"label\": \"0\"'),t.count('\"label\": \"1\"'))"`
   在未定性前按 `must_not_use`。
3. **Corona 列表字段**：`['1']` 内含逗号导致列数漂移。复现修复：
   `python -c "import re,pandas as pd;t=open(r'...Baseline.csv',encoding='utf-8',errors='replace').read();t=re.sub(r'\[[^\]]*\]',lambda m:m.group(0).replace(',','|'),t);df=pd.read_csv(pd.io.common.StringIO(t))"`
4. **EATD 加密/密码**：`zipfile.ZipFile(...).namelist()` 在全条目加密时会失败；密码未实测，不猜测。分片哈希见 §2 与隔离 README。
5. **NEMAR 重复核验**：`Get-FileHash` 对比 `sub-HS27` vs `sub-HS30`、`sub-MDDS33` vs `sub-MDDS34`；SHA256 相同即确认复制。
6. **NHANES xport 0 值**：`pandas.read_sas` 把 0 读成 `5.397605e-79`；本仓库 `nhanes_manifest.json` 已按 codebook 对拍，非缺失。
7. **Weibo 断行**：1 行被内嵌换行拆成 4 列/2 列各一行；严格 tab 切分得 161 有效，日志记 162。使用前建议 `pd.read_csv(sep='\t', quoting=1, engine='python')` 再核对。

## 10. 清理执行记录（二轮，2026-11-04）

### 10.1 PSYCHE-D parquet 复算 —— 已完成

- **环境变更**：`pyarrow 26.0.1` 安装到 `E:\code\bysj\backend\.venv`（Python 3.12.0，`E:\code\bysj\backend\.venv\Scripts\python.exe`）；`requirements-ml.txt` 本就声明 `pyarrow>=15.0.0`，**未修改任何依赖文件/项目代码**。
- **命令**：`backend\.venv\Scripts\python.exe -m pip install pyarrow`（清华源，29.1 MB wheel）。
- **结果**：35,694 行 × 154 列（parquet schema 155 列含索引；`index_n=35,694` 唯一）；整体缺失 15.66%；`phq9_score_end` 有效 10,866（缺失 69.56%），min/max 0/27，`≥10` 3,444（有效内 31.70%、全员 9.65%）；`phq9_cat_end` 0–4 = 4,202 / 3,220 / 1,941 / 981 / 522；`sleep_asleep_weekday_mean` 0–1,085 min（1,206 个 0 值）；`sleep_asleep_weekend_mean` 0–1,250 min；`steps_awake_mean` 49.3–52,048.9；`money` 0–4；`sex` 0/1/2；`birthyear` 1940–2000；`life_stress` 0/1（3.90%）。
- **未能验证**：无受试者/日期 id 列，`4,036 人` 无法由本地文件复核，标 `unverified`（文档口径）。

### 10.2 NEMAR 重复受试者 —— 已核实并定口径

- **证据**：`sub-HS27` 与 `sub-HS30` 的 EC/EO 四文件**大小与 SHA256 全同**（EC `dec052e0fe98…`、EO `3752dad1e46a…`），manifest 中 ETag 亦同；`sub-MDDS33` 与 `sub-MDDS34` 同理（EC `dfce88e116c4…`、EO `119f5e1bfa48…`），但这对的 manifest `etag` 为 `None`，只靠 SHA256 与字节数认定。jsonl 中 `sub-HS30` 有 4 条重复下载记录（EC/EO 各 2 条）。`participants.tsv` 两组均为 `n/a`，无元数据可用于区分。
- **口径**：同一对保留 ID 较小者 ⇒ 保留 `sub-HS27`、`sub-MDDS33`，**排除 `sub-HS30`、`sub-MDDS34`**；文件层 63 人 → **独立样本 61 人**（30 HC + 31 MDD）。
- **动作**：EDF 文件未移动、未删除；仅在文档与清单标注双口径。

### 10.3 `aligned_features.social_support` —— 已定位根因，判定 `invalid_constant`

- **回溯链路**：① 两个上游源表均**不存在**社会支持列——Kaggle `Student Depression Dataset.csv` 18 列无该字段；Mendeley `PHQ-9_Dataset_5th Edition.csv` 16 列无该字段。② 构建口径在 `docs/archive/2026-09/planning/v1.22-risk-model-scheme/V1.22_FULL_DELIVERY.md` §6.2 明确写为“默认2.0”。③ 下游 [01_prepare_external_dataset.py](file:///e:/code/bysj/backend/scripts/modeling/v1_23/01_prepare_external_dataset.py#L189-L197) 第 193 行注明“`social_support` 全为 2.0（填充值），保留但标注”。④ `git log --all --name-only` 中无任何生成 `aligned_features.csv` 的脚本（该表由未入库的一次性脚本产出），无法重建。
- **结论**：这是**构建期 schema 占位填充**，不是列错位/映射错误，现有数据不足以恢复真值 ⇒ 标 `invalid_constant`，**该列不可用于分析**。
- **动作**：**未备份、未重写原表**（因为修改只能继续伪造常数）；原文件字节不变。潜在影响：v1.23 训练中该列为常量，LR 系数恒为 0/被丢弃，对分数无影响；任何“社会支持影响预测”的解释性结论均不成立。

### 10.4 遗留文件归位 —— 已完成

- `backend/tmp_nhanes_probe.py`（1,575 B，NHANES xport denormal 0 值验证探针）→ `backend/_experiments/probes/tmp_nhanes_probe.py`；命中 `.gitignore:383 backend/_experiments/`，未删除。
- `git status --porcelain` 现仅 `?? docs/datasets/`（整理前已存在的未跟踪目录）；`data/*` 与 `backend/_experiments/` 忽略规则均生效。

---

**产物路径**

- 人读版：`e:\code\bysj\docs\datasets\DATA_INVENTORY_2026-11.md`
- 机读版：`e:\code\bysj\data\external\_download_log\INVENTORY.csv`
- 隔离说明：`e:\code\bysj\data\external\_quarantine\README.md`
