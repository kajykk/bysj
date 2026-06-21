# v1.25 详细设计：mmpsy-lite 轻特征专用风险模型

> **版本**: v1.25 | **日期**: 2026-05-02 | **基线**: Round 3 Final — Locked
> **前置**: [01-requirements.md](file:///e:/code/bysj/docs/planning/v1.25-mmpsy-lite-risk-model/01-requirements.md), [02-architecture.md](file:///e:/code/bysj/docs/planning/v1.25-mmpsy-lite-risk-model/02-architecture.md)

---

## 一、脚本详细规格

### 1.1 `00_data_audit.py`

```
位置: backend/scripts/modeling/v1_25/00_data_audit.py
执行: python 00_data_audit.py

依赖:
  - pandas, pathlib (标准库)

常量:
  PROJECT_ROOT = Path(__file__).resolve().parents[3]

  REQUIRED_ASSETS = [
      ("mmpsy原始数据", "data/external/mmpsy_scores.csv"),
      ("mmpsy结构化特征", "data/processed/mmpsy_structured_features.csv"),
  ]

  # 基线统计 (用于一致性校验)
  BASELINE = {
      "n_rows": 1275,
      "n_cols": 9,
      "phq9_min": 0, "phq9_max": 27,
      "gad7_min": 0, "gad7_max": 21,
      "text_min_len": 41, "text_max_len": 3991,
      "positive_count": 258,
      "negative_count": 1017,
      "positive_ratio": 0.202,    # 容差 ±0.02
      "unique_users": 1275,
  }

函数:
  verify_mmpsy_scores(path: Path) -> dict:
      1. df = pd.read_csv(path)
      2. 验证: len(df) == BASELINE["n_rows"]
      3. 验证: set(df.columns) == {"user_id","phq9_score","phq9_level",
            "phq9_binary","gad7_score","gad7_level","gad7_binary",
            "audio_count","audio_transcript"}
      4. 验证: df["phq9_score"].between(0,27).all()
      5. 验证: df["gad7_score"].between(0,21).all()
      6. 验证: df["audio_transcript"].notna().all()
      7. 验证: df["audio_transcript"].str.len().between(41,3991).all()
         (如有个别越界，仅警告不报错)
      8. 标签一致性:
         derived = (df["phq9_score"] >= 10).astype(int)
         mismatch = (df["phq9_binary"] != derived).sum()
         如 mismatch > 0: 报告异常
      9. 阳性率: actual = df["phq9_binary"].mean()
         if abs(actual - BASELINE["positive_ratio"]) > 0.02: 警告
      10. user_id 唯一性: df["user_id"].nunique() == 1275
      11. 返回 {检查项: 结果} 字典

  verify_structured_features(path: Path) -> dict:
      1. df = pd.read_csv(path)
      2. 验证 row count = 1275
      3. 验证 _source 列存在 (14 个)
      4. 统计 derived vs imputed 比例
      5. 返回汇总

main():
  1. 逐资产检查，生成状态表
  2. 输出 data_audit_report.md:
     表头: | 资产 | 检查项 | 状态 | 实际值 | 基线值 | 备注 |
     底部: 汇总 (通过 / 总数)
  3. 如有 🔴 Critical 项，print 警告但不阻断 (仅报告)

输出文件:
  docs/planning/v1.25-mmpsy-lite-risk-model/data_audit_report.md
```

### 1.2 `01_build_lite_features.py`

```
位置: backend/scripts/modeling/v1_25/01_build_lite_features.py
执行: python 01_build_lite_features.py

依赖:
  - pandas, re (标准库)
  - 不依赖 jieba, sklearn

常量:
  KEYWORD_CATEGORIES = {
      "academic_pressure": [
          "挂科","退学","考研","论文","毕业","导师",
          "考试","成绩","作业","学习","背书","中考","高考",
          "学业","老师","周测",
      ],
      "sleep_problem": [
          "失眠","熬夜","早醒","嗜睡","噩梦",
          "睡不着","睡不好","多梦","彻夜难眠","整夜没睡",
      ],
      "social_withdrawal": [
          "独处","回避","不想说话","孤僻",
          "不想见人","不想出门","孤立","一个人",
      ],
      "self_harm_crisis": [
          "自残","自杀","想死","割腕","安眠药",
          "不想活","活不下去","死了算了","结束生命",
          "跳楼","上吊",
      ],  # 隐含权重 ×2 (计数时加倍)
      "exercise_deficit": [
          "不运动","躺着","不出门","宅",
      ],
      "low_mood": [
          "难过","绝望","空虚","麻木","没意义",
          "低落","沮丧","郁闷","痛苦","没意思",
      ],
      "anxiety_somatic": [
          "心慌","胸闷","发抖","出汗","窒息",
          "紧张","不安","害怕","担心",
      ],
  }

  # 人口学默认值 (mmpsy 数据集全部缺失，统一填充)
  DEMO_DEFAULTS = {"age": 25.0, "gender": 1, "cgpa": 3.1}

函数:
  chinese_ratio(text: str) -> float:
      chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
      return chinese / max(len(text), 1)

  check_text_quality(text: str) -> int:
      length = len(text)
      cr = chinese_ratio(text)
      if length < 20:     return 0   # 文本太短
      if cr < 0.30:       return 1   # 非中文主流
      return 2                        # 正常

  extract_keywords(text: str) -> dict:
      result = {"keyword_counts": {}, "total_keywords": 0, "crisis_weighted": 0}
      for cat, keywords in KEYWORD_CATEGORIES.items():
          count = sum(text.count(kw) for kw in keywords)
          if cat == "self_harm_crisis":
              count *= 2  # 危机词加权
              result["crisis_weighted"] = count
          result["keyword_counts"][cat] = count
          result["total_keywords"] += count
      result["unique_categories"] = sum(
          1 for v in result["keyword_counts"].values() if v > 0
      )
      return result

main():
  1. df = pd.read_csv("data/external/mmpsy_scores.csv")

  2. 逐行处理:
     features_list = []
     for _, row in df.iterrows():
         text = row["audio_transcript"]
         kw = extract_keywords(text)
         quality = check_text_quality(text)
         length = len(text)

         features = {
             "user_id":           row["user_id"],
             "gad7_score":        float(row["gad7_score"]),
             "phq9_score":        float(row["phq9_score"]),   # 仅保存，不作为模型输入
             "phq9_binary":       int(row["phq9_binary"]),
             "age":               DEMO_DEFAULTS["age"],
             "gender":            DEMO_DEFAULTS["gender"],
             "cgpa":              DEMO_DEFAULTS["cgpa"],
             "total_keywords":    kw["total_keywords"],
             "unique_categories": kw["unique_categories"],
             "text_length":       length,
             "chinese_ratio":     round(chinese_ratio(text), 4),
             "text_quality_flag": quality,
             "crisis_weighted":   kw["crisis_weighted"],
             "coverage_density":  round(kw["total_keywords"] / max(length, 1) * 100, 2),
         }
         # 7 类关键词计数
         for cat in KEYWORD_CATEGORIES:
             features[f"kw_{cat}"] = kw["keyword_counts"].get(cat, 0)

         features_list.append(features)

  3. df_out = pd.DataFrame(features_list)

  4. 保存 lite_features.csv

  5. 生成 lite_feature_report.md:
     - 总样本: N
     - 文本质量分布 (flag 0/1/2 计数)
     - 关键词覆盖率: 各类命中率 (%)
     - total_keywords 分布: mean, median, P10, P90
     - unique_categories 分布

输出文件:
  data/processed/lite_features.csv (1275 × 20 列)
  docs/planning/v1.25-mmpsy-lite-risk-model/lite_feature_report.md
```

### 1.3 `02_train_lite_model.py`

```
位置: backend/scripts/modeling/v1_25/02_train_lite_model.py
执行: python 02_train_lite_model.py

依赖:
  - pandas, numpy, sklearn (LogisticRegression, StandardScaler,
    CalibratedClassifierCV, StratifiedKFold, train_test_split,
    roc_auc_score, f1_score, precision_score, recall_score,
    confusion_matrix, brier_score_loss)
  - scipy.stats (pearsonr, spearmanr)
  - joblib, json, matplotlib

常量:
  RANDOM_STATE = 42
  TEST_SIZE = 0.15
  CV_SPLITS = 5
  LR_C = 1.0
  LR_MAX_ITER = 1000
  CLASS_WEIGHT = "balanced"

  # 模型输入特征 (17 维，不含 phq9_score)
  MODEL_FEATURES = [
      "gad7_score", "total_keywords", "unique_categories",
      "age", "gender", "cgpa",
      "kw_academic_pressure", "kw_sleep_problem",
      "kw_social_withdrawal", "kw_self_harm_crisis",
      "kw_exercise_deficit", "kw_low_mood", "kw_anxiety_somatic",
      "text_length", "chinese_ratio",
      "text_quality_flag", "coverage_density",
  ]

  # 排除字段 (保存在 CSV 但不作为模型输入)
  EXCLUDED_FIELDS = ["phq9_score", "phq9_binary", "user_id", "crisis_weighted"]

  # Go/No-Go 阈值
  GO_THRESHOLDS = {
      "auc": 0.80, "recall": 0.75, "specificity": 0.65,
      "f1": 0.60, "brier": 0.18,
  }

main():
  1. df = pd.read_csv("data/processed/lite_features.csv")
     X = df[MODEL_FEATURES].values
     y = df["phq9_binary"].values

  2. Hold-out split:
     X_train_val, X_test, y_train_val, y_test, idx_train, idx_test = (
         train_test_split(
             X, y, np.arange(len(y)),
             test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE
         )
     )

  3. 标准化 (仅在训练集拟合):
     scaler = StandardScaler()
     scaler.fit(X_train_val)
     X_train_val_scaled = scaler.transform(X_train_val)
     X_test_scaled = scaler.transform(X_test)

  4. 5-Fold CV + 校准:
     base_lr = LogisticRegression(
         C=LR_C, max_iter=LR_MAX_ITER, class_weight=CLASS_WEIGHT,
         random_state=RANDOM_STATE
     )
     cv = StratifiedKFold(n_splits=CV_SPLITS, shuffle=True, random_state=RANDOM_STATE)
     calibrated = CalibratedClassifierCV(
         base_lr, method="isotonic", cv=cv
     )
     calibrated.fit(X_train_val_scaled, y_train_val)

  5. 测试集评估 (仅最终报告，不用于模型选择):
     y_proba = calibrated.predict_proba(X_test_scaled)[:, 1]
     y_pred = calibrated.predict(X_test_scaled)

     metrics = {
         "auc":      roc_auc_score(y_test, y_proba),
         "f1":       f1_score(y_test, y_pred),
         "precision": precision_score(y_test, y_pred),
         "recall":    recall_score(y_test, y_pred),
         "brier":     brier_score_loss(y_test, y_proba),
     }
     tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
     metrics["specificity"] = tn / (tn + fp)

     # 相关性 (与 phq9_score 对照，使用保存的测试集索引)
     phq9_test = df["phq9_score"].values[idx_test]
     r, _ = pearsonr(y_proba, phq9_test)
     rho, _ = spearmanr(y_proba, phq9_test)
     metrics["pearson_r"] = r
     metrics["spearman_rho"] = rho

  6. Go/No-Go 判定:
     go = all(
         metrics[k] >= GO_THRESHOLDS[k]
         for k in ["auc", "recall", "specificity"]
     ) and metrics["brier"] <= GO_THRESHOLDS["brier"]
     metrics["go_decision"] = go

  7. 备选模型: LightGBM (P1) — try/except ImportError
     try:
         import lightgbm as lgb
         lgb_base = lgb.LGBMClassifier(
             max_depth=3, n_estimators=50, min_child_samples=20,
             class_weight="balanced", random_state=RANDOM_STATE,
             verbose=-1,
         )
         lgb_calibrated = CalibratedClassifierCV(
             lgb_base, method="isotonic", cv=cv
         )
         lgb_calibrated.fit(X_train_val_scaled, y_train_val)
         lgb_proba = lgb_calibrated.predict_proba(X_test_scaled)[:, 1]
         metrics["gbdt_auc"] = roc_auc_score(y_test, lgb_proba)
         metrics["gbdt_f1"] = f1_score(y_test, lgb_calibrated.predict(X_test_scaled))
         # 保存 GBDT
         joblib.dump(lgb_calibrated, "backend/models/v1.25_mmpsy_lite/mmpsy_lite_model_gbdt.pkl")
     except (ImportError, Exception) as exc:
         logger.warning("LightGBM not available: %s", exc)

  8. 序列化:
     os.makedirs("backend/models/v1.25_mmpsy_lite", exist_ok=True)
     joblib.dump(calibrated, "backend/models/v1.25_mmpsy_lite/mmpsy_lite_model.pkl")
     joblib.dump(scaler, "backend/models/v1.25_mmpsy_lite/mmpsy_lite_scaler.pkl")
     with open("backend/models/v1.25_mmpsy_lite/mmpsy_lite_feature_names.json", "w") as f:
         json.dump(MODEL_FEATURES, f, indent=2)
     with open("backend/models/v1.25_mmpsy_lite/mmpsy_lite_metrics.json", "w") as f:
         json.dump(metrics, f, indent=2)

  9. 图表:
     - ROC 曲线 → mmpsy_lite_roc_curve.png
     - 混淆矩阵热力图 → mmpsy_lite_confusion_matrix.png
     - 校准曲线 → mmpsy_lite_calibration_curve.png
     (plt.savefig, dpi=150)

  10. 生成训练报告 (含 Go/No-Go 判定)

输出文件:
  backend/models/v1.25_mmpsy_lite/mmpsy_lite_model.pkl
  backend/models/v1.25_mmpsy_lite/mmpsy_lite_model_gbdt.pkl   (可选)
  backend/models/v1.25_mmpsy_lite/mmpsy_lite_scaler.pkl
  backend/models/v1.25_mmpsy_lite/mmpsy_lite_feature_names.json
  backend/models/v1.25_mmpsy_lite/mmpsy_lite_metrics.json
  docs/planning/v1.25-mmpsy-lite-risk-model/mmpsy_lite_roc_curve.png
  docs/planning/v1.25-mmpsy-lite-risk-model/mmpsy_lite_confusion_matrix.png
  docs/planning/v1.25-mmpsy-lite-risk-model/mmpsy_lite_calibration_curve.png
  docs/planning/v1.25-mmpsy-lite-risk-model/mmpsy_lite_training_report.md
```

### 1.4 `03_ablation_study.py`

```
位置: backend/scripts/modeling/v1_25/03_ablation_study.py
执行: python 03_ablation_study.py

依赖:
  - pandas, numpy, sklearn, scipy.stats

常量:
  CV = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
  ALPHA = 0.05
  ALPHA_CORRECTED = 0.005  # Bonferroni: 0.05/10

  # 完整 17 维特征 (从 mmpsy_lite_feature_names.json 读取或硬编码)
  MODEL_FEATURES = json.load(
      open("backend/models/v1.25_mmpsy_lite/mmpsy_lite_feature_names.json")
  )

  ABLATION_CONFIGS = [
      {"id": "A", "name": "PHQ-9 Only (upper bound)",
       "features": ["phq9_score"]},
      {"id": "B", "name": "GAD-7 Only (anxiety baseline)",
       "features": ["gad7_score"]},
      {"id": "C", "name": "Text Keywords Only",
       "features": [
           "kw_academic_pressure","kw_sleep_problem","kw_social_withdrawal",
           "kw_self_harm_crisis","kw_exercise_deficit","kw_low_mood",
           "kw_anxiety_somatic","total_keywords","unique_categories",
       ]},
      {"id": "D", "name": "GAD-7 + Text (v1.25 core)",
       "features": [
           "gad7_score",
           "kw_academic_pressure","kw_sleep_problem","kw_social_withdrawal",
           "kw_self_harm_crisis","kw_exercise_deficit","kw_low_mood",
           "kw_anxiety_somatic","total_keywords","unique_categories",
       ]},
      {"id": "E", "name": "GAD-7 + Text + Demo (v1.25 full)",
       "features": MODEL_FEATURES},  # 17 维全量
  ]

main():
  1. df = pd.read_csv("data/processed/lite_features.csv")
     y = df["phq9_binary"].values

  2. 对每个配置:
     results[config["id"]] = {"name": config["name"], "metrics": {}}
     X = df[config["features"]].values

     cv_scores = {"auc": [], "f1": [], "recall": [], "specificity": []}
     for train_idx, val_idx in CV.split(X, y):
         X_train, X_val = X[train_idx], X[val_idx]
         y_train, y_val = y[train_idx], y[val_idx]

         scaler = StandardScaler().fit(X_train)
         X_train_s = scaler.transform(X_train)
         X_val_s = scaler.transform(X_val)

         model = LogisticRegression(
             C=1.0, max_iter=1000, class_weight="balanced", random_state=42
         ).fit(X_train_s, y_train)
         y_proba = model.predict_proba(X_val_s)[:, 1]
         y_pred = model.predict(X_val_s)

         cv_scores["auc"].append(roc_auc_score(y_val, y_proba))
         cv_scores["f1"].append(f1_score(y_val, y_pred))
         cv_scores["recall"].append(recall_score(y_val, y_pred))
         tn, fp, fn, tp = confusion_matrix(y_val, y_pred).ravel()
         cv_scores["specificity"].append(tn / (tn + fp))

     for metric, scores in cv_scores.items():
         results[config["id"]]["metrics"][metric] = {
             "mean": np.mean(scores), "std": np.std(scores),
         }

  3. 统计检验:
     comparisons = [("D","B"), ("E","B"), ("D","C"), ("E","C")]
     for a_id, b_id in comparisons:
         bootstrap_p = compute_bootstrap_p(
             df, ABLATION_CONFIGS[a_id], ABLATION_CONFIGS[b_id], y
         )
         results[f"{a_id}_vs_{b_id}"] = {
             "p_value": bootstrap_p,
             "significant": bootstrap_p < ALPHA_CORRECTED,
         }

函数:
  compute_bootstrap_p(df, cfg_a, cfg_b, y, n_bootstrap=1000) -> float:
      """Bootstrap AUC 差异检验。
      
      原假设 H0: AUC(cfg_b) >= AUC(cfg_a)
      备择假设 H1: AUC(cfg_a) > AUC(cfg_b)
      
      步骤:
      1. Xa = df[cfg_a["features"]].values
         Xb = df[cfg_b["features"]].values
      2. 对 i in range(n_bootstrap):
           idx = np.random.choice(len(y), len(y), replace=True)
           train_a = LogisticRegression(...).fit(Xa[idx], y[idx])
           train_b = LogisticRegression(...).fit(Xb[idx], y[idx])
           auc_diff[i] = roc_auc(oob) - roc_auc(oob)
      3. p = max(1e-4, (auc_diff < 0).mean())
      4. 返回 p
      """

  4. 保存 ablation_results.json

  5. 生成 ablation_report.md:
     - 表格: 配置 | AUC | F1 | Recall | Specificity (mean±std)
     - 标出最优配置 (最高 AUC)
     - 统计检验结论

输出文件:
  docs/planning/v1.25-mmpsy-lite-risk-model/ablation_results.json
  docs/planning/v1.25-mmpsy-lite-risk-model/ablation_report.md
```

---

## 二、model_engine.py 修改规格

### 2.1 修改点汇总

| # | 位置 | 类型 | 内容 |
|---|------|------|------|
| M1 | 文件顶部 (import 后) | 新增 | `LITE_FEATURE_ORDER` 列表定义 (17 元素) |
| M2 | 文件顶部 | 新增 | `LiteFeatureExtractor` 类 (约 60 行) |
| M3 | 类尾 (`_build_intervention_plan` 后) | 新增 | `predict_lite()` 方法 (约 80 行) |
| M4 | 类尾 | 新增 | `_anxiety_only_fallback()` 方法 (约 20 行) |
| M5 | `predict_structured()` L505 | 插入 | 路由决策逻辑 (约 80 行) |
| M6 | `predict_structured()` L756 | 追加 | `result["routing_info"] = routing_info` |

### 2.2 M1: LITE_FEATURE_ORDER

```python
# 位置: 在 model_engine.py 文件顶部，feature_order 定义之后
LITE_FEATURE_ORDER = [
    "gad7_score", "total_keywords", "unique_categories",
    "age", "gender", "cgpa",
    "kw_academic_pressure", "kw_sleep_problem",
    "kw_social_withdrawal", "kw_self_harm_crisis",
    "kw_exercise_deficit", "kw_low_mood", "kw_anxiety_somatic",
    "text_length", "chinese_ratio",
    "text_quality_flag", "coverage_density",
]
```

### 2.3 M2: LiteFeatureExtractor

```python
# 位置: 文件顶部，class ModelEngine 之前
class LiteFeatureExtractor:
    """v1.25 专用关键词提取器，内嵌在 model_engine.py 中避免引入新依赖。"""

    KEYWORD_CATEGORIES: dict[str, list[str]] = {
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
        ],
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

    @staticmethod
    def _chinese_ratio(text: str) -> float:
        chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        return chinese / max(len(text), 1)

    @staticmethod
    def extract(transcript: str) -> dict:
        total = 0
        categories = 0
        counts: dict[str, int] = {}

        for cat, keywords in LiteFeatureExtractor.KEYWORD_CATEGORIES.items():
            c = sum(transcript.count(kw) for kw in keywords)
            if cat == "self_harm_crisis":
                c *= 2  # 危机词加权
            counts[cat] = c
            total += c
            if c > 0:
                categories += 1

        return {
            "keyword_counts": counts,
            "total_keywords": total,
            "unique_categories": categories,
        }
```

### 2.4 M3: predict_lite()

```python
# 位置: 在 _build_intervention_plan 之后，ModelEngine 类内部
async def predict_lite(
    self,
    gad7_score: float,
    audio_transcript: str,
    age: float | None = None,
    gender: int | None = None,
    cgpa: float | None = None,
) -> dict[str, Any]:

    async with self._timed_async("predict", "lite"):
        import numpy as np

        length = len(audio_transcript)
        chinese_c = sum(
            1 for c in audio_transcript if '\u4e00' <= c <= '\u9fff'
        )
        chinese_r = chinese_c / max(length, 1)

        # 文本太短 → 直接回退
        if length < 20:
            logger.warning(
                "Lite model: text too short (%d chars), "
                "falling back to anxiety_only", length
            )
            return self._anxiety_only_fallback(gad7_score)

        # 关键词提取
        extractor = LiteFeatureExtractor()
        kw = extractor.extract(audio_transcript)

        # 构建特征向量
        feature_dict: dict[str, float] = {
            "gad7_score": gad7_score,
            "total_keywords": float(kw["total_keywords"]),
            "unique_categories": float(kw["unique_categories"]),
            "age": age if age is not None else 25.0,
            "gender": float(gender if gender is not None else 1),
            "cgpa": cgpa if cgpa is not None else 3.1,
            "text_length": float(length),
            "chinese_ratio": round(chinese_r, 4),
        }

        for cat in LiteFeatureExtractor.KEYWORD_CATEGORIES:
            feature_dict[f"kw_{cat}"] = float(kw["keyword_counts"].get(cat, 0))

        if length < 20:
            feature_dict["text_quality_flag"] = 0.0
        elif chinese_r < 0.30:
            feature_dict["text_quality_flag"] = 1.0
        else:
            feature_dict["text_quality_flag"] = 2.0

        feature_dict["coverage_density"] = (
            kw["total_keywords"] / max(length, 1) * 100
        )

        # 模型推理
        try:
            model = self._load_model("mmpsy_lite_model")
            scaler = self._load_model("mmpsy_lite_scaler")

            feature_array = np.array(
                [[feature_dict.get(f, 0.0) for f in LITE_FEATURE_ORDER]],
                dtype=float,
            )
            scaled = scaler.transform(feature_array)
            proba = await asyncio.to_thread(model.predict_proba, scaled)
            probability = float(proba[0][1])
            prediction = 1 if probability >= 0.5 else 0
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
                "Lite model unavailable: %s, falling back to anxiety_only",
                exc,
            )
            return self._anxiety_only_fallback(gad7_score)
```

### 2.5 M4: _anxiety_only_fallback()

```python
# 位置: predict_lite 之后
def _anxiety_only_fallback(self, gad7_score: float) -> dict:
    estimated = min(gad7_score * 1.29, 27.0)
    risk_score = round(estimated / 27.0 * 100, 2)
    prediction = 1 if risk_score >= 50 else 0
    probability = risk_score / 100.0

    logger.info(
        "Anxiety-only fallback: gad7=%.1f -> score=%.2f",
        gad7_score, risk_score,
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

### 2.6 M5 + M6: 路由决策 (predict_structured 改造)

```python
# ── 修改 predict_structured() 方法 ──
# 在现有 L505 ("async with self._timed_async...") 之后立即插入:

async def predict_structured(
    self, features: dict[str, float | int | str | bool]
) -> dict[str, Any]:
    import numpy as np
    import pandas as pd

    async with self._timed_async("predict", "structured"):
        raw: dict[str, Any] = dict(features)

        # ──────── v1.25 路由决策 ────────
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

        gad7 = raw.get("gad7_score", None)
        transcript = raw.get("audio_transcript") or raw.get("text", "")

        routing_info = {
            "selected_model_id": None,
            "selected_model_family": None,
            "routing_reason": None,
            "feature_coverage_ratio": round(f_coverage, 4),
            "prediction_confidence_band": None,
        }

        if f_coverage >= 0.80:
            routing_info["selected_model_id"] = (
                "structured_logistic_regression_v1.20"
            )
            routing_info["selected_model_family"] = "structured"
            routing_info["routing_reason"] = (
                "feature_coverage_sufficient"
            )
            routing_info["prediction_confidence_band"] = (
                "high" if f_coverage >= 0.90 else "medium"
            )
            # ▼ 继续现有 L440-756 全部逻辑 ▼
            # (原有代码不动 —— model/fallback/scaler/experimental 路径全部保持)

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
            lite_result["routing_info"] = routing_info
            return lite_result  # ← 早期返回，不执行 structured 路径

        elif gad7 is not None:
            routing_info["selected_model_family"] = "anxiety_only"
            routing_info["routing_reason"] = "only_gad7_available"
            routing_info["prediction_confidence_band"] = "low"

            fb = self._anxiety_only_fallback(float(gad7))
            fb["routing_info"] = routing_info
            return fb

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
                "warning": (
                    "信息不足以评估风险，"
                    "请提供 GAD-7 评分或结构化特征"
                ),
            }

        # ──────── 路由决策结束 ────────

        # === 以下为 # structured 路径的原有代码 (L440-756) ===
        # model = None
        # model_used = "structured_logistic_regression_quick"
        # ...

