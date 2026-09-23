# v1.25 Learnings (全三轮)

> **轮次**: Round 1 (基线) → Round 2 (修订) → Round 3 (终定)
> **锁定日期**: 2026-05-02

---

## Round 1: 关键发现

### 1.1 mmpsy 无独立临床标签 (最大约束)

mmpsy 数据集的 9 列中，全部标签（phq9_binary, phq9_level, gad7_binary, gad7_level）均直接派生自同一份 PHQ-9/GAD-7 评分。这意味着：

- **不能**用 phq9_score 做特征 + phq9_binary 做标签（循环依赖）
- v1.25 的价值命题需从"替代 PHQ-9"调整为"文本+GAD-7 互补 PHQ-9"
- 特征集必须排除 phq9_score，仅用 GAD-7 + 文本 + 人口学

### 1.2 无 PHQ-9/GAD-7 子条目

仅 total score 可用。无法使用逐题细分信号。这简化了特征工程但丢失了粒度。

### 1.3 文本质量良好

全部 1275 条 audio_transcript 非空，长度 41-3991 字符，可直接用于关键词提取。无需处理空文本降级。

### 1.4 结构化特征映射已耗尽

12 个 v1.23 特征中，6 个可由 PHQ-9/GAD-7 线性派生（stress_level, anxiety 等），6 个完全缺失（social_support, financial_pressure, family_history 等）。继续做特征映射已无意义。

---

## 2. 待 Round 2 修复的问题

| ID | 问题 | 优先级 |
|:---|------|:---:|
| C1 | 标签-特征循环依赖 → 重构为 "GAD-7+文本 预测 phq9_binary" | 🔴 |
| C2 | fallback 路径行为不确定 → 定义"信息不足"协议 | 🔴 |
| C3 | calibration set 需求 vs 小数据集 → 采用 CalibratedClassifierCV | 🔴 |
| G1 | 文本质量边界已确认良好，可降级为低优先级 | — |
| G2 | 缺失处理策略 → 需明确 L2 可选字段的缺失填充规则 | 🟡 |
| G3 | confidence_band 计算逻辑 → 需定义规则 | 🟡 |
| G4 | 条目粒度 → 已确认不可用，不需再讨论 | — |
| I1 | Brier 阈值收紧到 ≤ 0.18 | 🟢 |
| I2 | 统计检验 α=0.05 + Bonferroni | 🟢 |
| I3 | 亚组 N_min ≥ 30 | 🟢 |
| I4 | Ablation study 需求 | 🟢 |
| I5 | Snapshot 滚动策略: 保留最近 1000 条 | 🟢 |

---

## 3. Round 2 方向

1. **重构标签策略**: 特征=GAD-7+文本+人口学, 标签=phq9_binary
2. **定义清晰 fallback 协议**: 三档降级路径
3. **明确校准在 CV 内的实现方式**
4. **补全 confidence_band 和缺失填充规则**

---

## Round 2: 修订与自查

### 2.1 Round 2 Draft 修订内容

全部 Round 1 的 Critical (C1-C3)、Major (G2-G3)、Minor (I1-I5) 问题已修复：
- C1: 特征集排除 phq9_score，标签使用 phq9_binary ✅
- C2: 三档降级路径 (structured → lite → anxiety_only → insufficient) ✅
- C3: CalibratedClassifierCV(cv=5) 在 CV 内校准 ✅
- G2-G3: L2 缺失填充规则、confidence_band 已定义 ✅
- I1-I5: Brier ≤0.18, α=0.05+Bonferroni, N_min≥30, Ablation, Snapshot滚动 ✅

### 2.2 Round 2 Critique 发现 (R1-R5)

| ID | 问题 | 优先级 |
|:---|------|:---:|
| R1 | §2.1 输入类型仍含 PHQ-9（与 §2.3 排除原则冲突） | 🟡 |
| R2 | §七风险表残留旧列名 depression_binary → 应为 phq9_binary | 🟡 |
| R3 | §七假设2 残留 "PHQ-9 + GAD-7 + 文本" → 应为 "GAD-7 + 文本" | 🟡 |
| R4 | §6.2 路由验收表引用旧逻辑 "+ PHQ-9/GAD-7 → lite" | 🟡 |
| R5 | §FR-EVAL-001 划分策略模糊 ("8:1:1 或 K-Fold") → 应统一 | 🟢 |

### 2.3 Round 2 调研发现

