# v1.25 需求文档 (PRD): mmpsy-lite 轻特征专用风险模型

> **版本**: Draft v3 (Round 3 / Final Draft — Locked)
> **迭代**: v1.25-mmpsy-lite-risk-model
> **中文名**: 面向 mmpsy-like 轻特征人群的专用风险模型
> **创建日期**: 2026-05-02
> **状态**: ✅ Locked (Round 3 — 全三轮规划完成)
> **前置依赖**: v1.24 CONDITIONAL-GO (2026-05-02)

---

## 一、执行摘要 (Executive Summary)

### 1.1 迭代背景

v1.24 达成了两项关键结论：

| 结论 | 数据 | 含义 |
|------|------|------|
| ✅ 分数迁移稳定性已解决 | Mean Abs Delta 21.29 → 4.37, AUC Loss 0.0196 | adapter 足以支撑系统内平滑迁移 |
| ❌ 跨人群泛化未解决 | mmpsy AUC 0.6249, Specificity 0.4887, 特征覆盖率 50% | 不是校准问题，是建模失配 |

v1.24 的 Score Adapter 解决了“新旧分对齐”，但无法弥补**底层特征空间鸿沟**——mmpsy 人群缺失 6/12 结构化特征，继续给现有模型打补丁收益已耗尽。

### 1.2 v1.25 核心目标

**为 mmpsy-like 轻特征人群训练专属的二分类风险识别模型**，形成与结构化主线并行的第二条模型轨道。

### 1.3 一句话定位

> v1.25 不是升级 v1.24，而是为"低结构化、问卷+文本主导人群"建立第二条可上线的专用风险模型通道。

---

## 二、问题定义 (Problem Definition)

### 2.1 目标人群画像

v1.25 服务的用户具有以下全部或多数特征：

| 维度 | 特征 |
|------|------|
| 输入类型 | GAD-7 总分 + 音频转录/文本摘要（PHQ-9 作为外部验证参照，不作为模型输入） |
| 结构化字段 | 缺失 ≥ 4/12 关键特征（stress_level, financial_pressure, family_history 等） |
| 数据来源 | mmpsy / 类 mmpsy 数据源（问卷型、对话型、筛查型） |
| 特征覆盖率 | 典型 < 70%，与 v1.23 训练集分布显著偏移 |
| 场景特点 | 更适合"筛查→分流"而非"完整临床表型评估" |

### 2.2 当前模型对此人群的失效表现

| 指标 | v1.23 在 mmpsy 上 | 阈值 | 差距 |
|------|:---:|:---:|:---:|
| AUC | 0.6249 | ≥ 0.80 | -0.175 |
| Recall | 0.6860 | ≥ 0.75 | -0.064 |
| Specificity | 0.4887 | ≥ 0.65 | -0.161 |
| Pearson r | 0.2151 | ≥ 0.50 | -0.285 |
| Spearman ρ | 0.1239 | ≥ 0.40 | -0.276 |

### 2.3 核心任务定义

> ⚠️ **标签约束**: mmpsy 数据集**无独立临床标签**。phq9_binary/phq9_level/gad7_binary 全部派生自同一份 PHQ-9/GAD-7 评分。因此**特征集必须排除 phq9_score**——否则构成"用 PHQ-9 预测 PHQ-9"的循环依赖。

#### 主任务：二分类风险识别（文本增强型）

- **输入（特征）**: GAD-7 总分, 文本关键词, 人口学（年龄/性别/cgpa）
- **明确排除**: ❌ phq9_score（保留为独立验证标准，不作为模型输入）
- **标签**: `phq9_binary`（PHQ-9 ≥ 10 → 1, 阳性率 20.2%, 258/1275）
- **输出**: P(高风险) 概率 + 二分类预测
- **优先指标**: Recall ≥ 0.75, Specificity ≥ 0.65, AUC ≥ 0.80
- **价值命题**: 证明"文本信号 + GAD-7 + 人口学"能产生与 PHQ-9 相当的判别力，为未来采集独立标签后的真实临床模型奠定基础

#### 次任务：连续风险分

- **输入**: GAD-7 + 文本 + 人口学（同主任务）
- **输出**: 0–100 风险评分（校准后概率 * 100）
- **外部参照**: 与 PHQ-9 的相关性（Pearson r, Spearman ρ）— 注意这是参照而非目标，因为 PHQ-9 不作为输入

#### 消融实验 (Ablation)

必须对比以下配置以量化文本贡献：

