from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.risk_thresholds import (
    RISK_LEVEL_THRESHOLDS as SHARED_RISK_LEVEL_THRESHOLDS,
)
from app.models.risk import RiskAssessment
from app.services.risk_service_assessment import AssessmentMixin
from app.services.risk_service_export import ExportMixin
from app.services.risk_service_report import ReportMixin
from app.services.risk_service_warning import WarningInterventionMixin

logger = logging.getLogger(__name__)

# C-Svc-4 修复：CSV 公式注入防护。
# Excel/LibreOffice/WPS 会将以 = + - @ \t \r 开头的单元格内容解释为公式，
# 若用户可控字段（assessment_type、severity 等）被注入 =cmd|'/c calc'!A1 等
# 公式，打开 CSV 时可能触发命令执行或数据外泄。统一对字符串字段做转义：
# 以危险字符开头的单元格前置一个单引号 '，Excel 会将其作为文本显示。
_CSV_FORMULA_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r", "\n")


def _sanitize_csv_cell(value: object) -> object:
    """对 CSV 单元格内容做公式注入防护。

    - 仅对 str 类型生效；int/float/None 等原样返回
    - 以 = + - @ \\t \\r \\n 开头的字符串前置单引号 '
    """
    if not isinstance(value, str) or not value:
        return value
    if value.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + value
    return value


_pdf_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pdf_gen")

# RES-P2-004: PDF 生成并发限流 Semaphore
# 原问题: ThreadPoolExecutor(max_workers=4) 限制了并发执行线程数, 但 submit() 调用本身无上限,
# 高并发场景下调用方持续 submit 任务, 队列堆积大量 PDF 生成请求, 占用内存并阻塞事件循环.
# 解决: 用 Semaphore 在 submit 之前限流, 最多允许 MAX_CONCURRENT_PDF_TASKS 个待处理任务
# (包括执行中 + 排队中), 超过后 submit_pdf 会阻塞等待 (async 场景) 或拒绝 (sync 场景).
# 配合 ThreadPoolExecutor 的 max_workers=4, 实际并发仍为 4, 但队列上限可控.
MAX_CONCURRENT_PDF_TASKS = 16  # 4 workers × 4 排队余量, 平衡吞吐与内存
_pdf_semaphore = threading.Semaphore(MAX_CONCURRENT_PDF_TASKS)


def shutdown_pdf_executor() -> None:
    """H-Svc-9 修复：关闭 PDF 生成线程池，供 FastAPI lifespan shutdown 阶段调用。"""
    _pdf_executor.shutdown(wait=True)


# PERF-P1-004: warning + intervention fire-and-forget 任务集合，防止被 GC 回收
_warning_intervention_tasks: set[asyncio.Task] = set()


def _log_warning_intervention_exception(task: asyncio.Task) -> None:
    """fire-and-forget 任务完成回调：记录未捕获异常。"""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "warning/intervention fire-and-forget task failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=exc,
        )


async def _trigger_warning_and_intervention(
    user_id: int,
    risk_id: int,
    risk_level: int,
) -> None:
    """PERF-P1-004: 在独立 session 中触发告警 + 干预计划 (fire-and-forget).

    - 使用独立 AsyncSessionLocal 避免共享请求事务边界
    - 通过 risk_id 重新查询 RiskAssessment (已 commit, 可见)
    - 调用 trigger_warning_for_risk + generate_intervention_for_risk
    - 自动 commit
    """
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        risk = (
            await db.execute(select(RiskAssessment).where(RiskAssessment.id == risk_id))
        ).scalar_one_or_none()
        if risk is None:
            logger.warning(
                "warning/intervention: RiskAssessment id=%s not found (user_id=%s)",
                risk_id,
                user_id,
            )
            return
        service = RiskService(db)
        await service.trigger_warning_for_risk(risk)
        await service.generate_intervention_for_risk(risk)
        await db.commit()
        logger.info(
            "warning/intervention completed async user_id=%s risk_id=%s risk_level=%s",
            user_id,
            risk_id,
            risk_level,
        )


def _schedule_warning_and_intervention(
    user_id: int,
    risk_id: int,
    risk_level: int,
) -> None:
    """PERF-P1-004: fire-and-forget 包装 — 调度异步任务, 不阻塞调用方.

    - 使用 asyncio.ensure_future 调度任务
    - 任务引用存入 _warning_intervention_tasks 防止 GC
    - 注册 done callback 记录异常
    - 调度失败不传播异常 (仅 log)
    """
    try:
        task = asyncio.ensure_future(
            _trigger_warning_and_intervention(user_id, risk_id, risk_level)
        )
        _warning_intervention_tasks.add(task)
        task.add_done_callback(_warning_intervention_tasks.discard)
        task.add_done_callback(_log_warning_intervention_exception)
        # R-005 修复: 注册可观测性指标 (scheduled/succeeded/failed/cancelled + duration)
        from app.core.fire_forget_metrics import register_task

        register_task(task, "warning_intervention")
    except Exception as exc:
        logger.error("Failed to schedule warning/intervention: %s", exc)


class RiskService(
    AssessmentMixin,
    ReportMixin,
    ExportMixin,
    WarningInterventionMixin,
):
    """风险评估服务主入口。

    通过 Mixin 多继承组合以下功能模块:
    - AssessmentMixin: 启发式打分、风险等级映射、结构化评估主流程
    - ReportMixin: 风险报告、风险因子分类、风险趋势、staticmethod 辅助函数
    - ExportMixin: CSV/JSON/PDF 导出
    - WarningInterventionMixin: 告警触发与干预计划生成

    本类仅保留类常量、__init__ 以及模块级工具函数 (位于本模块顶层):
    - `_sanitize_csv_cell`: CSV 公式注入防护 (ExportMixin 调用)
    - `_pdf_executor` / `_pdf_semaphore` / `shutdown_pdf_executor`: PDF 线程池管理
    - `_warning_intervention_tasks` / `_schedule_warning_and_intervention`:
      warning + intervention fire-and-forget 调度 (AssessmentMixin 调用)

    MAINT-P2-001: 原 1153 行单文件拆分为 5 文件, 每文件 ≤500 行。
    """

    # M-Svc-12 修复：启发式回退算法的权重配置。原注释称"可通过数据库或配置文件调整"，
    # 但实际实现为类常量，并未从 DB 或配置文件加载。修正注释使其与实现一致。
    # 如需动态调整，需扩展为从 settings 或 DB 读取。
    HEURISTIC_WEIGHTS = {
        "stress_level": 12.0,
        "anxiety": 14.0,
        "financial_pressure": 10.0,
        "panic_attack": 12.0,
        "sleep_duration": 5.0,
        "social_support": 6.0,
    }

    # 风险等级阈值配置，统一来自 shared constants
    RISK_LEVEL_THRESHOLDS = SHARED_RISK_LEVEL_THRESHOLDS

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
