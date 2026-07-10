from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import threading
import time
from collections import OrderedDict, defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any, AsyncIterator

# P1-E 修复：使用 TYPE_CHECKING 避免运行时导入，同时提供精确类型提示
if TYPE_CHECKING:
    from sklearn.pipeline import Pipeline

from app.core.config import BACKEND_DIR, settings
from app.core.crisis_detector import CrisisDetector

# MAINT-P0-002: _STR_TO_NUM / _DEFAULTS / LITE_FEATURE_ORDER 已抽离到 feature_maps.py
# 此处通过别名导入保持内部 _ 前缀命名约定, 同时 re-export 供外部
# `from app.core.model_engine import LITE_FEATURE_ORDER` 继续可用 (向后兼容)
from app.core.feature_maps import DEFAULTS as _DEFAULTS
from app.core.feature_maps import LITE_FEATURE_ORDER
from app.core.feature_maps import STR_TO_NUM as _STR_TO_NUM
from app.core.model_engine_fallback import FallbackMixin
from app.core.model_engine_predict import PredictMixin

# T-P2-001 PHASE_2 结构性优化: Mixin 拆分导入
# 风险映射/干预/危机/SHAP 方法 → RiskMixin (model_engine_risk.py)
# 启发式回退策略方法 → FallbackMixin (model_engine_fallback.py)
# 核心预测方法 → PredictMixin (model_engine_predict.py)
from app.core.model_engine_risk import RiskMixin
from app.core.model_registry import MODEL_PATHS, is_model_enabled, resolve_model_path
from app.ml.fusion_engine import FusionEngine
from app.ml.fusion_priority_engine import FusionPriorityEngine
from app.ml.text_analyzer import TextAnalyzer

logger = logging.getLogger(__name__)


# P2 修复：移除无意义的自赋值 MODEL_PATHS = MODEL_PATHS，MODEL_PATHS 已在顶部导入
# MAINT-P0-002: _STR_TO_NUM / _DEFAULTS / LITE_FEATURE_ORDER 常量已抽离至 app/core/feature_maps.py
# 详见 feature_maps.py 模块 docstring 与 tests/test_feature_maps.py 完整性测试


CHUNK_SIZE = 64 * 1024

_KNOWN_MODEL_HASHES: dict[str, str] = {}

_HASH_MISMATCH_POLICY: str = "warn"


def _verify_file_hash(model_id: str, file_path: Path, computed_hash: str) -> None:
    if model_id not in _KNOWN_MODEL_HASHES:
        logger.info(
            "Model %s: no known hash on record (computed=%s). "
            "Add to _KNOWN_MODEL_HASHES for strict verification.",
            model_id,
            computed_hash,
        )
        return
    expected = _KNOWN_MODEL_HASHES[model_id]
    if computed_hash != expected:
        msg = (
            f"Model {model_id} hash mismatch! "
            f"expected={expected} computed={computed_hash}. "
            f"File may have been tampered with."
        )
        if _HASH_MISMATCH_POLICY == "reject":
            raise ValueError(msg)
        logger.critical(msg)
    else:
        logger.info("Model %s hash verified: %s", model_id, computed_hash)


def _compute_file_sha256(file_path: Path) -> str:
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            sha.update(chunk)
    return sha.hexdigest()


