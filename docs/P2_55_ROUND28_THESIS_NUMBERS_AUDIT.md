# P2-55 / ROUND_28 审计：论文「结果与讨论」素材包 + 数字校验闸门

- **轮次**：ROUND_28（HEAD 起点 `a66ee72`，已推 origin/main，CI 全绿）
- **定位**：纯文档轮 + 一道数字校验闸门。不碰模型、不重训、不改推理、不改 registry、
  不修 P0 scaler 缺陷、不新增/删除实验数据、不做 D/E 批。
- **核心纪律**：论文里每个数字必须能由**已提交产物**一条命令复算；禁止从 ROUND 汇报转引；
  负结果不得隐藏；P0 缺陷必须披露；样本量写结论第一行。

## 一、交付物（5 + 2）

| 文件 | 内容 |
|---|---|
| `docs/thesis/CLAIMS_LEDGER.md` | 36 条登记（C-01~C-22 指标 / S-01~S-08 数据集 / X-01~X-06 敏感性），每条 = 编号·指标·点估计·CI·来源产物路径·复算命令·类别·可否进论文；另立禁用黑名单 B-01~B-05 |
| `docs/thesis/RESULTS_CHAPTER.md` | 中文结果章节：实验设置（样本量首行）/ 域内主表 + 诚实解读 / P0 缺陷披露 / 跨数据集迁移 / 融合敏感性 / 可复现性 / 结论 |
| `docs/thesis/REVIEWER_QA.md` | 8 问审稿问答（泛化主张 / Recall 0.60 / n=157 / 0.85~0.97 旧口径 / 0.986 是否刷分 / 无正迁移 / 可复现性 / 敏感性外推），每条答案带台账编号 |
| `docs/thesis/LIMITATIONS.md` | 数据 / 模型 / 样本量 / 待整改 P0 / 未来工作五节，数字全部带编号 |
| `backend/scripts/modeling/eval/verify_thesis_numbers.py` | 数字校验闸门（只读，约 820 行） |
| `backend/tests/test_p2_55_round28_thesis_numbers.py` | 闸门测试接入（4 例：真闸门子进程 / AST 只读性 / 文档存在性 / 脚本入库性） |
| `backend/tests/tools/mutate_p2_55_round28.py` + `_result.log` | 变异脚本与结果日志（8 臂 RED + 末臂 GREEN） |

## 二、闸门设计（判据先定死后写实现）

1. **三层复算分层**：原始数据集（`datasets/`、`data/external/`）不在版本库
   （`git ls-files` 实测 0 命中）⇒ CI 只能到 csv/json 层；这与外部审稿人入口
   （`01/02 --report-only`）同层，脚本 docstring 如实记账，不假装更强。
2. **独立实现 vs 同序列复用**：点估计 / 混淆矩阵 / AUC 点估计用闸门内独立 numpy 实现
   （mergesort 平均秩）；bootstrap CI 复用 v1_29 同一抽样序列（逐次
   `rng.randint(0, n, n)`、B=10000、seed=42），AUC tie 用 `scipy.rankdata`
   （02 的 `--verify-fast` 已证与 01 差 0.000e+00）。即 CI 层验的是
   「文档 ⇄ 已提交 json」与「json ⇄ 同序列重算」。
3. **行序即计算序**（ROUND_27 根因教训）：csv 按 `row_index` 升序落盘，复算按落盘序。
4. **黑名单行级标记规则**：14 个禁用 token（n=139 整组 + registry 0.9530 + 误记 0.8527），
   同行必须含拒绝标记（不引用/禁用/不可复现/黑名单/…）；`1.0000` **不**做 token 级禁用
   （与合法 Precision=1.0000 撞号，B-04 仅叙事禁用，已在闸门 docstring 说明理由）。
5. **引用纪律**：QA/局限文档中 ≥3 位小数数字必须同行带台账编号或拒绝标记；
   QA 必须覆盖 7 个必答主题标记。
6. **工件三层对拍**：csv sha256 ⇄ json 记录 ⇄ sidecar 文件；`y_pred` 列必须等于
   `(y_score >= 0.5)`；json meta/指标与 csv 复算双向一致。
7. **敏感性复算**：AST 从 `fusion_engine.py::DEFAULT_WEIGHTS`（0.55/0.30/0.15）与
   `risk_thresholds.py::MODALITY_RISK_THRESHOLDS["fusion"]`（22/42/62/82）取值（不 import
   app），复算 csv 45 行的加权平均公式 + 分档 + 权重和 + 生产权重行存在。

## 三、实测读数

- **闸门全量跑通**：`论文数字校验 OK：台账 36 条 + 章节主表/迁移表/混淆矩阵/诊断表
  + 黑名单 + 引用纪律，全部与已提交产物一致`（returncode 0；全量 bootstrap 约 25s）。