| 配置 | 特征 | 目的 |
|------|------|------|
| Upper bound | phq9_score 单独 | PHQ-9 → phq9_binary 的理论上限（循环参照） |
| GAD-7 only | gad7_score 单独 | 焦虑作为抑郁的替代信号 |
| Text only | 文本关键词 | 纯文本信号的判别力 |
| GAD-7 + Text | gad7_score + 文本关键词 | v1.25 主模型 |
| GAD-7 + Text + Demo | 上述 + age/gender/cgpa | v1.25 完整模型 |

---

## 三、功能需求 (Functional Requirements)

### 3.1 新模型 — mmpsy-lite 风险模型

#### FR-MODEL-001: 轻特征输入

模型必须仅依赖以下高可得输入字段（**禁止使用 phq9_score，保留为外部验证参照**）：

| 层级 | 字段 | 可得性 | 缺失处理 | 用途 |
|------|------|:---:|------|------|
| **L1 必选** | GAD-7 总分 (0–21) | 100% | N/A | 焦虑严重度核心信号 |
| **L1 必选** | 音频转录文本 | 100% | N/A | 语言行为信号 |
| **L1 必选** | 文本关键词计数 | 100% | N/A | 从转录派生 |
| **L2 可选** | 年龄 (age) | 100% | N/A (0缺失) | 人口学分层 |
| **L2 可选** | 性别 (gender) | 100% | N/A (0缺失) | 人口学分层 |
| **L2 可选** | cgpa | 100% | N/A (0缺失) | 学业表现 |
| **L3 鲁棒** | 文本长度 (chars) | 100% | N/A | 文本质量代理 |
| **L3 鲁棒** | 输入完整度标记 | 100% | N/A | 区分数据完整度 |
| **L3 鲁棒** | 关键词覆盖密度 | 100% | N/A | 文本信息密度 |

**文本关键词类别** (从 audio_transcript 提取):

| 类别 | 示例关键词 | 提取方式 |
|------|------|------|
| 学业压力 | 挂科/退学/考研/论文/毕业/导师 | 正则匹配 |
| 睡眠问题 | 失眠/熬夜/早醒/嗜睡/噩梦 | 正则匹配 |
| 社交退缩 | 独处/回避/不想说话/孤僻 | 正则匹配 |
| 自伤/危机 | 自残/自杀/想死/割腕/安眠药 | 正则 + 危险词加权 |
| 运动缺乏 | 不运动/躺着/不出门/宅 | 正则匹配 |
| 情绪低落 | 难过/绝望/空虚/麻木/没意义 | 正则匹配 |
| 焦虑躯体 | 心慌/胸闷/发抖/出汗/窒息 | 正则匹配 |

#### FR-MODEL-002: 模型架构约束

- 参数量 < 5,000（LR: N_features+1；GBDT: max_depth≤3 + n_estimators≤50）
- 必须支持 CPU 推理（不需要 GPU）
- 推理延迟 < 50ms（单样本）
- 校准: 使用 `CalibratedClassifierCV(method='isotonic', cv=5)` 在 5-Fold CV 内部校准，无需独立 calibration set

#### FR-MODEL-003: 候选模型类型

| 优先级 | 模型 | 超参数约束 | 理由 |
|:---:|------|------|------|
| P0 | Logistic Regression (LR) | C=1.0, max_iter=1000 | 可解释、训练稳定、首选 |
| P1 | LightGBM | max_depth=3, n_estimators=50, min_child=20 | 非线性交互、特征重要性 |
| P2 | Calibrated LR | CalibratedClassifierCV(LR, cv=5) | 概率校准对比 |
| 对照 | PHQ-9 Only | 仅 phq9_score → phq9_binary | 理论上限参照（循环） |
| 对照 | GAD-7 Only | 仅 gad7_score → phq9_binary | 焦虑作为替代信号基线 |

#### FR-MODEL-004: 文本质量边界

| 边界 | 阈值 | 行为 |
|------|:---:|------|
| 最低可处理长度 | ≥ 20 字符 | 短于此长度 → 文本特征向量全零 + warning |
| 正常范围 | 41–3991 chars (均值 345) | 正常提取关键词 |
| 非中文主流检测 | 中文字符占比 < 30% | 仅保留数字/统计特征，关键词特征设零 |

### 3.2 模型路由层 (Model Routing)

#### FR-ROUTE-001: 路由决策策略（三档降级）

系统必须根据输入特征可得性自动选择模型轨道：