# ── M6: 在 result 构建完成后 (L756 附近)、return result 前追加 ──
result["routing_info"] = routing_info
```

---

## 三、model_registry.py 修改规格

### 3.1 修改点

| # | 位置 | 类型 | 内容 |
|---|------|------|------|
| R1 | MODEL_PATHS dict | 新增 3 条目 | mmpsy_lite_model, mmpsy_lite_scaler, mmpsy_lite_gbdt |
| R2 | MODEL_REGISTRY 后 | 新增 2 条目 | mmpsy_lite_model, mmpsy_lite_scaler |

### 3.2 完整代码块

```python
# ── R1: MODEL_PATHS 新增 ──
MODEL_PATHS["mmpsy_lite_model"] = (
    "models/v1.25_mmpsy_lite/mmpsy_lite_model.pkl"
)
MODEL_PATHS["mmpsy_lite_scaler"] = (
    "models/v1.25_mmpsy_lite/mmpsy_lite_scaler.pkl"
)
MODEL_PATHS["mmpsy_lite_gbdt"] = (
    "models/v1.25_mmpsy_lite/mmpsy_lite_model_gbdt.pkl"
)

# ── R2: MODEL_REGISTRY 新增 ──
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

---

## 四、Schema 修改规格

> **修改文件**: `backend/app/schemas/model_predict.py`

