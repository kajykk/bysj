from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Lock
from time import time
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from app.core.cache import cache_get, cache_set, make_cache_key
from app.core.config import settings
from app.core.ml_breaker import call_with_ml_breaker
from app.core.model_engine import model_engine
from app.core.model_registry import MODEL_PATHS, get_model_info, resolve_model_path

logger = logging.getLogger(__name__)

# PERF-P2-009: ML 推理结果缓存 TTL (秒), 从 settings 读取, 0 表示禁用
_ML_INFERENCE_CACHE_TTL: int = getattr(settings, "ml_inference_cache_ttl", 60)

TRAINING_JOBS: dict[str, dict[str, Any]] = {}
TRAINING_JOBS_LOCK = Lock()

# RES-P1-005 修复：TRAINING_JOBS 字典 LRU 上限，避免长跑无限增长
# 策略: 超过上限时按 created_at 升序淘汰已完成任务 (completed/failed/interrupted)
#       running/queued 任务不淘汰 (避免误删活跃任务)
TRAINING_JOBS_MAX_SIZE = 100
# 不淘汰的活跃状态 (避免误删 running/queued 任务)
_ACTIVE_JOB_STATUSES: frozenset[str] = frozenset({"running", "queued"})

# M-21 修复：训练任务持久化到 JSON 文件，避免服务重启后丢失
_TRAINING_JOBS_FILE = (
    Path(getattr(settings, "model_dir", "models")) / "training_jobs.json"
)

# H-02 文档化：TRAINING_JOBS_LOCK 锁作用范围与并发安全不变式
# ============================================================================
# 锁保护对象: 内存中的 TRAINING_JOBS 字典（读-改-写复合操作）
# 锁不保护:   磁盘文件 I/O（写入操作在锁外执行）
#
# 安全不变式（修改本模块时必须遵守）:
#   1. 任何对 TRAINING_JOBS 的读-改-写操作必须在 TRAINING_JOBS_LOCK 内完成
#   2. _save_training_jobs 采用 "锁内快照 + 锁外写入" 模式：
#      - 锁内: 复制 dict 的浅拷贝（data = {k: dict(v) ...}）
#      - 锁外: 将快照写入磁盘
#      此模式安全的原因：快照是不可变副本，磁盘写入不会与内存修改竞争
#   3. 警告: 若未来增加 "写后读" 逻辑（如写入后立即从 TRAINING_JOBS 读取并依赖
#      写入结果），必须在同一锁内完成，否则会引入 TOCTOU 竞态
#   4. 多进程部署场景下，文件写入本身可能交错，如需跨进程互斥应改用 fcntl/flock
# ============================================================================