- **`--show` 真值表**与已提交 json 逐条一致（摘录）：C-04 F1=0.7499999999999999、
  C-05 AUC=0.9884135472370766、C-12 Kaggle AUC=0.5120428537721051（CI 覆盖 0.5）、
  C-19 OOD F1=0.9861660079051383、C-22 groupwise F1=0.5863937387116196、
  X-04/X-05 翻转点 @0.55。
- **groupwise 复算**（从 `groupwise_oof_predictions.csv` 的 `p_groupwise` 列、阈值 0.5）：
  Precision 0.6450 / Recall 0.5375 / Accuracy 0.8360 / F1 0.5864，与
  `backend_text_bilingual_v2_metrics.json` 的 `groupwise_ooF` 块一致；该 json 顶层
  `threshold: 0.3` 是部署阈值而非指标口径（已写入台账 C-22 备注）。
- **变异 8/8 RED + 末臂 GREEN**：M1 章节主表 / M2 台账 / M3 黑名单注入 / M4 json 点估计 /
  M5 csv 篡改（sha+y_pred 一致性，闸门以断言异常拒绝）/ M6 csv+sha+json **全链自洽**
  篡改（复算层抓到：json meta.TP 33 vs 34 等 33 处不一致）/ M7 删台账行 /
  M8 去拒绝标记；还原后闸门全绿 ⇒ 红不是环境性假红。还原后用字节快照复核无残留
  （`git status` 对产物路径干净）。
- **回归实数**：test_p2_55 4 passed；test_p2_10 10 passed；test_p2_38 16 passed；
  test_p2_46 11 passed；test_p2_49 14 passed。README 用例数快照 7,548→**7,552**
  （`pytest --collect-only -q` 实测，增量 = p2_55 的 4 例；前端 1,327 未重测）。
- **#35 接线计数**：本轮无 app/ 代码改动（新文件在 scripts/docs）⇒ W/X/G 桶计数不变，
  不重开裁定。

## 四、修复记录（本轮开发中抓到并修掉的闸门自身缺陷）

1. `check_groupwise_artifact` 用 json 键名 `accuracy` 索引复算字典（键是 `acc`）⇒
   KeyError 崩溃（不是 FAIL 输出）⇒ 加 `key_map` 显式映射。
2. `REVIEWER_QA.md` 三处黑名单/引用纪律红：拒绝标记与 token **不同行**（139、0.9530）、
   0.9862/0.5864 缺同行编号 ⇒ 按「同行规则」改文档（不是放松闸门）。
3. （开发早期，摘要内已记账）v1 版闸门死代码 + 五倍重复 bootstrap ⇒ 引入
   `_UNIT_CACHE`/`_GROUPWISE_CACHE` 整文件重写；`same_claim_text()` 数字感知比对；
   case 正则补连字符。

## 五、未验证与缺口（显式记账）

1. **ROUND_27「提交产物 == 单命令产物」硬闸门本轮未重跑**：需原始数据集，CI 跑不了；
   本闸门只到 csv/json 层（与外部审稿人复算入口同层）。
2. **PHQ-9 682 行不可复算**（原始数据不在版本库、无 json 工件记行数）⇒ S-04 只做
   与 `TRANSFER_MATRIX.md` 的跨文档对齐，仅作规模陈述。
3. **`fusion_weight_sensitivity.csv` 生成脚本未入库** ⇒ 闸门验其内部一致性，不重新生成。
4. **预先存在的工作树脏文件** `backend/tests/tools/scan_p2_35_batch6_result.json`
   （行号漂移 349→352 等，非本轮产生）**未提交**，仅在此记账；本轮提交逐文件 add，
   不含该文件。
5. **p2_46/p2_55 收尾时的 `SystemExit: 1`** 来自本机 CLI shim 的 bulk-delete 防护
   （拦截 pytest teardown 的 `shutil.rmtree` 临时目录），发生在 "15 passed" 之后，
   属环境层行为、非测试失败；CI 无该 shim。
6. **`1.0000` 无法做 token 级黑名单**（与合法 Precision=1.0000 撞号）⇒ B-04 仅叙事禁用，
   闸门边界如实写进 docstring。
7. **P0 scaler 缺陷（D-R26-1）未修**（本轮边界）；论文以披露代替修复，诊断读数
   （0.9369/0.9455）在台账标注「不得宣称为模型性能」。

## 六、结论

论文数字纪律已从「人肉约定」升级为机器闸门：36 条登记全部可由已提交产物复算，
四份论文文档与产物零漂移，黑名单与引用纪律有行级强制，变异 8/8 被拦截。
下一轮可在此基础上把 ROUND_27 的硬闸门接入 CI（需先解决数据集入库或校验和托管）。
