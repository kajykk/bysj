# v1.24 详细设计：外部一致性验证与风险评分迁移治理

> **版本**: v1.24 | **日期**: 2026-05-02 | **基线**: Round 3 Locked
> **前置**: [01-requirements.md](file:///e:/code/bysj/docs/planning/v1.24-mmpsy-external-consistency-and-score-stability/01-requirements.md), [02-architecture.md](file:///e:/code/bysj/docs/planning/v1.24-mmpsy-external-consistency-and-score-stability/02-architecture.md)

---

## 一、脚本详细规格

### 1.1 `00_asset_check.py`

```
位置: backend/scripts/modeling/v1_24/00_asset_check.py
执行: python 00_asset_check.py

常量:
  PROJECT_ROOT = Path(__file__).resolve().parents[3]
  
  ASSETS = [
      ("v1.23 model",        "backend/models/v1.23_external_lr/model.pkl"),
      ("v1.23 schema",       "backend/models/v1.23_external_lr/feature_schema.json"),
      ("v1.23 ext metrics",  "backend/models/v1.23_external_lr/external_validation_metrics.json"),
      ("v1.23 metrics",      "backend/models/v1.23_external_lr/metrics.json"),
      ("v1.23 delta csv",    "backend/models/v1.23_external_lr/model_delta_samples.csv"),
      ("mmpsy raw data",     "data/external/mmpsy_scores.csv"),
      ("v1.20 model",        "backend/models/artifacts/structured_v1.20/model.pkl"),
      ("model registry",     "backend/app/core/model_registry.py"),
      ("model engine",       "backend/app/core/model_engine.py"),
  ]

函数:
  check_asset(name, rel_path) -> bool:
      1. abs_path = PROJECT_ROOT / rel_path
      2. 检查 exists(), is_file()
      3. 返回 True/False
  
  verify_delta_csv(abs_path) -> dict:
      1. df = pd.read_csv(abs_path)
      2. 验证 len(df) == 4318
      3. 验证 "delta_v123_v120" in df.columns
      4. 验证 abs(df.delta_v123_v120).mean() ≈ 21.29 (容差 ±0.5)
      5. 返回 {"rows": n, "cols": n, "mean_abs_delta": x, "ok": bool}

  main():
      1. 遍历 ASSETS
      2. 每个资产: ok = check_asset(name, path)
      3. 对 delta csv: extra = verify_delta_csv(abs_path)
      4. 生成 asset_check_report.md:
          表头: | 资产 | 路径 | 状态 | 备注 |
          状态: ✅ / ❌
          底部: 汇总 (N_pass / N_total)
  
输出文件:
  docs/planning/v1.24-mmpsy-external-consistency-and-score-stability/asset_check_report.md
```

### 1.2 `01_build_mmpsy_features.py`

```
位置: backend/scripts/modeling/v1_24/01_build_mmpsy_features.py
执行: python 01_build_mmpsy_features.py

依赖:
  - pandas, re (标准库)
  - 不依赖 jieba

常量:
  CRISIS_WORDS = ["想死","不想活","自杀","自残","活不下去","死了算了","结束生命"]
  
  SLEEP_RULES = {
      "整夜没睡": 0, "彻夜难眠": 0,
      "失眠": 3, "睡不着": 3,
      "熬夜": 5, "睡眠不足": 5, "早醒": 5,
      "睡眠": 8, "睡得好": 8, "入睡": 8,
  }
  # 注意: "睡眠" 匹配需排除含否定词的 (如 "睡眠不足" 已在前面匹配)
  # 简化: 从高分到低分遍历，取 min；否定词天然被低分覆盖
  
  ACADEMIC_WORDS = ["考试","成绩","作业","学习","背书","中考","高考","学业","老师","周测"]
  EXERCISE_WORDS = ["跑步","打球","运动","散步","锻炼","篮球","足球","游泳","健身"]

函数:
  count_keywords(text: str, keywords: list[str]) -> int:
      对每个 kw in keywords: count += text.count(kw)
      返回 count
  
  check_crisis(text: str) -> int:
      for w in CRISIS_WORDS:
          if w in text: return 1
      return 0
  
  derive_sleep_duration(text: str, default: float) -> float:
      values = []
      for kw, val in SLEEP_RULES.items():
          if kw in text:
              values.append(val)
      return min(values) if values else default
  
  derive_stress(phq9: float) -> float:
      return phq9 / 27.0 * 5.0
  
  derive_anxiety(gad7: float) -> float:
      return gad7 / 21.0 * 5.0

main():
  1. df = pd.read_csv("data/external/mmpsy_scores.csv")
  2. schema = json.load("feature_schema.json")
  3. medians = {f["name"]: f["stats"]["median"] for f in schema["features"]}
  
  4. 构建特征矩阵:
     df_out = pd.DataFrame()
     df_out["age"]                = medians["age"]
     df_out["gender"]             = medians["gender"]
     df_out["cgpa"]               = medians["cgpa"]
     df_out["stress_level"]       = df["phq9_score"].apply(derive_stress)
     df_out["sleep_duration"]     = df["audio_transcript"].apply(derive_sleep_duration, default=medians["sleep_duration"])
     df_out["social_support"]     = medians["social_support"]
     df_out["financial_pressure"] = medians["financial_pressure"]
     df_out["family_history"]     = medians["family_history"]
     df_out["academic_pressure"]  = df["audio_transcript"].apply(lambda t: min(count_keywords(t, ACADEMIC_WORDS)*1.25, 5.0))
     df_out["exercise_frequency"] = df["audio_transcript"].apply(lambda t: min(count_keywords(t, EXERCISE_WORDS)/2.0, 3.0))
     df_out["anxiety"]            = df["gad7_score"].apply(derive_anxiety)
     df_out["panic_attack"]       = df["audio_transcript"].apply(check_crisis)
  
  5. 添加来源列: 每个特征加 _source (derived / imputed)
  6. 保存 mmpsy_structured_features.csv
  7. 生成 mmpsy_feature_mapping_report.md (含覆盖率统计)
  8. 生成 mmpsy_missingness_report.md

输出文件:
  data/processed/mmpsy_structured_features.csv (1275 × 12 + 12 _source 列)
  docs/planning/v1.24-mmpsy-external-consistency-and-score-stability/mmpsy_feature_mapping_report.md
  docs/planning/v1.24-mmpsy-external-consistency-and-score-stability/mmpsy_missingness_report.md
```

### 1.3 `02_validate_mmpsy.py`

```
位置: backend/scripts/modeling/v1_24/02_validate_mmpsy.py
执行: python 02_validate_mmpsy.py

依赖:
  - pandas, numpy, sklearn, matplotlib, scipy.stats, joblib

main():
  1. df = pd.read_csv("data/processed/mmpsy_structured_features.csv")
  2. pipeline = joblib.load("backend/models/v1.23_external_lr/model.pkl")
  
  3. 提取 12 特征列 (按 pipeline.feature_names_in_ 顺序排列)
     X = df[feature_names].values
     y_true = df["phq9_binary"].values  # ← 需要用实际列名
  
  4. 预测:
     y_prob = pipeline.predict_proba(X)[:, 1]
     y_pred = pipeline.predict(X)
  
  5. 主指标:
     auc = roc_auc_score(y_true, y_prob)
     precision, recall, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary")
     tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
     specificity = tn / (tn + fp)
  
  6. 相关性:
     phq9 = df["phq9_score"].values  # ← 实际列名
     gad7 = df["gad7_score"].values
     pearson_r, pearson_p = pearsonr(y_prob, phq9)
     spearman_rho, spearman_p = spearmanr(y_prob, gad7)
  
  7. 高风险召回:
     high_risk_mask = y_true == 1
     high_risk_recall = y_pred[high_risk_mask].mean()
  
  8. 有效特征子集基线:
     X_3 = df[["stress_level","anxiety","panic_attack"]].values
     cv_scores = cross_val_score(LogisticRegression(), X_3, y_true, cv=5, scoring="roc_auc")
     auc_3feature = cv_scores.mean()
     auc_gap = auc - auc_3feature
  
  9. 图表:
     - ROC 曲线 → mmpsy_roc_curve.png
     - 校准曲线 → mmpsy_calibration_curve.png
     (plt.savefig, dpi=150)
  
  10. 保存 metrics JSON 和生成报告

输出文件:
  docs/planning/v1.24-mmpsy-external-consistency-and-score-stability/mmpsy_external_validation_metrics.json
  docs/planning/v1.24-mmpsy-external-consistency-and-score-stability/mmpsy_external_validation_report.md
  docs/planning/v1.24-mmpsy-external-consistency-and-score-stability/mmpsy_roc_curve.png
  docs/planning/v1.24-mmpsy-external-consistency-and-score-stability/mmpsy_calibration_curve.png
```

### 1.4 `03_analyze_delta.py`

```
位置: backend/scripts/modeling/v1_24/03_analyze_delta.py
执行: python 03_analyze_delta.py

依赖: pandas, numpy, scipy.stats

main():
  1. df = pd.read_csv("backend/models/v1.23_external_lr/model_delta_samples.csv")
  
  2. Level 1 — 全局统计:
     delta = df["delta_v123_v120"]
     输出: N, mean, abs_mean, std, P10/25/50/75/90
     输出: (|d| > 15/20/30/40) 计数与比例
  
  3. Level 2 — 按 v1.20 风险等级:
     # 加载阈值配置
     thresholds = [18, 35, 55, 72]  # 从 threshold_config.json 读取
     df["risk_level"] = df["v120_risk"].apply(lambda x: digitize(x, thresholds))
     grouped = df.groupby("risk_level")["delta"].agg(["count","mean","std"])
     对每组: abs_mean = grouped["mean"].abs()
  
  4. Level 3 — 按 PHQ-9/GAD-7:
     phq9_bins = [0, 5, 10, 15, 20, 28]
     df["phq9_bin"] = pd.cut(df["phq9_score"], bins=phq9_bins)
     按 phq9_bin 分组统计 delta
  
  5. Level 4 — 按人群:
     按 age_group (pd.cut), gender, source 各自分组
  
  6. Level 5 — 极端样本:
     extreme_30 = df[delta.abs() > 30]
     extreme_40 = df[delta.abs() > 40]
     输出: count, risk_level 分布, 共同特征均值
     低→高: df[(df["v120_risk"] <= 1) & (df["v123_risk"] >= 3)]
     高→低: df[(df["v120_risk"] >= 3) & (df["v123_risk"] <= 1)]
  
  7. Level 6 — 分段点推荐:
     按 v120_score 五分位数分组
     每区间: score_range, mean_delta, delta_std, count
     输出为 CSV (供 Phase 4 使用)
  
  8. 生成报告

输出文件:
  docs/planning/v1.24-mmpsy-external-consistency-and-score-stability/delta_distribution_report.md
  docs/planning/v1.24-mmpsy-external-consistency-and-score-stability/delta_by_risk_group.csv
  docs/planning/v1.24-mmpsy-external-consistency-and-score-stability/delta_by_feature_group.csv
  docs/planning/v1.24-mmpsy-external-consistency-and-score-stability/extreme_delta_cases.csv
```

### 1.5 `04_train_adapter.py`

```
位置: backend/scripts/modeling/v1_24/04_train_adapter.py
执行: python 04_train_adapter.py

依赖: numpy, pandas, sklearn.metrics, joblib

类:
  ScoreAdapter — 完整实现 (参考 02-architecture.md §3.5)

main():
  1. delta_df = pd.read_csv("delta_by_risk_group.csv")
  
  2. 提取分段点:
     segments = []
     for _, row in delta_df.iterrows():
         lo, hi = map(int, row["score_range"].split("-"))
         slope = clamp(target_delta / max(abs(row["mean_delta"]), 1.0), 0.2, 1.0)
         segments.append({"range": [lo, hi], "slope": round(slope, 3)})
  
  3. 构建 config:
     config = {
         "version": "v1.24",
         "type": "piecewise_monotonic",
         "segments": segments,
         "clamp": 20,
         "smooth": 3,
         "training_date": datetime.date.today().isoformat(),
     }
  
  4. adapter = ScoreAdapter(config)
  
  5. 全量验证:
     full_df = pd.read_csv("model_delta_samples.csv")  # 4318 行
     adjusted_scores = []
     for _, row in full_df.iterrows():
         res = adapter.transform(row["v120_score"], row["v123_score"])
         adjusted_scores.append(res["score"])
     
     new_delta = np.abs(np.array(adjusted_scores) - full_df["v120_score"].values)
     new_mean_abs = new_delta.mean()
     
     # AUC 变化
     y_true = full_df["depression_binary"].values
     auc_original = roc_auc_score(y_true, full_df["v123_score"].values)
     auc_adjusted = roc_auc_score(y_true, adjusted_scores)
     auc_loss = auc_original - auc_adjusted
  
  6. Pareto 实验:
     候选 slope 乘数: [0.3, 0.5, 0.7, 0.9]
     对每个乘数，重新计算 new_mean_abs 和 auc_loss
     输出 CSV: multiplier, mean_abs_delta, auc, auc_loss
  
  7. 保存:
     joblib.dump(adapter, "backend/models/v1.24_adapter/score_adapter.pkl")
     json.dump(config, open("score_adapter_config.json", "w"), indent=2)

输出文件:
  backend/models/v1.24_adapter/score_adapter.pkl
  backend/models/v1.24_adapter/score_adapter_config.json
  docs/planning/v1.24-mmpsy-external-consistency-and-score-stability/adapter_experiment_results.csv
  docs/planning/v1.24-mmpsy-external-consistency-and-score-stability/adapter_selection_report.md
```

---

## 二、model_engine.py 修改规格

### 2.1 修改点汇总

| # | 位置 | 类型 | 内容 |
|---|------|------|------|
| M1 | import 区 | 新增 | `import time, asyncio` |
| M2 | `__init__` | 新增 | `self._start_time`, `self._persist_task`, `self._snapshot_path` |
| M3 | L530 前 | 插入 | lifecycle 检查 if 块包裹 |
| M4 | L604 后 | 新增 | v1.24 adapter 路径 (40 行) |
| M5 | 类尾 | 新增 | `_load_adapter()`, `_persist_loop()`, `start_persist()`, `stop_persist()` |
| M6 | `get_metrics_snapshot` | 修改 | 增加 `uptime_seconds`, `delta_by_level` |

### 2.2 M3 详细: v1.21 路径包裹

```python
# 位置: 在现有 L530 之前插入 (替换原来的 try 块开头)
from app.core.model_registry import get_model_info

v1_21_info = get_model_info("structured_v1.21_binary_lr")
if v1_21_info is not None and v1_21_info.lifecycle != "deprecated":
    try:
        # === 原有 L530-556 全部不变 ===
        exp_model = self._load_model("structured_v1.21_binary_lr")
        exp_scaler = self._load_model("structured_v1.21_scaler")
        # ...
    except Exception as exc:
        logger.warning(...)
else:
    logger.debug("v1.21 binary LR deprecated, skipping")
```

### 2.3 M4 详细: v1.24 adapter 路径

```python
# 位置: L604 (result["experimental_external_schema_version"] = ...) 之后

experimental_external_raw_score = experimental_external_score
experimental_external_adjusted_score = None
experimental_external_adapter_delta = None
experimental_external_migration_safe = None

if experimental_external_score is not None:
    try:
        adapter = self._load_adapter()
        adjusted = adapter.transform(
            v1_20_score=risk_score,
            v1_23_raw_score=experimental_external_score
        )
        experimental_external_adjusted_score = adjusted["score"]
        experimental_external_adapter_delta = adjusted["delta"]
        experimental_external_migration_safe = adjusted["safe_label"]
    except Exception as exc:
        logger.warning("v1.24 adapter unavailable: %s", exc)

result["experimental_external_raw_score"] = experimental_external_raw_score
result["experimental_external_adjusted_score"] = experimental_external_adjusted_score
result["experimental_external_adapter_delta"] = experimental_external_adapter_delta
result["experimental_external_migration_safe"] = experimental_external_migration_safe
result["experimental_external_migration_risk_level"] = experimental_external_level
result["experimental_external_adapter_version"] = (
    "v1.24" if experimental_external_adjusted_score is not None else None
)
```

### 2.4 M5+M6 详细: 新增方法

```python
# 在 __init__ 末尾:
self._start_time = time.time()
self._persist_task: asyncio.Task | None = None
self._snapshot_path = (
    Path(__file__).resolve().parents[2] / "logs" / "monitoring_snapshot.json"
)

# 新增方法 (类内部):
def _load_adapter(self):
    import joblib
    adapter_path = self._abs_path("models/v1.24_adapter/score_adapter.pkl")
    if not adapter_path.exists():
        raise FileNotFoundError(f"Adapter not found: {adapter_path}")
    return joblib.load(adapter_path)

async def _persist_loop(self, interval: float = 60.0):
    import datetime, json
    while True:
        await asyncio.sleep(interval)
        try:
            snapshot = self.get_metrics_snapshot()
            snapshot["persisted_at"] = datetime.datetime.now().isoformat()
            self._snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            self._snapshot_path.write_text(
                json.dumps(snapshot, indent=2, default=str), encoding="utf-8"
            )
        except Exception as exc:
            logger.error("Failed to persist monitoring snapshot: %s", exc)

def start_persist(self):
    if self._persist_task is None:
        self._persist_task = asyncio.create_task(self._persist_loop())

def stop_persist(self):
    if self._persist_task:
        self._persist_task.cancel()
        self._persist_task = None

# get_metrics_snapshot 中 experimental_external 增加:
"uptime_seconds": round(time.time() - self._start_time, 1),
"delta_by_level": {
    str(level): self.monitoring_counters.get(
        f"external_delta_by_level_{level}", 0
    )
    for level in range(5)
}
```

---

## 三、model_registry.py 修改规格

### 3.1 修改点

| # | 位置 | 类型 | 内容 |
|---|------|------|------|
| R1 | import 区 | 新增 | `from enum import StrEnum` |
| R2 | 类定义前 | 新增 | `class ModelLifecycle(StrEnum)` |
| R3 | ModelMetadata | 新增字段 | `lifecycle: ModelLifecycle = ModelLifecycle.EXPERIMENTAL` |
| R4 | REGISTRY 定义后 | 新增代码 | 逐模型 lifecycle 赋值 + v1.24 注册 |

### 3.2 完整代码块

```python
# R1 + R2
from enum import StrEnum

class ModelLifecycle(StrEnum):
    DEFAULT = "default"
    CANDIDATE = "candidate"
    EXPERIMENTAL = "experimental"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"

# R3: ModelMetadata dataclass 中插入
lifecycle: ModelLifecycle = ModelLifecycle.EXPERIMENTAL

# R4: REGISTRY 定义后
MODEL_REGISTRY["structured_logistic_regression_v1.20"].lifecycle = ModelLifecycle.DEFAULT
MODEL_REGISTRY["structured_v1.21_binary_lr"].lifecycle = ModelLifecycle.DEPRECATED
MODEL_REGISTRY["structured_v1.21_binary_rf"].lifecycle = ModelLifecycle.DEPRECATED
MODEL_REGISTRY["structured_v1.21_multiclass_lr"].lifecycle = ModelLifecycle.DISABLED
MODEL_REGISTRY["structured_v1.21_multiclass_rf"].lifecycle = ModelLifecycle.DISABLED
MODEL_REGISTRY["structured_v1.23_external_lr"].lifecycle = ModelLifecycle.EXPERIMENTAL

MODEL_REGISTRY["structured_v1.24_adapter"] = ModelMetadata(
    name="structured_v1.24_adapter",
    path="models/v1.24_adapter/score_adapter.pkl",
    version="v1.24",
    enabled=True,
    lifecycle=ModelLifecycle.CANDIDATE,
)
```

---

## 四、启动入口修改规格

### 4.1 main.py lifespan

```python
# backend/app/main.py
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    model_engine.preload()
    model_engine.start_persist()   # ← v1.24 新增
    yield
    model_engine.stop_persist()    # ← v1.24 新增

app = FastAPI(lifespan=lifespan)
```

**降级方案**: 如果 main.py 无法修改为 lifespan，在现有 `@app.on_event("startup")` 中添加 `model_engine.start_persist()`。

---

## 五、前端修改规格

### 5.1 modelApi.ts

```typescript
// 在 ModelPredictResponse interface 中追加 5 个字段:
experimental_external_raw_score: number | null;
experimental_external_adjusted_score: number | null;
experimental_external_adapter_delta: number | null;
experimental_external_migration_safe: "stable" | "slight_diff" | "marked_diff" | "review" | null;
experimental_external_adapter_version: string | null;
```

### 5.2 UserRiskPage.vue

```html
<!-- 在"实验参考 2"卡片内, delta 显示 <p> 之后增加: -->
<p v-if="modelTabResult?.experimental_external_adjusted_score != null"
   style="margin-top: 4px; color: #409eff; font-size: 13px">
  v1.24 适配分: 
  <strong>{{ modelTabResult.experimental_external_adjusted_score.toFixed(2) }}</strong>
  <el-tag :type="migrationTagType(modelTabResult.experimental_external_migration_safe)"
          size="small" effect="plain" style="margin-left: 6px">
    {{ migrationLabel(modelTabResult.experimental_external_migration_safe) }}
  </el-tag>
</p>
```

```typescript
// script setup 中新增辅助函数:
const migrationTagType = (safe: string | null) => {
  if (safe === "stable") return "success";
  if (safe === "slight_diff") return "primary";
  if (safe === "marked_diff") return "warning";
  return "danger";
};
const migrationLabel = (safe: string | null) => {
  if (safe === "stable") return "稳定";
  if (safe === "slight_diff") return "轻微差异";
  if (safe === "marked_diff") return "明显差异";
  return "需复核";
};
```

---

## 六、字典与常量定义

### 6.1 threshold_config.json 阈值

```json
{
  "risk_thresholds": [18, 35, 55, 72],
  "default_model": "structured_logistic_regression_v1.20"
}
```

### 6.2 风险等级映射

| v1.20_score 范围 | risk_level | 标签 |
|-----------------|------------|------|
| 0 ≤ score < 18 | 0 | 无风险 |
| 18 ≤ score < 35 | 1 | 轻度 |
| 35 ≤ score < 55 | 2 | 中度 |
| 55 ≤ score < 72 | 3 | 高度 |
| score ≥ 72 | 4 | 极高度 |

---

## 七、错误处理矩阵

| 模块 | 错误类型 | 处理方式 |
|------|---------|----------|
| 00_asset_check | 文件不存在 | 报告 ❌，不阻断 |
| 01_build_mmpsy | mmpsy CSV 不存在 | sys.exit(1) + 错误信息 |
| 01_build_mmpsy | audio_transcript 全空 | 警告，全部用 median 填充 |
| 02_validate_mmpsy | model.pkl 加载失败 | sys.exit(1) |
| 02_validate_mmpsy | 特征列顺序不匹配 | AssertionError + 打印差异 |
| 03_analyze_delta | delta CSV 加载失败 | sys.exit(1) |
| 04_train_adapter | 分段点 < 3 个 | 警告，使用等距分段 |
| model_engine M3 | get_model_info 返回 None | 跳过 v1.21 实验路径 |
| model_engine M4 | adapter.pkl 不存在 | 日志 WARNING，adjusted=null |
| model_engine M5 | persist 写失败 | 日志 ERROR，不抛异常 |

---

> **Round 3 Draft** | 下一步: Round 3 Step 2 — 自查 (Critique)