```
f_coverage = 可用结构化特征数 / 总结构化特征数 (基于 v1.23 的 14 字段)

if f_coverage >= 0.80:
    route = "structured"   → v1.20(default) + v1.24 adapter(shadow)
elif gad7_score 存在 AND audio_transcript 存在 AND len(transcript) >= 20:
    route = "lite"         → v1.25 mmpsy-lite
elif gad7_score 存在:
    route = "anxiety_only" → GAD-7 规则分数线（PHQ-9≈GAD-7*1.29 经验映射）
else:
    route = "insufficient" → 返回 None + warning "信息不足以评估风险"
```

**降级路径表**:

| 路径 | 触发条件 | 行为 |
|------|------|------|
| `structured` | 特征 ≥ 80% | v1.20 default + v1.24 shadow |
| `lite` | GAD-7 + 文本 ≥ 20 字符 | v1.25 lite 模型 |
| `anxiety_only` | 仅 GAD-7 | GAD-7 经验线: score=min(gad7/21*100, 100) |
| `insufficient` | 其他 | 不评分，返回 error flag |

#### FR-ROUTE-004: confidence_band 计算规则

| Band | 条件 |
|------|------|
| `high` | route=structured + 特征覆盖率 ≥ 90% |
| `medium` | route=structured(80-90%) 或 route=lite |
| `low` | route=anxiety_only 或 route=insufficient |

#### FR-ROUTE-002: 路由策略配置化

- 路由阈值（如 80%）必须可配置，不要硬编码
- 路由决策需记录到日志
- 路由结果需体现在 API 响应中

#### FR-ROUTE-003: 新增响应字段

| 字段 | 类型 | 含义 |
|------|------|------|
| `selected_model_id` | string | 实际使用的模型 ID |
| `selected_model_family` | string | 模型家族: structured / lite / fallback |
| `routing_reason` | string | 路由原因（如 "feature_coverage_below_threshold"） |
| `feature_coverage_ratio` | float | 特征覆盖率 (0.0–1.0) |
| `prediction_confidence_band` | string | 置信区间: high / medium / low |

### 3.3 监控与运维

#### FR-MON-001: 路由分布监控

- 必须按模型轨道（structured / lite / fallback）记录调用量
- 必须按轨道记录高风险样本分布
- 数据写入 `monitoring_snapshot.json`（复用 v1.24 持久化通道）

#### FR-MON-002: 模型性能代理指标

- 记录各轨道 score 分布统计（均值、方差、分位数）
- 记录各轨道与 PHQ-9/GAD-7 的相关性（仅当标签可用时）
- snapshot 滚动策略: 保留最近 1000 条记录，超出部分写入 `monitoring_snapshot.{date}.json` 归档

### 3.4 前端展示

#### FR-FE-001: 路由透明展示

在风险评估结果页新增：

- **本次使用模型**: 结构化模型 / 轻特征模型 / 默认回退
- **路由原因**: 一行简短说明（如 "结构化特征不足，启用轻特征专用模型"）
- **置信提示**: 高 / 中 / 低

#### FR-FE-002: 与实验参考卡片兼容

- 保留 v1.24 的"实验参考 3" adapter 卡片
- v1.25 lite 结果作为新的实验参考展示区
- 明确标注"本结果来自 mmpsy-lite 专用模型，仅供参考"

### 3.5 评估与验证

#### FR-EVAL-001: 内部验证

- 5-Fold 分层 CV（StratifiedKFold(n_splits=5, shuffle=True, random_state=42)），每折内部独立进行文本特征提取和标准化；校准通过 CalibratedClassifierCV(cv=5) 在 CV 内完成，无需独立 calibration set
- 最终测试集: 从全量数据中分层抽取 15%（random_state=42），在整个训练/校准过程中保持隔离，仅用于最终评估
- 报告 AUC, F1, Precision, Recall, Specificity
- 报告 Brier Score（校准质量）
- 生成混淆矩阵

#### FR-EVAL-002: 亚组验证

- 按 PHQ-9 严重度分层（0–4, 5–9, 10–14, 15–19, 20–27）
- 按 GAD-7 严重度分层
- 按性别分层
- 按文本长度/质量分层
- 每个亚组报告完整的分类指标

#### FR-EVAL-003: 外部对照

- v1.25 lite 模型 vs v1.23 结构化模型（同 mmpsy cohort）
- v1.25 lite 模型 vs 纯 PHQ-9/GAD-7 规则基线
- 必须进行统计显著性检验（McNemar / DeLong）

---

## 四、非功能性需求 (Non-Functional Requirements)

