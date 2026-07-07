"""v1.39 ObservabilityExporter.

将 v1.36 _compute_* 函数结果发布为 Prometheus Gauge,
供 Grafana Alerting 规则查询.

启动: FastAPI lifespan (T-AR-003)
周期: 60s (R1 决策 Q5)
错误处理: 单 _compute_* 失败不阻塞, 由 _loop 持续重试
DB ready: 启动时检测, 最多 3 次重试 (R3 GAP-3)

R-C 改造: 同时订阅 EventBus 事件, 实时更新 Prometheus 指标 (端到端延迟 < 5s).
保留 60s 周期轮询作为兜底 (防止事件丢失).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.core.database import AsyncSessionLocal, engine
from app.core.event_bus import event_bus

logger = logging.getLogger(__name__)


class ObservabilityExporter:
    """v1.39: 将 v1.36 _compute_* 结果发布为 Prometheus Gauge.

    R-C: 同时订阅 EventBus 事件, 实时更新 Prometheus 指标.

    Usage (T-AR-003 lifespan):
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            exporter = ObservabilityExporter()
            await exporter.start()
            yield
            await exporter.stop()
    """

    # 60s 周期 (R1 决策 Q5) — R-C 保留作为兜底
    INTERVAL_SECONDS = 60

    # R3 GAP-3: DB ready 检测 3 次重试
    DB_READY_MAX_RETRIES = 3
    DB_READY_RETRY_DELAY_SECONDS = 1.0

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False
        # v1.39: 跟踪上一次 total_fired, 用于计算 Counter 增量
        self._prev_total_fired: int = 0
        # H-8 修复：标记计数器是否已初始化。服务重启后 _prev_total_fired 为 0，
        # 若不初始化则首次 delta = total_fired - 0 会将所有历史告警作为增量计入 Counter。
        self._counter_initialized: bool = False
        # R-C: 注册事件处理器
        self._register_event_handlers()

    def _register_event_handlers(self) -> None:
        """R-C: 注册事件订阅器, 实时更新 Prometheus 指标."""
        event_bus.subscribe("alert.fired", self._on_alert_fired)
        event_bus.subscribe("alert.resolved", self._on_alert_resolved)
        event_bus.subscribe("alert.escalated", self._on_alert_escalated)
        event_bus.subscribe("warning.created", self._on_warning_created)
        event_bus.subscribe("review.submitted", self._on_review_submitted)
        logger.info("ObservabilityExporter registered 5 event handlers")

    # ---- R-C 事件处理器 (实时更新 Prometheus 指标) ----

    async def _on_alert_fired(self, data: dict) -> None:
        """实时更新 event_alerts_fired_total Counter."""
        metrics.event_alerts_fired_total.inc()
        logger.debug("Event alert.fired processed: alert_id=%s", data.get("alert_id"))

    async def _on_alert_resolved(self, data: dict) -> None:
        """实时更新 event_alerts_resolved_total Counter."""
        metrics.event_alerts_resolved_total.inc()
        logger.debug(
            "Event alert.resolved processed: alert_id=%s", data.get("alert_id")
        )

    async def _on_alert_escalated(self, data: dict) -> None:
        """实时更新 event_alerts_escalated_total Counter."""
        metrics.event_alerts_escalated_total.inc()
        logger.debug(
            "Event alert.escalated processed: alert_id=%s", data.get("alert_id")
        )

    async def _on_warning_created(self, data: dict) -> None:
        """实时更新 event_warnings_created_total Counter."""
        metrics.event_warnings_created_total.inc()
        logger.debug(
            "Event warning.created processed: warning_id=%s", data.get("warning_id")
        )

    async def _on_review_submitted(self, data: dict) -> None:
        """实时更新 event_reviews_submitted_total Counter."""
        metrics.event_reviews_submitted_total.inc()
        logger.debug(
            "Event review.submitted processed: review_id=%s", data.get("review_id")
        )

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
        # R-C: 启动 EventBus 消费循环
        await event_bus.start()
        # 保留 60s 周期作为兜底 (防止事件丢失)
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "ObservabilityExporter started (interval=%ds, event_driven=True)",
            self.INTERVAL_SECONDS,
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
        # R-C: 停止 EventBus 消费循环
        await event_bus.stop()
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
                logger.warning(
                    "DB not ready (attempt %d/%d): %s",
                    attempt,
                    self.DB_READY_MAX_RETRIES,
                    e,
                )
                if attempt < self.DB_READY_MAX_RETRIES:
                    await asyncio.sleep(self.DB_READY_RETRY_DELAY_SECONDS)
        return False

    async def _loop(self) -> None:
        # M-Svc-13 修复：异常时指数退避，避免快速重试加剧下游故障（如 DB 过载）
        retry_count = 0
        while self._running:
            try:
                await self._collect_all()
                retry_count = 0  # 成功时重置退避计数
            except Exception as e:
                retry_count += 1
                logger.exception("ObservabilityExporter _collect_all failed: %s", e)
                backoff = min(60, 2**retry_count)
                await asyncio.sleep(backoff)
                continue
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

            # channel=None 表示聚合所有通道 (与 API 端点默认行为一致)
            cs = await _compute_channel_stats(db, start, end, None)
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

            # operation=None 表示聚合所有操作 (与 API 端点默认行为一致)
            am = await _compute_am_sync(db, start, end, None)
            metrics.observability_am_sync_success_rate.set(am.get("success_rate", 0.0))
        except Exception as e:
            logger.warning("am_sync collect failed (FM-1 fallback): %s", e)

    async def _safe_set_lock(self, db: AsyncSession) -> None:
        """3-6. 锁 4 个 metric."""
        try:
            from app.api.v1.observability import _compute_lock_stats

            lk = await _compute_lock_stats(db)
            # _compute_lock_stats 返回嵌套结构: {"memory": {...}, "historical_recent": {...}}
            mem = lk.get("memory", {})
            metrics.observability_lock_acquire_rate.set(mem.get("acquire_rate", 0.0))
            metrics.observability_lock_fallback_rate.set(mem.get("fallback_rate", 0.0))
            metrics.observability_lock_error_rate.set(mem.get("error_rate", 0.0))
            metrics.observability_lock_acquire_total.set(mem.get("total", 0))
        except Exception as e:
            logger.warning("lock_stats collect failed (FM-1 fallback): %s", e)

    async def _safe_set_escalation(
        self, db: AsyncSession, start: datetime, end: datetime
    ) -> None:
        """7. 升级率."""
        try:
            from app.api.v1.observability import _compute_escalation

            # severity=None 表示聚合所有严重度 (与 API 端点默认行为一致)
            es = await _compute_escalation(db, start, end, None)
            metrics.observability_escalation_rate.set(es.get("escalation_rate", 0.0))
        except Exception as e:
            logger.warning("escalation collect failed (FM-1 fallback): %s", e)

    async def _safe_set_alert_total(
        self, db: AsyncSession, start: datetime, end: datetime
    ) -> None:
        """8. 告警总量 (Counter, 仅累加 delta)."""
        try:
            from app.api.v1.observability import _compute_trend

            # bucket="1h", severity=None, status=None, group_by="none"
            # 表示获取全量合计 (与 API 端点默认行为一致)
            tr = await _compute_trend(db, start, end, "1h", None, None, "none")
            # _compute_trend 返回 by_status={"firing": N, "resolved": M}
            # total_fired = firing 数量 (不含 resolved)
            total_fired = tr.get("by_status", {}).get("firing", 0)
            # H-8 修复：首次采集时仅初始化基线，不计算 delta。
            # 避免服务重启后 _prev_total_fired=0 导致所有历史告警被作为增量计入 Counter。
            if not self._counter_initialized:
                self._prev_total_fired = total_fired
                self._counter_initialized = True
                logger.info(
                    "ObservabilityExporter counter initialized: total_fired=%d",
                    total_fired,
                )
                return
            # 仅记录本周期新增, 避免重复计数
            delta = max(0, total_fired - self._prev_total_fired)
            self._prev_total_fired = total_fired
            # total_fired 是所有严重级别的合计，仅累加一次（severity="total"）
            # 避免循环 4 个 severity 导致计数膨胀 4 倍
            if delta > 0:
                metrics.observability_alert_total.inc(delta, severity="total")
        except Exception as e:
            logger.warning("alert_total collect failed (FM-1 fallback): %s", e)
