# v1.24 PRD：外部一致性验证与风险评分迁移治理

> **迭代名称**: v1.24-mmpsy-external-consistency-and-score-stability
> **中文名称**: mmpsy 外部一致性验证与风险评分稳定性治理
> **版本**: v1.24
> **日期**: 2026-05-02
> **来源**: `e:\code\bysj\md\7.md`
> **基线**: Round 1 Locked
> **上级依赖**: v1.23-external-risk-model-upgrade (已交付)

---

## 一、背景与问题陈述

### 1.1 前置状态

v1.23 External LR 模型已交付，以候选实验模型身份在线（未替换 v1.20 默认模型）：

| 指标 | 值 |
|------|-----|
| Test AUC | 0.9131 |
| Test F1 | 0.8589 |
| PHQ-9 Pearson r (Mendeley, N=137) | 0.6826 |
| v1.23 model path | `backend/models/v1.23_external_lr/model.pkl` |
| Feature schema | `backend/models/v1.23_external_lr/feature_schema.json` (12 特征) |
| 接入方式 | `model_engine.py` 实验路径 (L565-604)，输出 `experimental_external_*` 字段 |
| Delta 监控 | `model_engine.py` (L624-636)，内存计数器 `external_delta_*` |

### 1.2 两个关键问题

| # | 问题 | 实证数据 |
|---|------|----------|
| 1 | **mmpsy 无法验证** | `external_validation_metrics.json` 已确认: mmpsy (N=1275) 仅含 `phq9_score/gad7_score/audio_transcript` 等 9 个字段，12 个结构化特征**全部缺失**，`model_inference_possible: false` |
| 2 | **v1.23 与 v1.20 分数差异过大** | Mean Abs Delta = 21.29（阈值 15），(\|delta\|>30) 比例 = 26.79%（阈值 10%），(\|delta\|>40) 比例 = 20.10%（阈值 5%） |

### 1.3 核心定位

v1.24 不以"继续提升 AUC"为第一目标，而以**验证可信度、评分稳定性、上线安全性**为第一目标。

---

## 二、资产基线（Phase 0 前置条件）

> **Phase 0 是 v1.24 的独立前置步骤**，必须在任何特征构建/验证前完成。

### 2.1 已有资产清单

| 资产 | 路径 | 确认 |
|------|------|------|
| v1.23 模型 | `backend/models/v1.23_external_lr/model.pkl` | ✅ |
| v1.23 Feature Schema | `backend/models/v1.23_external_lr/feature_schema.json` | ✅ |
| v1.23 外部验证指标 | `backend/models/v1.23_external_lr/external_validation_metrics.json` | ✅ |
| v1.23 聚合指标 | `backend/models/v1.23_external_lr/metrics.json` | ✅ |
| v1.23 Delta 样本 | `backend/models/v1.23_external_lr/model_delta_samples.csv` | 待确认 |
| mmpsy 原始数据 | `data/external/mmpsy_scores.csv` (N=1275) | ✅ |
| v1.20 模型 | `backend/models/artifacts/structured_v1.20/` | ✅ |
| 模型注册表 | `backend/app/core/model_registry.py` | ✅ |
| 模型引擎 | `backend/app/core/model_engine.py` | ✅ |

### 2.2 v1.23 特征 Schema（完整 12 特征）

```
来源: backend/models/v1.23_external_lr/feature_schema.json
```

| # | 特征名 | 类型 | 取值范围 | 缺失策略 |
|---|--------|------|---------|----------|
| 1 | age | numeric | 12-35 | median |
| 2 | gender | numeric | 0=女, 1=男 | — |
| 3 | cgpa | numeric | 0-4 | median |
| 4 | stress_level | numeric | — | median |
| 5 | sleep_duration | numeric, hours | — | median |
| 6 | social_support | numeric | — | median (⚠️ 多数数据集为 2.0) |
| 7 | financial_pressure | numeric | — | median |
| 8 | family_history | numeric | 0/1 | — |
| 9 | academic_pressure | numeric | — | median |
| 10 | exercise_frequency | numeric | — | median |
| 11 | anxiety | numeric | — | median |
| 12 | panic_attack | numeric | 0/1 | — |

