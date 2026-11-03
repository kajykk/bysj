# 人群感知模型卡模板（Phase 0）

> 日期：2026-11-02
> 用途：任何进入推理链的模型，必须先按本模板登记「人群、标签、验证队列、适用范围、
> 弃权策略」；缺项的模型不得声称可用于全人群或自动决策。
> 配套：`POPULATION_EVIDENCE_MATRIX.md`（证据矩阵）、`backend/app/core/population_scope.py`
> （运行时唯一登记表）。本模板不改变任何模型产物或阈值。

## 1. 模板

```yaml
model_card:
  card_version: "2026-11-02"
  model_id: ""                     # 注册表 ID，与 MODEL_PATHS / model_registry 一致
  model_version: ""
  artifact_path: ""
  artifact_sha256: ""              # 可为空，但对外发布前必须补
  owner: ""

  population:
    population_id: ""              # 运行时 population_scope.population_id
    population_label: ""           # 人类可读人群描述
    language: ""                   # zh / en / multilingual
    age_range: ""                  # 如 "18-35"；未知写 "unknown"
    setting: ""                    # 在线自报 / 临床访谈 / 可穿戴 / 社交媒体
    inclusion: []
    exclusion: []

  label:
    definition: ""                 # 二元/多类/量表阈值，必须写明
    instrument: ""                 # PHQ-9 / PHQ-8 / CES-D / 自报 / 临床诊断
    source: ""                     # 自报 / 临床评定 / 规则生成
    alignment_check: ""            # 与目标人群标签的一致性检查结果

  validation:
    cohorts:
      - name: ""
        n: 0
        positive_rate: 0.0
        protocol: ""               # 内部切分 / groupwise OOF / 跨来源留出 / 外部
        group_isolation: ""        # 是否按 user_id / 来源分组
    metrics:
      auroc: null
      auprc: null
      brier: null
      ece: null
      calibration_slope: null
    uncertainty: ""                # CI 方法与宽度
    transport:
      target: ""
      result: ""                   # not_evaluated / stable / degraded / failed
      note: ""

  calibration:
    scope: ""                      # 同源 / 目标域 / 未校准
    method: ""
    target_labels_n: 0             # 目标域独立校准标签数

  thresholds:
    mild: null
    moderate: null
    high: null
    critical: null
    population_specific: false     # 是否为目标人群单独选点

  intended_use: ""
  contraindications: []
  out_of_scope: []

  abstention:
    automated_decision_allowed: false
    recommended: true
    reasons: []
    human_review_required_when: []

  fairness:
    evaluated_attributes: []
    known_gaps: []
    not_evaluable: []

  limitations: []
  monitoring: []
  rollback: ""
```

## 2. 字段规则

| 字段 | 必填 | 规则 |
|---|---|---|
| `population.population_id` | 是 | 必须与运行时 `population_scope` 的 ID 完全一致，不得一个模型多个别名 |
| `label.definition` | 是 | 不得只写「抑郁」；必须写明自报/量表阈值/临床诊断及来源 |
| `validation.cohorts[].protocol` | 是 | 内部切分、groupwise OOF、跨来源留出、外部验证必须区分；泄漏协议不得写入 |
| `metrics` | 是 | AUPRC 必须与阳性率基线比较；校准必须报 Brier/ECE/斜率，不能只报 AUC |
| `transport.result` | 是 | 未做迁移评估写 `not_evaluated`，不得写 `stable` |
| `calibration.target_labels_n` | 是 | 未在目标域校准写 0；少于 50 不得声称目标域校准完成 |
| `thresholds.population_specific` | 是 | 当前所有单元均为 `false`（全局固定阈值） |
| `intended_use` | 是 | 必须包含「筛查辅助/人工复核」限定，不得写「诊断」 |
| `out_of_scope` | 是 | 至少列出未验证人群、临床诊断、缺失模态场景 |
| `abstention.automated_decision_allowed` | 是 | Phase 0 全部为 `false`；改为 `true` 需满足证据矩阵 §1.2 五项条件 |
| `fairness` | 是 | 未评估写 `not_evaluable`，不得省略 |

## 3. 当前单元回填

### 3.1 结构化 v1.23

- **population**：`students_self_report_v1_23`；学生/青年自报问卷人群；英语数据集；在线自报场景。
  排除：非学生成人、临床确诊人群、仅有文本/生理数据者。