```python
# ── 在文件末尾追加 ──

class RoutingInfo(BaseModel):
    """v1.25 模型路由透明化信息"""
    selected_model_id: str | None = Field(
        default=None, description="实际使用的模型 ID"
    )
    selected_model_family: str | None = Field(
        default=None, description="模型家族: structured/lite/fallback"
    )
    routing_reason: str | None = Field(
        default=None, description="路由原因"
    )
    feature_coverage_ratio: float | None = Field(
        default=None, description="特征覆盖率 (0.0-1.0)"
    )
    prediction_confidence_band: str | None = Field(
        default=None, description="置信区间: high/medium/low"
    )
```

---

## 五、Service 层修改规格

> **修改文件**: `backend/app/services/model_predict_service.py`

```python
# ── predict_tabular 方法修改 ──
async def predict_tabular(
    self, features: dict[str, float | int | str | bool]
) -> dict:
    sanitized: dict[str, float | int | str | bool] = {}
    for key, value in features.items():
        sanitized[key] = value

    result = await model_engine.predict_structured(sanitized)

    # ── v1.25 新增: 路由决策日志 ──
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

---

## 六、前端修改规格

### 6.1 modelApi.ts

```typescript
// ── 接口定义 ──
export interface RoutingInfo {
  selected_model_id: string | null;
  selected_model_family: string | null;   // 'structured' | 'lite' | 'fallback'
  routing_reason: string | null;          // e.g. 'feature_coverage_sufficient'
  feature_coverage_ratio: number | null;  // 0.0 - 1.0
  prediction_confidence_band: string | null; // 'high' | 'medium' | 'low'
}

