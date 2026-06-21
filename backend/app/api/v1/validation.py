from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path as FilePath
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BACKEND_DIR, settings
from app.core.database import get_db
from app.core.deps import require_permission
from app.core.response import ok
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.validation import ValidationRunRequest, ValidationStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/validation", tags=["validation"])

# CRIT-009 修复：内存存储添加限制和 TTL 清理
# TD-013 修复：迁移到 Redis Hash 存储，支持多实例部署，内存作为降级方案
MAX_VALIDATION_JOBS = 50
JOB_TTL_SECONDS = 3600  # 1 小时后自动清理

# 允许存放验证数据集的安全根目录
VALIDATION_DATA_ROOT = FilePath(BACKEND_DIR) / "data" / "validation"

# Redis Key 前缀
_REDIS_JOB_PREFIX = "validation:job:"
_REDIS_JOB_INDEX = "validation:jobs:index"


class ValidationJobStore:
    """验证任务存储：Redis 优先 + 内存降级。

    TD-013 修复：将任务状态从进程内字典迁移到 Redis Hash，
    支持多实例部署下的状态共享。Redis 不可用时自动降级到内存存储。

    Redis 数据结构：
    - Hash: validation:job:{job_id} -> 任务字段
    - Set: validation:jobs:index -> 所有 job_id 集合（用于列表查询）
    - 每个 job Hash 自动设置 TTL（JOB_TTL_SECONDS）
    """

    def __init__(self) -> None:
        self._memory_store: dict[str, dict] = {}
        self._redis_client: Any = None
        self._redis_checked = False

    async def _get_redis(self) -> Any:
        """获取 Redis 客户端，不可用时返回 None。"""
        if self._redis_checked and self._redis_client is None:
            return None
        if self._redis_client is not None:
            return self._redis_client
        try:
            import redis.asyncio as aioredis

            url = getattr(settings, "redis_url", None)
            if not url or not str(url).startswith("redis"):
                self._redis_checked = True
                return None
            self._redis_client = aioredis.from_url(
                str(url),
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            # 测试连接
            await self._redis_client.ping()
            self._redis_checked = True
            logger.info("[validation_store] Redis connected, using Redis for job storage")
            return self._redis_client
        except Exception as exc:
            logger.warning("[validation_store] Redis unavailable, falling back to memory: %s", exc)
            self._redis_client = None
            self._redis_checked = True
            return None

    async def create(self, job_id: str, job_data: dict) -> None:
        """创建验证任务。"""
        redis = await self._get_redis()
        if redis is not None:
            try:
                key = f"{_REDIS_JOB_PREFIX}{job_id}"
                # 将所有字段转为字符串存储
                mapping = {k: self._serialize(v) for k, v in job_data.items()}
                await redis.hset(key, mapping=mapping)
                await redis.expire(key, JOB_TTL_SECONDS)
                await redis.sadd(_REDIS_JOB_INDEX, job_id)
                await redis.expire(_REDIS_JOB_INDEX, JOB_TTL_SECONDS)
                return
            except Exception as exc:
                logger.warning("[validation_store] Redis create failed, using memory: %s", exc)

        # 内存降级
        self._memory_store[job_id] = job_data.copy()

    async def get(self, job_id: str) -> dict | None:
        """获取验证任务。"""
        redis = await self._get_redis()
        if redis is not None:
            try:
                key = f"{_REDIS_JOB_PREFIX}{job_id}"
                data = await redis.hgetall(key)
                if not data:
                    return None
                return self._deserialize_dict(data)
            except Exception as exc:
                logger.warning("[validation_store] Redis get failed, using memory: %s", exc)

        # 内存降级
        return self._memory_store.get(job_id)

    async def update(self, job_id: str, **fields: Any) -> None:
        """更新验证任务字段。"""
        redis = await self._get_redis()
        if redis is not None:
            try:
                key = f"{_REDIS_JOB_PREFIX}{job_id}"
                mapping = {k: self._serialize(v) for k, v in fields.items()}
                await redis.hset(key, mapping=mapping)
                # 更新后重置 TTL
                await redis.expire(key, JOB_TTL_SECONDS)
                return
            except Exception as exc:
                logger.warning("[validation_store] Redis update failed, using memory: %s", exc)

        # 内存降级
        if job_id in self._memory_store:
            self._memory_store[job_id].update(fields)

    async def delete(self, job_id: str) -> None:
        """删除验证任务。"""
        redis = await self._get_redis()
        if redis is not None:
            try:
                await redis.delete(f"{_REDIS_JOB_PREFIX}{job_id}")
                await redis.srem(_REDIS_JOB_INDEX, job_id)
                return
            except Exception as exc:
                logger.warning("[validation_store] Redis delete failed, using memory: %s", exc)

        self._memory_store.pop(job_id, None)

    async def list_jobs(self) -> list[dict]:
        """列出所有验证任务。"""
        redis = await self._get_redis()
        if redis is not None:
            try:
                job_ids = await redis.smembers(_REDIS_JOB_INDEX)
                jobs = []
                expired_ids = []
                for job_id in job_ids:
                    data = await redis.hgetall(f"{_REDIS_JOB_PREFIX}{job_id}")
                    if not data:
                        # Hash 已过期但 Set 中残留，清理
                        expired_ids.append(job_id)
                        continue
                    jobs.append(self._deserialize_dict(data))
                # 清理过期索引
                if expired_ids:
                    await redis.srem(_REDIS_JOB_INDEX, *expired_ids)
                return jobs
            except Exception as exc:
                logger.warning("[validation_store] Redis list failed, using memory: %s", exc)

        # 内存降级：手动清理过期任务
        self._cleanup_memory_expired()
        return list(self._memory_store.values())

    async def count(self) -> int:
        """获取当前任务数量。"""
        redis = await self._get_redis()
        if redis is not None:
            try:
                return await redis.scard(_REDIS_JOB_INDEX)
            except Exception as exc:
                logger.warning("[validation_store] Redis count failed, using memory: %s", exc)

        self._cleanup_memory_expired()
        return len(self._memory_store)

    def _cleanup_memory_expired(self) -> None:
        """清理内存模式下的过期任务。"""
        now = datetime.now(timezone.utc)
        expired_ids = []
        for job_id, job in self._memory_store.items():
            created_at_str = job.get("created_at")
            if not created_at_str:
                continue
            try:
                created_at = datetime.fromisoformat(created_at_str)
                if (now - created_at).total_seconds() > JOB_TTL_SECONDS:
                    expired_ids.append(job_id)
            except (ValueError, TypeError):
                continue
        for job_id in expired_ids:
            self._memory_store.pop(job_id, None)
        if expired_ids:
            logger.info("Cleaned up %d expired validation jobs (memory mode)", len(expired_ids))

    @staticmethod
    def _serialize(value: Any) -> str:
        """序列化值为 Redis Hash 字段字符串。"""
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, default=str)
        return str(value)

    @staticmethod
    def _deserialize_dict(data: dict[str, str]) -> dict:
        """反序列化 Redis Hash 为字典。"""
        result = {}
        for key, value in data.items():
            if value == "":
                result[key] = None
            elif key in ("result",):
                try:
                    result[key] = json.loads(value) if value else None
                except (json.JSONDecodeError, TypeError):
                    result[key] = value
            elif key in ("progress",):
                try:
                    result[key] = int(value)
                except (ValueError, TypeError):
                    result[key] = 0
            elif key in ("created_by",):
                try:
                    result[key] = int(value)
                except (ValueError, TypeError):
                    result[key] = value
            else:
                result[key] = value
        return result