- **label**：Kaggle 自报抑郁二分类（约 97.6%）+ Mendeley PHQ-9≥10（约 2.4%，样本权重 5×）；
  标签来源为自报/量表，不是临床诊断。
- **validation**：内部测试 n=4,318（阳性率 0.5813，同源切分）；干净 Kaggle→Mendeley n=682
  （阳性率 0.4707）。内部 AUC 0.9131 / Brier 0.1152 / ECE 0.0139；
  跨来源 AUC 0.8633 / Brier 0.1734 / ECE 0.1435 / 斜率 1.161。
- **transport**：`degraded`；目标域平均预测概率 0.3272 vs 实际 0.4707，0.5 阈值灵敏度约 0.511。
- **calibration**：同源良好；目标域未校准（目标标签数 0）。
- **thresholds**：运行时 20/70/93/97（v1.23 校准集 p25/p50/p75/p90，生产唯一源
  `risk_thresholds.MODALITY_RISK_THRESHOLDS`）；工件 `threshold_config.json` 的
  18/35/55/72 仅作评估对照，不接入生产。全局固定，`population_specific=false`。
- **intended_use**：学生/青年自报场景的风险筛查辅助、人工复核排序。
- **out_of_scope**：非学生人群、临床诊断、仅有文本或生理数据的场景、以学业字段缺失推断风险。
- **abstention**：`automated_decision_allowed=false`，`recommended=true`；
  原因：输入者人群归属无法在运行时验证；跨来源校准与阈值未在目标域重建。
- **fairness**：性别差距小且 CI 跨 0；年龄组 TPR/FPR 差距较大；来源差距与标签定义混淆。
- **limitations**：`social_support` 全表恒为 2.0；`stress_level` 与 `academic_pressure` 完全重合；
  `anxiety` 与 `stress_level` 相关 0.9868；Mendeley 多列常量。

### 3.2 文本 v1.27（groupwise 重训）

- **population**：`chinese_student_text_v1_27`；中文学生文本（MMPsy 派生语料）；中文；
  社交媒体/日记文本场景。排除：非中文、普通成人、临床访谈文本。
- **label**：PHQ-9 二分类（按 `user_id` 聚合）；来源为量表自报；含增强样本的兄弟关系已隔离。
- **validation**：sibling-aware groupwise OOF n=8,379 / 1,277 组，阳性率 0.2163；
  AUC 0.8437 / AUPRC 0.5840 / Brier 0.1280 / ECE 0.0855 / 斜率 1.347。
  textwise AUC 0.9950 是泄漏读数，不得写入模型卡正面。
- **transport**：`not_evaluated`；无独立中文外部集；英文 holdout 仅同 Reddit 域。
- **calibration**：cross-fitted Platt 可改善（ΔBrier −0.0064、ΔECE −0.0544），但未上生产。
- **thresholds**：20/40/60/80，全局固定，`population_specific=false`。
- **intended_use**：中文学生文本的筛查辅助；必须人工复核。
- **out_of_scope**：非中文、非学生、临床诊断、长文本跨域、纯关键词决策。
- **abstention**：`automated_decision_allowed=false`，`recommended=true`；
  原因：groupwise F1 0.5864，跨人群覆盖未验证；90% 覆盖下仅约三成阳性被自动告警。
- **fairness**：未按人口学分组评估，`not_evaluable`。
- **limitations**：训练语料为 MMPsy 派生且含增强样本；无外部中文专家标注集。

### 3.3 生理 v2（Depresjon，合成特征）

- **population**：`depresjon_clinical_v2`；Depresjon 队列的**合成生理特征映射**
  （n=1,029；队列标签真实）。排除：任何真实可穿戴/体检数据、普通人群、
  消费级可穿戴用户、非 Depresjon 采集协议。
- **label**：`depression_label` 为真实病例/对照分组；`phq9_score` 是标签的噪声副本，
  不是真实 PHQ-9。
