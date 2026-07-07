"""H-2 修复：BERT 模型训练 Celery 任务.

将原 model_predict_service.py 中的 daemon Thread 训练改为 Celery 任务，
避免训练占用 Web 进程资源，并支持多实例部署下的任务状态共享。

任务状态通过 Redis 存储（key: training:job:{job_id}），Web 进程与 Celery
worker 共享同一 Redis 实例，实现跨进程状态读写。
"""

from __future__ import annotations

import json
import logging
import re
from time import time
from typing import Any

from app.core.celery_app import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)

_TRAINING_JOB_KEY_PREFIX = "training:job:"
_TRAINING_JOB_INDEX_KEY = "training:jobs"

# 同步 Redis 客户端（Celery worker 进程级，懒加载）
_sync_redis_client = None

# ISS-008 修复: 任务参数路径安全白名单, 防止路径遍历
_SAFE_PARAM_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_path_param(name: str, value: str) -> None:
    """ISS-008 修复: 校验任务参数防止路径遍历.

    仅允许字母、数字、下划线、连字符, 拒绝包含路径分隔符或特殊字符的输入,
    避免恶意参数构造路径遍历到任意文件.
    """
    if not isinstance(value, str) or not _SAFE_PARAM_PATTERN.match(value):
        raise ValueError(
            f"参数 {name} 包含非法字符: {value!r}, "
            f"仅允许字母、数字、下划线、连字符 (^[a-zA-Z0-9_-]+$)"
        )


def _get_sync_redis():
    """获取同步 Redis 客户端（Celery worker 进程级单例）。"""
    global _sync_redis_client
    if _sync_redis_client is not None:
        return _sync_redis_client
    import redis as sync_redis

    _sync_redis_client = sync_redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=5,
    )
    return _sync_redis_client


def _job_key(job_id: str) -> str:
    return f"{_TRAINING_JOB_KEY_PREFIX}{job_id}"


def save_job_to_redis(job_id: str, job_data: dict[str, Any]) -> None:
    """将训练任务状态写入 Redis (Hash 结构).

    ISS-009 修复: 改用 Hash 存储, 每个字段独立 JSON 编码,
    支持 update_job_in_redis 通过 HSET 原子更新单个字段.
    """
    try:
        r = _get_sync_redis()
        # Hash 字段值为 JSON 编码, 保持与 get_job_from_redis 反序列化一致
        mapping = {k: json.dumps(v, ensure_ascii=False) for k, v in job_data.items()}
        r.hset(_job_key(job_id), mapping=mapping)
        r.sadd(_TRAINING_JOB_INDEX_KEY, job_id)
    except Exception as exc:
        logger.warning(
            "[training_task] failed to save job %s to Redis: %s", job_id, exc
        )


def get_job_from_redis(job_id: str) -> dict[str, Any] | None:
    """从 Redis 读取训练任务状态 (Hash 结构)."""
    try:
        r = _get_sync_redis()
        raw = r.hgetall(_job_key(job_id))
        if not raw:
            return None
        # ISS-009 修复: Hash 字段值为 JSON 编码, 需逐字段反序列化
        return {k: json.loads(v) for k, v in raw.items()}
    except Exception as exc:
        logger.warning(
            "[training_task] failed to get job %s from Redis: %s", job_id, exc
        )
        return None


def list_jobs_from_redis() -> list[dict[str, Any]]:
    """从 Redis 列出所有训练任务 (Hash 结构)."""
    try:
        r = _get_sync_redis()
        job_ids = r.smembers(_TRAINING_JOB_INDEX_KEY)
        jobs: list[dict[str, Any]] = []
        for job_id in job_ids:
            raw = r.hgetall(_job_key(job_id))
            if raw:
                jobs.append({k: json.loads(v) for k, v in raw.items()})
        return jobs
    except Exception as exc:
        logger.warning("[training_task] failed to list jobs from Redis: %s", exc)
        return []


