from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path as FilePath
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BACKEND_DIR
from app.core.database import get_db
from app.core.deps import require_permission
from app.core.rate_limit import limiter
from app.core.response import ok
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.validation import ValidationRunRequest, ValidationStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/validation", tags=["validation"])

# 保存后台任务引用，防止被 GC 回收导致任务静默终止
_background_tasks: set[asyncio.Task] = set()

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

    P1-2: 复用 app.core.cache.get_redis_client() 共享单例, 移除独立的
    Redis 客户端单例 + 重复断路器逻辑, 统一连接池管理.
    """

    def __init__(self) -> None:
        self._memory_store: dict[str, dict] = {}
        # P1-2: 移除独立 _redis_client / _redis_checked / _last_check_time,
        # 共享客户端由 app.core.cache 统一管理 (含双重检查锁 + 断路器).
        # _redis_failed_until 用于在降级到内存后短暂跳过 Redis 探测, 与共享断路器协同.
        self._redis_failed_until: float = 0.0

    async def _get_redis(self) -> Any:
        """获取共享 Redis 客户端，不可用时返回 None.

        P1-2: 委托给 app.core.cache.get_redis_client(), 复用同一连接池.
        本地仅维护一个短的失败冷却窗口 (60s), 避免在共享断路器未触发时
        仍频繁探测 Redis (例如首次 ping 失败但未达到共享断路器阈值).
        """
        import time

        # 本地冷却窗口: 降级后 60s 内不再尝试 Redis, 直接走内存
        if time.time() < self._redis_failed_until:
            return None
        try:
            from app.core.cache import get_redis_client

            client = await get_redis_client()
            if client is None:
                # 无 redis_url 或断路器开启
                return None
            # 首次获取后做一次 ping 验证 (共享客户端创建时不做 ping)
            # 后续调用复用同一客户端, ping 失败由调用方异常分支处理
            return client
        except Exception as exc:
            logger.warning(
                "[validation_store] Redis unavailable, falling back to memory: %s", exc
            )
            # 设置 60s 本地冷却, 避免每次操作都触发 ping 探测
            self._redis_failed_until = time.time() + 60.0
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
                logger.warning(
                    "[validation_store] Redis create failed, using memory: %s", exc
                )

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
                logger.warning(
                    "[validation_store] Redis get failed, using memory: %s", exc
                )

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
                logger.warning(
                    "[validation_store] Redis update failed, using memory: %s", exc
                )

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
                logger.warning(
                    "[validation_store] Redis delete failed, using memory: %s", exc
                )

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
                logger.warning(
                    "[validation_store] Redis list failed, using memory: %s", exc
                )

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
                logger.warning(
                    "[validation_store] Redis count failed, using memory: %s", exc
                )

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
            logger.info(
                "Cleaned up %d expired validation jobs (memory mode)", len(expired_ids)
            )

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


# C-API-6 修复：Windows 保留设备名（CON, AUX, PRN, NUL, COM1-9, LPT1-9）
# 这些名称在 Windows 下会被解析为设备而非文件，可能绕过路径校验
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def _validate_dataset_path(raw_path: str) -> Path:
    """CRIT-008 修复：验证数据集路径，防止路径遍历攻击。

    只允许访问 VALIDATION_DATA_ROOT 目录下的文件。
    C-API-6 加固：额外拒绝 null byte、`..` 组件、Windows 保留设备名，
    避免 Windows 下因路径规范化差异导致的校验绕过。
    """
    if not raw_path or not raw_path.strip():
        raise HTTPException(status_code=400, detail="dataset_path is required")

    stripped = raw_path.strip()

    # C-API-6 修复：拒绝 null byte，防止在 Windows 下截断校验
    if "\x00" in stripped:
        raise HTTPException(
            status_code=400, detail="Invalid path: null byte is not allowed"
        )

    # 构建安全路径：将用户提供的路径解析为相对于安全根目录的路径
    user_path = FilePath(stripped)

    # 如果是绝对路径，拒绝（防止访问系统任意文件）
    if user_path.is_absolute():
        raise HTTPException(
            status_code=400,
            detail="Absolute paths are not allowed. Use a relative path within the validation data directory.",
        )

    # C-API-6 修复：显式拒绝 `..` 组件，避免依赖 resolve() 的规范化行为
    # （不同平台对符号链接、大小写、保留名的处理差异可能导致绕过）
    for part in user_path.parts:
        if part == "..":
            raise HTTPException(
                status_code=403,
                detail="Path traversal detected: '..' is not allowed in dataset_path.",
            )
        # 检查 Windows 保留设备名（CON.txt 等带扩展形式也要拦截）
        stem = part.split(".")[0].upper()
        if stem in _WINDOWS_RESERVED_NAMES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid path: Windows reserved name '{stem}' is not allowed.",
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
@limiter.limit("5/minute")
async def run_validation(
    request: Request,
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
        "baseline_dataset_path": (
            str(safe_baseline_path) if safe_baseline_path else None
        ),
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
    task = asyncio.create_task(_execute_validation(job_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    # R-005 修复: 注册可观测性指标 (scheduled/succeeded/failed/cancelled + duration)
    from app.core.fire_forget_metrics import register_task

    register_task(task, "validation_job")

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
@limiter.limit("30/minute")
async def get_validation_status(
    request: Request,
    job_id: Annotated[str, Path()],
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """Get validation job status."""
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Validation job not found")
    # L-API-7 修复：仅允许创建者查看自己的验证任务状态，防止任意 admin 读取他人任务
    if job.get("created_by") != str(current_user.id):
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
@limiter.limit("30/minute")
async def get_validation_results(
    request: Request,
    job_id: Annotated[str, Path()],
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """Get validation job results."""
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Validation job not found")
    # L-API-7 修复：仅允许创建者查看自己的验证任务结果，防止任意 admin 读取他人任务
    if job.get("created_by") != str(current_user.id):
        raise HTTPException(status_code=404, detail="Validation job not found")

    if job["status"] != "completed":
        # L-7 修复：ApiResponse.data 字段类型为 T | None（见 schemas/common.py），允许 None 返回。
        # 任务未完成时返回 None 符合项目约定，与 ok() 默认 data=None 一致，无需改为空 dict。
        return ok(
            None,
            message=f"Validation job is {job['status']}",
            code=202,
        )

    return ok(job.get("result"))


@router.get("/jobs", response_model=ApiResponse)
@limiter.limit("30/minute")
async def list_validation_jobs(
    request: Request,
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """List all validation jobs."""
    jobs = await job_store.list_jobs()
    # L-API-7 修复：仅返回当前用户创建的验证任务，防止任意 admin 读取他人任务列表
    jobs = [job for job in jobs if job.get("created_by") == str(current_user.id)]
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