// ── ModelPredictResponse 中追加: ──
routing_info: RoutingInfo | null;  // v1.25 新增
```

### 6.2 UserRiskPage.vue

```html
<!--
  插入位置: 现有"风险评估结果"区域 (<el-card>) 顶部，
  即在 risk_score 显示之前。
-->

<!-- v1.25: 路由透明展示 -->
<div v-if="modelTabResult?.routing_info"
     style="margin-bottom: 12px; padding: 8px 12px;
            background: #f0f9ff; border: 1px solid #d9ecff;
            border-radius: 6px; font-size: 13px; color: #606266">
  <el-icon style="margin-right: 4px"><InfoFilled /></el-icon>
  <span>
    本次评估:
    <strong>{{
      routeFamilyLabel(modelTabResult.routing_info.selected_model_family)
    }}</strong>
  </span>
  <span style="margin: 0 8px; color: #c0c4cc">|</span>
  <span>
    {{ routeReasonLabel(modelTabResult.routing_info.routing_reason) }}
  </span>
  <el-tag
    v-if="modelTabResult.routing_info.prediction_confidence_band"
    :type="confidenceTagType(
      modelTabResult.routing_info.prediction_confidence_band
    )"
    size="small" effect="plain" style="margin-left: 8px">
    置信度: {{
      confidenceLabel(
        modelTabResult.routing_info.prediction_confidence_band
      )
    }}
  </el-tag>
