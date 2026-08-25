"""风险评估模型引擎（核心编排器）— 包结构化拆分版。

负责把多模态输入组装为特征、加载模型、执行推理并输出风险分。
为避免 app.core 反向依赖 app.ml（层级倒置反模式），ML 相关组件在方法内延迟导入。

架构采用 Mixin 拆分，按职责分层组装：
- LoadingMixin   (.loading.py)  : 模型加载 / LRU 缓存 / 哈希校验 / adapter 加载
- InferenceMixin (.inference.py): 路由决策 / 特征工程 / 监控计数与持久化 /
                                   BERT micro-batch 收集器 / Lite 文本特征抽取
- PredictMixin   (.predict.py)  : 结构化 / 文本 / BERT / Lite / 生理预测主流程
- FusionMixin    (.fusion.py)   : 多模态融合预测
- FallbackMixin  (.fallback.py) : 分层启发式回退策略
- RiskMixin      (.risk.py)     : 风险映射 / 干预建议 / 危机检测 / SHAP 解释

历史沿革 (T-P2-001 PHASE_2 → model_engine 包拆分):
- 单文件 model_engine.py (2051 行) 首轮拆出 model_engine_risk.py /
  model_engine_fallback.py / model_engine_predict.py 三个 Mixin 模块;
- 本轮将双巨石 (model_engine.py + model_engine_predict.py) 进一步收编为
  `app.core.model_engine` 包, 原 model_engine_risk.py / model_engine_fallback.py
  整体迁入包内 risk.py / fallback.py;
- 原 model_engine_predict.py 保留为薄壳转发模块以兼容外部引用。

公共 API 保持完全兼容：所有既有调用点
`from app.core.model_engine import ModelEngine / model_engine /
LiteFeatureExtractor / LITE_FEATURE_ORDER / _BertMicroBatchCollector`
零改动（本包 __init__ 统一 re-export）。
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import OrderedDict, defaultdict, deque
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.crisis_detector import CrisisDetector

# MAINT-P0-002: _STR_TO_NUM / _DEFAULTS / LITE_FEATURE_ORDER 已抽离到 feature_maps.py
# 此处通过别名导入保持内部 _ 前缀命名约定, 同时 re-export 供外部
# `from app.core.model_engine import LITE_FEATURE_ORDER` 继续可用 (向后兼容)
from app.core.feature_maps import DEFAULTS as _DEFAULTS  # noqa: F401 — backward-compat alias
from app.core.feature_maps import LITE_FEATURE_ORDER  # noqa: F401 — re-export for backward compat
from app.core.feature_maps import STR_TO_NUM as _STR_TO_NUM  # noqa: F401 — backward-compat alias

# MAINT-P2-003: app.core 不应在顶层导入 app.ml (层级倒置)
# FusionEngine/FusionPriorityEngine/TextAnalyzer 仅在 ModelEngine.__init__ 中
# 延迟导入实例化; grimp/import-linter 静态分析函数体导入时不计入模块依赖图
# (豁免项见 pyproject.toml [tool.importlinter] ignore_imports)
from .fallback import FallbackMixin
from .fusion import FusionMixin
from .inference import (  # noqa: F401 — re-export for backward compat
    InferenceMixin,
    LiteFeatureExtractor,
    _BertMicroBatchCollector,
)
from .loading import (
    CHUNK_SIZE,  # noqa: F401 — re-export for backward compat
    LoadingMixin,
    _compute_file_sha256,  # noqa: F401 — re-export for backward compat
    _get_expected_hash,  # noqa: F401 — re-export for backward compat
    _verify_file_hash,  # noqa: F401 — re-export for backward compat
)
from .predict import PredictMixin
from .risk import RiskMixin


class ModelEngine(LoadingMixin, InferenceMixin, PredictMixin, FusionMixin, FallbackMixin, RiskMixin):
    """model_engine 包结构化拆分: ModelEngine 通过 Mixin 多继承装配各职责层.

    本文件仅保留核心编排职责: PRELOAD_IDS 装载清单、__init__ 状态初始化、
    ML 组件延迟装配。其余职责分布:

    - LoadingMixin   (loading.py)  : preload/_load_model/_load_model_async/
                                      _cache_get/_cache_put/_abs_path/
                                      _load_adapter(_async)/_patch_simple_imputer
    - InferenceMixin (inference.py): start/stop_bert_batch_collector/
                                      _incr_counter/_incr_routing/_incr_fallback/
                                      _incr_crisis_override/_record_score_delta/
                                      _timed_async/get_metrics_snapshot/
                                      _persist_loop/_publish_to_prometheus/
                                      start_persist/stop_persist/
                                      _build_structured_input/_route_structured/
                                      _update_structured_monitoring
    - PredictMixin   (predict.py)  : predict_structured/_run_experimental_v121/
                                      _run_experimental_v123/_run_adapter/
                                      predict_text/_predict_text_ml/
                                      _predict_text_bert(_single/_batch)/
                                      predict_lite/predict_physiological/
                                      _predict_physiological(_sync)/explain_prediction
    - FusionMixin    (fusion.py)   : predict_fusion
    - FallbackMixin  (fallback.py) : _structured_heuristic_fallback/
                                      _text_heuristic_fallback/
                                      _anxiety_only_fallback/
                                      _physiological_heuristic_fallback
    - RiskMixin      (risk.py)     : _score_to_level/score_to_level/
                                      _level_to_severity/_build_intervention_plan/
                                      _check_crisis_safety/_attention_gate/
                                      _boost_gate_for_physiology/
                                      _compute_shap_factors(_array)

    当模型不可用或推理失败时，依次回退到统计基线、规则启发式、轻量模型等，
    在保证高可用的前提下仍能产出可用的风险分。
    """

    PRELOAD_IDS = [
        "text_depression_tfidf",
        "text_depression_model",
        "text_improved_bilingual_tfidf",
        "text_improved_bilingual_model",
        "structured_logistic_regression_quick",
        "physiological_risk_model",
        "physiological_risk_scaler",
        "fusion_dnn_best",
        "fusion_cross_modal_best",
        "fusion_transformer_best",
    ]

    def __init__(self) -> None:
        # RES-P0-001 修复: 使用 OrderedDict 实现 LRU 缓存, 防止大模型无界累积导致 OOM
        # 访问时移到末尾 (MRU), 超过 maxsize 时弹出最旧 (LRU)
        self.models: OrderedDict[str, Any] = OrderedDict()
        self._cache_maxsize: int = max(int(getattr(settings, "model_cache_maxsize", 20)), 0)
        # 缓存操作锁: _load_model 通过 asyncio.to_thread 在线程池执行, 需保护缓存读改写
        self._cache_lock = threading.Lock()
        # LRU 淘汰计数器 (监控用)
        self._cache_evictions: int = 0
        # P1-1: adapter 缓存, 避免每次 predict_structured 都重新加载
        self._adapter_cached: Any = None
        self.feature_order = [
            "age",
            "gender",
            "study_year",
            "cgpa",
            "stress_level",
            "sleep_duration",
            "social_support",
            "financial_pressure",
            "family_history",
            "academic_pressure",
            "exercise_frequency",
            "anxiety",
            "panic_attack",
            "treatment_seeking",
        ]
        self.model_load_stats: dict[str, dict[str, float | int]] = defaultdict(
            lambda: {
                "loads": 0,
                "cache_hits": 0,
                "first_load_ms": 0.0,
                "last_load_ms": 0.0,
            }
        )
        self.predict_stats: dict[str, dict[str, float | int]] = defaultdict(
            lambda: {"count": 0, "total_ms": 0.0, "last_ms": 0.0}
        )
        self.monitoring_counters: dict[str, int] = defaultdict(int)
        # RES-P3-003: 使用 deque(maxlen=500) 替代 list 手动截断,
        # 自动淘汰旧数据, 避免 O(n) 切片赋值开销
        self.monitoring_score_deltas: deque[float] = deque(maxlen=500)
        self._routing_stats: dict[str, int] = {
            "structured": 0,
            "lite": 0,
            "anxiety_only": 0,
            "insufficient": 0,
        }
        self._fallback_count: int = 0
        self._crisis_override_count: int = 0
        # M-03 修复：监控计数器在多线程环境下（模型推理通过 asyncio.to_thread 执行）
        # 存在读-改-写竞态。使用锁保护所有监控计数器的更新与快照读取。
        self._monitoring_lock = threading.Lock()
        self._start_time = time.monotonic()
        self._persist_task: asyncio.Task | None = None
        self._snapshot_path = Path(__file__).resolve().parents[3] / "logs"
        self.crisis_detector = CrisisDetector()
        # MAINT-P2-003: 延迟导入 app.ml, 避免 app.core 顶层依赖 app.ml
        from app.ml.fusion_engine import FusionEngine
        from app.ml.fusion_priority_engine import FusionPriorityEngine
        from app.ml.text_analyzer import TextAnalyzer

        self.text_analyzer = TextAnalyzer()
        self.fusion_priority_engine = FusionPriorityEngine()
        self.fusion_engine = FusionEngine(
            use_confidence_weighting=True,
            use_modality_missing_handling=True,
        )
        # PERF-P3-007: BERT micro-batch collector (lazy init, None = 未启用)
        self._bert_batch_collector: _BertMicroBatchCollector | None = None


# ── T-P2-001 PHASE_2 → 包结构化拆分: 方法归属索引 ──
# 风险映射/干预/危机/SHAP 方法 → RiskMixin (risk.py):
#   _score_to_level, score_to_level, _level_to_severity,
#   _build_intervention_plan, _check_crisis_safety,
#   _attention_gate, _boost_gate_for_physiology,
#   _compute_shap_factors, _compute_shap_factors_array
#
# 启发式回退策略方法 → FallbackMixin (fallback.py):
#   _structured_heuristic_fallback, _text_heuristic_fallback,
#   _anxiety_only_fallback, _physiological_heuristic_fallback
#
# 核心预测方法 → PredictMixin (predict.py):
#   predict_structured, _run_experimental_v121, _run_experimental_v123,
#   _run_adapter, predict_text, _predict_text_ml, _predict_text_bert,
#   predict_lite, predict_physiological, _predict_physiological,
#   _predict_physiological_sync, explain_prediction
#
# 多模态融合预测 → FusionMixin (fusion.py):
#   predict_fusion
#
# 模型加载/LRU缓存 → LoadingMixin (loading.py):
#   preload, _load_model, _load_model_async, _cache_get, _cache_put,
#   _abs_path, _load_adapter, _load_adapter_async, _patch_simple_imputer
#
# 推理编排/路由/特征工程/监控 → InferenceMixin (inference.py):
#   start/stop_bert_batch_collector, _incr_counter/_incr_routing/
#   _incr_fallback/_incr_crisis_override/_record_score_delta,
#   _timed_async, get_metrics_snapshot, _persist_loop,
#   _publish_to_prometheus, start_persist, stop_persist,
#   _build_structured_input, _route_structured,
#   _update_structured_monitoring
#
# 死代码清理: _predict_keras_fusion (无任何调用方) 已删除.


model_engine = ModelEngine()