def update_job_in_redis(job_id: str, **updates: Any) -> None:
    """ISS-009 修复: 使用 HSET 原子更新字段, 替代非原子的 get-modify-set.

    HSET 对单个字段或多个字段均为原子操作, 无需 WATCH/MULTI/EXEC 乐观锁.
    自动追加 updated_at 字段以记录最后更新时间.
    """
    try:
        r = _get_sync_redis()
        key = _job_key(job_id)
        # 检查 job 是否存在, 避免为不存在任务创建空 Hash
        if not r.exists(key):
            logger.warning(
                "[training_task] job %s not found in Redis, cannot update",
                job_id,
            )
            return
        # 构造 HSET mapping: 字段值 JSON 编码, 自动追加 updated_at
        updates_with_ts = dict(updates)
        updates_with_ts["updated_at"] = time()
        mapping = {
            k: json.dumps(v, ensure_ascii=False) for k, v in updates_with_ts.items()
        }
        r.hset(key, mapping=mapping)
    except Exception as exc:
        logger.warning(
            "[training_task] failed to update job %s in Redis: %s", job_id, exc
        )


@celery_app.task(
    bind=True,
    name="app.tasks.model_training.train_bert_model_task",
    max_retries=0,
    time_limit=1800,
    soft_time_limit=1700,
)
def train_bert_model_task(
    self,
    job_id: str,
    dataset_name: str,
    model_name: str,
    epochs: int,
    batch_size: int,
    learning_rate: float,
) -> dict[str, Any]:
    """H-2 修复：Celery 任务执行 BERT 模型训练。

    替代原 daemon Thread，训练在 Celery worker 进程中执行，
    不占用 Web 进程资源，且支持服务重启后任务状态持久化。

    Args:
        job_id: 训练任务 ID
        dataset_name: 数据集名称
        model_name: 模型名称
        epochs: 训练轮数
        batch_size: 批大小
        learning_rate: 学习率

    Returns:
        训练任务最终状态
    """
    from app.services.experiment_service import (
        ExperimentService as BertExperimentService,
    )

    # ISS-008 修复: 任务入口对路径参数做白名单校验, 防止路径遍历
    _validate_path_param("dataset_name", dataset_name)
    _validate_path_param("model_name", model_name)

    logger.info(
        "[training_task] started job_id=%s dataset=%s model=%s",
        job_id,
        dataset_name,
        model_name,
    )

    try:
        update_job_in_redis(
            job_id,
            status="running",
            progress=10,
            stage="import",
            message="开始导入数据集",
        )
        service = BertExperimentService()
        service.import_dataset(dataset_name, "local", 0.7, 0.15, 0.15)

        update_job_in_redis(job_id, progress=35, stage="train", message="开始训练模型")
        result = service.train_model(
            dataset_name, model_name, epochs, batch_size, learning_rate
        )

        update_job_in_redis(
            job_id, progress=75, stage="evaluate", message="开始评估模型"
        )
        evaluation = service.evaluate_model(dataset_name, model_name, "validation")

        update_job_in_redis(
            job_id,
            progress=100,
            stage="completed",
            status="completed",
            message="训练完成",
            result={"train": result, "evaluation": evaluation},
        )
        logger.info("[training_task] completed job_id=%s", job_id)
    except Exception as exc:
        update_job_in_redis(
            job_id,
            status="failed",
            progress=100,
            stage="failed",
            message="训练失败",
            error=str(exc),
        )
        logger.exception("[training_task] failed job_id=%s", job_id)
        # M-ML-5 修复：重新抛出异常，让 Celery 能追踪任务失败状态（标记为 FAILURE），
        # 否则任务会被误判为成功并执行后续 return
        raise

    return get_job_from_redis(job_id) or {"job_id": job_id, "status": "unknown"}


