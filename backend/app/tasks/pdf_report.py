"""P-D: PDF 报告生成 Celery 异步任务.

将原 reports.py 中的 asyncio.create_task (进程内异步) 升级为 Celery 任务,
支持跨节点调度与任务持久化. 当 Celery broker 不可用时, 自动回退到
daemon Thread (复用 PERF-P1-006 的 fallback 模式).

任务状态通过 Redis 存储 (key: pdf:job:{job_id}), 与 model_training 一致.
PDF 字节因体积较大 (可达数 MB), 不存入 Redis result backend (JSON 序列化开销大),
而是存入 Redis 二进制 key (pdf:bytes:{job_id}), 下载时读取.

关联:
- app/services/pdf_job_store.py: 进程内 PdfJobStore (旧端点兼容)
- app/services/pdf_report_service.py: ReportLab 生成逻辑
- app/api/v1/reports.py: API 端点 (新增 /celery-async 路径)
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

# ISS-048 修复：控制字符过滤正则，保留 \t \n \r，移除其他 \x00-\x1f 与 \x7f
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize_text(s: Any) -> Any:
    """ISS-048 修复：过滤字符串参数中的控制字符，防止 PDF 生成异常或日志注入.

    保留制表符 (\\t)、换行符 (\\n)、回车符 (\\r)，移除其他 C0 控制字符与 DEL。
    非字符串类型原样返回（如 None/int/list/dict）。

    Args:
        s: 待清洗的参数值（任意类型）。

    Returns:
        清洗后的字符串（若输入为 str），或原值（若输入非 str）。
    """
    if not isinstance(s, str):
        return s
    return _CONTROL_CHAR_RE.sub("", s)


def _sanitize_param(value: Any) -> Any:
    """ISS-048 修复：递归清洗任务参数中的字符串字段.

    支持 str / list / dict / None / 基本类型。
    """
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, list):
        return [_sanitize_param(v) for v in value]
    if isinstance(value, dict):
        return {k: _sanitize_param(v) for k, v in value.items()}
    return value


# Redis key 前缀 (与 model_training 命名风格一致)
_PDF_JOB_KEY_PREFIX = "pdf:job:"
_PDF_JOB_INDEX_KEY = "pdf:jobs"
_PDF_BYTES_KEY_PREFIX = "pdf:bytes:"
# PDF 字节 TTL: 1 小时后自动清理 (与 PdfJobStore.JOB_TTL_SECONDS 一致)
_PDF_BYTES_TTL_SECONDS = 3600

# 同步 Redis 客户端 (Celery worker 进程级, 懒加载)
_sync_redis_client = None


def _get_sync_redis():
    """获取同步 Redis 客户端 (Celery worker 进程级单例)."""
    global _sync_redis_client
    if _sync_redis_client is not None:
        return _sync_redis_client
    import redis as sync_redis

    _sync_redis_client = sync_redis.from_url(
        settings.redis_url,
        decode_responses=False,  # 二进制模式, 支持 PDF bytes 存储
        socket_connect_timeout=3,
        socket_timeout=5,
    )
    return _sync_redis_client


def _job_key(job_id: str) -> str:
    return f"{_PDF_JOB_KEY_PREFIX}{job_id}"


def _bytes_key(job_id: str) -> str:
    return f"{_PDF_BYTES_KEY_PREFIX}{job_id}"


def save_job_to_redis(job_id: str, job_data: dict[str, Any]) -> None:
    """将 PDF 任务状态写入 Redis (字符串值, JSON 编码)."""
    try:
        r = _get_sync_redis()
        r.set(
            _job_key(job_id), json.dumps(job_data, ensure_ascii=False).encode("utf-8")
        )
        r.sadd(_PDF_JOB_INDEX_KEY, job_id)
    except Exception as exc:
        logger.warning("[pdf_task] failed to save job %s to Redis: %s", job_id, exc)


def get_job_from_redis(job_id: str) -> dict[str, Any] | None:
    """从 Redis 读取 PDF 任务状态."""
    try:
        r = _get_sync_redis()
        data = r.get(_job_key(job_id))
        if data:
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            return json.loads(data)
        return None
    except Exception as exc:
        logger.warning("[pdf_task] failed to get job %s from Redis: %s", job_id, exc)
        return None


def update_job_in_redis(job_id: str, **updates: Any) -> None:
    """更新 Redis 中的 PDF 任务状态."""
    job = get_job_from_redis(job_id)
    if job is None:
        logger.warning("[pdf_task] job %s not found in Redis, cannot update", job_id)
        return
    job.update(updates)
    job["updated_at"] = time()
    save_job_to_redis(job_id, job)


def save_pdf_bytes_to_redis(job_id: str, pdf_bytes: bytes) -> None:
    """将 PDF 字节存入 Redis 二进制 key (带 TTL 自动清理)."""
    try:
        r = _get_sync_redis()
        r.setex(_bytes_key(job_id), _PDF_BYTES_TTL_SECONDS, pdf_bytes)
    except Exception as exc:
        logger.warning(
            "[pdf_task] failed to save pdf bytes %s to Redis: %s", job_id, exc
        )


def get_pdf_bytes_from_redis(job_id: str) -> bytes | None:
    """从 Redis 读取 PDF 字节."""
    try:
        r = _get_sync_redis()
        return r.get(_bytes_key(job_id))
    except Exception as exc:
        logger.warning(
            "[pdf_task] failed to get pdf bytes %s from Redis: %s", job_id, exc
        )
        return None


def delete_pdf_bytes_from_redis(job_id: str) -> None:
    """下载后可选调用, 释放 Redis 内存."""
    try:
        r = _get_sync_redis()
        r.delete(_bytes_key(job_id))
    except Exception as exc:
        logger.warning(
            "[pdf_task] failed to delete pdf bytes %s from Redis: %s", job_id, exc
        )


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    """统计 PDF 页数 (基于 /Type /Page 计数, 与 PDFReportService 一致)."""
    import re

    count = len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", pdf_bytes))
    return max(1, count)


@celery_app.task(
    name="app.tasks.pdf_report.generate_pdf_report",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    time_limit=300,  # 硬超时 5 分钟
    soft_time_limit=270,  # 软超时 4.5 分钟
)
def generate_pdf_report(
    self,
    job_id: str,
    user_name: str,
    risk_level: str | None = None,
    risk_trend: list[dict[str, Any]] | None = None,
    recommendations: list[str] | None = None,
) -> dict[str, Any]:
    """Celery 任务: 生成 PDF 报告.

    Args:
        job_id: 任务 ID (前端轮询用, 与 Redis key 对应)
        user_name: 用户名 (PDF 显示用)
        risk_level: 风险等级
        risk_trend: 风险趋势数据列表 (JSON 可序列化)
        recommendations: 干预建议列表

    Returns:
        任务状态字典 (不含 PDF 字节, 字节存入 Redis 二进制 key)

    注意:
        - items (risk_trend) 必须是 JSON 可序列化结构 (dict/list/str/number)
        - 失败自动重试 3 次, 间隔 10s
        - 重试耗尽后状态置为 failed
    """
    logger.info(
        "[pdf_task] start job_id=%s user=%s retries=%s",
        job_id,
        user_name,
        getattr(self.request, "retries", 0),
    )

    # ISS-048 修复：在任务入口对字符串参数做 sanitization，过滤控制字符
    user_name = _sanitize_text(user_name)
    risk_level = _sanitize_text(risk_level)
    recommendations = _sanitize_param(recommendations) or []
    # risk_trend 是 list[dict]，递归清洗其中的字符串字段
    risk_trend = _sanitize_param(risk_trend) or []

    update_job_in_redis(
        job_id,
        status="running",
        started_at=time(),
        progress=10,
    )

    try:
        from app.services.pdf_report_service import pdf_report_service

        # 调用同步生成函数 (ReportLab 是同步阻塞库)
        result = pdf_report_service.generate_user_risk_report(
            user_name=user_name,
            risk_level=risk_level,
            risk_trend=risk_trend or [],
            recommendations=recommendations or [],
        )

        if not result.success:
            update_job_in_redis(
                job_id,
                status="failed",
                completed_at=time(),
                progress=100,
                error=result.error_message or "PDF generation failed",
            )
            logger.error("[pdf_task] job %s failed: %s", job_id, result.error_message)
            return {
                "job_id": job_id,
                "status": "failed",
                "error": result.error_message,
            }

        # PDF 字节存入 Redis 二进制 key (带 TTL)
        save_pdf_bytes_to_redis(job_id, result.pdf_bytes)

        update_job_in_redis(
            job_id,
            status="completed",
            completed_at=time(),
            progress=100,
            file_size=result.file_size,
            page_count=result.page_count,
        )

        logger.info(
            "[pdf_task] job %s completed: size=%d bytes, pages=%d",
            job_id,
            result.file_size,
            result.page_count,
        )
        return {
            "job_id": job_id,
            "status": "completed",
            "file_size": result.file_size,
            "page_count": result.page_count,
        }

    except Exception as exc:
        logger.exception("[pdf_task] job %s failed: %s", job_id, exc)
        update_job_in_redis(
            job_id,
            status="failed",
            completed_at=time(),
            progress=100,
            error=str(exc),
        )

        # 重试 (最多 3 次)
        if getattr(self.request, "retries", 0) < 3:
            logger.info(
                "[pdf_task] retrying job %s (retry %d/3)",
                job_id,
                self.request.retries + 1,
            )
            raise self.retry(exc=exc)

        return {
            "job_id": job_id,
            "status": "failed",
            "error": str(exc),
        }


def create_initial_job(job_id: str, user_name: str, created_by: int) -> dict[str, Any]:
    """创建初始任务状态字典 (供 API 端点调用)."""
    now = time()
    job_data = {
        "job_id": job_id,
        "status": "queued",
        "user_name": user_name,
        "created_by": created_by,
        "progress": 0,
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "completed_at": None,
        "error": None,
        "file_size": 0,
        "page_count": 0,
    }
    return job_data