预处理: SimpleImputer(median) + StandardScaler

### 2.3 mmpsy 原始数据字段（仅 9 个）

```
来源: data/external/mmpsy_scores.csv (N=1275)
```

| 字段 | 说明 |
|------|------|
| user_id | 用户标识 |
| phq9_score | PHQ-9 总分 (均值 6.7) |
| phq9_level | Normal/Mild/Moderate/Severe |
| phq9_binary | 0/1 (阳性率 20%) |
| gad7_score | GAD-7 总分 (均值 3.8) |
| gad7_level | Normal/Mild/Moderate/Severe |
| gad7_binary | 0/1 (阳性率 11%) |
| audio_count | 音频段数 |
| audio_transcript | 中文语音转录文本 |

**关键事实**: mmpsy **没有任何一个字段可直接映射**到 v1.23 的 12 个特征。

### 2.4 Phase 0 交付物

| 交付物 | 说明 |
|--------|------|
| `feature_schema_v1_23.json` | v1.23 schema 副本 (已存在) |
| `mmpsy_field_inventory.csv` | mmpsy 字段清单与命中分析 |
| `v1_20_v1_23_delta_baseline.csv` | 从 `model_delta_samples.csv` 提取的 delta 基线 |
| `asset_check_report.md` | 资产完整性与可复现性检查 |

Phase 0 验收: 所有资产路径可解析，delta 基线可复现。

---

## 三、迭代目标

### 3.1 第一目标

> **证明 v1.23 能安全进入灰度升级路径**

### 3.2 P0 目标（必须达成）

1. **mmpsy 结构化特征构建与受限外部验证**
   - 通过规则派生 + 统计估计构建 mmpsy 的结构化特征数据集
   - 在 mmpsy 上运行 v1.23 进行受限外部验证（受特征覆盖率限制）
   - **即使覆盖率 < 80%，也产出外部验证报告并标注"受限"**

2. **v1.20 → v1.23 风险分迁移安全评估**
   - Delta 分层深度分析（按风险等级/特征/人群分组）
   - 产出分数迁移策略候选
   - **Delta 分析是 Score Adapter 分段点选择的前置依赖**

### 3.3 P1 目标（建议达成）

3. **v1.24 Score Adapter** — 分段单调映射，平滑过渡分段边界
4. **监控持久化** — JSON 快照文件 + uptime 标记
5. **注册表治理** — 五态生命周期 + 清理实验路径引用

---

## 四、功能需求

### 4.1 mmpsy 结构化特征构建

> **前置**: Phase 0 资产审计完成

**输入**: `data/external/mmpsy_scores.csv` (N=1275, 仅 9 个字段)

**字段映射策略**（逐特征）：

| v1.23 特征 | 策略 | 方法 | 置信度 |
|-----------|------|------|--------|
| age | 统计估计 | 青少年学生群体中位数 ≈ 16 | 低 ⚠️ |
| gender | 缺失标记 | 默认值 0 (female)，或从转录文本推断 | 极低 ⚠️ |
| cgpa | 缺失标记 | median 填充 | 极低 ⚠️ |
| stress_level | **规则派生** | `phq9_score / 27 * 5` 归一化映射 | 中 |
| sleep_duration | **规则派生** | 从 `audio_transcript` 提取睡眠关键词（如"睡不着""失眠"） | 低 |
| social_support | 缺失标记 | median 填充 (已知为 2.0) | 低 ⚠️ |
| financial_pressure | 缺失标记 | median 填充 | 极低 ⚠️ |
| family_history | 缺失标记 | 默认值 0 | 极低 ⚠️ |
| academic_pressure | **规则派生** | 从 `audio_transcript` 提取学业关键词（"考试""成绩""作业"） | 低 |
| exercise_frequency | **规则派生** | 从 `audio_transcript` 提取运动关键词（"跑步""打球""运动"） | 低 |
| anxiety | **规则派生** | `gad7_score / 21 * 5` 归一化映射 | 中 |
| panic_attack | **规则派生** | 从 `audio_transcript` 检测危机关键词（"想死""不想活"），匹配则=1 | 中 |