# 全局任务存储实例（Redis 优先 + 内存降级）
job_store = ValidationJobStore()


def _validate_dataset_path(raw_path: str) -> Path:
    """CRIT-008 修复：验证数据集路径，防止路径遍历攻击。

    只允许访问 VALIDATION_DATA_ROOT 目录下的文件。
    """
    if not raw_path or not raw_path.strip():
        raise HTTPException(status_code=400, detail="dataset_path is required")

    # 构建安全路径：将用户提供的路径解析为相对于安全根目录的路径
    user_path = FilePath(raw_path.strip())

    # 如果是绝对路径，拒绝（防止访问系统任意文件）
    if user_path.is_absolute():
        raise HTTPException(
            status_code=400,
            detail="Absolute paths are not allowed. Use a relative path within the validation data directory.",
        )

    # 解析为安全根目录下的绝对路径
    safe_path = (VALIDATION_DATA_ROOT / user_path).resolve()

    # 验证解析后的路径仍在安全根目录内
    try:
        safe_path.relative_to(VALIDATION_DATA_ROOT.resolve())
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail="Path traversal detected. The dataset path must stay within the validation data directory.",
        ) from None

    return safe_path


@router.post("/run", response_model=ApiResponse)
async def run_validation(
    payload: ValidationRunRequest,
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Start an asynchronous validation run.

    Returns immediately with a job ID. Use /validation/{id}/status to poll.

    CRIT-008 修复：验证数据集路径，防止路径遍历。
    CRIT-009 修复：限制内存中的任务数量，自动清理过期任务。
    TD-013 修复：任务状态迁移到 Redis Hash，支持多实例部署。
    """
    # 检查任务数量限制
    current_count = await job_store.count()
    if current_count >= MAX_VALIDATION_JOBS:
        raise HTTPException(
            status_code=429,
            detail=f"Too many validation jobs in progress (max={MAX_VALIDATION_JOBS}). "
            "Please wait for existing jobs to complete.",
        )

    # CRIT-008 修复：验证数据集路径安全性
    safe_dataset_path = _validate_dataset_path(payload.dataset_path)
    safe_baseline_path = None
    if payload.baseline_dataset_path:
        safe_baseline_path = _validate_dataset_path(payload.baseline_dataset_path)

    job_id = str(uuid.uuid4())

    job_data = {
        "id": job_id,
        "status": "queued",
        "model_version": payload.model_version,
        "dataset_path": str(safe_dataset_path),
        "baseline_version": payload.baseline_version,
        "baseline_dataset_path": str(safe_baseline_path) if safe_baseline_path else None,
        "created_by": str(current_user.id),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
        "progress": "0",
    }

    await job_store.create(job_id, job_data)

    # Start validation in background
    asyncio.create_task(_execute_validation(job_id))

    return ok(
        ValidationStatusResponse(
            id=job_id,
            status="queued",
            progress=0,
            model_version=payload.model_version,
        ).model_dump()
    )


async def _execute_validation(job_id: str) -> None:
    """Execute validation job in background."""
    from app.services.validation_engine import validation_engine

    job = await job_store.get(job_id)
    if not job:
        return

    await job_store.update(
        job_id,
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
        progress=10,
    )

    try:
        dataset_path = FilePath(job["dataset_path"])
        baseline_dataset = job.get("baseline_dataset_path")
        baseline_dataset_path = FilePath(baseline_dataset) if baseline_dataset else None

        result = await validation_engine.validate_model(
            model_version=job["model_version"],
            dataset_path=dataset_path,
            baseline_version=job.get("baseline_version"),
            baseline_dataset_path=baseline_dataset_path,
        )

        await job_store.update(
            job_id,
            status="completed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            result=result.to_dict(),
            progress=100,
        )

    except Exception as exc:
        await job_store.update(
            job_id,
            status="failed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            error=str(exc),
            progress=100,
        )
        logger.error("Validation job %s failed: %s", job_id, exc, exc_info=True)


@router.get("/{job_id}/status", response_model=ApiResponse)
async def get_validation_status(
    job_id: Annotated[str, Path()],
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """Get validation job status."""
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Validation job not found")

    progress = job.get("progress", 0)
    try:
        progress = int(progress)
    except (ValueError, TypeError):
        progress = 0

    return ok(
        ValidationStatusResponse(
            id=job_id,
            status=job["status"],
            progress=progress,
            model_version=job["model_version"],
            error=job.get("error"),
        ).model_dump()
    )


@router.get("/{job_id}/results", response_model=ApiResponse)
async def get_validation_results(
    job_id: Annotated[str, Path()],
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """Get validation job results."""
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Validation job not found")

    if job["status"] != "completed":
        return ok(
            None,
            message=f"Validation job is {job['status']}",
            code=202,
        )

    return ok(job.get("result"))


@router.get("/jobs", response_model=ApiResponse)
async def list_validation_jobs(
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """List all validation jobs."""
    jobs = await job_store.list_jobs()
    job_list = [
        {
            "id": job["id"],
            "status": job["status"],
            "model_version": job["model_version"],
            "progress": int(job.get("progress", 0) or 0),
            "created_at": job["created_at"],
        }
        for job in jobs
    ]
    return ok({"jobs": job_list, "total": len(job_list)})
