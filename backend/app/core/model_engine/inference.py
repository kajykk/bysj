"""推理编排与监控层 (IN 层).

本模块从 `app.core.model_engine` 拆分而来 (model_engine 包结构化拆分),
承担 ModelEngine 的推理支撑职责:

- 路由决策 (`_route_structured`: 结构化/lite/anxiety_only/insufficient 四路)
- 特征工程 (`_build_structured_input`, 配套 `_get_numeric_pipe_cols`)
- 线程安全监控计数器 (`_incr_counter` / `_incr_routing` / `_record_score_delta` 等)
- 监控快照与持久化 (`get_metrics_snapshot` / `_persist_loop` / Prometheus 发布)
- BERT micro-batch 收集器 (`_BertMicroBatchCollector`) 与 Lite 文本特征抽取器
  (`LiteFeatureExtractor`)

通过 Mixin 多继承模式装配到 ModelEngine:

    class ModelEngine(InferenceMixin, ...):
        ...

依赖关系 (装配后由 ModelEngine 主体提供):
- `self.monitoring_counters` / `self._monitoring_lock` → ModelEngine.__init__
- `self.predict_stats` / `self._routing_stats`          → ModelEngine.__init__
- `self.monitoring_score_deltas` / `self._start_time`   → ModelEngine.__init__
- `self._snapshot_path` / `self._persist_task`           → ModelEngine.__init__

向后兼容: 仅需 `from app.core.model_engine import ModelEngine` 即可继续使用,
本模块对调用方完全透明.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from time import perf_counter
from typing import TYPE_CHECKING, Any, AsyncIterator

# P1-E 修复：使用 TYPE_CHECKING 避免运行时导入，同时提供精确类型提示
if TYPE_CHECKING:
    from sklearn.pipeline import Pipeline

    # 仅类型提示用: _BertMicroBatchCollector 持有 engine 引用 (运行时不导入, 避免循环依赖)
    from app.core.model_engine import ModelEngine

# MAINT-P0-002: _STR_TO_NUM / _DEFAULTS 已抽离到 feature_maps.py,
# 此处通过别名导入保持内部 _ 前缀命名约定
from app.core.feature_maps import DEFAULTS as _DEFAULTS
from app.core.feature_maps import STR_TO_NUM as _STR_TO_NUM

logger = logging.getLogger(__name__)


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
    _KEYWORD_TO_CATEGORY: dict[str, str] = {kw: cat for cat, kws in KEYWORD_CATEGORIES.items() for kw in kws}
    # 按长度降序排列, 优先匹配更长关键词, 避免短关键词覆盖长关键词的子串
    _SORTED_KEYWORDS: list[str] = sorted(_KEYWORD_TO_CATEGORY.keys(), key=len, reverse=True)
    _COMPILED_PATTERN: re.Pattern[str] = re.compile("|".join(re.escape(kw) for kw in _SORTED_KEYWORDS))

    @staticmethod
    def extract(transcript: str) -> dict:
        # RES-P1-002: 使用预编译正则一次扫描, 替代 O(n*k) 嵌套 count
        counts: dict[str, int] = {cat: 0 for cat in LiteFeatureExtractor.KEYWORD_CATEGORIES}
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


class _BertMicroBatchCollector:
    """PERF-P3-007: BERT micro-batching collector.

    收集短时间内的多条文本预测请求, 批量推理提高吞吐量.
    通过 asyncio.Queue 收集请求, 后台 worker 定期触发 batch 推理.

    设计要点:
    - max_batch_size=8: 一次 batch 最多 8 条文本 (CPU 推理友好)
    - max_wait_ms=50: 最多等待 50ms 攒 batch, 避免低流量时延迟过高
    - Future 管理: 每个请求返回 Future, batch 完成后设置结果
    - 异常隔离: batch 推理失败时所有 Future 返回 None (走 TF-IDF 回退)
    """

    def __init__(
        self,
        engine: "ModelEngine",
        max_batch_size: int = 8,
        max_wait_ms: float = 50.0,
    ) -> None:
        self._engine = engine
        self._max_batch_size = max_batch_size
        self._max_wait_seconds = max_wait_ms / 1000.0
        self._queue: asyncio.Queue[tuple[str, asyncio.Future[dict[str, Any] | None]]] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        """启动后台 batch worker."""
        if self._worker_task is not None:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info(
            "PERF-P3-007: BERT micro-batch collector started " "(max_batch_size=%d, max_wait_ms=%.0f)",
            self._max_batch_size,
            self._max_wait_seconds * 1000,
        )

    async def stop(self) -> None:
        """停止后台 batch worker, 排空队列并取消未完成的 futures."""
        self._running = False
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        # 排空队列, 取消未完成的 futures
        while not self._queue.empty():
            try:
                _, fut = self._queue.get_nowait()
                if not fut.done():
                    fut.cancel()
            except asyncio.QueueEmpty:
                break
        logger.info("PERF-P3-007: BERT micro-batch collector stopped")

    async def submit(self, text: str) -> dict[str, Any] | None:
        """提交单条文本到 batch 队列, 等待结果."""
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any] | None] = loop.create_future()
        await self._queue.put((text, fut))
        return await fut

    async def _worker_loop(self) -> None:
        """后台 worker: 收集请求并批量推理."""
        while self._running:
            try:
                # 等待第一个请求 (1s 超时, 便于检查 _running 状态)
                first_item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            first_text, first_fut = first_item
            batch_texts: list[str] = [first_text]
            batch_futs: list[asyncio.Future[dict[str, Any] | None]] = [first_fut]
            deadline = asyncio.get_event_loop().time() + self._max_wait_seconds

            # 收集更多请求 (最多 max_batch_size - 1 个, 最多等 max_wait_ms)
            while len(batch_texts) < self._max_batch_size:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    break
                try:
                    text, fut = await asyncio.wait_for(self._queue.get(), timeout=remaining)
                    batch_texts.append(text)
                    batch_futs.append(fut)
                except asyncio.TimeoutError:
                    break

            # 批量推理
            try:
                results = await self._engine._predict_text_bert_batch(batch_texts)
                for fut, result in zip(batch_futs, results):
                    if not fut.done():
                        fut.set_result(result)
            except Exception as exc:
                logger.error("PERF-P3-007: batch inference failed: %s", exc)
                for fut in batch_futs:
                    if not fut.done():
                        fut.set_result(None)


class InferenceMixin:
    """推理编排 / 路由 / 特征工程 / 监控方法集合.

    这些方法通过 Mixin 装配到 ModelEngine, 依赖 ModelEngine.__init__ 提供的
    监控计数器 / 统计字典 / 快照路径等实例属性.
    """

    async def start_bert_batch_collector(self, max_batch_size: int = 8, max_wait_ms: float = 50.0) -> None:
        """PERF-P3-007: 启动 BERT micro-batch collector.

        启动后 _predict_text_bert 会自动走 batch 路径,
        收集短时间内的多条请求批量推理, 提高吞吐量.
        """
        if self._bert_batch_collector is not None:
            return
        self._bert_batch_collector = _BertMicroBatchCollector(
            self, max_batch_size=max_batch_size, max_wait_ms=max_wait_ms
        )
        await self._bert_batch_collector.start()

    async def stop_bert_batch_collector(self) -> None:
        """PERF-P3-007: 停止 BERT micro-batch collector."""
        if self._bert_batch_collector is not None:
            await self._bert_batch_collector.stop()
            self._bert_batch_collector = None

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
        """线程安全地记录分数差值。deque(maxlen=500) 自动淘汰旧数据, 无需手动截断。"""
        with self._monitoring_lock:
            self.monitoring_score_deltas.append(delta)

    @asynccontextmanager
    async def _timed_async(self, metric: str, label: str) -> AsyncIterator[dict[str, float | int]]:
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

    def get_metrics_snapshot(self) -> dict[str, Any]:
        # M-03 修复：在锁内一次性快照所有监控计数器，避免读取过程中被并发修改
        with self._monitoring_lock:
            # 保持 defaultdict 语义：访问未设置的 key 返回 0 而非 KeyError
            counters: defaultdict[str, int] = defaultdict(int, self.monitoring_counters)
            # RES-P3-003: deque 不支持切片, 先转 list 再切片
            deltas = list(self.monitoring_score_deltas)[-100:]
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
                    "mean_abs_delta": round(sum(abs(d) for d in deltas) / max(len(deltas), 1), 2),
                    "max_abs_delta": (round(max(abs(d) for d in deltas), 2) if deltas else 0),
                },
                "experimental_external": {
                    "hit_ratio": round(ext_hit / ext_total, 4),
                    "hit_count": ext_hit,
                    "miss_count": ext_miss,
                    "delta_recent": {
                        "mean_abs_delta": round(ext_delta_sum / max(ext_hit, 1), 2),
                        "delta_gt_15_ratio": round(counters.get("external_delta_gt_15", 0) / max(ext_hit, 1), 4),
                        "delta_gt_30_ratio": round(counters.get("external_delta_gt_30", 0) / max(ext_hit, 1), 4),
                        "delta_gt_40_ratio": round(counters.get("external_delta_gt_40", 0) / max(ext_hit, 1), 4),
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

    async def _persist_loop(self, interval: float = 60.0) -> None:
        import json

        self._snapshot_path.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                await asyncio.sleep(interval)
                snapshot = self.get_metrics_snapshot()
                snapshot["persisted_at"] = time.time()
                # RES-P2-006: 统一 Prometheus — 发布到 metrics.py Gauge
                self._publish_to_prometheus(snapshot)
                # 保留 monitoring_snapshot.json 作为可选备份 (向后兼容)
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

    def _publish_to_prometheus(self, snapshot: dict[str, Any]) -> None:
        """RES-P2-006: 将监控快照发布到 Prometheus 指标 (替代本地文件冗余持久化).

        更新 metrics.py 中的 Gauge, 由 /metrics 端点统一导出.
        保留 monitoring_snapshot.json 作为备份, 但 Prometheus 是主要数据源.
        """
        try:
            from app.core import metrics

            monitoring = snapshot.get("monitoring", {})
            metrics.model_cache_size.set(snapshot.get("cache_size", 0))
            metrics.model_uptime_seconds.set(snapshot.get("uptime_seconds", 0))
            metrics.model_high_critical_ratio.set(monitoring.get("high_critical_ratio", 0))
            metrics.model_high_critical_count.set(monitoring.get("high_critical_count", 0))
            metrics.model_fallback_count.set(monitoring.get("fallback_count", 0))
            metrics.model_fallback_rate.set(monitoring.get("fallback_ratio", 0))
            metrics.model_experimental_hit_count.set(monitoring.get("experimental_hit_count", 0))
            metrics.model_experimental_miss_count.set(monitoring.get("experimental_miss_count", 0))
            metrics.model_structured_total.set(monitoring.get("structured_total", 0))
        except Exception as exc:
            logger.warning("RES-P2-006: Publish to Prometheus failed: %s", exc)

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
                        numeric_pipe_cols.update(_cols if isinstance(_cols, list) else list(_cols))
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
        family_history = int(raw.get("family_history", 0)) if raw.get("family_history") is not None else 0
        academic_pressure = _get_num("academic_pressure", 2)
        _anxiety = _get_num("anxiety", 1)  # noqa: F841
        _panic_attack = int(raw.get("panic_attack", 0)) if raw.get("panic_attack") is not None else 0  # noqa: F841
        _treatment_seeking = int(raw.get("treatment_seeking", 0)) if raw.get("treatment_seeking") is not None else 0  # noqa: F841
        suicidal_thoughts = int(raw.get("suicidal_thoughts", 0)) if raw.get("suicidal_thoughts") is not None else 0
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

        # D1 修复:推导 Working Professional or Student(从 profession 字段或 age 推断)
        profession_str = str(raw.get("profession", raw.get("Profession", ""))).lower().strip()
        if "student" in profession_str:
            working_or_student = "Student"
        elif profession_str and profession_str not in ("none", "nan", ""):
            working_or_student = "Working Professional"
        elif age <= 25:
            working_or_student = "Student"
        else:
            working_or_student = "Working Professional"

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
            "Have you ever had suicidal thoughts ?": ("Yes" if suicidal_thoughts == 1 else "No"),
            "Work/Study Hours": float(8 + academic_pressure * 1.5),
            "Financial Stress": max(0.0, min(5.0, financial_pressure)),
            "Family History of Mental Illness": "Yes" if family_history == 1 else "No",
            "SleepDurationOrdinal": sleep_ordinal_map[sleep_duration_cat],
            "DietaryHabitsOrdinal": 1,
            "AgeGroup": age_group,
            "Working Professional or Student": working_or_student,
        }

        for col, val in raw.items():
            if col in model_feature_names:
                input_dict[col] = val
        for col, val in derived_map.items():
            if col in model_feature_names:
                input_dict[col] = val

        numeric_pipe_cols = InferenceMixin._get_numeric_pipe_cols(model)
        if not numeric_pipe_cols and model_feature_names:
            numeric_pipe_cols = set(model_feature_names)

        for _col in numeric_pipe_cols:
            if _col in input_dict and isinstance(input_dict[_col], str):
                _mapping = _STR_TO_NUM.get(_col, {})
                input_dict[_col] = _mapping.get(input_dict[_col], 0)

        return input_dict

    def _route_structured(self, raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
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
        available = sum(1 for f in STRUCTURED_FEATURE_SET if f in raw and raw[f] is not None and raw[f] != "")
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
            routing_info["prediction_confidence_band"] = "high" if f_coverage >= 0.90 else "medium"
            self._incr_routing("structured")
            return routing_info, None

        if gad7 is not None and transcript and len(str(transcript)) >= 20:
            routing_info["selected_model_family"] = "lite"
            routing_info["routing_reason"] = "feature_coverage_insufficient_text_available"
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
            ext_delta = abs(experimental_external_score - risk_score) if experimental_external_score is not None else 0
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