**预估特征覆盖率**:

| 策略层级 | 特征数 | 占比 |
|----------|--------|------|
| 可直接映射 | 0 | 0% |
| 可规则派生 (中置信度) | 3 (stress_level, anxiety, panic_attack) | 25% |
| 可规则派生 (低置信度) | 3 (sleep_duration, academic_pressure, exercise_frequency) | 25% |
| 不可映射 | 6 (age, gender, cgpa, social_support, financial_pressure, family_history) | 50% |

> **预估总覆盖率: 30-50%** — 几乎不可能达到 80%。v1.24 明确接受这一事实。

**交付物**:
- `mmpsy_structured_features.csv` (1275 × 12 特征矩阵，含来源标注列)
- `mmpsy_feature_mapping_report.md` (逐特征映射详情与置信度)
- `mmpsy_missingness_report.md` (缺失分布与填充策略)

**验收**:
- 12 个特征全部有值（无论是派生还是填充）
- 每个特征的来源策略可追溯
- 关键派生特征（stress_level, anxiety）的映射逻辑有文档

### 4.2 mmpsy 受限外部验证

> **前置**: 4.1 mmpsy 结构化特征构建完成
> **依赖**: v1.23 模型 pipeline 已加载

**输入**: `mmpsy_structured_features.csv` + `backend/models/v1.23_external_lr/model.pkl`

**Ground Truth**: mmpsy 已有 `phq9_binary` (0/1, 阳性率 20%)

**已知风险**: 大量特征用中位数填充会导致"回归到均值 (regression to mean)"效应——高风险样本被低估、低风险样本被高估。

**缓解**: 报告中单独分析"有效特征子集贡献" vs "填充特征的噪声效应"

**输出指标**:

| 指标 | 目标阈值 | 说明 |
|------|---------|------|
| mmpsy Binary AUC | ≥ 0.80 | 即使受限，PHQ-9 派生的 stress_level + anxiety 应提供信号 |
| mmpsy Recall | ≥ 0.70 |  |
| mmpsy Specificity | ≥ 0.60 | 大量填充值可能降低特异性 |
| mmpsy Pearson r (vs PHQ-9) | ≥ 0.50 |  |
| mmpsy Spearman ρ (vs GAD-7) | ≥ 0.50 |  |
| 高风险样本召回 | ≥ 0.75 | phq9_binary=1 样本 |

**降级策略（三级）**:

| 条件 | 标记 | 结论 |
|------|------|------|
| 覆盖率 ≥ 50% 且 AUC ≥ 0.80 | 无 | 外部一致性验证通过 |
| 覆盖率 < 50% 或 AUC < 0.80 | `mmpsy feature compatibility insufficient` | 受限验证 — 非模型泛化失败 |
| 覆盖率 < 50% 且 AUC < 0.65 | `mmpsy feature compatibility insufficient` + 回归均值主导 | 无法得出有效结论 |

**交付物**:
- `mmpsy_external_validation_metrics.json`
- `mmpsy_external_validation_report.md` (含受限声明)
- `mmpsy_calibration_curve.png`
- `mmpsy_roc_curve.png`

### 4.3 Delta 分层深度分析

> **前置**: Phase 0 delta 基线确认
> **下游依赖**: 4.4 Score Adapter 分段点选择

**目标**: 回答三个核心问题：
1. 哪些人群 delta 最大？
2. delta 是否集中在某些特征、风险等级或边界样本？
3. 是否可以确定 Score Adapter 的分段策略？

**数据源**: `backend/models/v1.23_external_lr/model_delta_samples.csv`