</div>

<!-- v1.25: 实验参考 3 -->
<div
  v-if="modelTabResult?.routing_info?.selected_model_family === 'lite'"
  style="margin-top: 16px; padding: 12px;
         border: 1px dashed #e6a23c; border-radius: 6px;
         background: #fdf6ec">
  <h4 style="margin: 0 0 8px; font-size: 14px; color: #e6a23c">
    实验参考 3 — v1.25 mmpsy-lite 专用模型
  </h4>
  <p v-if="modelTabResult?.risk_score != null" style="margin: 0; font-size: 13px">
    Lite 风险分:
    <strong style="color: #303133">
      {{ modelTabResult.risk_score.toFixed(2) }}
    </strong>
  </p>
  <p v-if="modelTabResult?.probability != null" style="margin: 4px 0 0; font-size: 13px">
    高风险概率:
    <strong style="color: #303133">
      {{ (modelTabResult.probability * 100).toFixed(1) }}%
    </strong>
  </p>
  <p style="margin: 8px 0 0; font-size: 11px; color: #909399">
    ⚠️ 本结果来自 v1.25 mmpsy-lite 专用模型（基于 GAD-7 + 文本关键词），
    仅供参考，不作为临床诊断依据。
  </p>
</div>
```

```typescript
// ── script setup 新增辅助函数 ──

