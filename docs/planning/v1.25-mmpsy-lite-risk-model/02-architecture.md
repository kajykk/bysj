# v1.25 架构设计：mmpsy-lite 轻特征专用风险模型

> **版本**: v1.25 | **日期**: 2026-05-02 | **基线**: Round 3 Final — Locked
> **前置**: [01-requirements.md](file:///e:/code/bysj/docs/planning/v1.25-mmpsy-lite-risk-model/01-requirements.md) Round 3 Locked

---

## 一、系统边界与定位

### 1.1 v1.25 在系统中的位置

```
┌──────────────────────────────────────────────────────────────┐
│                         系统全景                               │
│                                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│  │ v1.20    │  │ v1.23    │  │ v1.24    │  │ v1.25 (新增)  │ │
│  │ Synth LR │  │ Ext LR   │  │ Adapter  │  │ mmpsy-lite    │ │
│  │ default  │  │ experim. │  │ candid.  │  │ candidate     │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘ │
│       │              │             │               │         │
│       ▼              ▼             ▼               ▼         │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                  model_engine.py                        │  │
│  │  predict_structured()                                   │  │
│  │    ├─ L440-520: v1.20 主路径 (不动)                     │  │
│  │    ├─ L530-563: v1.21 实验路径 (lifecycle 检查)         │  │
│  │    ├─ L565-604: v1.23 实验路径 (external LR)            │  │
│  │    ├─ L606-687: v1.24 Adapter 路径                      │  │
│  │    └─ [新增]: v1.25 路由分派 → predict_lite()           │  │
│  │                                                          │  │
│  │  [新增] predict_lite() — 轻特征专用预测                  │  │
│  │    ├─ 特征提取: LiteFeatureExtractor (7类关键词)         │  │
│  │    ├─ 模型推理: mmpsy_lite_model.pkl (LR/GBDT)           │  │
│  │    └─ 回退: GAD-7 heuristic (anxiety_only)              │  │
│  └────────────────────────────────────────────────────────┘  │
│         │                                                     │
│         ▼                                                     │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                    API Response                          │  │
│  │  routing_info: { selected_model_id, routing_reason,     │  │
│  │    feature_coverage_ratio, prediction_confidence_band } │  │
│  │  lite_result: { score, level, model_family, ... }       │  │
│  │  (现有 structured/text/physiological 字段保持不变)       │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

**核心原则**:
1. v1.25 不替换任何现有路径，作为第三条模型轨道（structured → lite → fallback）并行运行
2. 路由逻辑在 `predict_structured()` 入口处根据特征可得性自动分派
3. lite 模型加载失败 → 自动回退 GAD-7 启发式规则（anxiety_only）

### 1.2 模型轨道总览

| 轨道 | 模型 | Lifecycle | 触发条件 |
|------|------|:---:|------|
| `structured` | v1.20 LR + v1.24 adapter (shadow) | `default` | 特征覆盖率 ≥ 80% |
| `lite` | v1.25 mmpsy-lite (LR/GBDT) | `candidate` | GAD-7 + 文本 ≥ 20 字符 |
| `anxiety_only` | GAD-7 经验映射规则 | `fallback` | 仅 GAD-7 可用 |
| `insufficient` | 无模型 | — | 信息不足以评估 |

---

## 二、模块架构

### 2.1 Phase 依赖与数据流

```
Phase 0: 数据审计
  │
  └──[mmpsy_scores.csv]──→ Phase 1: 文本特征工程 (lite 关键词提取)
                                │
                                ├──[lite_features.csv]──→ Phase 2: 模型训练 + 消融实验
                                │                              │
                                │                              └──[mmpsy_lite_model.pkl]
                                │                                     │
                                └──[关键词覆盖率报告]                       │
                                                                       │
Phase 3: 路由层改造 ──────────────────────────────────────────────────┤
  │                                                                   │
  ├── model_engine.py: 新增 predict_lite() + 路由分派                    │
  ├── model_registry.py: 注册 v1.25 lite 模型                          │
  ├── model_predict_service.py: 透传 routing_info                      │
  └── schemas: 新增 LitePredictRequest/Response                        │
                                                                       │
Phase 4: 前端展示 ────────────────────────────────────────────────────┤
  │                                                                   │
  ├── modelApi.ts: 新增 lite 响应字段                                   │
  └── UserRiskPage.vue: 新增 "实验参考 3" 卡片                          │
```

### 2.2 模块清单

| 模块 | 类型 | 输入 | 输出 | 关键技术 |
|------|------|------|------|----------|
| data_audit | 脚本 | `mmpsy_scores.csv` | `data_audit_report.md` | pandas, pathlib |
| lite_feature_builder | 脚本 | `mmpsy_scores.csv` | `lite_features.csv` | re (正则) |
| lite_model_trainer | 脚本 | `lite_features.csv` | `mmpsy_lite_model.pkl` | sklearn, CalibratedClassifierCV |
| ablation_runner | 脚本 | `lite_features.csv` | `ablation_results.json` | sklearn, scipy.stats |
| model_engine_patch | 代码修改 | — | `model_engine.py` 新增 predict_lite() | Python |
| routing_patch | 代码修改 | — | `model_engine.py` 入口路由分派 | Python |
| registry_patch | 代码修改 | — | `model_registry.py` 注册 lite 模型 | Python dataclass |
| schema_patch | 代码修改 | — | `schemas/model_predict.py` | Pydantic |
| frontend_patch | 代码修改 | — | `modelApi.ts` + `UserRiskPage.vue` | TypeScript, Vue |

---

## 三、核心模块详细设计

### 3.1 Phase 0: 数据审计 (`scripts/v1_25/00_data_audit.py`)

```
功能: 验证 mmpsy 数据资产完整性
输入: data/external/mmpsy_scores.csv (1275 × 9)
      data/processed/mmpsy_structured_features.csv (1275 × 26)

检查项:
  1. mmpsy_scores.csv 行数 = 1275, 列数 = 9
  2. 字段验证:
     - user_id: 1275 唯一值
     - phq9_score: 0-27, 非空, 1275 条
     - gad7_score: 0-21, 非空, 1275 条
     - audio_transcript: 非空, 41-3991 字符
     - phq9_binary: 0/1, 阳性率 = 258/1275 ≈ 20.2%
  3. 标签一致性: phq9_binary = (phq9_score ≥ 10).astype(int) → 全部一致

输出: data_audit_report.md (含异常检测和修正建议)
```

### 3.2 Phase 1: 文本特征工程 (`scripts/v1_25/01_build_lite_features.py`)

```
输入: data/external/mmpsy_scores.csv (1275 × 9)

输出: lite_features.csv (1275 × 20+) — 供模型训练使用
      lite_feature_report.md — 关键词覆盖率统计

─────────────────────────────────────────────
LiteFeatureExtractor (与现有 TextAnalyzer 独立)
─────────────────────────────────────────────

class LiteFeatureExtractor:
    """v1.25 专用: 7 类关键词提取，对齐 01-requirements.md §FR-MODEL-001"""

    KEYWORD_CATEGORIES = {
        "academic_pressure": [
            "挂科", "退学", "考研", "论文", "毕业", "导师",
            "考试", "成绩", "作业", "学习", "背书", "中考", "高考",
            "学业", "老师", "周测",
        ],
        "sleep_problem": [
            "失眠", "熬夜", "早醒", "嗜睡", "噩梦",
            "睡不着", "睡不好", "多梦", "彻夜难眠", "整夜没睡",
        ],
        "social_withdrawal": [
            "独处", "回避", "不想说话", "孤僻",
            "不想见人", "不想出门", "孤立", "一个人",
        ],
        "self_harm_crisis": [
            "自残", "自杀", "想死", "割腕", "安眠药",
            "不想活", "活不下去", "死了算了", "结束生命",
            "跳楼", "上吊",
        ],  # 危机词加权 × 2
        "exercise_deficit": [
            "不运动", "躺着", "不出门", "宅",
        ],
        "low_mood": [
            "难过", "绝望", "空虚", "麻木", "没意义",
            "低落", "沮丧", "郁闷", "痛苦", "没意思",
        ],
        "anxiety_somatic": [
            "心慌", "胸闷", "发抖", "出汗", "窒息",
            "紧张", "不安", "害怕", "担心",
        ],
    }

    def extract(self, audio_transcript: str) -> dict:
        """
        返回:
        {
            "keyword_counts": {category: count},       # 7 类计数
            "keyword_density": {category: density},     # 密度 (count/len)
            "crisis_weighted": float,                   # 危机加权分
            "total_keywords": int,                      # 总匹配次数
            "unique_categories": int,                   # 命中类别数
            "text_length": int,                         # 字符数
            "chinese_ratio": float,                     # 中文字符占比
        }
        """
```

**特征向量化策略**:

```
L1 必选特征 (3):
  gad7_score             → float (0-21)
  total_keywords         → int
  unique_categories      → int (0-7)

L2 可选特征 (3):
  age                    → float (imputed=25)
  gender                 → int (0/1, imputed=1)
  cgpa                   → float (imputed=3.1)

L3 鲁棒特征 (9):
  keyword_counts[x7]     → int (7 个单类计数)
  text_length            → int
  chinese_ratio          → float (0.0-1.0)

文本质量标记:
  text_quality_flag      → int (0=short<20, 1=non-chinese<30%, 2=normal)
  coverage_density       → float (total_keywords / text_length * 100)

总计: 17 维特征向量
```

**文本质量边界处理**:

```python
def check_text_quality(transcript: str) -> dict:
    length = len(transcript)
    chinese_chars = sum(1 for c in transcript if '\u4e00' <= c <= '\u9fff')
    chinese_ratio = chinese_chars / max(length, 1)

    if length < 20:
        return {"flag": 0, "action": "zero_text_features"}
    if chinese_ratio < 0.30:
        return {"flag": 1, "action": "keyword_zero_stats_only"}
    return {"flag": 2, "action": "normal_extraction"}
```

### 3.3 Phase 2: 模型训练 (`scripts/v1_25/02_train_lite_model.py`)

```
输入: lite_features.csv (1275 × 18+)
标签: phq9_binary (258 Positive / 1017 Negative, ratio 0.202)

输出: mmpsy_lite_model.pkl (LR + 可选 GBDT)
      mmpsy_lite_scaler.pkl
      mmpsy_lite_feature_names.json
      mmpsy_lite_metrics.json
      mmpsy_lite_confusion_matrix.png
      mmpsy_lite_calibration_curve.png
      mmpsy_lite_roc_curve.png

─────────────────────────────────────────────
训练协议
─────────────────────────────────────────────

Step 1: Hold-out 测试集隔离
  X_train_val, X_test, y_train_val, y_test = train_test_split(
      X, y, test_size=0.15, stratify=y, random_state=42
  )

Step 2: 标准化 (仅在训练集拟合)
  scaler = StandardScaler().fit(X_train_val)
  → 保存为 mmpsy_lite_scaler.pkl

Step 3: 5-Fold CV 训练 + 校准
  base_model = LogisticRegression(C=1.0, max_iter=1000, class_weight='balanced')
  calibrated_model = CalibratedClassifierCV(
      base_model, method='isotonic', cv=StratifiedKFold(5, shuffle=True, random_state=42)
  )
  calibrated_model.fit(X_train_val_scaled, y_train_val)

Step 4: 测试集评估 (仅最终报告，不用于模型选择)
  y_pred = calibrated_model.predict(X_test_scaled)
  y_proba = calibrated_model.predict_proba(X_test_scaled)[:, 1]

  报告:
    - AUC, F1, Precision, Recall, Specificity
    - Brier Score
    - 混淆矩阵
    - Pearson r / Spearman ρ (predicted proba vs phq9_score)

Step 5: 备选模型 (P1)
  import lightgbm as lgb
  lgb_model = lgb.LGBMClassifier(
      max_depth=3, n_estimators=50, min_child_samples=20,
      class_weight='balanced', random_state=42
  )
  → 同样 CalibratedClassifierCV 包装
  → 保存为 mmpsy_lite_model_gbdt.pkl (如果可用)

Step 6: 模型序列化
  joblib.dump(calibrated_model, "mmpsy_lite_model.pkl")
  json.dump(feature_names, open("mmpsy_lite_feature_names.json", "w"))
  json.dump(metrics, open("mmpsy_lite_metrics.json", "w"))
```

**文件命名规范**:

```
backend/models/v1.25_mmpsy_lite/
├── mmpsy_lite_model.pkl          # 主模型 (LR, calibrated)
├── mmpsy_lite_model_gbdt.pkl     # 备选模型 (LightGBM, 可选)
├── mmpsy_lite_scaler.pkl         # StandardScaler
├── mmpsy_lite_feature_names.json  # 特征名列表
└── mmpsy_lite_metrics.json       # 评估指标
```

### 3.4 消融实验 (`scripts/v1_25/03_ablation_study.py`)

```
输入: lite_features.csv

输出: ablation_results.json
      ablation_report.md

─────────────────────────────────────────────
消融配置 (对齐 01-requirements.md §2.3 消融实验表)
─────────────────────────────────────────────

| 配置 ID | 特征集 | 期望 AUC |
|:---:|------|:---:|
| A | phq9_score → phq9_binary | 理论上限 (~0.95) |
| B | gad7_score → phq9_binary | 焦虑替代基线 |
| C | 文本关键词 (7类计数) | 纯文本信号 |
| D | gad7_score + 文本关键词 | v1.25 核心 |
| E | gad7_score + 文本 + age/gender/cgpa | v1.25 完整 |

每配置:
  - 5-Fold Stratified CV
  - 报告: AUC, F1, Recall, Specificity (mean ± std)
  - DeLong 检验: 配置 D/E vs 配置 B, 配置 D/E vs v1.23 on mmpsy

多重比较: Bonferroni 校正 α' = 0.05 / 10 = 0.005
```

### 3.5 Phase 3: 路由层改造

#### 3.5.1 model_engine.py — 新增 `predict_lite()`

> **修改文件**: `backend/app/core/model_engine.py`

```python
# ── v1.25 新增: LITE_FEATURE_ORDER ──
LITE_FEATURE_ORDER = [
    "gad7_score", "total_keywords", "unique_categories",
    "age", "gender", "cgpa",
    "kw_academic_pressure", "kw_sleep_problem",
    "kw_social_withdrawal", "kw_self_harm_crisis",
    "kw_exercise_deficit", "kw_low_mood", "kw_anxiety_somatic",
    "text_length", "chinese_ratio",
    "text_quality_flag", "coverage_density",
]


class LiteFeatureExtractor:
    """内嵌在 model_engine.py 中，避免引入新依赖"""
    # ... 关键词定义同 Phase 1 的 KEYWORD_CATEGORIES ...

    @staticmethod
    def extract(transcript: str) -> dict:
        # 1. 文本质量检测
        # 2. 关键词正则匹配
        # 3. 返回特征字典
        ...


async def predict_lite(
    self,
    gad7_score: float,
    audio_transcript: str,
    age: float | None = None,
    gender: int | None = None,
    cgpa: float | None = None,
) -> dict[str, Any]:
    """v1.25 轻特征专用模型预测。

    仅依赖 GAD-7 + 文本 + 人口学，不使用 phq9_score。
    """

    async with self._timed_async("predict", "lite"):
        import numpy as np  # 文件顶部已有 import，此处为显式声明

        # Step 1: 文本质量检测
        length = len(audio_transcript)
        chinese_chars = sum(
            1 for c in audio_transcript if '\u4e00' <= c <= '\u9fff'
        )
        chinese_ratio = chinese_chars / max(length, 1)

        if length < 20:
            # 文本太短 → 回退到 anxiety_only
            logger.warning(
                "Lite model: text too short (%d chars), "
                "falling back to anxiety_only", length
            )
            return self._anxiety_only_fallback(gad7_score)

        # Step 2: 关键词提取
        extractor = LiteFeatureExtractor()
        features = extractor.extract(audio_transcript)

        # Step 3: 构建特征向量
        feature_dict = {
            "gad7_score": gad7_score,
            "total_keywords": features["total_keywords"],
            "unique_categories": features["unique_categories"],
            "age": age if age is not None else 25.0,
            "gender": gender if gender is not None else 1,
            "cgpa": cgpa if cgpa is not None else 3.1,
            "text_length": length,
            "chinese_ratio": chinese_ratio,
        }

        # 关键词单类计数
        for cat_name in LiteFeatureExtractor.KEYWORD_CATEGORIES:
            feature_dict[f"kw_{cat_name}"] = features["keyword_counts"].get(
                cat_name, 0
            )

        # 文本质量标记
        if length < 20:
            feature_dict["text_quality_flag"] = 0
        elif chinese_ratio < 0.30:
            feature_dict["text_quality_flag"] = 1
        else:
            feature_dict["text_quality_flag"] = 2

        feature_dict["coverage_density"] = (
            features["total_keywords"] / max(length, 1) * 100
        )

        # Step 4: 模型推理
        try:
            model = self._load_model("mmpsy_lite_model")
            scaler = self._load_model("mmpsy_lite_scaler")

            feature_array = np.array(
                [[feature_dict.get(f, 0) for f in LITE_FEATURE_ORDER]],
                dtype=float,
            )
            scaled = scaler.transform(feature_array)
            proba = await asyncio.to_thread(
                model.predict_proba, scaled
            )
            probability = float(proba[0][1])
            prediction = int(proba[0][1] >= 0.5)
            risk_score = round(probability * 100, 2)

            return {
                "prediction": prediction,
                "probability": round(probability, 4),
                "risk_score": risk_score,
                "risk_level": self._score_to_level(risk_score),
                "model_used": "mmpsy_lite_model",
                "model_version": "v1.25",
                "model_family": "lite",
                "fallback_used": False,
            }

        except Exception as exc:
            logger.warning(
                "Lite model unavailable, falling back to "
                "anxiety_only: %s", exc
            )
            return self._anxiety_only_fallback(gad7_score)
```

#### 3.5.2 model_engine.py — 新增 `_anxiety_only_fallback()`

```python
def _anxiety_only_fallback(self, gad7_score: float) -> dict:
    """GAD-7 经验映射回退规则。

    PHQ-9 ≈ GAD-7 × 1.29 (经验比例)。
    注意: 此回退不提供概率，仅提供风险分。
    """
    estimated_phq9 = min(gad7_score * 1.29, 27.0)
    risk_score = round(estimated_phq9 / 27.0 * 100, 2)
    prediction = 1 if risk_score >= 50 else 0
    probability = risk_score / 100.0

    logger.info(
        "Anxiety-only fallback: gad7=%.1f → score=%.2f", gad7_score, risk_score
    )

    return {
        "prediction": prediction,
        "probability": round(probability, 4),
        "risk_score": risk_score,
        "risk_level": self._score_to_level(risk_score),
        "model_used": "anxiety_only_heuristic",
        "model_version": "v1.25",
        "model_family": "fallback",
        "fallback_used": True,
        "fallback_reason": "lite_model_unavailable_or_text_insufficient",
    }
```

#### 3.5.3 model_engine.py — 路由分派改造 (`predict_structured()` 入口)

> **修改位置**: `predict_structured()` 方法首部（L505 之前），增加路由决策逻辑。

```python
async def predict_structured(
    self, features: dict[str, float | int | str | bool]
) -> dict[str, Any]:
    import numpy as np
    import pandas as pd

    async with self._timed_async("predict", "structured"):
        raw: dict[str, Any] = dict(features)

        # ── v1.25 新增: 路由决策 ──
        # Step 1: 计算特征覆盖率
        STRUCTURED_FEATURE_SET = {
            "age", "gender", "study_year", "cgpa", "stress_level",
            "sleep_duration", "social_support", "financial_pressure",
            "family_history", "academic_pressure", "exercise_frequency",
            "anxiety", "panic_attack", "treatment_seeking",
        }
        available = sum(
            1 for f in STRUCTURED_FEATURE_SET
            if f in raw and raw[f] is not None and raw[f] != ""
        )
        f_coverage = available / len(STRUCTURED_FEATURE_SET)

        # Step 2: 路由
        gad7 = raw.get("gad7_score") or raw.get("gad7_score", None)
        transcript = raw.get("audio_transcript") or raw.get("text", "")

        routing_info = {
            "selected_model_id": None,
            "selected_model_family": None,
            "routing_reason": None,
            "feature_coverage_ratio": round(f_coverage, 4),
            "prediction_confidence_band": None,
        }

        if f_coverage >= 0.80:
            routing_info["selected_model_id"] = "structured_logistic_regression_v1.20"
            routing_info["selected_model_family"] = "structured"
            routing_info["routing_reason"] = "feature_coverage_sufficient"
            routing_info["prediction_confidence_band"] = (
                "high" if f_coverage >= 0.90 else "medium"
            )
            # 继续现有 structured 路径（L440-756 原逻辑不变）
            # ⚠️ 在现有 result 返回前追加:
            # result["routing_info"] = routing_info
        elif (
            gad7 is not None
            and transcript
            and len(str(transcript)) >= 20
        ):
            routing_info["selected_model_family"] = "lite"
            routing_info["routing_reason"] = (
                "feature_coverage_insufficient_text_available"
            )
            routing_info["prediction_confidence_band"] = "medium"

            lite_result = await self.predict_lite(
                gad7_score=float(gad7),
                audio_transcript=str(transcript),
                age=float(raw.get("age", 25)),
                gender=int(raw.get("gender", 1)),
                cgpa=float(raw.get("cgpa", 3.1)),
            )
            # 将 routing_info 合并到 lite_result
            lite_result["routing_info"] = routing_info
            return lite_result

        elif gad7 is not None:
            routing_info["selected_model_family"] = "anxiety_only"
            routing_info["routing_reason"] = "only_gad7_available"
            routing_info["prediction_confidence_band"] = "low"

            fallback_result = self._anxiety_only_fallback(float(gad7))
            fallback_result["routing_info"] = routing_info
            return fallback_result

        else:
            routing_info["selected_model_family"] = "insufficient"
            routing_info["routing_reason"] = "insufficient_information"
            routing_info["prediction_confidence_band"] = "low"

            return {
                "prediction": None,
                "probability": None,
                "risk_score": None,
                "risk_level": None,
                "model_used": None,
                "model_version": None,
                "fallback_used": True,
                "fallback_reason": "insufficient_information",
                "routing_info": routing_info,
                "warning": "信息不足以评估风险，请提供 GAD-7 评分或结构化特征",
            }
```

**路由阈值可配置化** (对齐 FR-ROUTE-002):

```python
# backend/app/core/config.py
# 新增配置项:
ROUTE_FEATURE_COVERAGE_THRESHOLD: float = 0.80  # 默认 80%
ROUTE_LITE_MIN_TEXT_LENGTH: int = 20             # lite 最低文本长度
```

#### 3.5.4 Fusion 路径兼容性

> `predict_fusion()` 在 [model_engine.py:L893](file:///e:/code/bysj/backend/app/core/model_engine.py#L893) 调用 `predict_structured()`。v1.25 的路由分派会改变 `predict_structured()` 的返回结构，需确保 fusion 兼容。

**问题**: fusion 中 structured 权重 0.55，读取 `structured_result["risk_score"]`。当路由到 lite 时，返回结构中 `risk_score` 仍然存在（含义一致：0-100 风险分），但缺少 `experimental_*` 字段。

**方案**: lite 返回结构与 structured 的最小公共子集兼容：

```python
# lite_result 必须包含（与 structured_result 对齐）:
{
    "risk_score": float,      # 0-100，fusion 权重计算需要
    "risk_level": int,        # 0-4
    "prediction": int,        # 0/1
    "probability": float,     # 0.0-1.0
    "model_used": str,
    "model_version": str,
    "fallback_used": bool,
    "routing_info": dict,     # v1.25 新增，fusion 忽略
}
```

fusion 路径中结构化的 `model_used` 字段用于展示，lite 的 `model_family` 和 `routing_info` 仅在 `predict_structured()` 的直接调用者可见，`predict_fusion()` 不感知路由细节。

### 3.6 模型注册表

> **修改文件**: `backend/app/core/model_registry.py`

```python
# ── MODEL_PATHS 新增 ──
MODEL_PATHS["mmpsy_lite_model"] = "models/v1.25_mmpsy_lite/mmpsy_lite_model.pkl"
MODEL_PATHS["mmpsy_lite_scaler"] = "models/v1.25_mmpsy_lite/mmpsy_lite_scaler.pkl"
MODEL_PATHS["mmpsy_lite_gbdt"] = "models/v1.25_mmpsy_lite/mmpsy_lite_model_gbdt.pkl"

# ── MODEL_REGISTRY 新增 ──
MODEL_REGISTRY["mmpsy_lite_model"] = ModelMetadata(
    name="mmpsy_lite_model",
    path="models/v1.25_mmpsy_lite/mmpsy_lite_model.pkl",
    version="v1.25",
    enabled=True,
    supports_fusion=False,
    lifecycle="candidate",
    feature_schema={
        "features": [
            "gad7_score", "total_keywords", "unique_categories",
            "age", "gender", "cgpa",
            "text_length", "chinese_ratio",
            "text_quality_flag", "coverage_density",
            # + 7 keyword category counts
        ],
        "input_features": 17,
        "model_type": "CalibratedClassifierCV(LogisticRegression)",
        "framework": "sklearn",
        "class_weight": "balanced",
        "excluded_inputs": ["phq9_score"],
        "label": "phq9_binary",
    },
    artifact_metadata={
        "training_date": "2026-05-02",
        "random_seed": 42,
        "dataset": "mmpsy",
        "dataset_size": 1275,
        "positive_ratio": 0.202,
    },
)

MODEL_REGISTRY["mmpsy_lite_scaler"] = ModelMetadata(
    name="mmpsy_lite_scaler",
    path="models/v1.25_mmpsy_lite/mmpsy_lite_scaler.pkl",
    version="v1.25",
    enabled=True,
    lifecycle="candidate",
)
```

### 3.7 API Schema 变更

> **修改文件**: `backend/app/schemas/model_predict.py`

```python
# ── 新增 LitePredictRequest ──
class LitePredictRequest(BaseModel):
    gad7_score: float = Field(..., ge=0, le=21, description="GAD-7 总分")
    audio_transcript: str = Field(
        ..., min_length=1, max_length=5000,
        description="音频转录文本"
    )
    age: float | None = Field(default=None, ge=10, le=100, description="年龄")
    gender: int | None = Field(default=None, ge=0, le=1, description="性别 0=女 1=男")
    cgpa: float | None = Field(default=None, ge=0, le=10, description="GPA")


class RoutingInfo(BaseModel):
    selected_model_id: str | None = None
    selected_model_family: str | None = None
    routing_reason: str | None = None
    feature_coverage_ratio: float | None = None
    prediction_confidence_band: str | None = None
```

**TabularPredictRequest 兼容**: 现有 `TabularPredictRequest.features: dict[str, Any]` 已支持传递 `gad7_score` 和 `audio_transcript`，无需新增 schema。路由决策在后端自动完成。

### 3.8 Service 层变更

> **修改文件**: `backend/app/services/model_predict_service.py`

```python
async def predict_tabular(
    self, features: dict[str, float | int | str | bool]
) -> dict:
    sanitized: dict[str, float | int | str | bool] = {}
    for key, value in features.items():
        sanitized[key] = value

    result = await model_engine.predict_structured(sanitized)

    # ── v1.25 新增: 路由日志 ──
    routing_info = result.get("routing_info", {})
    if routing_info:
        logger.info(
            "Model routing: family=%s reason=%s coverage=%.2f band=%s",
            routing_info.get("selected_model_family"),
            routing_info.get("routing_reason"),
            routing_info.get("feature_coverage_ratio", 0),
            routing_info.get("prediction_confidence_band"),
        )

    return result
```

### 3.9 前端改造

> **修改文件**: `frontend/src/api/modelApi.ts`, `frontend/src/views/user/UserRiskPage.vue`

**`modelApi.ts` — 新增 lite 路由字段**:

```typescript
export interface RoutingInfo {
  selected_model_id: string | null
  selected_model_family: string | null    // 'structured' | 'lite' | 'fallback'
  routing_reason: string | null
  feature_coverage_ratio: number | null
  prediction_confidence_band: string | null  // 'high' | 'medium' | 'low'
}

export interface ModelPredictResponse {
  // ... 现有字段不变 ...
  routing_info: RoutingInfo | null        // v1.25 新增
}
```

**`UserRiskPage.vue` — 新增路由透明展示 + 实验参考 3 卡片**:

```html
<!-- 在现有风险结果区域，增加路由信息行 -->
<div v-if="modelTabResult?.routing_info"
     style="margin-bottom: 12px; padding: 8px 12px;
            background: #f0f9ff; border-radius: 4px;
            font-size: 13px; color: #606266">
  <span>本次使用模型: <strong>{{
    routeFamilyLabel(modelTabResult.routing_info.selected_model_family)
  }}</strong></span>
  <span style="margin-left: 12px">
    路由原因: {{ modelTabResult.routing_info.routing_reason }}
  </span>
  <el-tag v-if="modelTabResult.routing_info.prediction_confidence_band"
          :type="confidenceBandTagType(...)"
          size="small" effect="plain" style="margin-left: 8px">
    置信度: {{
      confidenceBandLabel(modelTabResult.routing_info.prediction_confidence_band)
    }}
  </el-tag>
</div>

<!-- 实验参考 3: v1.25 lite 结果 (仅当路由到 lite 时显示) -->
<div v-if="modelTabResult?.routing_info?.selected_model_family === 'lite'"
     style="...">
  <h4>实验参考 3 — mmpsy-lite 专用模型</h4>
  <p v-if="modelTabResult?.risk_score != null">
    Lite 风险分: {{ modelTabResult.risk_score.toFixed(2) }}
  </p>
  <p style="font-size: 12px; color: #909399">
    本结果来自 v1.25 mmpsy-lite 专用模型，仅供参考
  </p>
</div>
```

---

## 四、文件系统布局

```
docs/planning/v1.25-mmpsy-lite-risk-model/
├── 01-requirements.md          ✅ Locked (Round 3)
├── 02-architecture.md           ← 本文件
├── 03-design.md                (待创建)
├── 04-ralph-tasks.md           (待创建)
├── 05-test-plan.md             (待创建)
├── 06-learnings.md

backend/
├── app/core/
│   ├── model_registry.py       (修改: 新增 mmpsy_lite_model 注册)
│   └── model_engine.py         (修改: 新增 predict_lite() + 路由分派 + LiteFeatureExtractor)
├── app/schemas/
│   └── model_predict.py        (修改: 新增 RoutingInfo, LitePredictRequest)
├── app/services/
│   └── model_predict_service.py(修改: 路由日志)
├── models/
│   └── v1.25_mmpsy_lite/       (新建)
│       ├── mmpsy_lite_model.pkl
│       ├── mmpsy_lite_scaler.pkl
│       ├── mmpsy_lite_feature_names.json
│       ├── mmpsy_lite_metrics.json
│       └── mmpsy_lite_model_gbdt.pkl  (可选)
└── scripts/modeling/v1_25/     (新建)
    ├── 00_data_audit.py
    ├── 01_build_lite_features.py
    ├── 02_train_lite_model.py
    └── 03_ablation_study.py

frontend/src/
├── api/modelApi.ts             (修改: 新增 RoutingInfo 接口)
└── views/user/UserRiskPage.vue (修改: 路由透明展示 + 实验参考 3)
```

---

## 五、API 接口影响

### 5.1 `/api/v1/model/predict/tabular` — 响应新增路由信息

```json
{
  "routing_info": {
    "selected_model_id": "mmpsy_lite_model",
    "selected_model_family": "lite",
    "routing_reason": "feature_coverage_insufficient_text_available",
    "feature_coverage_ratio": 0.1429,
    "prediction_confidence_band": "medium"
  },
  "risk_score": 62.5,
  "risk_level": 3,
  "prediction": 1,
  "probability": 0.625,
  "model_used": "mmpsy_lite_model",
  "model_version": "v1.25",
  "model_family": "lite",
  "fallback_used": false
}
```

### 5.2 路由到 structured 时 — 现有响应 + routing_info

```json
{
  "routing_info": {
    "selected_model_id": "structured_logistic_regression_v1.20",
    "selected_model_family": "structured",
    "routing_reason": "feature_coverage_sufficient",
    "feature_coverage_ratio": 0.8571,
    "prediction_confidence_band": "high"
  },
  "prediction": 0,
  "probability": 0.452,
  "risk_score": 45.2,
  "risk_level": 2,
  "model_used": "structured_logistic_regression_v1.20",
  "model_version": "v1.20",
  "fallback_used": false,
  "data_quality": {
    "missing_fields": [],
    "confidence_penalty": 0,
    "quality_level": "complete"
  }
}
```

### 5.3 路由到 insufficient 时

```json
{
  "routing_info": {
    "selected_model_family": "insufficient",
    "routing_reason": "insufficient_information",
    "feature_coverage_ratio": 0.0,
    "prediction_confidence_band": "low"
  },
  "risk_score": null,
  "risk_level": null,
  "warning": "信息不足以评估风险，请提供 GAD-7 评分或结构化特征"
}
```

### 5.4 `/api/v1/model/status` — 新增 lite 模型

```json
{
  "items": [
    "... 现有模型 ...",
    {
      "model_id": "mmpsy_lite_model",
      "path": "models/v1.25_mmpsy_lite/mmpsy_lite_model.pkl",
      "exists": true,
      "lifecycle": "candidate"
    }
  ]
}
```

---

## 六、安全与回退设计

### 6.1 三层回退链

```
L1: v1.20 default (structured)    → 始终可用，不受 v1.25 修改影响
L2: v1.25 lite model              → 加载失败 → L3
L3: anxiety_only heuristic         → 纯规则计算，无外部依赖
L4: insufficient                   → 不评分，明确告知用户信息不足
```

### 6.2 PHQ-9 防泄漏机制

| 层级 | 防护措施 |
|------|------|
| 特征提取 | `LiteFeatureExtractor` 不包含 `phq9_score` 字段 |
| 模型输入 | `LITE_FEATURE_ORDER` 不包含 `phq9_score` |
| API 入口 | `predict_lite()` 参数不接收 `phq9_score` |
| 路由分派 | routing 不检查 `phq9_score` 是否存在 |
| 代码审查 | training script 明确注释 "excluded_inputs = ['phq9_score']" |

### 6.3 不破坏原则

| 原则 | 保证方式 |
|------|----------|
| v1.20 主路径不变 | `predict_structured()` 在 `f_coverage >= 0.80` 时完整走旧代码路径 |
| API 向后兼容 | 仅追加 `routing_info` 字段，不删除/重命名现有字段 |
| 注册表向后兼容 | 新增条目，不修改现有模型 lifecycle |
| 前端向后兼容 | 新增条件渲染区块，不影响现有卡片展示 |

---

## 七、Phase 执行顺序依赖

```
Phase 0 (数据审计)
  │
  └──→ Phase 1 (文本特征工程)
          │
          ├──→ Phase 2a (模型训练)
          │       │
          │       └──→ Phase 2b (消融实验)
          │
          └──→ Phase 3 (路由层改造)
                  │
                  ├──→ Phase 3a (model_engine.py: predict_lite + 路由分派)
                  ├──→ Phase 3b (model_registry.py: 注册)
                  ├──→ Phase 3c (schemas: RoutingInfo)
                  └──→ Phase 3d (service: 日志)
                          │
                          └──→ Phase 4 (前端)
```

- Phase 2a ∥ Phase 3 (模型训练可与路由代码并行开发，接口约定先行)
- Phase 2b 依赖 Phase 2a 完成
- Phase 4 依赖 Phase 3 完成 (API 响应格式确定)

---

## 八、与 v1.24 的差异总结

| 维度 | v1.24 | v1.25 |
|------|------|------|
| 核心机制 | Score Adapter (分数映射) | 专用模型 (独立训练) |
| 数据依赖 | v1.23 模型 + delta 数据 | mmpsy 原生数据 |
| 特征空间 | 复用 v1.23 的 12 特征 (6 个 imputed) | 全新 17 维 (GAD-7 + 文本) |
| 模型类型 | Piecewise Monotonic 映射函数 | LR + CalibratedClassifierCV |
| 路由方式 | 仅 experimental shadow（v1.23 下游），无入口路由 | 四档入口路由 (structured/lite/anxiety/insufficient) |
| 系统侵入 | append-only (v1.23 下游) | 入口分派 (predict_structured 首部) |
| 生命周期 | candidate | candidate → 目标: 灰度验证后晋升 default (v1.2x) |

---

> **Round 3 Final — Locked** | 下一步: 进入详细设计阶段 (03-design.md)