class LiteFeatureExtractor:
    KEYWORD_CATEGORIES: dict[str, list[str]] = {
        "academic_pressure": [
            "挂科",
            "退学",
            "考研",
            "论文",
            "毕业",
            "导师",
            "考试",
            "成绩",
            "作业",
            "学习",
            "背书",
            "中考",
            "高考",
            "学业",
            "老师",
            "周测",
        ],
        "sleep_problem": [
            "失眠",
            "熬夜",
            "早醒",
            "嗜睡",
            "噩梦",
            "睡不着",
            "睡不好",
            "多梦",
            "彻夜难眠",
            "整夜没睡",
        ],
        "social_withdrawal": [
            "独处",
            "回避",
            "不想说话",
            "孤僻",
            "不想见人",
            "不想出门",
            "孤立",
            "一个人",
        ],
        "self_harm_crisis": [
            "自残",
            "自杀",
            "想死",
            "割腕",
            "安眠药",
            "不想活",
            "活不下去",
            "死了算了",
            "结束生命",
            "跳楼",
            "上吊",
        ],
        "exercise_deficit": [
            "不运动",
            "躺着",
            "不出门",
            "宅",
        ],
        "low_mood": [
            "难过",
            "绝望",
            "空虚",
            "麻木",
            "没意义",
            "低落",
            "沮丧",
            "郁闷",
            "痛苦",
            "没意思",
        ],
        "anxiety_somatic": [
            "心慌",
            "胸闷",
            "发抖",
            "出汗",
            "窒息",
            "紧张",
            "不安",
            "害怕",
            "担心",
        ],
    }

    CRISIS_KEYWORDS: list[str] = [
        "想死",
        "自杀",
        "自残",
        "活不下去",
        "不想活",
        "结束生命",
        "死了算了",
        "一死了之",
        "不如死了",
        "死了一了百了",
    ]

    # RES-P1-002: 预编译关键词正则 + 关键词到类别映射, 替代 O(n*k) 嵌套 str.count
    # 一次 re.finditer 扫描替代 60 次独立 count, 时间复杂度 O(n+k) → O(n*m) 改善为 O(n+m)
    _KEYWORD_TO_CATEGORY: dict[str, str] = {
        kw: cat for cat, kws in KEYWORD_CATEGORIES.items() for kw in kws
    }
    # 按长度降序排列, 优先匹配更长关键词, 避免短关键词覆盖长关键词的子串
    _SORTED_KEYWORDS: list[str] = sorted(
        _KEYWORD_TO_CATEGORY.keys(), key=len, reverse=True
    )
    _COMPILED_PATTERN: re.Pattern[str] = re.compile(
        "|".join(re.escape(kw) for kw in _SORTED_KEYWORDS)
    )

    @staticmethod
    def extract(transcript: str) -> dict:
        # RES-P1-002: 使用预编译正则一次扫描, 替代 O(n*k) 嵌套 count
        counts: dict[str, int] = {
            cat: 0 for cat in LiteFeatureExtractor.KEYWORD_CATEGORIES
        }
        for m in LiteFeatureExtractor._COMPILED_PATTERN.finditer(transcript):
            cat = LiteFeatureExtractor._KEYWORD_TO_CATEGORY.get(m.group())
            if cat is not None:
                counts[cat] += 1
        total = 0
        categories = 0
        for cat, c in counts.items():
            if cat == "self_harm_crisis":
                c *= 2
            counts[cat] = c
            total += c
            if c > 0:
                categories += 1
        return {
            "keyword_counts": counts,
            "total_keywords": total,
            "unique_categories": categories,
        }