const routeFamilyLabel = (family: string | null): string => {
  const map: Record<string, string> = {
    structured: "结构化模型 (v1.20)",
    lite: "轻特征专用模型 (v1.25)",
    anxiety_only: "GAD-7 参考评估",
    fallback: "备用规则",
    insufficient: "信息不足",
  };
  return family ? map[family] || family : "未知";
};

const routeReasonLabel = (reason: string | null): string => {
  const map: Record<string, string> = {
    feature_coverage_sufficient:
      "结构化特征完整，使用主力模型",
    feature_coverage_insufficient_text_available:
      "结构化特征不足，启用轻特征专用模型",
    only_gad7_available:
      "仅 GAD-7 可用，使用参考评估",
    insufficient_information:
      "信息不足以评估风险",
  };
  return reason ? map[reason] || reason : "";
};

const confidenceTagType = (band: string | null) => {
  if (band === "high") return "success";
  if (band === "medium") return "warning";
  return "info";
};

const confidenceLabel = (band: string | null): string => {
  if (band === "high") return "高";
  if (band === "medium") return "中";
  return "低";
};
```

---

## 七、配置项新增

> **修改文件**: `backend/app/core/config.py`

```python
# ── v1.25 路由配置 ──
ROUTE_FEATURE_COVERAGE_THRESHOLD: float = 0.80  # 结构化路由阈值
ROUTE_LITE_MIN_TEXT_LENGTH: int = 20             # lite 路由最低文本长度
```

> **读取方式**: 在 model_engine.py 中 `from app.core.config import settings`，使用 `settings.ROUTE_FEATURE_COVERAGE_THRESHOLD`。

---

## 八、统计常量

### 8.1 显著性水平

| 参数 | 值 | 说明 |
|------|:---:|------|
| α (主检验) | 0.05 | 单次比较显著性水平 |
| α' (Bonferroni) | 0.005 | 0.05 / 10 比较 |
| Bootstrap iterations | 1000 | DeLong 检验 Bootstrap 次数 |
| CV splits | 5 | StratifiedKFold |
| Hold-out test ratio | 0.15 | 测试集比例 |

### 8.2 亚组最小样本量

```
N_min = 30  # 不足 30 的亚组仅报告描述性统计，不做统计推断
```

### 8.3 文本质量标记

| Flag | 含义 | 触发条件 |
|:---:|------|------|
| 0 | 文本过短 | length < 20 chars |
| 1 | 非中文主流 | chinese_ratio < 0.30 |
| 2 | 正常 | 其他情况 |

### 8.4 GAD-7 经验映射

```
PHQ-9_estimated = min(GAD-7 × 1.29, 27.0)
risk_score = PHQ-9_estimated / 27.0 × 100

