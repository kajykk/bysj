# v1.24 架构设计：外部一致性验证与风险评分迁移治理

> **版本**: v1.24 | **日期**: 2026-05-02 | **基线**: Round 2 Locked
> **前置**: [01-requirements.md](file:///e:/code/bysj/docs/planning/v1.24-mmpsy-external-consistency-and-score-stability/01-requirements.md) Round 1 Locked

---

## 一、系统边界与定位

### 1.1 v1.24 在系统中的位置

```
┌──────────────────────────────────────────────────────┐
│                    系统全景                            │
│                                                       │
│  ┌──────────────┐   ┌──────────────┐   ┌───────────┐ │
│  │ v1.20 (默认)  │   │ v1.23 (实验)  │   │ v1.24     │ │
│  │ Synthetic LR │   │ External LR  │   │  Adapter   │ │
│  │ default      │   │ experimental │   │ candidate  │ │
│  └──────┬───────┘   └──────┬───────┘   └─────┬─────┘ │
│         │                  │                  │       │
│         ▼                  ▼                  ▼       │
│  ┌───────────────────────────────────────────────┐   │
│  │            model_engine.py                     │   │
│  │  predict_structured()                          │   │
│  │    ├─ L440-520: v1.20 主路径 (不修改)          │   │
│  │    ├─ L530-563: v1.21 实验路径 (lifecycle检查) │   │
│  │    ├─ L565-604: v1.23 实验路径 (→ 扩展)        │   │
│  │    └─ [新增]: v1.24 Adapter 路径               │   │
│  └───────────────────────────────────────────────┘   │
│         │                                             │
│         ▼                                             │
│  ┌───────────────────────────────────────────────┐   │
│  │             API Response                        │   │
│  │  experimental_external_raw_score               │   │
│  │  experimental_external_adjusted_score          │   │
│  │  experimental_external_adapter_delta           │   │
│  │  experimental_external_migration_safe          │   │
│  │  experimental_external_adapter_version         │   │
│  └───────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

**核心原则**: v1.24 不替换任何现有路径，仅在 v1.23 实验路径下游增加 Adapter 转换层。

---

## 二、模块架构

### 2.1 Phase 依赖与数据流

```
Phase 0: 资产审计
  │
  ├──[数据]──→ Phase 1: mmpsy 特征构建
  │              │
  │              └──[mmpsy_structured_features.csv]──→ Phase 2: mmpsy 受限验证
  │
  └──[数据]──→ Phase 3: Delta 分层分析
                 │
                 └──[delta_by_risk_group.csv, 分段点推荐]──→ Phase 4: Score Adapter
                                                                │
                                                                └──[score_adapter.pkl]──→ Phase 5: Shadow 接入
                                                                                             │
                                                                                             ├──→ Phase 6: 前端
                                                                                             └──→ Phase 7: 注册表
```

### 2.2 模块清单

| 模块 | 类型 | 输入 | 输出 | 关键技术 |
|------|------|------|------|----------|
| asset_check | 脚本 | 文件系统 | `asset_check_report.md` | pathlib, json |
| mmpsy_feature_builder | 脚本 | `mmpsy_scores.csv`, `feature_schema.json` | `mmpsy_structured_features.csv` | pandas, re |
| mmpsy_validator | 脚本 | `mmpsy_structured_features.csv`, `model.pkl` | 验证指标 + 图表 | sklearn, matplotlib |
| delta_analyzer | 脚本 | `model_delta_samples.csv` | 分层 delta 报告 | pandas, scipy.stats |
| adapter_trainer | 脚本 | `delta_by_risk_group.csv` | `score_adapter.pkl` | numpy, ScoreAdapter |
| model_engine_patch | 代码修改 | — | 更新 `model_engine.py` | Python |
| registry_patch | 代码修改 | — | 更新 `model_registry.py` | Python dataclass, StrEnum |
| frontend_patch | 代码修改 | — | 更新 `modelApi.ts` + `UserRiskPage.vue` | TypeScript, Vue |
| monitoring_persist | 代码修改 | — | `model_engine.py` 持久化逻辑 | json, asyncio |

---

## 三、核心模块详细设计

### 3.1 Phase 0: 资产审计 (`scripts/v1_24/00_asset_check.py`)

```
功能: 验证所有依赖资产存在且可读
逻辑:
  1. 遍历资产清单 (01-requirements.md §2.1)
  2. 对每个路径: os.path.exists() + 尝试打开
  3. 对 model_delta_samples.csv: 验证行数 (4318) 和列数 (19) 与基线一致
  4. 输出 asset_check_report.md (表格 + 状态灯)
```

### 3.2 Phase 1: mmpsy 特征构建 (`scripts/v1_24/01_build_mmpsy_features.py`)

```
输入: data/external/mmpsy_scores.csv (1275 × 9)
      backend/models/v1.23_external_lr/feature_schema.json

输出: mmpsy_structured_features.csv (1275 × 12 + 来源列)

处理管道:
  Step 1: 加载 schema → 提取 12 个特征名和 median 默认值
  Step 2: 逐特征映射:
  
    ┌─ stress_level       ← phq9_score / 27 * 5
    ├─ anxiety            ← gad7_score / 21 * 5
    ├─ panic_attack       ← audio_transcript 危机词检测 (任一匹配 → 1)
    ├─ sleep_duration     ← audio_transcript 睡眠词匹配 → 规则映射 → min(匹配值)
    ├─ academic_pressure  ← audio_transcript 学业词计数 → min(计数*1.25, 5)
    ├─ exercise_frequency ← audio_transcript 运动词计数 → min(计数/2, 3)
    └─ 其余 6 个          ← median 填充

  Step 3: 为每个特征添加 _source 列 (derived/imputed)
  Step 4: 生成 mmpsy_feature_mapping_report.md
  Step 5: 生成 mmpsy_missingness_report.md

关键词列表:

  危机词 (任一匹配 → panic_attack=1):
    ["想死", "不想活", "自杀", "自残", "活不下去", "死了算了", "结束生命"]

  睡眠词 (匹配后取最差值):
    "整夜没睡", "彻夜难眠"                    → sleep_duration = 0
    "失眠", "睡不着"                          → sleep_duration = 3
    "熬夜", "睡眠不足"                        → sleep_duration = 5
    "早醒"                                   → sleep_duration = 5
    "睡眠" (无否定词), "睡得好", "入睡"       → sleep_duration = 8
    取 min(所有匹配映射值); 无匹配 → median

  学业词 (计数后归一化):
    "考试", "成绩", "作业", "学习", "背书", "中考", "高考", "学业", "老师", "周测"
    → academic_pressure = min(匹配次数 * 1.25, 5.0)

  运动词 (计数后归一化):
    "跑步", "打球", "运动", "散步", "锻炼", "篮球", "足球", "游泳", "健身"
    → exercise_frequency = min(匹配次数 / 2, 3.0)

⚠️ NLP: 使用 str.count() 子串匹配，不引入 jieba。如环境已有 jieba 则优先。
```

### 3.3 Phase 2: mmpsy 受限验证 (`scripts/v1_24/02_validate_mmpsy.py`)

```
输入: mmpsy_structured_features.csv
      backend/models/v1.23_external_lr/model.pkl

输出: mmpsy_external_validation_metrics.json
      mmpsy_external_validation_report.md
      mmpsy_roc_curve.png
      mmpsy_calibration_curve.png

处理:
  Step 1: 加载 v1.23 pipeline (model.pkl 含 SimpleImputer + StandardScaler + LR)
  Step 2: 确保特征列顺序与 model.feature_names_in_ 一致
  Step 3: 预测全量 1275 样本
  Step 4: 以 phq9_binary 为 ground truth:
    - ROC-AUC, Precision, Recall, F1, Specificity
    - 混淆矩阵
  Step 5: 相关性: Pearson r (predicted vs phq9_score), Spearman ρ (predicted vs gad7_score)
  Step 6: 高风险召回 (phq9_binary=1 中 predicted_binary=1 的比例)
  Step 7: 有效特征子集基线:
    - 提取仅 3 个有效派生特征 (stress_level, anxiety, panic_attack) + phq9_binary
    - 训练微型 LR (3 特征, 无正则) → 5-fold CV AUC
    - 报告: AUC_12feature vs AUC_3feature gap
      gap > 0: 填充特征有微弱贡献
      gap ≈ 0: 填充特征几乎无贡献
      gap < 0: 填充特征引入噪声 (回归均值效应)
  Step 8: 生成报告 (含受限声明)

受限声明模板:
  "⚠️ 此验证为受限外部验证 (Constrained External Validation)。
   mmpsy 数据集的 12 个 v1.23 模型输入特征中，仅 X 个 (Y%) 可通过
   规则派生获得，其余以中位数填充。因此本报告反映的是 v1.23 模型
   在'部分信息可用'场景下的性能下界，不代表完整泛化能力。"
```

### 3.4 Phase 3: Delta 分层分析 (`scripts/v1_24/03_analyze_delta.py`)

```
输入: backend/models/v1.23_external_lr/model_delta_samples.csv
      确认: 4318 行, 19 列 (含 delta_v123_v120, delta_v123_v121)

输出: delta_distribution_report.md
      delta_by_risk_group.csv
      delta_by_feature_group.csv
      extreme_delta_cases.csv

分析层次:

Level 1 — 全局统计:
  N, Mean Delta, Mean Abs Delta, Std Delta
  分位数: P10, P25, P50, P75, P90
  (|delta| > 15/20/30/40) 比例 → 验证与已知基线 (21.29, 26.8%, 20.1%)

Level 2 — 按 v1.20 风险等级分组:
  每等级: count, mean_delta, abs_mean_delta
  v1.20_risk 由 threshold_config.json 阈值映射 (18/35/55/72)

Level 3 — 按 PHQ-9/GAD-7 区间:
  GROUP BY (0-4,5-9,10-14,15-19,20-27) → mean_delta
  GROUP BY gad7_bin → mean_delta

Level 4 — 按人群分组:
  GROUP BY age_group, gender, source → mean_delta

Level 5 — 极端样本:
  (|delta| > 30): 全部样本 → 共同特征模式
  (|delta| > 40): 全部样本 → 风险等级分布
  v1.20_low + v1.23_high vs v1.20_high + v1.23_low

Level 6 — 分段点推荐:
  按 v1.20_score 分位数: [P0-P20, P20-P40, ..., P80-P100]
  每区间: mean_delta, delta_std, count
  输出推荐分段点值 (边界 score)
```

### 3.5 Phase 4: Score Adapter (`scripts/v1_24/04_train_adapter.py`)

```
输入: delta_by_risk_group.csv (来自 Phase 3)

输出: score_adapter.pkl + score_adapter_config.json
      adapter_experiment_results.csv
      adapter_selection_report.md

─────────────────────────────────────────────
ScoreAdapter 类定义 (训练时保存，推理时加载)
─────────────────────────────────────────────

class ScoreAdapter:
    def __init__(self, config: dict):
        self.version = config["version"]
        self.segments = config["segments"]       # [{range, slope}]
        self.clamp_delta = config["clamp"]       # max_delta
        self.buffer = config["smooth"]           # buffer width

    def transform(self, v1_20_score: float,
                  v1_23_raw_score: float) -> dict:
        delta = v1_23_raw_score - v1_20_score
        seg = self._find_segment(v1_20_score)

        # 核心映射: 纯乘法压缩
        adjusted = v1_20_score + delta * seg["slope"]

        # 钳制
        adjusted = max(v1_20_score - self.clamp_delta,
                       min(v1_20_score + self.clamp_delta, adjusted))

        # 边界平滑 (分段点 ±buffer 内线性插值)
        if self._near_boundary(v1_20_score, seg):
            adjusted = self._smooth(v1_20_score, delta, seg)

        diff = abs(adjusted - v1_20_score)
        return {
            "score": round(adjusted, 2),
            "delta": round(adjusted - v1_23_raw_score, 2),
            "safe_label": self._label(diff),
        }

    def _find_segment(self, score: float) -> dict:
        for seg in self.segments:
            lo, hi = seg["range"]
            if lo <= score < hi or (hi == 100 and lo <= score <= hi):
                return seg
        return self.segments[-1]

    def _near_boundary(self, score: float, seg: dict) -> bool:
        lo, hi = seg["range"]
        return abs(score - lo) <= self.buffer or abs(score - hi) <= self.buffer

    def _smooth(self, score, delta, seg) -> float:
        # 与相邻段线性插值
        idx = self.segments.index(seg)
        neighbor = self.segments[idx - 1] if idx > 0 else self.segments[idx + 1]
        # ... 加权平均实现 ...
        return score + delta * seg["slope"]  # 简化

    def _label(self, diff: float) -> str:
        if diff <= 5:  return "stable"
        if diff <= 15: return "slight_diff"
        if diff <= 25: return "marked_diff"
        return "review"

─────────────────────────────────────────────
Adapter Config 结构 (无 intercept 字段)
─────────────────────────────────────────────
{
  "version": "v1.24",
  "type": "piecewise_monotonic",
  "segments": [
    {"range": [0, 20],   "slope": 0.5},
    {"range": [20, 40],  "slope": 0.6},
    {"range": [40, 60],  "slope": 0.55},
    {"range": [60, 80],  "slope": 0.5},
    {"range": [80, 100], "slope": 0.4}
  ],
  "clamp": 20,
  "smooth": 3,
  "training_date": "2026-05-02"
}

─────────────────────────────────────────────
训练流程
─────────────────────────────────────────────
Step 1: 加载 delta_by_risk_group.csv
Step 2: 对每个区间计算 actual_mean_delta
  slope = target_delta / max(|actual_mean_delta|, 1)
  目标 delta: [5, 10, 12, 10, 5] (对应 5 区间)
Step 3: 构建 config → ScoreAdapter(config)
Step 4: 遍历全量样本验证:
  adjusted = adapter.transform(v1_20_score, v1_23_score)
  new_mean_abs_delta = mean(|adjusted.score - v1_20_score|)
  AUC_change = AUC(v1_20_score 替换为 adjusted.score, 同 gt)
Step 5: Pareto 前沿 (5 候选 slope 组 → trade-off 曲线)
Step 6: joblib.dump(adapter, "score_adapter.pkl")
```

### 3.6 Phase 5: model_engine Shadow 接入

> **修改文件**: `backend/app/core/model_engine.py`

**改造点 1: v1.21 实验路径完整包裹 (L530-563)**

```python
# 获取 lifecycle 信息
from app.core.model_registry import get_model_info

v1_21_info = get_model_info("structured_v1.21_binary_lr")
if v1_21_info is not None and v1_21_info.lifecycle != "deprecated":
    try:
        exp_model = self._load_model("structured_v1.21_binary_lr")
        exp_scaler = self._load_model("structured_v1.21_scaler")
        # ... 现有 L532-556 全部逻辑 ...
    except Exception as exc:
        logger.warning("v1.22 experimental real binary LR unavailable: %s", exc)
else:
    logger.debug("v1.21 binary LR deprecated, skipping experimental path")

# L559-562 结果字段初始化不变 (值始终为 None 当路径跳过时)
```

**改造点 2: v1.24 Adapter 路径 (L604 之后新增)**

```python
# ── v1.24 Phase 5: Adapter 路径 ──
experimental_external_raw_score = experimental_external_score  # 别名
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
        logger.info("v1.24 adapter: raw=%.2f adj=%.2f safe=%s delta=%.2f",
                     experimental_external_score,
                     experimental_external_adjusted_score,
                     experimental_external_migration_safe,
                     experimental_external_adapter_delta)
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

**新增方法: `_load_adapter()`**

```python
def _load_adapter(self) -> ScoreAdapter:
    import joblib
    adapter_path = self._abs_path("models/v1.24_adapter/score_adapter.pkl")
    if not adapter_path.exists():
        raise FileNotFoundError(f"Adapter not found: {adapter_path}")
    return joblib.load(adapter_path)
```

### 3.7 监控持久化

> **修改文件**: `backend/app/core/model_engine.py`

```python
# __init__ 中新增:
self._start_time = time.time()
self._persist_task: asyncio.Task | None = None
self._snapshot_path = (
    Path(__file__).resolve().parents[2] / "logs" / "monitoring_snapshot.json"
)

# 新增方法:
async def _persist_loop(self, interval: float = 60.0):
    import datetime, json
    while True:
        await asyncio.sleep(interval)
        try:
            snapshot = self.get_metrics_snapshot()
            snapshot["persisted_at"] = datetime.datetime.now().isoformat()
            self._snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            self._snapshot_path.write_text(
                json.dumps(snapshot, indent=2, default=str),
                encoding="utf-8"
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
```

**调用时机**: 在 FastAPI lifespan 中启动/停止：

```python
# backend/app/main.py (或启动入口)
@asynccontextmanager
async def lifespan(app: FastAPI):
    model_engine.preload()
    model_engine.start_persist()   # ← v1.24 新增
    yield
    model_engine.stop_persist()    # ← v1.24 新增
```

如果不能修改为 lifespan（如使用旧式 `@app.on_event("startup")`），则在 `on_event("startup")` 中调用 `model_engine.start_persist()`。如果两者都不可行，作为降级方案在 `predict_structured()` 首次调用时惰性启动。

**get_metrics_snapshot 增强**:

```python
"experimental_external": {
    # ... 现有字段 ...
    "uptime_seconds": round(time.time() - self._start_time, 1),
    "delta_by_level": {
        str(level): self.monitoring_counters.get(
            f"external_delta_by_level_{level}", 0
        )
        for level in range(5)
    }
}
```

### 3.8 Phase 7: 注册表治理

> **修改文件**: `backend/app/core/model_registry.py`

```python
from enum import StrEnum

class ModelLifecycle(StrEnum):
    DEFAULT = "default"
    CANDIDATE = "candidate"
    EXPERIMENTAL = "experimental"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


@dataclass(slots=True)
class ModelMetadata:
    name: str
    path: str
    version: str = "v1"
    enabled: bool = True
    lifecycle: ModelLifecycle = ModelLifecycle.EXPERIMENTAL  # 新增
    supports_fusion: bool = False
    feature_schema: dict[str, object] = field(default_factory=dict)
    artifact_metadata: dict[str, object] = field(default_factory=dict)


# 生命周期分配 (REGISTRY 中逐模型设置):
MODEL_REGISTRY["structured_logistic_regression_v1.20"].lifecycle = ModelLifecycle.DEFAULT
MODEL_REGISTRY["structured_v1.21_binary_lr"].lifecycle = ModelLifecycle.DEPRECATED
MODEL_REGISTRY["structured_v1.21_binary_rf"].lifecycle = ModelLifecycle.DEPRECATED
MODEL_REGISTRY["structured_v1.21_multiclass_lr"].lifecycle = ModelLifecycle.DISABLED
MODEL_REGISTRY["structured_v1.21_multiclass_rf"].lifecycle = ModelLifecycle.DISABLED
MODEL_REGISTRY["structured_v1.23_external_lr"].lifecycle = ModelLifecycle.EXPERIMENTAL

# v1.24 Adapter 新注册:
MODEL_REGISTRY["structured_v1.24_adapter"] = ModelMetadata(
    name="structured_v1.24_adapter",
    path="models/v1.24_adapter/score_adapter.pkl",
    version="v1.24",
    enabled=True,
    lifecycle=ModelLifecycle.CANDIDATE,
)
```

### 3.9 Phase 6: 前端改造

> **修改文件**: `frontend/src/api/modelApi.ts`, `frontend/src/views/user/UserRiskPage.vue`

**现有状态 (调研确认)**:
- `modelApi.ts` L12-21: 已有 `experimental_external_score/level/model/available/delta`
- `UserRiskPage.vue` L942-969: 已展示"实验参考 2" (v1.23 raw + delta)

**v1.24 改造**:

`modelApi.ts` — 新增 5 个字段:
```typescript
export interface ModelPredictResponse {
  // ... 现有字段不变 ...
  experimental_external_raw_score: number | null           // v1.24 新增
  experimental_external_adjusted_score: number | null      // v1.24 新增
  experimental_external_adapter_delta: number | null       // v1.24 新增
  experimental_external_migration_safe: string | null      // v1.24 新增
  experimental_external_adapter_version: string | null     // v1.24 新增
}
```

`UserRiskPage.vue` — 在"实验参考 2"卡片中增加 1 行:
```html
<!-- 在 L962 的 </p> (delta 显示) 之后、</div> 之前增加: -->
<p v-if="modelTabResult?.experimental_external_adjusted_score != null"
   style="margin-top: 4px; color: #409eff">
  v1.24 适配分: {{ modelTabResult.experimental_external_adjusted_score.toFixed(2) }}
  <el-tag :type="migrationSafeTagType(modelTabResult.experimental_external_migration_safe)"
          size="small" effect="plain" style="margin-left: 6px">
    {{ migrationSafeLabel(modelTabResult.experimental_external_migration_safe) }}
  </el-tag>
</p>
```

---

## 四、文件系统布局

```
docs/planning/v1.24-mmpsy-external-consistency-and-score-stability/
├── 01-requirements.md
├── 02-architecture.md
├── 03-design.md                (Round 3)
├── 04-ralph-tasks.md           (Round 3)
├── 05-test-plan.md             (Round 3)
├── 06-learnings.md

backend/
├── app/core/
│   ├── model_registry.py       (修改: StrEnum + lifecycle 字段)
│   └── model_engine.py         (修改: adapter + persist + v1.21 修正)
├── models/
│   └── v1.24_adapter/          (新建)
│       ├── score_adapter.pkl
│       └── score_adapter_config.json
└── scripts/modeling/v1_24/     (新建)
    ├── 00_asset_check.py
    ├── 01_build_mmpsy_features.py
    ├── 02_validate_mmpsy.py
    ├── 03_analyze_delta.py
    └── 04_train_adapter.py

frontend/src/
├── api/modelApi.ts             (修改: 新增 5 个字段)
└── views/user/UserRiskPage.vue (修改: 新增适配分展示)

logs/
└── monitoring_snapshot.json    (运行时生成)
```

---

## 五、API 接口影响

### 5.1 `/api/v1/model/predict/tabular` 响应新增字段

```json
{
  "risk_score": 45.2,
  "risk_level": 2,
  "experimental_external_score": 62.1,
  "experimental_external_level": 3,
  "experimental_external_delta": 16.9,
  "experimental_external_raw_score": 62.1,
  "experimental_external_adjusted_score": 55.3,
  "experimental_external_adapter_delta": -6.8,
  "experimental_external_migration_safe": "slight_diff",
  "experimental_external_migration_risk_level": 2,
  "experimental_external_adapter_version": "v1.24"
}
```

**migration_safe 取值**:
- `"stable"` — adjusted 与 v1.20 差异 ≤ 5
- `"slight_diff"` — 差异 5-15
- `"marked_diff"` — 差异 15-25
- `"review"` — 差异 > 25，需人工复核

### 5.2 `/api/v1/metrics` 新增字段

```json
{
  "monitoring": {
    "experimental_external": {
      "uptime_seconds": 3600.0,
      "delta_by_level": {"0": 120, "1": 85, "2": 42, "3": 15, "4": 3}
    }
  }
}
```

---

## 六、安全与回退设计

### 6.1 分层回退

```
L1: v1.20 default → 始终可用，不受任何修改影响
L2: v1.23 experimental → 加载失败 → experimental_external_available=false
L3: v1.24 adapter → 加载失败 → adjusted_score=null, raw_score 仍返回
```

### 6.2 不破坏原则

| 原则 | 保证方式 |
|------|----------|
| v1.20 主路径不变 | predict_structured() L440-520 不动 |
| API 向后兼容 | 仅追加字段，不删除 |
| 注册表向后兼容 | lifecycle 默认值 EXPERIMENTAL |

---

## 七、Phase 执行顺序依赖

```
Phase 0 ──┬──→ Phase 1 ──→ Phase 2
          │
          └──→ Phase 3 ──→ Phase 4 ──→ Phase 5 ──┬──→ Phase 6
                                                   │
                                                   └──→ Phase 7
                                                          │
                                                          └──→ Phase 8 (决策)
```

- Phase 1 ∥ Phase 3 (可并行)
- Phase 6 ∥ Phase 7 (可并行)
- Phase 8 依赖 Phase 2 + Phase 5 + Phase 7

---

> **Round 2 Locked** | 下一步: Round 3 — 终定