| 维度 | 要求 |
|------|------|
| 推理延迟 | < 50ms / 样本 (P95) |
| 模型大小 | < 500KB (序列化) |
| 可用性 | 模型加载失败 → 自动回退 v1.20，日志记录 |
| 可复现性 | 固定 random_state，记录超参数 |
| 向后兼容 | 不影响现有 v1.20/v1.23/v1.24 路径 |
| 部署 | 纯 CPU，不需要 CUDA / GPU |
| 文档 | 训练过程记录完整，特征公式可追溯 |

---

## 五、明确排除范围 (Out of Scope)

| 排除项 | 原因 |
|------|------|
| ❌ 继续给 v1.23 做 mmpsy 特征映射补丁 | v1.24 已证明覆盖率 50%，再补收益有限 |
| ❌ 把 structured 和 lite 混成一个模型 | 输入分布差异大，两边都做不好 |
| ❌ 直接把 v1.25 设为 default | 新模型需灰度验证，不应替代主力 |
| ❌ 重型深度学习模型（BERT, LLM） | 样本量不足（1275），过拟合风险高 |
| ❌ 多分类风险等级 | v1.25 聚焦二分类，多分类由结构化主模型承担 |

---

## 六、验收标准 (Acceptance Criteria)

### 6.1 模型性能阈值

| 指标 | v1.25 lite 目标 | 对照: v1.23 在 mmpsy 上 |
|------|:---:|:---:|
| AUC | **≥ 0.80** | 0.6249 |
| Recall | **≥ 0.75** | 0.6860 |
| Specificity | **≥ 0.65** | 0.4887 |
| F1 | ≥ 0.60 | 0.3707 |
| Pearson r | ≥ 0.50 | 0.2151 |
| Spearman ρ | ≥ 0.40 | 0.1239 |
| Brier | **≤ 0.18** | — |

**统计要求**:
- 显著性水平: α = 0.05
- 模型对比: McNemar 检验（分类）或 DeLong 检验（AUC）
- 多重比较（≥3 个模型对比）: Bonferroni 校正 α' = α / N_comparisons
- 亚组验证: N_min ≥ 30（不足 30 的亚组仅报告描述性统计，不做统计推断）

### 6.2 路由验收

| 条件 | 标准 |
|------|------|
| 路由决策正确性 | 特征覆盖率 ≥ 80% → structured; GAD-7 + 文本 ≥ 20字符 → lite; 仅 GAD-7 → anxiety_only; 否则 → insufficient |
| 回退安全性 | 模型加载失败 → 自动回退，不影响默认评分 |
| 监控数据完整性 | routing distribution 写入 snapshot |

### 6.3 Go/No-Go 决门槛（Phase 6 最终判定）

| 维度 | 条件 |
|------|------|
| mmpsy-like AUC | ≥ 0.80 |
| Recall | ≥ 0.75 |
| Specificity | ≥ 0.65 |
| 亚组稳定性 | 主要亚组无明显崩溃 |
| 路由逻辑 | 规则清晰可复现 |
| 失败回退 | 经过验证且可用 |

---

## 七、风险与假设 (Risks & Assumptions)

| 风险 | 等级 | 缓解 |
|------|:---:|------|
| mmpsy 样本量小 (1275) | 🔴 高 | 简单模型优先，K-Fold CV 防过拟合 |
| 文本质量参差不齐 | 🟡 中 | 关键词检测 + 缺失标记作为特征 |
| 标签可靠性（PHQ-9 自评） | 🟡 中 | 以 phq9_binary 为主标签，PHQ-9 ≥ 15 为辅助 |
| 路由切换衔接 bug | 🟡 中 | 路由逻辑独立测试，灰度上线 |

### 关键假设

1. mmpsy 1275 样本足以训练轻量 LR/GBDT（< 5000 参数）
2. GAD-7 + 文本关键词 + 人口学 能够达到 AUC ≥ 0.80（不使用 PHQ-9 作为输入）
3. 文本转录质量足够提取关键词信号
4. 路由阈值 80% 合理（后续可根据监控数据调整）

---

## 八、依赖与前置条件

| 依赖 | 状态 |
|------|:---:|
| v1.24 adapter 已交付 | ✅ |
| v1.23 external_lr 模型可加载 | ✅ |
| mmpsy 数据集可用 (N=1275) | ✅ |
| model_registry 五态生命周期就绪 | ✅ |
| monitoring snapshot 通道可用 | ✅ |
| mmpsy 结构化特征 CSV 已产出 | ✅ (v1.24 Phase 1) |

---

> **下一步**: 进入架构设计阶段 (02-architecture.md)