class ModelEngine(PredictMixin, FallbackMixin, RiskMixin):
    """T-P2-001 PHASE_2: ModelEngine 通过 Mixin 多继承装配预测/回退/风险方法.

    保留核心职责: 模型加载/缓存(LRU)、监控计数器、路由、
    特征工程、adapter 加载、persist loop 等.
    预测/回退/风险相关方法已迁移至:
    - PredictMixin (model_engine_predict.py)
    - FallbackMixin (model_engine_fallback.py)
    - RiskMixin (model_engine_risk.py)
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
        self._cache_maxsize: int = max(
            int(getattr(settings, "model_cache_maxsize", 20)), 0
        )
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
        self.monitoring_score_deltas: list[float] = []
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
        self._snapshot_path = Path(__file__).resolve().parents[2] / "logs"
        self.crisis_detector = CrisisDetector()
        self.text_analyzer = TextAnalyzer()
        self.fusion_priority_engine = FusionPriorityEngine()
        self.fusion_engine = FusionEngine(
            use_confidence_weighting=True,
            use_modality_missing_handling=True,
        )

    # ── M-03 修复：线程安全的监控计数器辅助方法 ──
    # 模型推理通过 asyncio.to_thread 在线程池中执行，监控计数器的
    # 读-改-写操作需在锁内完成以避免竞态条件。

    def _incr_counter(self, key: str, amount: int = 1) -> None:
        """线程安全地递增监控计数器。"""
        with self._monitoring_lock:
            self.monitoring_counters[key] += amount

    def _incr_routing(self, key: str) -> None:
        """线程安全地递增路由统计。"""
        with self._monitoring_lock:
            self._routing_stats[key] += 1

    def _incr_fallback(self) -> None:
        """线程安全地递增 fallback 计数。"""
        with self._monitoring_lock:
            self._fallback_count += 1

    def _incr_crisis_override(self) -> None:
        """线程安全地递增危机覆盖计数。"""
        with self._monitoring_lock:
            self._crisis_override_count += 1

    def _record_score_delta(self, delta: float) -> None:
        """线程安全地记录分数差值，并维护最大 500 条的滚动窗口。"""
        with self._monitoring_lock:
            self.monitoring_score_deltas.append(delta)
            if len(self.monitoring_score_deltas) > 500:
                self.monitoring_score_deltas = self.monitoring_score_deltas[-500:]

    @asynccontextmanager
    async def _timed_async(
        self, metric: str, label: str
    ) -> AsyncIterator[dict[str, float | int]]:
        started = perf_counter()
        bucket = self.predict_stats[label]
        try:
            yield bucket
        finally:
            elapsed_ms = (perf_counter() - started) * 1000.0
            bucket["count"] = int(bucket["count"]) + 1
            bucket["total_ms"] = float(bucket["total_ms"]) + elapsed_ms
            bucket["last_ms"] = elapsed_ms
            logger.info("ml_%s took %.2f ms", metric, elapsed_ms)

    def preload(self) -> None:
        for model_id in self.PRELOAD_IDS:
            try:
                self._load_model(model_id)
                logger.info("Preloaded model %s", model_id)
            except FileNotFoundError as exc:
                logger.warning(
                    "Model file not found for %s (recoverable, will fall back): %s",
                    model_id,
                    exc,
                )
            except ImportError as exc:
                logger.warning(
                    "Optional dependency missing for %s (recoverable): %s",
                    model_id,
                    exc,
                )
            except PermissionError as exc:
                logger.critical(
                    "Permission denied loading %s (NON-RECOVERABLE): %s. "
                    "Check file permissions and process user.",
                    model_id,
                    exc,
                )
            except OSError as exc:
                logger.critical(
                    "Disk/system error loading %s (NON-RECOVERABLE): %s. "
                    "Check disk space and hardware status.",
                    model_id,
                    exc,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to preload model %s (recoverable): %s", model_id, exc
                )

    def get_metrics_snapshot(self) -> dict[str, Any]:
        # M-03 修复：在锁内一次性快照所有监控计数器，避免读取过程中被并发修改
        with self._monitoring_lock:
            # 保持 defaultdict 语义：访问未设置的 key 返回 0 而非 KeyError
            counters: defaultdict[str, int] = defaultdict(int, self.monitoring_counters)
            deltas = list(self.monitoring_score_deltas[-100:])
            routing = dict(self._routing_stats)
            fallback_total = self._fallback_count
            crisis_override_count = self._crisis_override_count

        total = counters["total_structured"] or 1
        high_critical = counters["high_critical"]
        fallback = counters["fallback_used"]
        exp_hit = counters["experimental_hit"]
        exp_miss = counters["experimental_miss"]
        ext_hit = counters.get("external_hit", 0)
        ext_miss = counters.get("external_miss", 0)
        ext_total = max(ext_hit + ext_miss, 1)
        ext_delta_sum = counters.get("external_delta_sum", 0)
        uptime = time.monotonic() - self._start_time
        adapt_hit = counters.get("adapter_hit", 0)
        adapt_miss = counters.get("adapter_miss", 0)
        adapt_total = max(adapt_hit + adapt_miss, 1)
        return {
            "model_load_stats": {k: dict(v) for k, v in self.model_load_stats.items()},
            "predict_stats": {k: dict(v) for k, v in self.predict_stats.items()},
            "cache_size": len(self.models),
            "uptime_seconds": round(uptime, 1),
            "monitoring": {
                "structured_total": counters["total_structured"],
                "high_critical_ratio": round(high_critical / total, 4),
                "high_critical_count": high_critical,
                "fallback_ratio": round(fallback / total, 4),
                "fallback_count": fallback,
                "experimental_hit_ratio": round(exp_hit / total, 4),
                "experimental_hit_count": exp_hit,
                "experimental_miss_count": exp_miss,
                "input_quality": {
                    "complete": counters["quality_complete"],
                    "partial": counters["quality_partial"],
                    "poor": counters["quality_poor"],
                },
                "score_delta_recent": {
                    "count": len(deltas),
                    "mean_abs_delta": round(
                        sum(abs(d) for d in deltas) / max(len(deltas), 1), 2
                    ),
                    "max_abs_delta": (
                        round(max(abs(d) for d in deltas), 2) if deltas else 0
                    ),
                },
                "experimental_external": {
                    "hit_ratio": round(ext_hit / ext_total, 4),
                    "hit_count": ext_hit,
                    "miss_count": ext_miss,
                    "delta_recent": {
                        "mean_abs_delta": round(ext_delta_sum / max(ext_hit, 1), 2),
                        "delta_gt_15_ratio": round(
                            counters.get("external_delta_gt_15", 0) / max(ext_hit, 1), 4
                        ),
                        "delta_gt_30_ratio": round(
                            counters.get("external_delta_gt_30", 0) / max(ext_hit, 1), 4
                        ),
                        "delta_gt_40_ratio": round(
                            counters.get("external_delta_gt_40", 0) / max(ext_hit, 1), 4
                        ),
                    },
                },
                "delta_by_level": {
                    "gt_15": counters.get("external_delta_gt_15", 0),
                    "gt_30": counters.get("external_delta_gt_30", 0),
                    "gt_40": counters.get("external_delta_gt_40", 0),
                },
                "adapter": {
                    "hit_ratio": round(adapt_hit / adapt_total, 4),
                    "hit_count": adapt_hit,
                    "miss_count": adapt_miss,
                },
                "routing": routing,
                "fallback_total": fallback_total,
                "crisis_override_count": crisis_override_count,
            },
            # RES-P0-001: LRU 缓存淘汰指标
            "cache_evictions": self._cache_evictions,
            "cache_maxsize": self._cache_maxsize,
        }

    def _abs_path(self, rel_path: str) -> Path:
        raw = Path(rel_path)
        if raw.is_absolute():
            return raw

        candidate_paths: list[Path] = []
        candidate_paths.append(raw)

        model_dir = Path(settings.model_dir)
        if raw.parts and raw.parts[0] == "models":
            candidate_paths.append(model_dir.parent / raw)
        else:
            candidate_paths.append(model_dir / raw)

        backend_root = Path(__file__).resolve().parents[2]
        candidate_paths.append(backend_root / raw)
        if raw.parts and raw.parts[0] == "models":
            candidate_paths.append(backend_root / raw)
        else:
            candidate_paths.append(backend_root / "models" / raw)

        for p in candidate_paths:
            if p.exists():
                return p

        return candidate_paths[1]

    def _load_adapter(self) -> Any:

        try:
            adapter_pkl = (
                Path(__file__).resolve().parents[2]
                / "models"
                / "v1.24_adapter"
                / "score_adapter.pkl"
            )
            if not adapter_pkl.exists():
                logger.debug("v1.24 adapter pkl not found at %s", adapter_pkl)
                return None

            # ML-005 修复：使用安全加载器（路径校验 + 大小校验 + 审计日志）
            from app.core.safe_pickle import safe_joblib_load

            models_root = Path(__file__).resolve().parents[2] / "models"
            adapter = safe_joblib_load(
                adapter_pkl,
                trusted_root=models_root,
                model_id="v1.24_adapter",
            )
            logger.info(
                "v1.24 adapter loaded (version=%s)",
                getattr(adapter, "version", "unknown"),
            )
            return adapter
        except Exception as exc:
            logger.warning("Failed to load v1.24 adapter: %s", exc)
            return None

    async def _persist_loop(self, interval: float = 60.0) -> None:
        import json

        self._snapshot_path.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                await asyncio.sleep(interval)
                snapshot = self.get_metrics_snapshot()
                snapshot["persisted_at"] = time.time()
                snapshot_file = self._snapshot_path / "monitoring_snapshot.json"
                snapshot_file.write_text(
                    json.dumps(snapshot, indent=2, ensure_ascii=False, default=str),
                    encoding="utf-8",
                )
                logger.debug("Monitoring snapshot persisted to %s", snapshot_file)
            except asyncio.CancelledError:
                logger.info("Monitoring persist loop cancelled")
                break
            except Exception as exc:
                logger.warning("Monitoring persist error: %s", exc)

    def start_persist(self, interval: float = 60.0) -> None:
        if self._persist_task is not None and not self._persist_task.done():
            return
        self._persist_task = asyncio.create_task(self._persist_loop(interval))
        logger.info("Monitoring persist started (interval=%ss)", interval)

    async def stop_persist(self) -> None:
        if self._persist_task is not None and not self._persist_task.done():
            self._persist_task.cancel()
            try:
                await self._persist_task
            except asyncio.CancelledError:
                pass
            self._persist_task = None
            logger.info("Monitoring persist stopped")

    # ── RES-P0-001 修复: LRU 缓存操作方法 ──
    # _load_model 通过 asyncio.to_thread 在线程池中执行, 多个 predict 并发时
    # 可能同时访问 self.models, 因此所有缓存操作需在 _cache_lock 内完成.

    def _cache_get(self, model_id: str) -> Any:
        """LRU 缓存读取: 命中时移到末尾 (MRU), 未命中返回 None."""
        with self._cache_lock:
            if model_id not in self.models:
                return None
            self.models.move_to_end(model_id)
            return self.models[model_id]

    def _cache_put(self, model_id: str, model: Any) -> None:
        """LRU 缓存写入: 存入并移到末尾 (MRU), 超过 maxsize 时弹出最旧 (LRU).

        maxsize=0 时禁用 LRU (仅用于测试), 无限缓存保持向后兼容.
        """
        if model is None:
            return
        with self._cache_lock:
            self.models[model_id] = model
            self.models.move_to_end(model_id)
            # maxsize=0 禁用淘汰 (测试用)
            if self._cache_maxsize > 0:
                while len(self.models) > self._cache_maxsize:
                    evicted_id, _ = self.models.popitem(last=False)
                    self._cache_evictions += 1
                    logger.info(
                        "LRU cache evicted model %s (size=%d, maxsize=%d, evictions=%d)",
                        evicted_id,
                        len(self.models),
                        self._cache_maxsize,
                        self._cache_evictions,
                    )

    def _load_model(self, model_id: str) -> Any:

        # RES-P0-001: 使用 LRU 缓存读取
        cached = self._cache_get(model_id)
        if cached is not None:
            stats = self.model_load_stats[model_id]
            stats["cache_hits"] = int(stats["cache_hits"]) + 1
            return cached

        if model_id not in MODEL_PATHS:
            raise FileNotFoundError(f"Unknown model_id: {model_id}")
        if not is_model_enabled(model_id):
            raise FileNotFoundError(f"Model disabled: {model_id}")

        model_path = self._abs_path(resolve_model_path(model_id))
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        started = perf_counter()
        if model_path.suffix == ".pkl":
            # P0-S1 修复：使用 safe_joblib_load 替代直接 joblib.load，启用路径白名单防止路径遍历
            # safe_joblib_load 内部完成：路径校验、大小校验、哈希计算、joblib.load
            # 此处保留 _verify_file_hash 用于与模型注册表的预期哈希比对（额外完整性层）
            try:
                file_hash = _compute_file_sha256(model_path)
                _verify_file_hash(model_id, model_path, file_hash)
                logger.info("Loading model %s (hash=%s)", model_id, file_hash)
                from app.core.safe_pickle import safe_joblib_load

                # 模型文件可能位于项目根 models/ 或 backend/models/ 两个位置。
                # _abs_path 会返回第一个存在的候选路径，因此 trusted_root 需要动态确定
                # 以匹配实际文件所在目录，否则路径白名单校验会误拒合法文件。
                resolved = model_path.resolve()
                config_root = Path(settings.model_dir).resolve()
                if not resolved.is_relative_to(config_root):
                    # 文件不在配置的 model_dir 下，回退到 BACKEND_DIR/models
                    trusted_root = BACKEND_DIR / "models"
                else:
                    trusted_root = config_root
                model = safe_joblib_load(
                    model_path,
                    trusted_root=trusted_root,
                    model_id=model_id,
                    expected_hash=file_hash,
                    # H-04 修复：传入预计算的哈希，避免 safe_joblib_load 内部重复计算
                    precomputed_hash=file_hash,
                )
            except Exception as exc:
                raise ValueError(
                    f"Failed to load model {model_id}: corrupted or invalid file"
                ) from exc
        elif model_path.suffix == ".keras":
            import tensorflow as tf

            try:
                file_hash = _compute_file_sha256(model_path)
                _verify_file_hash(model_id, model_path, file_hash)
                logger.info("Loading Keras model %s (hash=%s)", model_id, file_hash)
                model = tf.keras.models.load_model(model_path)
            except (TypeError, ValueError) as exc:
                message = str(exc)
                if (
                    "quantization_config" not in message
                    and "Could not locate class" not in message
                ):
                    raise
                # C-Core-2 修复：改用 custom_objects 传递兼容 Dense 子类，
                # 避免修改全局 Dense.from_config（原实现即使加 _keras_load_lock 仍有并发风险：
                # 若 load_model 内部触发其他线程的模型加载，会用到被修改的 from_config）。
                from keras.src.layers.core.dense import Dense

                class _CompatDense(Dense):
                    @classmethod
                    def from_config(cls, config):
                        config = dict(config)
                        config.pop("quantization_config", None)
                        return super().from_config(config)

                logger.warning(
                    "Loading Keras model %s with compat Dense (quantization_config)",
                    model_id,
                )
                try:
                    model = tf.keras.models.load_model(
                        model_path, custom_objects={"Dense": _CompatDense}
                    )
                except Exception as e:
                    logger.warning("Keras model load failed: %s", e)
                    return None
        elif model_path.is_dir():
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(model_path)
            bert_model = AutoModelForSequenceClassification.from_pretrained(model_path)
            model = {"tokenizer": tokenizer, "model": bert_model}
        else:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(model_path)
            bert_model = AutoModelForSequenceClassification.from_pretrained(model_path)
            model = {"tokenizer": tokenizer, "model": bert_model}

        elapsed_ms = (perf_counter() - started) * 1000.0
        stats = self.model_load_stats[model_id]
        stats["loads"] = int(stats["loads"]) + 1
        stats["last_load_ms"] = elapsed_ms
        if not stats["first_load_ms"]:
            stats["first_load_ms"] = elapsed_ms
        # RES-P0-001: 使用 LRU 缓存写入 (超限自动淘汰最旧模型)
        self._cache_put(model_id, model)
        logger.info("Loaded model %s in %.2f ms", model_id, elapsed_ms)
        return model

    async def _load_model_async(self, model_id: str) -> Any:
        """P1-1: 异步加载模型, 缓存命中时直接返回, 缓存未命中时在线程池加载.

        避免首次加载 (如 BERT/Keras 模型) 阻塞事件循环.
        缓存命中 (常见场景) 无线程调度开销.
        """
        # RES-P0-001: 使用 LRU 缓存读取 (命中时移到 MRU)
        cached = self._cache_get(model_id)
        if cached is not None:
            stats = self.model_load_stats[model_id]
            stats["cache_hits"] = int(stats["cache_hits"]) + 1
            return cached
        return await asyncio.to_thread(self._load_model, model_id)

    async def _load_adapter_async(self) -> Any:
        """P1-1: 异步加载 v1.24 adapter, 带缓存避免重复 I/O."""
        if self._adapter_cached is not None:
            return self._adapter_cached
        self._adapter_cached = await asyncio.to_thread(self._load_adapter)
        return self._adapter_cached

    @staticmethod
    def _patch_simple_imputer(model: Pipeline) -> None:
        from sklearn.impute import SimpleImputer

        if hasattr(model, "named_steps") and "preprocessor" in model.named_steps:
            preprocessor = model.named_steps["preprocessor"]
            if hasattr(preprocessor, "transformers_"):
                for _, transformer, _ in preprocessor.transformers_:
                    if transformer == "drop" or transformer == "passthrough":
                        continue
                    if hasattr(transformer, "named_steps"):
                        for step_name, step in transformer.named_steps.items():
                            if not isinstance(step, SimpleImputer):
                                continue
                            try:
                                import sklearn
                                from packaging import version

                                current_ver = version.parse(sklearn.__version__)
                                if current_ver >= version.parse("1.3.0"):
                                    if hasattr(step, "_fill_dtype"):
                                        step._fill_dtype = None  # type: ignore[attr-defined]
                                    else:
                                        logger.debug(
                                            "SimpleImputer[%s] @ sklearn %s: no _fill_dtype patch needed",
                                            step_name,
                                            sklearn.__version__,
                                        )
                            except Exception:
                                # M-L 修复：记录 sklearn 兼容性补丁失败，避免静默掩盖问题
                                logger.debug(
                                    "model_engine: SimpleImputer _fill_dtype patch failed",
                                    exc_info=True,
                                )
                                if hasattr(step, "_fill_dtype"):
                                    step._fill_dtype = None  # type: ignore[attr-defined]

    @staticmethod
    def _get_numeric_pipe_cols(model: Pipeline) -> set[str]:
        numeric_pipe_cols: set[str] = set()
        if hasattr(model, "named_steps") and "preprocessor" in model.named_steps:
            _prep = model.named_steps["preprocessor"]
            if hasattr(_prep, "transformers_"):
                for _tname, _trans, _cols in _prep.transformers_:
                    if _trans in ("drop", "passthrough"):
                        continue
                    if _tname == "num":
                        numeric_pipe_cols.update(
                            _cols if isinstance(_cols, list) else list(_cols)
                        )
        return numeric_pipe_cols

    @staticmethod
    def _build_structured_input(
        raw: dict[str, Any],
        model_feature_names: list[str],
        model: Pipeline,
    ) -> dict[str, Any]:
        input_dict: dict[str, Any] = {}

        for col in model_feature_names:
            input_dict[col] = _DEFAULTS.get(col, 0)

        # C-01 修复：使用显式 None 检查替代 `or`，避免合法的 0 值被替换为默认值
        def _get_num(key: str, default: float, cast: type = float) -> float:
            val = raw.get(key)
            return cast(val) if val is not None else default

        # C-1 修复：移除 `or 1`，避免 gender=0（女性）被错误转换为 1（男性）
        gender = int(raw.get("gender", 1)) if raw.get("gender") is not None else 1
        age = _get_num("age", 20)
        sleep_duration_hours = _get_num("sleep_duration", 7)
        stress_level = _get_num("stress_level", 2)
        _social_support = _get_num("social_support", 3)  # noqa: F841
        financial_pressure = _get_num("financial_pressure", 2)
        family_history = (
            int(raw.get("family_history", 0))
            if raw.get("family_history") is not None
            else 0
        )
        academic_pressure = _get_num("academic_pressure", 2)
        _anxiety = _get_num("anxiety", 1)  # noqa: F841
        _panic_attack = (
            int(raw.get("panic_attack", 0))
            if raw.get("panic_attack") is not None
            else 0
        )  # noqa: F841
        _treatment_seeking = (
            int(raw.get("treatment_seeking", 0))
            if raw.get("treatment_seeking") is not None
            else 0
        )  # noqa: F841
        suicidal_thoughts = (
            int(raw.get("suicidal_thoughts", 0))
            if raw.get("suicidal_thoughts") is not None
            else 0
        )
        cgpa_src = _get_num("cgpa", 3.0)
        _gpa_scale_default = 4.0 if cgpa_src <= 4 else 10.0
        gpa_scale = _get_num("gpa_scale", _gpa_scale_default)
        cgpa = cgpa_src / gpa_scale * 10 if gpa_scale > 0 else cgpa_src

        sleep_duration_cat = "7-8 hours"
        if sleep_duration_hours < 5:
            sleep_duration_cat = "Less than 5 hours"
        elif sleep_duration_hours < 7:
            sleep_duration_cat = "5-6 hours"
        elif sleep_duration_hours > 8:
            sleep_duration_cat = "More than 8 hours"

        sleep_ordinal_map = {
            "Less than 5 hours": 0,
            "5-6 hours": 1,
            "7-8 hours": 2,
            "More than 8 hours": 3,
        }

        if age <= 18:
            age_group = "<=18"
        elif age <= 25:
            age_group = "19-25"
        elif age <= 35:
            age_group = "26-35"
        elif age <= 45:
            age_group = "36-45"
        elif age <= 60:
            age_group = "46-60"
        else:
            age_group = "60+"

        derived_map: dict[str, Any] = {
            "Gender": "Male" if int(gender) == 1 else "Female",
            "Age": age,
            "Academic Pressure": max(0.0, min(5.0, academic_pressure)),
            "Work Pressure": 0.0,
            "CGPA": max(0.0, min(10.0, cgpa)),
            "Study Satisfaction": max(0.0, min(5.0, 5.0 - stress_level)),
            "Job Satisfaction": 0.0,
            "Sleep Duration": sleep_duration_cat,
            "Dietary Habits": "Moderate",
            "Have you ever had suicidal thoughts ?": (
                "Yes" if suicidal_thoughts == 1 else "No"
            ),
            "Work/Study Hours": float(8 + academic_pressure * 1.5),
            "Financial Stress": max(0.0, min(5.0, financial_pressure)),
            "Family History of Mental Illness": "Yes" if family_history == 1 else "No",
            "SleepDurationOrdinal": sleep_ordinal_map[sleep_duration_cat],
            "DietaryHabitsOrdinal": 1,
            "AgeGroup": age_group,
        }

        for col, val in raw.items():
            if col in model_feature_names:
                input_dict[col] = val
        for col, val in derived_map.items():
            if col in model_feature_names:
                input_dict[col] = val

        numeric_pipe_cols = ModelEngine._get_numeric_pipe_cols(model)
        if not numeric_pipe_cols and model_feature_names:
            numeric_pipe_cols = set(model_feature_names)

        for _col in numeric_pipe_cols:
            if _col in input_dict and isinstance(input_dict[_col], str):
                _mapping = _STR_TO_NUM.get(_col, {})
                input_dict[_col] = _mapping.get(input_dict[_col], 0)

        return input_dict

    def _route_structured(
        self, raw: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        STRUCTURED_FEATURE_SET = {
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
        }
        available = sum(
            1
            for f in STRUCTURED_FEATURE_SET
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
            routing_info["selected_model_id"] = "structured_logistic_regression_v1.20"
            routing_info["selected_model_family"] = "structured"
            routing_info["routing_reason"] = "feature_coverage_sufficient"
            routing_info["prediction_confidence_band"] = (
                "high" if f_coverage >= 0.90 else "medium"
            )
            self._incr_routing("structured")
            return routing_info, None

        if gad7 is not None and transcript and len(str(transcript)) >= 20:
            routing_info["selected_model_family"] = "lite"
            routing_info["routing_reason"] = (
                "feature_coverage_insufficient_text_available"
            )
            routing_info["prediction_confidence_band"] = "medium"
            self._incr_routing("lite")
            return routing_info, "lite"

        if gad7 is not None:
            routing_info["selected_model_family"] = "anxiety_only"
            routing_info["routing_reason"] = "only_gad7_available"
            routing_info["prediction_confidence_band"] = "low"
            self._incr_routing("anxiety_only")
            return routing_info, "anxiety_only"

        routing_info["selected_model_family"] = "insufficient"
        routing_info["routing_reason"] = "insufficient_information"
        routing_info["prediction_confidence_band"] = "low"
        self._incr_routing("insufficient")
        return routing_info, "insufficient"

    def _update_structured_monitoring(
        self,
        risk_score: float,
        risk_level: int,
        fallback_used: bool,
        experimental_real_score: float | None,
        experimental_real_model: str | None,
        experimental_external_available: bool,
        experimental_external_score: float | None,
        quality_level: str,
    ) -> None:
        self._incr_counter("total_structured")
        if risk_level >= 3:
            self._incr_counter("high_critical")
        if fallback_used:
            self._incr_counter("fallback_used")
        if experimental_real_model is not None:
            self._incr_counter("experimental_hit")
        else:
            self._incr_counter("experimental_miss")
        qual = quality_level or "complete"
        self._incr_counter(f"quality_{qual}")
        if experimental_real_score is not None:
            delta = experimental_real_score - risk_score
            self._record_score_delta(delta)
        if experimental_external_available:
            self._incr_counter("external_hit")
            ext_delta = (
                abs(experimental_external_score - risk_score)
                if experimental_external_score is not None
                else 0
            )
            # external_delta_sum 累积 float 差值，单独在锁内更新
            with self._monitoring_lock:
                self.monitoring_counters["external_delta_sum"] += ext_delta  # type: ignore[operator]
            if ext_delta > 15:
                self._incr_counter("external_delta_gt_15")
            if ext_delta > 30:
                self._incr_counter("external_delta_gt_30")
            if ext_delta > 40:
                self._incr_counter("external_delta_gt_40")
        else:
            self._incr_counter("external_miss")

    # ── T-P2-001 PHASE_2: 以下方法已迁移至 Mixin 模块 ──
    # 风险映射/干预/危机/SHAP 方法 → RiskMixin (model_engine_risk.py):
    #   _score_to_level, score_to_level, _level_to_severity,
    #   _build_intervention_plan, _check_crisis_safety,
    #   _attention_gate, _boost_gate_for_physiology,
    #   _compute_shap_factors, _compute_shap_factors_array
    #
    # 启发式回退策略方法 → FallbackMixin (model_engine_fallback.py):
    #   _structured_heuristic_fallback, _text_heuristic_fallback,
    #   _anxiety_only_fallback, _physiological_heuristic_fallback
    #
    # 核心预测方法 → PredictMixin (model_engine_predict.py):
    #   predict_structured, _run_experimental_v121, _run_experimental_v123,
    #   _run_adapter, predict_text, _predict_text_ml, _predict_text_bert,
    #   predict_lite, predict_physiological, _predict_physiological,
    #   _predict_physiological_sync, predict_fusion, explain_prediction
    #
    # 死代码清理: _predict_keras_fusion (无任何调用方) 已删除.


model_engine = ModelEngine()