@celery_app.task(
    bind=True,
    name="app.tasks.model_training.evaluate_model_task",
    max_retries=0,
    time_limit=600,
    soft_time_limit=550,
)
def evaluate_model_task(
    self,
    job_id: str,
    dataset_name: str,
    model_name: str,
    split: str,
) -> dict[str, Any]:
    """PERF-P1-006: Celery 任务执行模型评估.

    替代原 experiment.py evaluate 端点中的 asyncio.to_thread 阻塞调用,
    评估在 Celery worker 进程中执行, 客户端通过 job_id 轮询状态.

    Args:
        job_id: 评估任务 ID (复用 training job 状态机)
        dataset_name: 数据集名称
        model_name: 模型名称
        split: 评估数据集划分 (validation | test)

    Returns:
        评估任务最终状态
    """
    from app.services.experiment_service import (
        ExperimentService as BertExperimentService,
    )

    # ISS-008 修复: 任务入口对路径参数做白名单校验, 防止路径遍历
    _validate_path_param("dataset_name", dataset_name)
    _validate_path_param("model_name", model_name)

    logger.info(
        "[evaluate_task] started job_id=%s dataset=%s model=%s split=%s",
        job_id,
        dataset_name,
        model_name,
        split,
    )

    try:
        update_job_in_redis(
            job_id,
            status="running",
            progress=20,
            stage="evaluate",
            message="开始评估模型",
        )
        service = BertExperimentService()
        result = service.evaluate_model(dataset_name, model_name, split)

        update_job_in_redis(
            job_id,
            progress=100,
            stage="completed",
            status="completed",
            message="评估完成",
            result=result,
        )
        logger.info("[evaluate_task] completed job_id=%s", job_id)
    except Exception as exc:
        update_job_in_redis(
            job_id,
            status="failed",
            progress=100,
            stage="failed",
            message="评估失败",
            error=str(exc),
        )
        logger.exception("[evaluate_task] failed job_id=%s", job_id)
        # M-ML-5 一致性: 重新抛出异常, 让 Celery 追踪 FAILURE 状态
        raise

    return get_job_from_redis(job_id) or {"job_id": job_id, "status": "unknown"}


@celery_app.task(
    bind=True,
    name="app.tasks.model_training.compare_models_task",
    max_retries=0,
    time_limit=1800,
    soft_time_limit=1700,
)
def compare_models_task(
    self,
    job_id: str,
    dataset_name: str,
    model_names: list[str],
) -> dict[str, Any]:
    """PERF-P1-006: Celery 任务执行多模型对比.

    替代原 experiment.py compare 端点中的 asyncio.to_thread 阻塞调用,
    对比在 Celery worker 进程中执行 (串行评估 N 个模型, 耗时 = N × 单模型评估时间).

    Args:
        job_id: 对比任务 ID (复用 training job 状态机)
        dataset_name: 数据集名称
        model_names: 待对比的模型名称列表

    Returns:
        对比任务最终状态
    """
    from app.services.experiment_service import (
        ExperimentService as BertExperimentService,
    )

    # ISS-008 修复: 任务入口对路径参数做白名单校验, 防止路径遍历
    _validate_path_param("dataset_name", dataset_name)
    for _mn in model_names or []:
        _validate_path_param("model_names[]", _mn)

    logger.info(
        "[compare_task] started job_id=%s dataset=%s models=%s",
        job_id,
        dataset_name,
        model_names,
    )

    try:
        update_job_in_redis(
            job_id,
            status="running",
            progress=10,
            stage="compare",
            message="开始对比模型",
        )
        service = BertExperimentService()
        result = service.compare_models(dataset_name, model_names)

        update_job_in_redis(
            job_id,
            progress=100,
            stage="completed",
            status="completed",
            message="对比完成",
            result=result,
        )
        logger.info("[compare_task] completed job_id=%s", job_id)
    except Exception as exc:
        update_job_in_redis(
            job_id,
            status="failed",
            progress=100,
            stage="failed",
            message="对比失败",
            error=str(exc),
        )
        logger.exception("[compare_task] failed job_id=%s", job_id)
        # M-ML-5 一致性: 重新抛出异常, 让 Celery 追踪 FAILURE 状态
        raise

    return get_job_from_redis(job_id) or {"job_id": job_id, "status": "unknown"}