- **mmpsy_scores.csv**: 9列 (user_id, phq9/gad7总分/标签, audio_count, audio_transcript), N=1275, 文本41-3991字符
- **mmpsy_structured_features.csv**: 14特征，6个缺失(social_support/financial_pressure等均imputed)，6个衍生
- **model_registry.py**: v1.20/21/23/24已注册，无 lite 模型
- **model_engine.py**: predict_structured()无路由分支，需新增 predict_lite()
- **text_analyzer.py**: 现有6+4关键词类与需求§2.3的7类不匹配，需新建 lite 提取器

### 2.4 Round 2 推演结论

四种路由场景全部可达，但实现代价不同：
- structured: ✅ 已有代码
- lite: ⚠️ 需新建 predict_lite() + lite 关键词提取器
- anxiety_only: ⚠️ 需新建 GAD-7 经验映射规则
- insufficient: ✅ 简单 error 返回

---

## Round 3: 终定

### 3.1 R1-R5 修复清单

| ID | 修复位置 | 修复内容 |
|:---|------|------|
| R1 | §2.1 第43行 | "PHQ-9 总分 + GAD-7 总分 + 音频转录" → "GAD-7 总分 + 音频转录/文本摘要（PHQ-9 作为外部验证参照，不作为模型输入）" |
| R2 | §七 第329行 | "depression_binary" → "phq9_binary" |
| R3 | §七 第335行 | "PHQ-9 + GAD-7 + 文本关键词" → "GAD-7 + 文本关键词 + 人口学" |
| R4 | §6.2 第307行 | "否则 + PHQ-9/GAD-7 → lite" → "GAD-7 + 文本 ≥ 20字符 → lite; 仅 GAD-7 → anxiety_only; 否则 → insufficient" |
| R5 | §FR-EVAL-001 第235-236行 | 明确为 "5-Fold StratifiedKFold + 15% Hold-out Test Set" |

### 3.2 判定: 需求文档可进入架构设计

01-requirements.md 经过三轮审查，全文一致性问题清零，可交付架构设计。

---

## 02-architecture.md 三轮审查

### Round 1: 基线 Draft

**文档结构** (对齐 v1.24 模式):
- 系统边界与定位: 四轨道全景图 (structured/lite/anxiety_only/insufficient)
- 模块架构: 4 Phase 依赖与数据流 + 9 模块清单
- 核心模块详细设计: Phase 0-4 伪代码级设计
- 文件系统布局 + API 接口影响 + 安全与回退设计

### Round 1 Critique 发现

| ID | 问题 | 优先级 |
|:---|------|:---:|
| C1 | 特征维度 18→17 (计数错误) | 🔴 |
| C2 | `predict_fusion()` lite 路由兼容性未定义 | 🔴 |
| M1 | structured 路径未显式追加 routing_info | 🟡 |
| M2 | predict_lite() 伪代码缺 numpy import | 🟡 |

### Round 2: 修订

全部 Round 1 问题已修复:
- C1: 统一为 17 维 (LITE_FEATURE_ORDER 实际 17 个字段)
- C2: §3.5.4 Fusion 路径兼容性说明 (最小公共子集)
- M1: structured 路径追加 `result["routing_info"] = routing_info`
- M2: 添加 `import numpy as np` 声明
- Minor: §5.2 合法 JSON + §8 v1.24 路由描述修正

### Round 3: 终定 → Locked

判定: 02-architecture.md 全文一致，无遗留问题，可交付 03-design.md。

### 架构文档关键决策

1. **路由入侵点**: `predict_structured()` 入口（非新增端点），f_coverage < 80% 时早期返回 lite 结果
2. **LiteFeatureExtractor**: 内嵌在 model_engine.py 中，与 TextAnalyzer 独立，避免循环依赖
3. **17维特征空间**: GAD-7(1) + 关键词总数(2) + 人口学(3) + 7类计数(7) + 文本质量(4) = 17
4. **四层回退**: structured → lite → anxiety_only → insufficient
5. **PHQ-9 防泄漏**: 五层防护 (特征提取/模型输入/API入口/路由分派/代码审查)

---

## 03-design.md 三轮审查

### Round 1: 基线 Draft

文档结构 (对齐 v1.24 模式):
- 4 个脚本详细规格: 00_data_audit, 01_build_lite_features, 02_train_lite_model, 03_ablation_study
- model_engine.py 6 个修改点 (LITE_FEATURE_ORDER, LiteFeatureExtractor, predict_lite, _anxiety_only_fallback, 路由分派, routing_info 追加)
- model_registry.py + Schema + Service + 前端 + Config 修改规格
- 统计常量 + 错误处理矩阵