**分析维度**:
- 全体分布: Mean Abs Delta, 分位数
- 按 v1.20 风险等级分组: 0=无风险 / 1=轻度 / 2=中度 / 3=高度 / 4=极高度
- 按 PHQ-9 区间分组: 0-4 / 5-9 / 10-14 / 15-19 / 20-27
- 按 GAD-7 区间分组: 0-4 / 5-9 / 10-14 / 15-21
- 按年龄/性别分组
- 按数据来源分组 (label_source)

**极端 delta 样本画像**:
- (\|delta\| > 30) 样本: 数量、比例、共同特征模式
- (\|delta\| > 40) 样本: 数量、比例、风险等级分布
- v1.20 低→v1.23 高: 被 v1.20 低估的样本
- v1.20 高→v1.23 低: 被 v1.23 降级的样本

**交付物**:
- `delta_distribution_report.md`
- `delta_by_risk_group.csv`
- `delta_by_feature_group.csv`
- `extreme_delta_cases.csv`

**验收**:
- 明确 (\|delta\| > 30) 的主要来源人群
- 明确低转高、高转低的样本画像
- 给出分段单调映射的推荐分段点 (≥3 个候选)

### 4.4 Score Adapter

> **前置**: 4.3 Delta 分层分析完成
> **策略**: v1.23 External LR + v1.24 Score Adapter

**候选方案对比**:

| 方案 | 描述 | 优点 | 风险 |
|------|------|------|------|
| A: 线性映射 | Y = a·X + b 全量映射 | 简单、可解释 | 对分布尾部无效 |
| B: 分段单调映射 | 按 v1.20 分数区间分段线性映射 | 压缩极端 delta、保持排序 | 分段边界不连续 |
| C: Isotonic Regression | 非参数保序回归 | 灵活 | 过拟合风险 |
| D: 双阈值策略 | 仅中高风险区间影响等级 | 适合医疗场景 | 边界样本需复核 |

**推荐方案: 方案 B（分段单调映射）+ 平滑过渡**

**核心算法**（伪代码）:
```
输入:
  v1.20_score, v1.23_raw_score
  delta = v1.23_raw_score - v1.20_score

分段策略 (以 v1.20_score 为基准):
  区间1: [0, 20)   → 目标 mean_delta ≤ 5
  区间2: [20, 40)  → 目标 mean_delta ≤ 10
  区间3: [40, 60)  → 目标 mean_delta ≤ 12
  区间4: [60, 80)  → 目标 mean_delta ≤ 10
  区间5: [80, 100] → 目标 mean_delta ≤ 5
  
每区间映射:
  slope = target_delta / actual_mean_delta
  adjusted_score = v1.20_score + delta * slope

极端值钳制:
  adjusted_score 钳制到 [v1.20_score - 20, v1.20_score + 20]

分段边界平滑:
  在分段点 ± 3 分的缓冲区使用线性插值过渡
  adjusted_score = w * segment_A_result + (1-w) * segment_B_result
```

**新增输出字段**:
| 字段 | 含义 |
|------|------|
| `experimental_external_raw_score` | v1.23 原始输出 |
| `experimental_external_adjusted_score` | v1.24 Adapter 输出 |
| `experimental_external_adapter_delta` | adjusted - raw 差值 |
| `experimental_external_migration_safe` | 升级安全标签 (stable/slight_diff/marked_diff/review) |
| `experimental_external_migration_risk_level` | 迁移风险等级 |
| `experimental_external_adapter_version` | Adapter 版本号 (v1.24) |

**验收标准**:

| 指标 | 当前 v1.23 | v1.24 目标 |
|------|-----------|------------|
| Mean Abs Delta | 21.29 | < 15 |
| (\|delta\| > 30) 比例 | 26.79% | < 10% |
| (\|delta\| > 40) 比例 | 20.10% | < 5% |
| AUC 损失 (vs v1.23 raw) | — | ≤ 0.02 |
| Recall | 0.8733 | ≥ 0.82 |
| Specificity | 0.7777 | ≥ 0.70 |

**如果 Adapter 无法同时满足 Mean Abs Delta < 15 且 AUC 损失 ≤ 0.02**:
→ 优先输出 **Pareto 前沿**，让决策者看到 trade-off 曲线，并给出推荐配置。