def _load_training_jobs() -> None:
    """从磁盘加载训练任务状态。"""
    try:
        if _TRAINING_JOBS_FILE.exists():
            with open(_TRAINING_JOBS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for job_id, job_data in data.items():
                # 重启后，running 状态的任务标记为 interrupted
                if job_data.get("status") in ("running", "queued"):
                    job_data["status"] = "interrupted"
                    job_data["stage"] = "interrupted"
                    job_data["message"] = "服务重启，任务中断"
                    job_data["error"] = "service_restart"
                TRAINING_JOBS[job_id] = job_data
            logger.info("Loaded %d training jobs from disk", len(TRAINING_JOBS))
    except Exception as exc:
        logger.warning("Failed to load training jobs from disk: %s", exc)


def _save_training_jobs() -> None:
    """将训练任务状态持久化到磁盘。

    H-02 文档化：采用 "锁内快照 + 锁外写入" 模式保证并发安全。
    锁内仅做 dict 浅拷贝（O(n) 且无 I/O 阻塞），锁外执行磁盘写入。
    这样既保证快照一致性，又避免长时间持锁阻塞其他线程的内存操作。
    """
    try:
        _TRAINING_JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        # 复制一份避免序列化过程中被修改
        # 注意: 快照后即可释放锁，磁盘写入操作不需要持锁
        with TRAINING_JOBS_LOCK:
            data = {k: dict(v) for k, v in TRAINING_JOBS.items()}
        with open(_TRAINING_JOBS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning("Failed to save training jobs to disk: %s", exc)


def cleanup_old_training_jobs(max_size: int = TRAINING_JOBS_MAX_SIZE) -> int:
    """RES-P1-005: 清理超出上限的旧训练任务.

    策略:
        1. 如果 len(TRAINING_JOBS) <= max_size, 直接返回 0
        2. 按 created_at 升序排序 (老的在前)
        3. 仅淘汰非活跃状态 (completed/failed/interrupted/not_found) 的任务
        4. running/queued 任务不淘汰 (避免误删活跃任务)
        5. 直到 len(TRAINING_JOBS) <= max_size 或无可淘汰项

    Args:
        max_size: 保留的最大任务数, 默认 TRAINING_JOBS_MAX_SIZE=100

    Returns:
        被淘汰的任务数
    """
    removed = 0
    with TRAINING_JOBS_LOCK:
        if len(TRAINING_JOBS) <= max_size:
            return 0

        # 按创建时间升序 (老的在前), 缺失或非法 created_at 视为 0 (最老)
        def _safe_created_at(job_data: dict[str, Any]) -> float:
            try:
                return float(job_data.get("created_at", 0) or 0)
            except (TypeError, ValueError):
                return 0.0

        sorted_jobs = sorted(
            TRAINING_JOBS.items(),
            key=lambda kv: _safe_created_at(kv[1]),
        )
        for job_id, job_data in sorted_jobs:
            if len(TRAINING_JOBS) <= max_size:
                break
            status = job_data.get("status", "")
            if status in _ACTIVE_JOB_STATUSES:
                # 跳过活跃任务, 不淘汰
                continue
            del TRAINING_JOBS[job_id]
            removed += 1
    if removed > 0:
        logger.info(
            "cleanup_old_training_jobs: removed %d old jobs (current size=%d, max=%d)",
            removed,
            len(TRAINING_JOBS),
            max_size,
        )
        # 持久化清理后的状态到磁盘
        _save_training_jobs()
    return removed


# 模块加载时从磁盘恢复训练任务
_load_training_jobs()
# RES-P1-005: 加载后立即执行一次清理 (避免历史遗留任务累积)
cleanup_old_training_jobs()


class ModelPredictService:
    def get_model_status(self) -> dict[str, Any]:
        model_dir = Path(settings.model_dir)
        status: list[dict[str, Any]] = []
        for model_id, rel_path in MODEL_PATHS.items():
            path = Path(resolve_model_path(model_id))
            abs_path = (
                path
                if path.is_absolute()
                else (
                    model_dir.parent / path
                    if path.parts and path.parts[0] == "models"
                    else model_dir / path
                )
            )
            exists = abs_path.exists()
            model_info = get_model_info(model_id)
            lifecycle = model_info.lifecycle if model_info else None
            # L-10 修复：避免重复调用 stat()，缓存结果
            stat_info = abs_path.stat() if exists else None
            status.append(
                {
                    "model_id": model_id,
                    "path": str(abs_path),
                    "exists": exists,
                    "size_kb": (
                        round(stat_info.st_size / 1024, 2) if stat_info else None
                    ),
                    "modified_at": stat_info.st_mtime if stat_info else None,
                    "lifecycle": lifecycle,
                }
            )

        performance = model_engine.get_metrics_snapshot()
        performance_summary = {
            "cached_models": performance["cache_size"],
            "tracked_models": len(performance["model_load_stats"]),
            "tracked_paths": len(performance["predict_stats"]),
            "cache_hits_total": sum(
                int(item.get("cache_hits", 0))
                for item in performance["model_load_stats"].values()
            ),
            "loads_total": sum(
                int(item.get("loads", 0))
                for item in performance["model_load_stats"].values()
            ),
            "predict_calls_total": sum(
                int(item.get("count", 0))
                for item in performance["predict_stats"].values()
            ),
            "avg_predict_ms": round(
                sum(
                    float(item.get("total_ms", 0.0))
                    for item in performance["predict_stats"].values()
                )
                / max(
                    1,
                    sum(
                        int(item.get("count", 0))
                        for item in performance["predict_stats"].values()
                    ),
                ),
                2,
            ),
        }

        return {
            "model_dir": str(model_dir),
            "items": status,
            "ready": all(
                item["exists"]
                for item in status
                if item["model_id"]
                in {
                    "structured_logistic_regression_quick",
                    "text_depression_model",
                    "text_depression_tfidf",
                }
            ),
            "performance": performance,
            "performance_summary": performance_summary,
        }

    def start_training_job(
        self,
        dataset_name: str,
        model_name: str,
        epochs: int,
        batch_size: int,
        learning_rate: float,
    ) -> dict[str, Any]:
        job_id = uuid4().hex
        job_data = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0,
            "stage": "queued",
            "message": "任务已排队",
            "created_at": time(),
            "updated_at": time(),
            "result": None,
            "error": None,
        }

        # H-2 修复：使用 Celery 任务替代 daemon Thread，训练在独立 worker 进程执行
        # 任务状态通过 Redis 共享，Web 进程与 Celery worker 均可读写
        try:
            from app.tasks.model_training import (
                save_job_to_redis,
                train_bert_model_task,
            )

            save_job_to_redis(job_id, job_data)
            # M-21 修复：同时持久化到磁盘作为备份（兼容旧版读取路径）
            with TRAINING_JOBS_LOCK:
                TRAINING_JOBS[job_id] = dict(job_data)
            _save_training_jobs()
            # RES-P1-005: 添加任务后执行清理 (避免字典无限增长)
            cleanup_old_training_jobs()

            # 提交 Celery 任务，训练在 worker 进程中执行
            train_bert_model_task.delay(
                job_id=job_id,
                dataset_name=dataset_name,
                model_name=model_name,
                epochs=epochs,
                batch_size=batch_size,
                learning_rate=learning_rate,
            )
            logger.info(
                "[training] submitted Celery task job_id=%s dataset=%s model=%s",
                job_id,
                dataset_name,
                model_name,
            )
        except Exception as exc:
            # PERF-P2-001: 移除 daemon Thread 回退, Celery/Redis 不可用时返回 503
            # 原回退路径在 Web 进程内执行长跑训练, 会阻塞 worker 线程并绕过 Celery 资源治理
            logger.error(
                "[training] Celery submission failed, returning 503: %s", exc
            )
            raise HTTPException(
                status_code=503,
                detail="训练服务暂时不可用，请稍后重试 (Celery/Redis 故障)",
            ) from exc

        return self.get_training_job(job_id)

    def start_evaluate_job(
        self, dataset_name: str, model_name: str, split: str
    ) -> dict[str, Any]:
        """PERF-P1-006: 启动异步模型评估任务.

        替代原 experiment.py evaluate 端点中的 asyncio.to_thread 阻塞调用,
        立即返回 job_id, 评估在 Celery worker 中执行.

        Args:
            dataset_name: 数据集名称
            model_name: 模型名称
            split: 评估数据集划分 (validation | test)

        Returns:
            任务状态字典 (含 job_id, status, progress 等)
        """
        job_id = uuid4().hex
        job_data = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0,
            "stage": "queued",
            "message": "评估任务已排队",
            "created_at": time(),
            "updated_at": time(),
            "result": None,
            "error": None,
        }

        # PERF-P2-001: Celery 不可用时返回 503 (不再回退到 daemon Thread)
        try:
            from app.tasks.model_training import evaluate_model_task, save_job_to_redis

            save_job_to_redis(job_id, job_data)
            with TRAINING_JOBS_LOCK:
                TRAINING_JOBS[job_id] = dict(job_data)
            _save_training_jobs()
            cleanup_old_training_jobs()

            evaluate_model_task.delay(
                job_id=job_id,
                dataset_name=dataset_name,
                model_name=model_name,
                split=split,
            )
            logger.info(
                "[evaluate] submitted Celery task job_id=%s dataset=%s model=%s split=%s",
                job_id,
                dataset_name,
                model_name,
                split,
            )
        except Exception as exc:
            # PERF-P2-001: 移除 daemon Thread 回退, Celery/Redis 不可用时返回 503
            logger.error(
                "[evaluate] Celery submission failed, returning 503: %s", exc
            )
            raise HTTPException(
                status_code=503,
                detail="评估服务暂时不可用，请稍后重试 (Celery/Redis 故障)",
            ) from exc

        return self.get_training_job(job_id)

    def start_compare_job(
        self, dataset_name: str, model_names: list[str]
    ) -> dict[str, Any]:
        """PERF-P1-006: 启动异步多模型对比任务.

        替代原 experiment.py compare 端点中的 asyncio.to_thread 阻塞调用,
        立即返回 job_id, 对比在 Celery worker 中执行.

        Args:
            dataset_name: 数据集名称
            model_names: 待对比的模型名称列表

        Returns:
            任务状态字典 (含 job_id, status, progress 等)
        """
        if not model_names:
            raise ValueError("model_names 不能为空")

        job_id = uuid4().hex
        job_data = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0,
            "stage": "queued",
            "message": "对比任务已排队",
            "created_at": time(),
            "updated_at": time(),
            "result": None,
            "error": None,
        }

        # PERF-P2-001: Celery 不可用时返回 503 (不再回退到 daemon Thread)
        try:
            from app.tasks.model_training import compare_models_task, save_job_to_redis

            save_job_to_redis(job_id, job_data)
            with TRAINING_JOBS_LOCK:
                TRAINING_JOBS[job_id] = dict(job_data)
            _save_training_jobs()
            cleanup_old_training_jobs()

            compare_models_task.delay(
                job_id=job_id,
                dataset_name=dataset_name,
                model_names=model_names,
            )
            logger.info(
                "[compare] submitted Celery task job_id=%s dataset=%s models=%s",
                job_id,
                dataset_name,
                model_names,
            )
        except Exception as exc:
            # PERF-P2-001: 移除 daemon Thread 回退, Celery/Redis 不可用时返回 503
            logger.error(
                "[compare] Celery submission failed, returning 503: %s", exc
            )
            raise HTTPException(
                status_code=503,
                detail="对比服务暂时不可用，请稍后重试 (Celery/Redis 故障)",
            ) from exc

        return self.get_training_job(job_id)

    def get_training_job(self, job_id: str) -> dict[str, Any]:
        # H-2 修复：优先从 Redis 读取（Celery worker 写入），回退到内存字典
        try:
            from app.tasks.model_training import get_job_from_redis

            redis_job = get_job_from_redis(job_id)
            if redis_job is not None:
                return redis_job
        except Exception:
            pass
        with TRAINING_JOBS_LOCK:
            return dict(
                TRAINING_JOBS.get(
                    job_id,
                    {
                        "job_id": job_id,
                        "status": "not_found",
                        "progress": 0,
                        "stage": "not_found",
                        "message": "任务不存在",
                    },
                )
            )

    def list_training_jobs(self) -> list[dict[str, Any]]:
        # H-2 修复：优先从 Redis 读取，回退到内存字典
        try:
            from app.tasks.model_training import list_jobs_from_redis

            redis_jobs = list_jobs_from_redis()
            if redis_jobs:
                return redis_jobs
        except Exception:
            pass
        with TRAINING_JOBS_LOCK:
            return [dict(item) for item in TRAINING_JOBS.values()]

    def _update_job(self, job_id: str, **updates: Any) -> None:
        with TRAINING_JOBS_LOCK:
            job = TRAINING_JOBS.get(job_id)
            if not job:
                return
            job.update(updates)
            job["updated_at"] = time()
        # M-21 修复：每次更新都持久化到磁盘
        _save_training_jobs()
        # H-2 修复：同步到 Redis（daemon Thread 回退路径需要，Celery 路径由 task 自行更新）
        try:
            from app.tasks.model_training import update_job_in_redis

            update_job_in_redis(job_id, **updates)
        except Exception:
            # L-18 修复：原代码静默吞掉所有异常（pass），添加日志记录便于排查 Redis 同步失败
            logger.warning("update_job_in_redis failed", exc_info=True)

    async def predict_tabular(
        self, features: dict[str, float | int | str | bool]
    ) -> dict:
        sanitized: dict[str, float | int | str | bool] = {}
        for key, value in features.items():
            sanitized[key] = value

        # PERF-P2-009: 60s Redis 缓存, 相同输入直接返回缓存结果
        if _ML_INFERENCE_CACHE_TTL > 0:
            cache_key = make_cache_key("ml:tabular", sanitized)
            cached = await cache_get(cache_key)
            if cached is not None:
                logger.debug("[predict_tabular] cache hit key=%s", cache_key)
                return cached

        # STAB-P1-002: ML 推理熔断器 + asyncio.wait_for 超时保护
        result = await call_with_ml_breaker(model_engine.predict_structured(sanitized))

        routing_info = result.get("routing_info", {})
        if routing_info:
            logger.info(
                "Model routing: family=%s reason=%s coverage=%.2f band=%s",
                routing_info.get("selected_model_family"),
                routing_info.get("routing_reason"),
                routing_info.get("feature_coverage_ratio", 0),
                routing_info.get("prediction_confidence_band"),
            )

        # PERF-P2-009: 写入缓存 (best-effort, 失败不影响推理结果)
        if _ML_INFERENCE_CACHE_TTL > 0:
            await cache_set(cache_key, result, ttl=_ML_INFERENCE_CACHE_TTL)

        return result

    async def predict_text(self, text: str) -> dict:
        # M-Svc-5 修复：开头验证空文本，避免空字符串进入模型推理导致未定义行为
        if not text or not text.strip():
            raise ValueError("text cannot be empty")
        cleaned = text.strip()

        # PERF-P2-009: 60s Redis 缓存
        if _ML_INFERENCE_CACHE_TTL > 0:
            cache_key = make_cache_key("ml:text", {"text": cleaned})
            cached = await cache_get(cache_key)
            if cached is not None:
                logger.debug("[predict_text] cache hit key=%s", cache_key)
                return cached

        # STAB-P1-002: ML 推理熔断器 + asyncio.wait_for 超时保护
        result = await call_with_ml_breaker(model_engine.predict_text(cleaned))

        # PERF-P2-009: 写入缓存
        if _ML_INFERENCE_CACHE_TTL > 0:
            await cache_set(cache_key, result, ttl=_ML_INFERENCE_CACHE_TTL)

        return result

    async def predict_physiological(
        self, physiological: dict[str, float | int]
    ) -> dict:
        # PERF-P2-009: 60s Redis 缓存
        if _ML_INFERENCE_CACHE_TTL > 0:
            cache_key = make_cache_key("ml:physiological", physiological)
            cached = await cache_get(cache_key)
            if cached is not None:
                logger.debug("[predict_physiological] cache hit key=%s", cache_key)
                return cached

        # STAB-P1-002: ML 推理熔断器 + asyncio.wait_for 超时保护
        result = await call_with_ml_breaker(
            model_engine.predict_physiological(physiological)
        )

        # PERF-P2-009: 写入缓存
        if _ML_INFERENCE_CACHE_TTL > 0:
            await cache_set(cache_key, result, ttl=_ML_INFERENCE_CACHE_TTL)

        return result

    async def predict_fusion(
        self,
        features: dict[str, float | int] | None = None,
        text: str | None = None,
        physiological: dict[str, float | int] | None = None,
    ) -> dict:
        # PERF-P2-009: 60s Redis 缓存 (组合输入哈希)
        if _ML_INFERENCE_CACHE_TTL > 0:
            cache_key = make_cache_key(
                "ml:fusion",
                {
                    "features": features,
                    "text": text,
                    "physiological": physiological,
                },
            )
            cached = await cache_get(cache_key)
            if cached is not None:
                logger.debug("[predict_fusion] cache hit key=%s", cache_key)
                return cached

        # STAB-P1-002: ML 推理熔断器 + asyncio.wait_for 超时保护
        result = await call_with_ml_breaker(
            model_engine.predict_fusion(
                features=features, text=text, physiological=physiological
            )
        )

        # PERF-P2-009: 写入缓存
        if _ML_INFERENCE_CACHE_TTL > 0:
            await cache_set(cache_key, result, ttl=_ML_INFERENCE_CACHE_TTL)

        return result


class ModelExperimentService:
    def __init__(self) -> None:
        from app.services.experiment_service import (
            ExperimentService as BertExperimentService,
        )

        self._service = BertExperimentService()

    def import_dataset(
        self,
        dataset_name: str,
        source_type: str,
        train_ratio: float,
        val_ratio: float,
        test_ratio: float,
    ) -> dict:
        return self._service.import_dataset(
            dataset_name, source_type, train_ratio, val_ratio, test_ratio
        )

    def train(
        self,
        dataset_name: str,
        model_name: str,
        epochs: int,
        batch_size: int,
        learning_rate: float,
    ) -> dict:
        return self._service.train_model(
            dataset_name, model_name, epochs, batch_size, learning_rate
        )

    def evaluate(self, dataset_name: str, model_name: str, split: str) -> dict:
        return self._service.evaluate_model(dataset_name, model_name, split)

    def compare(self, dataset_name: str, model_names: list[str]) -> dict:
        if not model_names:
            raise ValueError("model_names 不能为空")
        return self._service.compare_models(dataset_name, model_names)