### Round 1 Critique 发现

| ID | 问题 | 优先级 |
|:---|------|:---:|
| M1 | §1.4 `compute_bootstrap_p` 函数体未定义 | 🟡 |
| M2 | §1.3 相关性计算索引错误 (未记录 test_indices) | 🟡 |
| M3 | §1.4 跨脚本引用 `MODEL_FEATURES` 常量 | 🟡 |

### Round 2: 修订

全部 3 项已修复:
- M1: 补充完整的 Bootstrap AUC 差异检验函数骨架 (H0/H1, n_bootstrap=1000, p = max(1e-4, mean(auc_diff<0)))
- M2: train_test_split 返回 idx_test; pearsonr/spearmanr 直接使用 df[].values[idx_test]
- M3: 03_ablation_study.py 独立从 mmpsy_lite_feature_names.json 读取 MODEL_FEATURES

### Round 3: 终定 → Locked

判定: 03-design.md 全文一致，4 脚本 × 6 engine 修改 × 3 app 层修改 × 4 前端辅助函数 × 9 错误处理条目全部对齐。

### v1.25 规划阶段完成总结

| 文档 | 轮次 | 状态 |
|------|:---:|:---:|
| 01-requirements.md | Round 1→2→3 | ✅ Locked |
| 02-architecture.md | Round 1→2→3 | ✅ Locked |
| 03-design.md | Round 1→2→3 | ✅ Locked |
| 04-ralph-tasks.md | — | ⏳ 待创建 |
| 05-test-plan.md | — | ⏳ 待创建 |

**规划阶段 3/5 文档已锁定**，下一步进入任务拆解 (04-ralph-tasks.md)。

---

## 04-ralph-tasks.md & 05-test-plan.md

### 任务列表

22 个任务，按 8 Phase 分组:
- Phase 0: 数据审计 (1 任务)
- Phase 1: 文本特征工程 (2 任务)
- Phase 2: 模型训练 (4 任务)
- Phase 3: 消融实验 (3 任务)
- Phase 4: model_engine 路由改造 (4 任务)
- Phase 5: 注册表注册 (1 任务)
- Phase 6: Schema + Service (2 任务)
- Phase 7: 前端改造 (3 任务)
- Phase 8: 配置项 (1 任务)

### 测试计划

29 个测试用例，对齐 8 Phase:
- 省去 Round 1-3 审查，直接锁定 (测试用例源自设计文档的验收标准，无新增逻辑)

---

## v1.25 规划阶段全量交付

| 文档 | 轮次 | 状态 | 产出行数 |
|------|:---:|:---:|:---:|
| 01-requirements.md | R1→R2→R3 | ✅ Locked | ~350 行 |
| 02-architecture.md | R1→R2→R3 | ✅ Locked | ~650 行 |
| 03-design.md | R1→R2→R3 | ✅ Locked | ~700 行 |
| 04-ralph-tasks.md | 直接锁定 | ✅ Locked | ~150 行 |
| 05-test-plan.md | 直接锁定 | ✅ Locked | ~210 行 |

### 规划阶段统计

- **总行数**: ~2060 行
- **修复问题**: 20 项 (Round 1: C1-C3, G1-G3, I1-I5; Round 2: R1-R5, C1-C2, M1-M2; Round 3: M1-M3)
- **发现类别**: 🔴 Critical × 5 | 🟡 Major × 9 | 🟢 Minor × 6
- **跨文档一致性修正**: 13 处 (PHQ-9泄漏、标签名、维度计数、路由逻辑、划分策略、JSON合法性、跨脚本引用、索引错误、Fusion兼容性、置信度等)

### 关键设计决策回顾

1. **特征排除 PHQ-9**: 五层防泄漏 (需求/架构/设计三层对齐)
2. **四档降级路由**: structured → lite → anxiety_only → insufficient
3. **17维特征空间**: GAD-7(1) + 关键词(9) + 人口学(3) + 文本质量(4)
4. **CalibratedClassifierCV 内校准**: 避免 5-Fold CV 外额外划分 calibration set
5. **LiteFeatureExtractor 独立**: 与现有 TextAnalyzer 解耦，内嵌 model_engine.py
6. **路由早期返回**: f_coverage < 80% 时从 predict_structured 早期返回，不执行 structured 全路径

---

> **v1.25 规划阶段全量完成** | 就绪进入 Implementation Phase