**交付物**:
- `adapter_experiment_results.csv` (5 种候选 + Pareto 前沿)
- `score_adapter.pkl` + `score_adapter_config.json`
- `adapter_selection_report.md`

### 4.5 监控持久化与增强

> **现状**: `model_engine.py` 监控数据全部在内存中，重启丢失。`get_metrics_snapshot()` 可 API 查询。

**v1.24 增强**:

| 层次 | 做什么 |
|------|--------|
| 持久化 | 每 60s 将 `monitoring_counters` + recent deltas dump 到 `logs/monitoring_snapshot.json` |
| API 增强 | 现有 `get_metrics_snapshot()` 中 `experimental_external` 增加 `uptime_seconds` 字段 |
| 日志告警 | 当 delta 超阈值时记录 WARNING 级别日志 (已有 `logger.info`) |
| 按风险等级 delta | `monitoring_counters` 新增 `external_delta_by_level_N` (N=0..4) 计数器 |

**新增监控指标（上线后）**:
1. 实验模型调用量 (`external_hit`)
2. 实验模型失败率 (`external_miss / total`)
3. v1.23→v1.20 delta 均值 (`external_delta_sum / external_hit`)
4. (\|delta\| > 15/30/40) 比例 (已有)
5. 按风险等级统计的 delta (新增 `external_delta_by_level_N`)
6. 高风险提升/下降样本数量 (可由 delta 聚合推算)
7. Adapter 前后分数变化 (v1.24 新增)

**告警阈值** (日志级):

| 指标 | 告警条件 |
|------|----------|
| experimental_external_error_rate | > 1% |
| Mean Abs Delta | > 20 |
| (\|delta\| > 30) 比例 | > 20% |
| 高风险降为低风险比例 | > 5% |
| 低风险升为高风险比例 | > 15% |
| Adapter 后 AUC 下降 | > 0.02 |
| 服务运行时间 | < 60min (近期重启警告) |

**不做的事**:
- 不做 Prometheus/Grafana 集成
- 不做 webhook/邮件/短信告警
- 不做时序数据库存储

这些延后到 v1.25+。

### 4.6 模型注册表治理

> **现状**: `backend/app/core/model_registry.py`

**当前模型状态（审计结果）**:

| 模型 ID | 版本 | enabled | 备注 |
|---------|------|---------|------|
| structured_logistic_regression_v1.20 | v1.20 | True | default |
| structured_v1.21_binary_lr | v1.21 | True | 实验路径 L530 硬编码引用 |
| structured_v1.21_binary_rf | v1.21 | True | |
| structured_v1.21_multiclass_lr | v1.21 | **False** | 已 disabled |
| structured_v1.21_multiclass_rf | v1.21 | **False** | 已 disabled |
| structured_v1.23_external_lr | v1.23 | True | candidate-experimental |

**v1.24 改造任务**:

1. **新增生命周期状态枚举** — 在 `ModelMetadata` 增加 `lifecycle` 字段:
   - `default` — 当前生产默认模型
   - `candidate` — 候选升级模型 (shadow 输出)
   - `experimental` — 实验模型 (仅实验路径)
   - `deprecated` — 已弃用但保留历史 (前端可隐藏)
   - `disabled` — 已禁用（等同于 enabled=False）

2. **修改 model_engine.py 实验路径**:
   - L530 硬编码调用 `structured_v1.21_binary_lr` → 改为检查 `lifecycle`，若为 `deprecated` 则跳过
   - L570 调用 `structured_v1.23_external_lr` → 更新为 v1.24 adapter 路径

3. **目标模型分配**:

   | 模型 | lifecycle |
   |------|-----------|
   | v1.20 Synthetic LR | default |
   | v1.21 Real Binary LR | deprecated |
   | v1.21 Multi-class LR/RF | disabled (不变) |
   | v1.23 External LR | experimental |
   | v1.24 Adapter | candidate |

