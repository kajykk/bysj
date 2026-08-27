"""Training, evaluation, and comparison job state management."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Lock
from time import time
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

TRAINING_JOBS: dict[str, dict[str, Any]] = {}
TRAINING_JOBS_LOCK = Lock()
TRAINING_JOBS_MAX_SIZE = 100
_ACTIVE_JOB_STATUSES: frozenset[str] = frozenset({"running", "queued"})
_TRAINING_JOBS_FILE = Path(getattr(settings, "model_dir", "models")) / "training_jobs.json"


def _load_training_jobs(load_json: Any = None) -> None:
    """Restore persisted job state and mark interrupted jobs after restart."""
    try:
        if not _TRAINING_JOBS_FILE.exists():
            return
        json_loader = load_json or json.load
        with open(_TRAINING_JOBS_FILE, "r", encoding="utf-8") as f:
            data = json_loader(f)
        for job_id, job_data in data.items():
            if job_data.get("status") in ("running", "queued"):
                job_data["status"] = "interrupted"
                job_data["stage"] = "interrupted"
                job_data["message"] = "服务重启，任务中断"
                job_data["error"] = "service_restart"
            TRAINING_JOBS[job_id] = job_data
        logger.info("Loaded %d training jobs from disk", len(TRAINING_JOBS))
    except Exception as exc:
        logger.warning("Failed to load training jobs from disk: %s", exc)


def _save_training_jobs(dump_json: Any = None) -> None:
    """Persist a lock-protected snapshot without holding the lock during I/O."""
    try:
        _TRAINING_JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with TRAINING_JOBS_LOCK:
            data = {key: dict(value) for key, value in TRAINING_JOBS.items()}
        json_dumper = dump_json or json.dump
        with open(_TRAINING_JOBS_FILE, "w", encoding="utf-8") as f:
            json_dumper(data, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning("Failed to save training jobs to disk: %s", exc)


def cleanup_old_training_jobs(max_size: int = TRAINING_JOBS_MAX_SIZE) -> int:
    """Remove the oldest completed jobs while retaining active jobs."""
    removed = 0
    with TRAINING_JOBS_LOCK:
        if len(TRAINING_JOBS) <= max_size:
            return 0

        def safe_created_at(job_data: dict[str, Any]) -> float:
            try:
                return float(job_data.get("created_at", 0) or 0)
            except (TypeError, ValueError):
                return 0.0

        sorted_jobs = sorted(TRAINING_JOBS.items(), key=lambda item: safe_created_at(item[1]))
        for job_id, job_data in sorted_jobs:
            if len(TRAINING_JOBS) <= max_size:
                break
            if job_data.get("status", "") in _ACTIVE_JOB_STATUSES:
                continue
            del TRAINING_JOBS[job_id]
            removed += 1

    if removed:
        logger.info(
            "cleanup_old_training_jobs: removed %d old jobs (current size=%d, max=%d)",
            removed,
            len(TRAINING_JOBS),
            max_size,
        )
        _save_training_jobs()
    return removed


def _new_job(message: str) -> dict[str, Any]:
    now = time()
    return {
        "job_id": uuid4().hex,
        "status": "queued",
        "progress": 0,
        "stage": "queued",
        "message": message,
        "created_at": now,
        "updated_at": now,
        "result": None,
        "error": None,
    }


def _persist_queued_job(job_data: dict[str, Any]) -> None:
    with TRAINING_JOBS_LOCK:
        TRAINING_JOBS[job_data["job_id"]] = dict(job_data)
    _save_training_jobs()
    cleanup_old_training_jobs()


def _submit_task(job_data: dict[str, Any], task: Any, **kwargs: Any) -> None:
    try:
        _persist_queued_job(job_data)
        task.delay(job_id=job_data["job_id"], **kwargs)
    except Exception as exc:
        logger.error("Celery submission failed, returning 503: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="训练服务暂时不可用，请稍后重试 (Celery/Redis 故障)",
        ) from exc


def start_training_job(
    dataset_name: str,
    model_name: str,
    epochs: int,
    batch_size: int,
    learning_rate: float,
) -> dict[str, Any]:
    from app.tasks.model_training import save_job_to_redis, train_bert_model_task

    job_data = _new_job("任务已排队")
    try:
        save_job_to_redis(job_data["job_id"], job_data)
        _submit_task(
            job_data,
            train_bert_model_task,
            dataset_name=dataset_name,
            model_name=model_name,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[training] Celery submission failed, returning 503: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="训练服务暂时不可用，请稍后重试 (Celery/Redis 故障)",
        ) from exc
    logger.info(
        "[training] submitted Celery task job_id=%s dataset=%s model=%s",
        job_data["job_id"],
        dataset_name,
        model_name,
    )
    return get_training_job(job_data["job_id"])


def start_evaluate_job(dataset_name: str, model_name: str, split: str) -> dict[str, Any]:
    from app.tasks.model_training import evaluate_model_task, save_job_to_redis

    job_data = _new_job("评估任务已排队")
    try:
        save_job_to_redis(job_data["job_id"], job_data)
        _submit_task(
            job_data,
            evaluate_model_task,
            dataset_name=dataset_name,
            model_name=model_name,
            split=split,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[evaluate] Celery submission failed, returning 503: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="评估服务暂时不可用，请稍后重试 (Celery/Redis 故障)",
        ) from exc
    return get_training_job(job_data["job_id"])


def start_compare_job(dataset_name: str, model_names: list[str]) -> dict[str, Any]:
    if not model_names:
        raise ValueError("model_names 不能为空")

    from app.tasks.model_training import compare_models_task, save_job_to_redis

    job_data = _new_job("对比任务已排队")
    try:
        save_job_to_redis(job_data["job_id"], job_data)
        _submit_task(job_data, compare_models_task, dataset_name=dataset_name, model_names=model_names)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[compare] Celery submission failed, returning 503: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="对比服务暂时不可用，请稍后重试 (Celery/Redis 故障)",
        ) from exc
    return get_training_job(job_data["job_id"])


def get_training_job(job_id: str) -> dict[str, Any]:
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


def list_training_jobs() -> list[dict[str, Any]]:
    try:
        from app.tasks.model_training import list_jobs_from_redis

        redis_jobs = list_jobs_from_redis()
        if redis_jobs:
            return redis_jobs
    except Exception:
        pass
    with TRAINING_JOBS_LOCK:
        return [dict(item) for item in TRAINING_JOBS.values()]


def update_job(job_id: str, **updates: Any) -> None:
    with TRAINING_JOBS_LOCK:
        job = TRAINING_JOBS.get(job_id)
        if not job:
            return
        job.update(updates)
        job["updated_at"] = time()
    _save_training_jobs()
    try:
        from app.tasks.model_training import update_job_in_redis

        update_job_in_redis(job_id, **updates)
    except Exception:
        logger.warning("update_job_in_redis failed", exc_info=True)


_load_training_jobs()
cleanup_old_training_jobs()
