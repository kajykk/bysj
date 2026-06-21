# FINAL_SYSTEM_ARCHITECTURE — v1.27 最终系统架构

> **生成日期**: 2026-05-02
> **覆盖范围**: 路由式多模型风险评估系统全架构

---

## 一、系统总览

```
┌─────────────────────────────────────────────────────┐
│                    前端 (Vue 3)                       │
│  UserRiskPage  │  AdminDashboard  │  管理端监控       │
└──────────────────────┬──────────────────────────────┘
                       │ REST API (FastAPI)
┌──────────────────────┴──────────────────────────────┐
│                   后端 API 层                         │
│  /model/predict/tabular  │  /monitoring/*            │
│  /model/predict/text     │  /model/status            │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│               Model Engine (核心)                     │
│                                                      │
│  ┌─────────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ 路由决策引擎  │  │ 模型加载  │  │ 安全检测引擎   │  │
│  │ (coverage   │  │ (registry│  │ (crisis       │  │
│  │  threshold) │  │  + paths)│  │  keywords)    │  │
│  └──────┬──────┘  └────┬─────┘  └───────┬───────┘  │
│         │              │                │           │
│  ┌──────┴──────────────┴────────────────┴───────┐  │
│  │              模型执行层                        │  │
│  │  v1.20    v1.25     v1.24    v1.23           │  │
│  │  default  lite      adapter  external        │  │
│  └──────────────────────────────────────────────┘  │
│                                                      │
│  ┌──────────────────────────────────────────────┐  │
│  │            监控与生命周期治理                    │  │
│  │  routing_stats │ fallback_count               │  │
│  │  crisis_count  │ lifecycle_filter             │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## 二、路由决策体系

### 2.1 路由决策树

```
POST /api/v1/model/predict/tabular  { features }
    │
    ├─ 计算 feature_coverage_ratio
    │  (14个结构化字段中非空比例)
    │
    ├─ coverage ≥ 0.80 ────────────────────────────┐
    │   → v1.20 structured (default)               │
    │   → confidence: high(≥0.90) / medium         │
    │   → [shadow] v1.24 adapter 产出 adjusted_score│
    │                                              │
    ├─ coverage < 0.80 ────────────────────────────┤
    │   ├─ GAD-7 有值 + text ≥ 20 chars            │
    │   │   → v1.25 lite (limited_active)          │
    │   │   → threshold = 0.40                     │
    │   │   → confidence: medium                   │
    │   │                                          │
    │   ├─ GAD-7 有值 + text < 20 chars / 无text   │
    │   │   → anxiety_only (fallback)              │
    │   │   → confidence: low                      │
    │   │                                          │
    │   └─ GAD-7 无值                              │
    │       → insufficient                         │
    │       → fallback_used=True                   │
    │       → warning: 信息不足                      │
```

### 2.2 路由计数器

每次路由决策触发对应计数器 +1：

| Counter | 触发条件 |
|:---|:---|
| `_routing_stats["structured"]` | coverage ≥ 0.80 |
| `_routing_stats["lite"]` | GAD-7 + text ≥ 20 chars |
| `_routing_stats["anxiety_only"]` | 仅 GAD-7 |
| `_routing_stats["insufficient"]` | 无有效输入 |
| `_fallback_count` | lite 模型缺失/异常 |
| `_crisis_override_count` | 危机关键词命中 |

---

## 三、安全治理体系

### 3.1 Crisis Override 机制

```
用户输入 text
    │
    ├─ 遍历 settings.crisis_keywords (10 个中文词)
    │
    ├─ 命中 ───────────────────────────────────────┐
    │   → safety_flags += ["crisis_keyword_detected"]
    │   → requires_human_review = True             │
    │   → crisis_keywords_matched 记录命中词        │
    │   → risk_level = max(risk_level, 3)           │
    │   → _crisis_override_count += 1              │
    │                                              │
    └─ 未命中                                      │
        → 正常流程，不影响预测结果                    │
```

### 3.2 安全设计原则

| 原则 | 实现 |
|:---|:---|
| **确定性** | 纯字符串匹配，不依赖任何模型加载状态 |
| **只升不降** | Crisis override 只能提升 risk_level，不能降低 |
| **始终可用** | 即使所有模型加载失败，crisis 检测仍然生效 |
| **可审计** | 每次命中都记录计数器和日志 |

### 3.3 危机关键词列表 (10 个)

```
想死、自杀、自残、活不下去、不想活、
结束生命、死了算了、一死了之、不如死了、死了一了百了
```

---

## 四、Fallback 容错层级

```
Level 1: 模型加载失败
    v1.20 structured 加载失败
    → 回退到启发式规则 (heuristic fallback)

Level 2: Lite 模型不可用
    v1.25 lite 模型加载失败或推理异常
    → 回退到 anxiety_only_fallback

Level 3: Keras 模型缺失
    fusion_cross_modal_best / fusion_transformer_best 不存在
    → 自动跳过，不影响主流程 (启动日志 Falling back…)

Level 4: TensorFlow/PyTorch 未安装
    → 导入检测 (config.py)，自动跳过深度学习路径

Level 5: 空输入/严重缺失
    → insufficient，返回友好提示
```

**设计原则**: Graceful degradation — 系统绝不因单个组件失败而整体崩溃。

---

## 五、模型生命周期治理

### 5.1 生命周期状态机

```
candidate → experimental → limited_active → default
                ↓               ↓               ↓
            disabled       deprecated      deprecated
```

### 5.2 状态定义

| 状态 | 含义 | API 可见性 |
|:---|:---|:--:|
| `default` | 全局默认模型，无特殊标记 | ✅ |
| `limited_active` | 限定场景活跃，标注路由条件 | ✅ (需说明限制) |
| `experimental` | 实验阶段，仅作参考 | ✅ (标注"实验") |
| `deprecated` | 已弃用，仅保留历史记录 | ⚠️ (隐藏) |
| `disabled` | 已禁用，不加载 | ❌ |

### 5.3 活跃模型过滤

```python
ACTIVE_LIFECYCLES = {"default", "limited_active"}
# get_active_models() 仅返回这两个状态 + enabled=True 的模型
```

---

## 六、监控观测体系

### 6.1 API 端点

| 端点 | 方法 | 说明 |
|:---|:---|:---|
| `/health` | GET | 健康检查 (database, redis, celery) |
| `/api/v1/monitoring/engine-snapshot` | GET | 引擎实时快照 |
| `/api/v1/monitoring/dashboard-summary` | GET | 仪表盘汇总 |

### 6.2 Engine Snapshot 数据结构

```json
{
  "routing_stats": {
    "structured": N,
    "lite": N,
    "anxiety_only": N,
    "insufficient": N
  },
  "fallback_count": N,
  "crisis_override_count": N,
  "timestamp": "ISO8601"
}
```

---

## 七、技术栈

| 层 | 技术 |
|:---|:---|
| 前端 | Vue 3 + TypeScript + Element Plus + Vite + ECharts |
| 后端 | FastAPI + Pydantic + SQLAlchemy (async) |
| ML 框架 | scikit-learn + TensorFlow (optional) |
| 数据库 | SQLite (dev) / PostgreSQL (prod) |
| 部署 | Docker + Nginx |

---

> **架构结论**: 系统已形成完整的三层架构 (前端→API→引擎)，具备路由决策、安全治理、模型生命周期管理和监控观测四大核心能力。
