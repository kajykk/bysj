# v1.26 架构设计

> **迭代编号**: v1.26-lite-recall-optimization-and-active-readiness
> **状态**: Round 1 / Step 1 — Draft v1
> **前置**: v1.25-mmpsy-lite-risk-model 架构 (Round 3 Locked)
> **原则**: 增量叠加，不破坏 v1.25 已锁定的架构基座

---

## 目录

- [一、架构全景](#一架构全景)
- [二、新增组件](#二新增组件)
- [三、修改组件](#三修改组件)
- [四、数据流](#四数据流)
- [五、API 规范](#五api-规范)
- [六、前端架构](#六前端架构)
- [七、安全架构](#七安全架构)
- [八、可观测性架构](#八可观测性架构)

---

## 一、架构全景

### 1.1 整体视图（v1.25 基座 + v1.26 增量）

```
┌──────────────────────────────────────────────────────────────┐
│                        Frontend (Vue 3)                       │
│  ┌──────────────────────┐  ┌───────────────────────────────┐ │
│  │  UserRiskPage.vue    │  │  Admin Dashboard (可选)        │ │
│  │  + routing透明展示    │  │  + lifecycle状态面板           │ │
│  │  + crisis人工复核提醒 │  │  + metrics快照                │ │
│  │  + lifecycle标签     │  │                               │ │
│  └──────────┬───────────┘  └───────────────────────────────┘ │
│             │ modelApi.ts                                     │
└─────────────┼────────────────────────────────────────────────┘
              │ HTTP /api/predict/tabular
┌─────────────┼────────────────────────────────────────────────┐
│             ▼              Backend (FastAPI)                   │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                  model_predict_service.py                 │ │
│  │  predict_tabular() → predict_structured() + routing log   │ │
│  └──────────────────────────┬───────────────────────────────┘ │
│                             │                                  │
│  ┌──────────────────────────▼───────────────────────────────┐ │
│  │                    model_engine.py                         │ │
│  │  predict_structured()                                      │ │
│  │    ├── routing dispatch (v1.25)                            │ │
│  │    ├── predict_lite() ───┐                                 │ │
│  │    │   ├── threshold override [NEW v1.26]                  │ │
│  │    │   ├── crisis safety check [NEW v1.26]                 │ │
│  │    │   └── anxiety_only_fallback (v1.25)                   │ │
│  │  _anxiety_only_fallback() (v1.25)                          │ │
│  └──────────────────────────┬───────────────────────────────┘ │
│                             │                                  │
│  ┌──────────────────────────▼───────────────────────────────┐ │
│  │                    model_registry.py                       │ │
│  │  MODEL_REGISTRY:                                           │ │
│  │    v1.20: default    │ v1.24: limited_active               │ │
│  │    v1.25/26: limited_active [NEW]                          │ │
│  │    v1.23: experimental│ v1.21 binary: deprecated            │ │
│  │    v1.21 multiclass: disabled [NEW lifecycle states]       │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                    config.py                                │ │
│  │  route_feature_coverage_threshold: 0.80                     │ │
│  │  route_lite_min_text_length: 20                             │ │
│  │  lite_decision_threshold: 0.50 → ??? [NEW v1.26]           │ │
│  │  crisis_keywords: [...] [NEW v1.26]                        │ │
│  └──────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

### 1.2 v1.25 vs v1.26 变更对照

| 层级 | v1.25 | v1.26 |
|---|---|---|
| 模型文件 | mmpsy_lite_model.pkl (LR + Calibrated) | 可能新增 recall_optimized 变体 |
| Decision Threshold | 默认 0.5 | 可配置 (config + API) |
| Safety | self_harm_crisis 关键词 ×2 加权 | + crisis safety override (硬规则) |
| Routing | 4 层分派 | + 路由稳定性统计 + 边界检查 |
| Lifecycle | candidate / experimental 等 | + limited_active + 7 模型统一治理 |
| Monitoring | 无专用设施 | + metrics_snapshot + 观测规范 |
| Config | 2 个路由参数 | + lite_decision_threshold + crisis_keywords |

---

## 二、新增组件

### 2.1 Threshold Manager

**位置**: `model_engine.py` 中的 `predict_lite()` 方法内部

```
predict_lite(gad7_score, audio_transcript, decision_threshold=None)
  │
  ├── 文本预处理 → LiteFeatureExtractor
  ├── 特征标准化 → scaler.transform()
  ├── 模型推理 → model.predict_proba()
  │
  ├── [NEW] threshold = decision_threshold or settings.lite_decision_threshold
  │     └── prediction = 1 if proba >= threshold else 0
  │
  └── 构建 result dict
```

**设计理由**：
- 不与模型绑定——同一模型文件可通过不同阈值产出不同 Recall/Specificity 权衡
- 可通过 config 或 API 参数覆盖，方便灰度期间调参
- 不影响现有 calibration（概率产出不变，仅阈值后处理的二值化改变）

### 2.2 Crisis Safety Override

**位置**: `model_engine.py` 中新方法 `_check_crisis_safety(text: str) -> dict`

```
_check_crisis_safety(text)
  │
  ├── 遍历 CRISIS_KEYWORDS = ["想死", "自杀", "自残", "活不下去", "不想活", "结束生命", "死了算了", "一死了之", "不如死了", "死了一了百了"]
  ├── 任一命中 → safety_flags.append("crisis_keyword_detected")
  │     ├── requires_human_review = True
  │     └── risk_override_reason = "crisis_keyword_detected"
  │
  └── 返回 safety dict
```

**调用位置**: 在 `predict_lite()` 返回前，以及 `predict_structured()` 的 lite 路由分支中注入。

**覆盖规则**（叠加增强，非替代模型输出）：

> Crisis override 是**安全补充层**，不是替代模型：模型仍然产出原始 risk_score/probability，safety layer 在此基础上追加 flags 并上调 risk_level 下限。

| 条件 | risk_level 最低 | safety_flag | 模型原始输出 |
|---|---|---|---|
| crisis keyword 命中 | max(原值, 3) | crisis_keyword_detected | 保留不变 |
| crisis + 低 GAD-7 (<5) | max(原值, 3) | + requires_human_review | 保留不变 |
| 无 crisis | 不调整 | 无 | 无变更 |

### 2.3 Metrics Snapshot

**位置**: `model_engine.py` 中新增类变量 + 方法

```
class ModelEngine:
    _routing_stats: dict  # {structured: N, lite: N, anxiety_only: N, insufficient: N}
    _fallback_count: int
    _crisis_override_count: int
    
    def get_metrics_snapshot() -> dict:
        return {
            "routing": self._routing_stats,
            "fallback_count": self._fallback_count,
            "crisis_override_count": self._crisis_override_count,
            "timestamp": ...
        }
```

**注意**：这些是内存计数器，仅用于当前进程生命周期内的观测。生产环境应接入结构化日志/Prometheus，此处仅提供最小可用版本。

---

## 三、修改组件

### 3.1 model_engine.py

| 方法/类 | 修改类型 | 说明 |
|---|---|---|
| `ModelEngine.__init__()` | 修改 | 初始化 `_routing_stats`, `_fallback_count`, `_crisis_override_count` |
| `predict_lite()` | 修改 | 添加 `decision_threshold` 参数 + threshold override + crisis safety 注入 |
| `LiteFeatureExtractor` | 修改 | 新增 `CRISIS_KEYWORDS = ["想死", "自杀", "自残", "活不下去", "不想活", "结束生命", "死了算了", "一死了之", "不如死了", "死了一了百了"]` 类常量 |
| `predict_structured()` | 修改 | 路由统计计数；lite 分支传递 safety info |
| 新增 `_check_crisis_safety()` | 新增 | crisis 关键词检测与覆盖 |
| 新增 `get_metrics_snapshot()` | 新增 | 观测指标快照 |

### 3.2 model_registry.py

| 条目 | 修改类型 | 说明 |
|---|---|---|
| lifecycle 状态枚举 | 扩展 | 新增 `limited_active` |
| v1.25 lite 模型 lifecycle | 修改 | candidate → limited_active (Phase 4 决策后) |
| v1.21 multiclass 模型 lifecycle | 修改 | disabled（不再可调用） |
| v1.21 binary 模型 lifecycle | 修改 | deprecated（不展示给普通用户） |

### 3.3 config.py

| 配置项 | 修改类型 | 默认值 |
|---|---|---|
| `lite_decision_threshold` | 新增 | `0.50`（v1.25 默认；Phase 1 后可能改为更低值） |
| `crisis_keywords` | 新增 | `["想死", "自杀", "自残", "活不下去", "不想活", "结束生命", "死了算了", "一死了之", "不如死了", "死了一了百了"]` |

### 3.4 schemas/model_predict.py

| 字段 | 修改类型 | 说明 |
|---|---|---|
| `RoutingInfo` | 不变 | 已存在，5 字段 |
| `ModelPredictResponse` | 修改 | 可选新增 `safety_flags: list[str]` / `requires_human_review: bool` |

### 3.5 services/model_predict_service.py

| 方法 | 修改类型 | 说明 |
|---|---|---|
| `predict_tabular()` | 修改 | 传递 safety info + 更新路由日志格式 |

### 3.6 前端

| 文件 | 修改类型 | 说明 |
|---|---|---|
| `modelApi.ts` | 修改 | 新增 `SafetyInfo` / `MetricsSnapshot` 接口 |
| `UserRiskPage.vue` | 修改 | 新增 crisis 人工复核提醒区块 + lifecycle 标签 |

---

## 四、数据流

### 4.1 单次预测完整数据流（v1.26 版本）

```
Client Request
  │  { gad7_score: 15, audio_transcript: "..." }
  ▼
model_predict_service.predict_tabular()
  │
  ▼
model_engine.predict_structured(features)
  │
  ├── 计算 f_coverage
  │     │  f_coverage = count(non_null_features) / 14
  │     │  expected_structured_fields = [
  │     │      "age", "gender", "cgpa", "sleep_duration",
  │     │      "exercise_frequency", "social_support", "stress_level",
  │     │      "anxiety", "family_history", "panic_attack",
  │     │      "treatment_seeking", "academic_pressure",
  │     │      "financial_pressure", "study_year"
  │     │  ]
  │     │  (不含 gad7_score / phq9_score / audio_transcript)
  │     │
  │     ├── f_coverage ≥ 0.80 → structured path
  │     │     ├── v1.20 / v1.24 model predict
  │     │     ├── routing_info { family: "structured", band: "high" }
  │     │     └── routing_stats.structured += 1
  │     │
  │     ├── f_coverage < 0.80 AND has_text → lite path
  │     │     ├── [NEW v1.26] threshold = settings.lite_decision_threshold
  │     │     │     (从 config.py 读取，需重启服务生效新值)
  │     │     ├── predict_lite(gad7, text, threshold)
  │     │     │     ├── LiteFeatureExtractor.extract(text)
  │     │     │     ├── scaler.transform(features)
  │     │     │     ├── model.predict_proba(scaled)
  │     │     │     ├── [NEW] threshold compare → binary prediction
  │     │     │     └── [NEW] _check_crisis_safety(text) → safety dict
  │     │     ├── routing_info { family: "lite", band: "medium" }
  │     │     ├── safety_info (if crisis detected)
  │     │     └── routing_stats.lite += 1
  │     │
  │     └── f_coverage < 0.80 AND no_text → anxiety_only path
  │           ├── _anxiety_only_fallback(gad7)
  │           ├── routing_info { family: "anxiety_only", band: "low" }
  │           └── routing_stats.anxiety_only += 1
  │
  ▼
Response
  {
    risk_score, risk_level, probability,
    routing_info: { ... },
    safety_flags: [...],         // [NEW]
    requires_human_review: bool  // [NEW]
  }
```

### 4.2 Phase 1 离线阈值扫描数据流

```
v1.25 mmpsy_lite_model.pkl + mmpsy_lite_scaler.pkl
  │
  ├── 加载模型 (不重训)
  ├── 遍历 thresholds = [0.15, 0.20, ..., 0.50]
  │     └── 对每个 threshold:
  │           predict_lite() on test set (192 samples)
  │           记录 Precision / Recall / F1 / Specificity
  │
  └── 输出 threshold_sweep_results.csv + 选定阈值 JSON
```

### 4.3 Phase 2 召回增强训练数据流

```
v1.25 训练/测试 split (固定)
  │
  ├── LR balanced → 5-Fold CV → 测试集评估
  ├── LR class_weight={0:1,1:1.5} → 同上
  ├── LR class_weight={0:1,1:2} → 同上
  ├── LR class_weight={0:1,1:3} → 同上
  ├── Calibrated LR + selected threshold → 同上
  └── GBDT shallow + selected threshold → 同上
  │
  └── recall_optimized_model_results.csv + 选定模型 (如优于原模型)
```

---

## 五、API 规范

### 5.1 新增/修改 API 端点

| 端点 | 方法 | 说明 | Phase |
|---|---|---|---|
| `GET /api/metrics/snapshot` | GET | 获取当前进程的指标快照 | P1 |
| `POST /api/predict/tabular` | 修改 | 响应新增 safety_flags / requires_human_review | P0 |

### 5.2 修改 POST /api/predict/tabular 请求体

无变更。

### 5.3 修改 POST /api/predict/tabular 响应体（新增字段）

```json
{
  "risk_score": 66.29,
  "risk_level": 3,
  "probability": 0.72,
  "routing_info": {
    "selected_model_id": "mmpsy_lite_model",
    "selected_model_family": "lite",
    "routing_reason": "lite_fallback",
    "feature_coverage_ratio": 0.12,
    "prediction_confidence_band": "medium"
  },
  "safety_flags": [],
  "requires_human_review": false
}
```

**crisis 命中时**：
```json
{
  ...
  "safety_flags": ["crisis_keyword_detected"],
  "requires_human_review": true
}
```

### 5.4 GET /api/metrics/snapshot 响应体 (Phase 5, P1)

```json
{
  "routing": {
    "structured": 1420,
    "lite": 315,
    "anxiety_only": 98,
    "insufficient": 12
  },
  "fallback_count": 23,
  "crisis_override_count": 7,
  "lite_avg_latency_ms": 12.3,
  "timestamp": "2026-05-02T12:00:00Z"
}
```

---

## 六、前端架构

### 6.1 组件树（增量部分）

```
UserRiskPage.vue
├── [v1.25] 路由透明展示行 (routing-info-bar)
│     ├── routeFamilyLabel tag
│     ├── routeReasonLabel span
│     └── confidenceTag tag
│
├── [NEW v1.26] Crisis 人工复核提醒区块
│     └── v-if="requires_human_review"
│           ├── el-alert type="warning"
│           ├── 文案: "检测到危机关键词，建议人工复核"
│           └── 不影响风险评分正常展示
│
├── [v1.25] 实验参考 3 — v1.25 lite 卡片
│
└── [NEW v1.26] Lifecycle 标签
      └── 当 modelTabResult?.routing_info?.selected_model_family === "lite"
            └── el-tag: lifecycle 状态文案
```

### 6.2 TypeScript 新增接口

```typescript
// modelApi.ts

export interface SafetyInfo {
  safety_flags: string[]
  requires_human_review: boolean
}

export interface ModelPredictResponse {
  // ... 现有字段
  routing_info: RoutingInfo | null
  safety_flags: string[]        // [NEW]
  requires_human_review: boolean // [NEW]
}

export interface MetricsSnapshot {
  routing: Record<string, number>
  fallback_count: number
  crisis_override_count: number
  lite_avg_latency_ms: number
  timestamp: string
}
```

---

## 七、安全架构

### 7.1 Crisis Safety 分层防护

```
Level 0: 模型层 (v1.25)
  └── self_harm_crisis 关键词 ×2 加权 → 提升模型预测概率

Level 1: 规则层 [NEW v1.26]
  └── _check_crisis_safety() 硬规则匹配
        └── 命中 → safety_flag + requires_human_review
        └── 不依赖模型加载状态（始终可用）

Level 2: 展示层 [NEW v1.26]
  └── 前端 el-alert 人工复核提醒
        └── 用户/咨询师可见
        └── 不影响正常评分流程

Level 3: 监控层 [NEW v1.26]
  └── crisis_override_count 计数
        └── 可追踪危机关键词命中频率
```

### 7.2 访问控制

无变更。沿用现有 JWT + RBAC 体系。

---

## 八、可观测性架构

### 8.1 观测体系

```
┌─────────────────────────────────────────┐
│           观测维度                        │
├───────────┬──────────┬──────────────────┤
│  路由层    │  模型层   │     安全层        │
├───────────┼──────────┼──────────────────┤
│ 各路径计数 │ 预测总数  │ crisis 命中数     │
│ 路径占比   │ 错误率   │ high_risk_override│
│ fallback率│ 延迟     │ insufficient数     │
│ 误分标记   │ 风险分均值│                  │
│           │ 高风险率 │                  │
└───────────┴──────────┴──────────────────┘
```

### 8.2 实现策略

| 层级 | 实现 | 说明 |
|---|---|---|
| 内存计数器 | `model_engine._routing_stats` 等 | 最小可用，进程级 |
| 结构化日志 | 扩展 `logger.info()` 调用 | 可被 ELK/Loki 采集 |
| API 暴露 | `GET /api/metrics/snapshot` | 前端/管理端可查询 |
| 生产推荐 | Prometheus + Grafana | 非 v1.26 范围，但架构预留接口 |

---

> **版本**: v1 (Draft)
> **创建日期**: 2026-05-02
> **下一动作**: 继续 Draft — 创建 04-ralph-tasks.md + 05-test-plan.md