系数来源: PHQ-9 满分 27 / GAD-7 满分 21 ≈ 1.2857 ≈ 1.29
```

---

## 九、错误处理矩阵

| 模块 | 错误类型 | 处理方式 |
|------|---------|----------|
| 00_data_audit | mmpsy CSV 不存在 | 报告 ❌，不阻断 |
| 00_data_audit | 标签一致性校验失败 | 报告 ⚠️，不阻断 |
| 01_build_lite | audio_transcript 全部非空已确认 | — |
| 01_build_lite | 个别样本关键词提取异常 | try/except per row，标记到质量列 |
| 02_train_lite | LightGBM ImportError | 跳过 GBDT，LR 仍正常训练 |
| 02_train_lite | Go/No-Go 不通过 | 保存模型但标记 metrics.go_decision=false |
| 03_ablation | scipy 不可用 | DeLong test 降级为 Bootstrap |
| predict_lite | mmpsy_lite_model 加载失败 | → _anxiety_only_fallback(gad7) |
| predict_lite | audio_transcript < 20 chars | → _anxiety_only_fallback(gad7) |
| predict_lite | scaler.transform shape mismatch | AssertionError → fallback |
| 路由决策 | gad7_score 存在但为 None/"" | 视为不存在，跳过 lite/anxiety 分支 |
| 路由决策 | f_coverage 计算过于严格 (空字符串) | "" 和 None 同样视为缺失 |
| model_registry | mmpsy_lite_model 未找到 | get_model_info → None, is_model_enabled → True |
| frontend | routing_info 为 null (旧版 API) | v-if 自动隐藏，不影响展示 |

---

> **Round 3 Final — Locked** | 下一步: 任务拆解 (04-ralph-tasks.md) + 测试计划 (05-test-plan.md)
