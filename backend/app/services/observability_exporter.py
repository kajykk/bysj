"""v1.39 ObservabilityExporter.

将 v1.36 _compute_* 函数结果发布为 Prometheus Gauge,
供 Grafana Alerting 规则查询.

启动: FastAPI lifespan (T-AR-003)
周期: 60s (R1 决策 Q5)
错误处理: 单 _compute_* 失败不阻塞, 由 _loop 持续重试
DB ready: 启动时检测, 最多 3 次重试 (R3 GAP-3)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.core.database import AsyncSessionLocal, engine

logger = logging.getLogger(__name__)


class ObservabilityExporter:
    """v1.39: 将 v1.36 _compute_* 结果发布为 Prometheus Gauge.

    Usage (T-AR-003 lifespan):
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            exporter = ObservabilityExporter()
            await exporter.start()
            yield
            await exporter.stop()
    """

    # 60s 周期 (R1 决策 Q5)
    INTERVAL_SECONDS = 60

    # R3 GAP-3: DB ready 检测 3 次重试
    DB_READY_MAX_RETRIES = 3
    DB_READY_RETRY_DELAY_SECONDS = 1.0

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False
        # v1.39: 跟踪上一次 total_fired, 用于计算 Counter 增量
        self._prev_total_fired: int = 0

    async def start(self) -> None:
        """app startup 时调用 (R3 GAP-3: 检测 DB ready)."""
        if self._running:
            return
        # R3 GAP-3: 等待 DB ready, 最多 3 次重试 (1s 间隔)
        db_ready = await self._wait_for_db_ready()
        if not db_ready:
            # DB 3 次都未 ready, 不阻断启动, _collect_all 内部会重试
            logger.warning(
                "DB not ready after %d attempts, exporter will retry on first _collect_all",
                self.DB_READY_MAX_RETRIES,
            )
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "ObservabilityExporter started (interval=%ds)", self.INTERVAL_SECONDS
        )

    async def stop(self) -> None:
        """app shutdown 时调用."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ObservabilityExporter stopped")

    async def _wait_for_db_ready(self) -> bool:
        """R3 GAP-3: 最多 3 次重试检测 DB ready."""
        for attempt in range(1, self.DB_READY_MAX_RETRIES + 1):
            try:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                logger.info("DB ready on attempt %d", attempt)
                return True
            except Exception as e:
                logger.warning("DB not ready (attempt %d/%d): %s", attempt, self.DB_READY_MAX_RETRIES, e)
                if attempt < self.DB_READY_MAX_RETRIES:
                    await asyncio.sleep(self.DB_READY_RETRY_DELAY_SECONDS)
        return False

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._collect_all()
            except Exception as e:
                logger.exception("ObservabilityExporter _collect_all failed: %s", e)
            await asyncio.sleep(self.INTERVAL_SECONDS)

    async def _collect_all(self) -> None:
        """采集 8 个 metric, 写入 Gauge + Counter.

        每个 _compute_* 调用独立 try/except (FM-1 fallback),
        单个失败不阻塞其他.
        """
        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            start = now - timedelta(minutes=5)

            # 1. channel_stats → observability_channel_success_rate
            await self._safe_set_channel(db, start, now)

            # 2. am_sync → observability_am_sync_success_rate
            await self._safe_set_am_sync(db, start, now)

            # 3-6. lock_stats → 4 个 metric (acquire_rate, fallback_rate, error_rate, acquire_total)
            await self._safe_set_lock(db)

            # 7. escalation → observability_escalation_rate
            await self._safe_set_escalation(db, start, now)

            # 8. trend → observability_alert_total (Counter, 累加增量)
            await self._safe_set_alert_total(db, start, now)

        logger.debug("ObservabilityExporter collected 8 metrics")

    async def _safe_set_channel(
        self, db: AsyncSession, start: datetime, end: datetime
    ) -> None:
        """1. 通道成功率."""
        try:
            from app.api.v1.observability import _compute_channel_stats
            cs = await _compute_channel_stats(db, start_time=start, end_time=end)
            metrics.observability_channel_success_rate.set(
                cs.get("overall_success_rate", 0.0), channel="all"
            )
        except Exception as e:
            logger.warning("channel_stats collect failed (FM-1 fallback): %s", e)

    async def _safe_set_am_sync(
        self, db: AsyncSession, start: datetime, end: datetime
    ) -> None:
        """2. AM 同步成功率."""
        try:
            from app.api.v1.observability import _compute_am_sync
            am = await _compute_am_sync(db, start_time=start, end_time=end)
            metrics.observability_am_sync_success_rate.set(
                am.get("success_rate", 0.0)
            )
        except Exception as e:
            logger.warning("am_sync collect failed (FM-1 fallback): %s", e)

    async def _safe_set_lock(self, db: AsyncSession) -> None:
        """3-6. 锁 4 个 metric."""
        try:
            from app.api.v1.observability import _compute_lock_stats
            lk = await _compute_lock_stats(db)
            metrics.observability_lock_acquire_rate.set(
                lk.get("acquire_rate", 0.0)
            )
            metrics.observability_lock_fallback_rate.set(
                lk.get("fallback_rate", 0.0)
            )
            metrics.observability_lock_error_rate.set(
                lk.get("error_rate", 0.0)
            )
            metrics.observability_lock_acquire_total.set(
                lk.get("total", 0)
            )
        except Exception as e:
            logger.warning("lock_stats collect failed (FM-1 fallback): %s", e)

    async def _safe_set_escalation(
        self, db: AsyncSession, start: datetime, end: datetime
    ) -> None:
        """7. 升级率."""
        try:
            from app.api.v1.observability import _compute_escalation
            es = await _compute_escalation(db, start_time=start, end_time=end)
            metrics.observability_escalation_rate.set(
                es.get("escalation_rate", 0.0)
            )
        except Exception as e:
            logger.warning("escalation collect failed (FM-1 fallback): %s", e)

    async def _safe_set_alert_total(
        self, db: AsyncSession, start: datetime, end: datetime
    ) -> None:
        """8. 告警总量 (Counter, 仅累加 delta)."""
        try:
            from app.api.v1.observability import _compute_trend
            tr = await _compute_trend(db, start_time=start, end_time=end)
            total_fired = tr.get("total_fired", 0)
            # 仅记录本周期新增, 避免重复计数
            delta = max(0, total_fired - self._prev_total_fired)
            self._prev_total_fired = total_fired
            # 累加 4 个 severity (P0/P1/P2/P3 共享 delta, 简化模型)
            for severity in ("P0", "P1", "P2", "P3"):
                metrics.observability_alert_total.inc(delta, severity=severity)
        except Exception as e:
            logger.warning("alert_total collect failed (FM-1 fallback): %s", e)