- **validation**：固定切分 validation 153 / test 157（阳性率 0.3503）。
  AUC 0.9451 / AUPRC 0.8961 / Brier 0.1408 / ECE 0.2160 / 斜率 3.760 **仅为管线读数**：
  同一数据上仅用真实 actigraphy 派生列（steps/exercise）的 5 折 OOF AUC 为 0.6443，
  而仅用标签驱动合成列的 OOF AUC 为 0.9898。
  ROUND_48 从原始分钟级数据重做同队列真实特征基线：受试者均值 LOSO AUC 0.6454
  [0.4861, 0.7983]，多日聚合 0.7620 ± 0.0093；同队列回顾性，不改变本卡生产读数。
  ROUND_49 的 18 规范网格显示该读数对聚合/日纳入选择敏感（0.5855–0.7364），
  且与零活动日/记录时长代理纠缠（仅代理模型 LOSO 0.7921）；0.6454 不是稳健估计。
  ROUND_50 的多日聚合 9 规范审计显示 0.7620 也是网格最大值（0.6565–0.7620），
  日级与受试者级 LOSO 不能互相替代；两项读数均不改变本卡生产读数。
- **data_provenance**：`synthetic_label_derived`——5/7 原始特征由转换脚本按标签分组均值
  生成，另有 1 个由其派生；审计见 `PHYSIO_DATA_PROVENANCE_AUDIT.md`。
- **transport**：`not_evaluated`；无真实同 7 列 schema 的外部抑郁数据集；WESAD 只有应激标签。
  ROUND_47 曾用 NHANES 2017–2018 做迁移压力测试（6/7 字段、PHQ-9≥10 标签，AUC 0.5459），
  因标签/特征/协议同时变化，仍不构成外部验证、不改变本卡证据等级。
  ROUND_48 的真实 actigraphy 基线同样是同队列回顾性结果，不改变 `not_evaluated`。
- **calibration**：原始概率未校准；Platt 仅在 153 行验证集拟合，探索性，未上生产；
  校准对象是合成特征管线，不能外推到真实传感器。
- **thresholds**：35/55/75/90，全局固定，`population_specific=false`；
  阈值选点基于合成特征，不能作为真实生理阈值依据。
- **intended_use**：仅用于接口联调、生产管线回归与演示；不得作为真实生理信号筛查依据。
- **out_of_scope**：任何真实可穿戴/体检数据解释、普通人群、消费级可穿戴、
  睡眠/血压缺失场景、因果解释、自动诊断或自动处置。
- **abstention**：`automated_decision_allowed=false`，`recommended=true`；
  原因：训练特征 5/7 为标签驱动合成；真实 actigraphy 列 OOF AUC 仅 0.6443；
  n=157、CI 宽、ECE 0.216。
- **fairness**：未评估，`not_evaluable`。
- **limitations**：单次切分；合成特征使内部指标主要反映标签映射；
  WESAD schema 缺口不得造列补齐。ROUND_48 已用原始 actigraphy 重做同队列基线，
  ROUND_49 进一步显示规范敏感与佩戴混杂，ROUND_50 显示多日聚合 0.7620 是 9 规范
  网格最大值（0.6565–0.7620）；仍缺外部队列、佩戴/非佩戴标注与目标域校准；n=55，
  不能外推。

### 3.4 融合 v1.16

- **population**：`no_aligned_three_modality_cohort`；无对齐三模态有标签人群。
- **label**：无可评估标签。
- **validation**：`not_evaluable`；现有模态数据来自不同人群与采集协议。
- **transport**：`unknown`。
- **calibration**：不适用。
- **thresholds**：22/42/62/82，全局固定；无证据支持任何人群选点。
- **intended_use**：仅作多模态信号汇总展示，必须人工复核；不得据此自动处置。
- **out_of_scope**：任何性能声明、模态贡献声明、阈值声明、全人群声明。
- **abstention**：`automated_decision_allowed=false`，`recommended=true`；
  原因：无对齐三模态标签，融合分数不能作为人群级证据。
- **fairness**：`not_evaluable`。
- **limitations**：权重敏感性只能说明冲突时权重重要，不能替代验证。

## 4. 回填检查清单

- [ ] `population_id` 与运行时登记表一致
- [ ] 标签定义写清来源与阈值，不写「抑郁」二字了事
- [ ] 验证协议区分内部/分组/跨来源/外部，泄漏读数不写入正面
- [ ] 特征来源登记为真实测量/可接受代理/标签驱动合成；合成特征不得支撑真实性能结论
- [ ] 校准与阈值是否为目标人群单独建立，写明标签数
- [ ] `out_of_scope` 覆盖未验证人群、临床诊断、缺失模态
- [ ] `automated_decision_allowed=false` 或满足证据矩阵 §1.2 五项条件
- [ ] 公平性未评估时写 `not_evaluable`，不省略
- [ ] 对外文案不出现「全人群」「通用」「诊断」等未验证表述