4. **前端隐藏规则**: lifecycle 为 `deprecated` 或 `disabled` 的模型不在前端展示

**交付物**:
- 更新 `model_registry.py` (新增 lifecycle 字段)
- 更新 `model_engine.py` (实验路径引用修正)
- `model_lifecycle_policy.md`
- `model_registry_cleanup_report.md`

---

## 五、非功能需求

### 5.1 安全性
- v1.24 后端实验输出**不影响** v1.20 默认预测路径（`default` lifecycle 模型路径不变）
- 前端**明确标注**实验分数性质（"实验参考，不作为正式风险等级依据"）

### 5.2 可追溯性
- 所有模型产物保持版本化
- v1.21 禁用但不物理删除模型文件
- 监控快照文件持久化到 `logs/` 目录

### 5.3 可解释性
- mmpsy 每个特征的来源策略可追溯（可直接映射 / 规则派生 / 统计估计 / 缺失填充）
- Score Adapter 映射逻辑透明可审计（分段点 + 斜率 + 钳制规则）
- Delta 分析结果可解释到人群和特征层面

### 5.4 可复现性 (按 Ralph 铁律第 5 条)
- 所有随机操作设置 random_state=42
- mmpsy 特征构建脚本记录完整处理逻辑

---

## 六、不做的事

1. **不直接替换 v1.20** — Mean Abs Delta 仍为 21.29
2. **不继续单纯追求 AUC** — v1.23 AUC 已达 0.9131
3. **不把 v1.24 做成完全独立新模型** — 除非 mmpsy 验证发现 v1.23 泛化失败
4. **不删除历史模型产物** — v1.21 禁用但保留文件
5. **不做生产级监控平台** — Prometheus/Grafana 延后到 v1.25+

---

## 七、依赖关系图

```
Phase 0 (资产审计)
  ├─→ Phase 1 (mmpsy 特征构建)
  │     └─→ Phase 2 (mmpsy 受限外部验证)
  │
  └─→ Phase 3 (Delta 分层分析)
        └─→ Phase 4 (Score Adapter)  ← 依赖 Phase 3 的分段点
              └─→ Phase 5 (Shadow 接入 model_engine)
                    ├─→ Phase 6 (前端展示优化)
                    └─→ Phase 7 (注册表治理)
                          └─→ Phase 8 (灰度资格评估)
```

Phase 1 和 Phase 3 可**并行**（互不依赖）。

---

## 八、迭代路线

```
Phase 0: 资产与 schema 审计
→ Phase 1: mmpsy 结构化特征构建
→ Phase 2: mmpsy 受限外部验证
→ Phase 3: Delta 分层深度分析
→ Phase 4: Score Adapter 实验与选择
→ Phase 5: 后端 Shadow 接入
→ Phase 6: 前端展示优化
→ Phase 7: 注册表与废弃模型治理
→ Phase 8: 灰度资格评估
```

---

## 九、上线决策分级

| 结论 | 条件 |
|------|------|
| 不上线 | mmpsy 受限验证结果不可解释 或 Adapter AUC 损失 > 0.05 |
| 继续实验 | mmpsy 受限验证可解释 但 delta 未收敛 |
| 灰度候选 | mmpsy 受限验证可解释 且 Mean Abs Delta < 15 且 AUC 损失 ≤ 0.02 |
| 可准备替换 | 连续监控周期稳定 (≥ 7天无异常) 且临床/业务复核通过 |

---

## 十、v1.24 关键矛盾声明

> **mmpsy 特征覆盖率几乎不可能达到 80%**。v1.24 不以"完整外部验证"为交付标准，而以：
> 1. **证明 mmpsy 不能做完整外部验证的原因**（特征不兼容的实证分析）
> 2. **给出"受限验证"的最佳结果**（可解释的、有置信度的部分验证）
> 3. **通过 delta 分析和 Score Adapter 证明 v1.23 的评分稳定性可控**
>
> 为实际交付目标。

---

> **Round 1 Locked** | 下一步: Round 2 — 自查与修订
