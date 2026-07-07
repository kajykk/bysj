from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import CanaryRecord, CanaryStatus
from app.services.observability_service import observability_collector

logger = logging.getLogger(__name__)


@dataclass
class TrafficDecision:
    """Traffic routing decision result."""

    use_canary: bool
    canary_version: str | None
    stable_version: str
    reason: str


@dataclass
class RollbackThresholds:
    """Auto-rollback thresholds."""

    max_fallback_rate: float = 0.05
    max_drift_alerts_per_hour: int = 10
    max_avg_latency_ms: float = 500.0


class CanaryManager:
    """Manages canary deployments with traffic splitting and auto-rollback.

    Features:
    - Stable hash-based traffic allocation (sha256(user_id)[0:8] % 100)
    - Dynamic configuration via database (no restart required)
    - Version routing decisions
    - Auto-rollback based on thresholds
    """

    DEFAULT_TRAFFIC_PERCENTAGES = [1, 5, 25, 50, 100]

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._cache_timestamp: datetime | None = None
        self._cache_ttl = timedelta(seconds=10)

    def _hash_user_id(self, user_id: int | str) -> int:
        """Compute stable hash for user_id.

        ISS-001/ISS-012 修复：使用 sha256 替代 md5，消除 Bandit High 告警。
        sha256(user_id)[0:8] % 100 保持一致的流量分配语义。
        """
        digest = hashlib.sha256(str(user_id).encode()).hexdigest()[:8]
        return int(digest, 16) % 100

    def is_canary_user(self, user_id: int | str, traffic_percent: int) -> bool:
        """Determine if a user should be routed to canary version.

        Args:
            user_id: User identifier.
            traffic_percent: Percentage of traffic to route to canary (0-100).

        Returns:
            True if user should use canary version.
        """
        if traffic_percent <= 0:
            return False
        if traffic_percent >= 100:
            return True
        user_hash = self._hash_user_id(user_id)
        return user_hash < traffic_percent

    async def get_active_canary(self, db_session: AsyncSession) -> CanaryRecord | None:
        """Get currently active canary record.

        Returns:
            Active canary record or None.
        """
        result = await db_session.execute(
            select(CanaryRecord)
            .where(
                CanaryRecord.status == CanaryStatus.RUNNING,
            )
            .order_by(CanaryRecord.started_at.desc())
        )
        return result.scalar_one_or_none()

    async def decide_version(
        self,
        db_session: AsyncSession,
        user_id: int | str,
        stable_version: str,
    ) -> TrafficDecision:
        """Decide which version to use for a user.

        Args:
            db_session: Database session.
            user_id: User identifier.
            stable_version: Current stable version.

        Returns:
            TrafficDecision with routing information.
        """
        canary = await self.get_active_canary(db_session)

        if not canary:
            return TrafficDecision(
                use_canary=False,
                canary_version=None,
                stable_version=stable_version,
                reason="no_active_canary",
            )

        if canary.status != CanaryStatus.RUNNING:
            return TrafficDecision(
                use_canary=False,
                canary_version=canary.version,
                stable_version=stable_version,
                reason=f"canary_status_{canary.status}",
            )

        is_canary = self.is_canary_user(user_id, canary.traffic_percent)

        if is_canary:
            return TrafficDecision(
                use_canary=True,
                canary_version=canary.version,
                stable_version=stable_version,
                reason=f"canary_traffic_{canary.traffic_percent}%",
            )

        return TrafficDecision(
            use_canary=False,
            canary_version=canary.version,
            stable_version=stable_version,
            reason="stable_traffic",
        )

    async def start_canary(
        self,
        db_session: AsyncSession,
        version: str,
        traffic_percent: int = 1,
        triggered_by: int | None = None,
        thresholds: dict[str, float] | None = None,
    ) -> CanaryRecord:
        """Start a new canary deployment.

        Args:
            db_session: Database session.
            version: Canary version.
            traffic_percent: Initial traffic percentage.
            triggered_by: User ID who triggered the canary.
            thresholds: Auto-rollback thresholds.

        Returns:
            Created canary record.
        """
        # Check if there's already a running canary
        existing = await self.get_active_canary(db_session)
        if existing:
            raise ValueError(f"Canary already running: {existing.version}")

        default_thresholds = {
            "max_fallback_rate": 0.05,
            "max_drift_alerts_per_hour": 10,
            "max_avg_latency_ms": 500.0,
        }
        if thresholds:
            default_thresholds.update(thresholds)

        canary = CanaryRecord(
            version=version,
            traffic_percent=traffic_percent,
            status=CanaryStatus.RUNNING,
            auto_rollback_thresholds=default_thresholds,
            triggered_by=triggered_by,
            # H-Svc-4 修复：DateTime 列为 naive，写入前剥离 tzinfo 避免 aware/naive 混用
            started_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(canary)
        # H-4 修复：service 层不调用 commit()，改用 flush() 将更改刷入数据库但不提交事务。
        # 事务边界由调用方（API 层或 auto_rollback_service 的 savepoint）管理。
        await db_session.flush()
        await db_session.refresh(canary)

        observability_collector.record_model_success(
            model_version=version,
            user_id=triggered_by,
            response_summary={
                "event": "canary_started",
                "traffic_percent": traffic_percent,
            },
        )

        logger.info(
            "Canary started: version=%s, traffic=%d%%", version, traffic_percent
        )
        return canary

    async def update_traffic_percent(
        self,
        db_session: AsyncSession,
        canary_id: int,
        new_percent: int,
    ) -> CanaryRecord:
        """Update canary traffic percentage.

        Args:
            db_session: Database session.
            canary_id: Canary record ID.
            new_percent: New traffic percentage.

        Returns:
            Updated canary record.
        """
        result = await db_session.execute(
            select(CanaryRecord).where(CanaryRecord.id == canary_id)
        )
        canary = result.scalar_one_or_none()

        if not canary:
            raise ValueError(f"Canary {canary_id} not found")

        if canary.status not in {CanaryStatus.RUNNING, CanaryStatus.PAUSED}:
            raise ValueError(
                f"Cannot update traffic for canary in status: {canary.status}"
            )

        old_percent = canary.traffic_percent
        canary.traffic_percent = new_percent
        # H-Svc-1 修复：与 start_canary/rollback_canary 保持一致，service 层使用 flush() 而非 commit()
        await db_session.flush()
        await db_session.refresh(canary)

        logger.info(
            "Canary %d traffic updated: %d%% -> %d%%",
            canary_id,
            old_percent,
            new_percent,
        )
        return canary

    async def pause_canary(
        self, db_session: AsyncSession, canary_id: int
    ) -> CanaryRecord:
        """Pause a running canary."""
        result = await db_session.execute(
            select(CanaryRecord).where(CanaryRecord.id == canary_id)
        )
        canary = result.scalar_one_or_none()

        if not canary:
            raise ValueError(f"Canary {canary_id} not found")

        if canary.status != CanaryStatus.RUNNING:
            raise ValueError(f"Cannot pause canary in status: {canary.status}")

        canary.status = CanaryStatus.PAUSED
        # H-Svc-1 修复：service 层使用 flush() 而非 commit()，事务边界由调用方管理
        await db_session.flush()
        await db_session.refresh(canary)

        logger.info("Canary %d paused", canary_id)
        return canary

    async def resume_canary(
        self, db_session: AsyncSession, canary_id: int
    ) -> CanaryRecord:
        """Resume a paused canary."""
        result = await db_session.execute(
            select(CanaryRecord).where(CanaryRecord.id == canary_id)
        )
        canary = result.scalar_one_or_none()

        if not canary:
            raise ValueError(f"Canary {canary_id} not found")

        if canary.status != CanaryStatus.PAUSED:
            raise ValueError(f"Cannot resume canary in status: {canary.status}")

        canary.status = CanaryStatus.RUNNING
        # H-Svc-1 修复：service 层使用 flush() 而非 commit()，事务边界由调用方管理
        await db_session.flush()
        await db_session.refresh(canary)

        logger.info("Canary %d resumed", canary_id)
        return canary

    async def rollback_canary(
        self,
        db_session: AsyncSession,
        canary_id: int,
        reason: str,
    ) -> CanaryRecord:
        """Rollback a canary deployment.

        Args:
            db_session: Database session.
            canary_id: Canary record ID.
            reason: Rollback reason.

        Returns:
            Updated canary record.
        """
        result = await db_session.execute(
            select(CanaryRecord).where(CanaryRecord.id == canary_id)
        )
        canary = result.scalar_one_or_none()

        if not canary:
            raise ValueError(f"Canary {canary_id} not found")

        if canary.status not in {CanaryStatus.RUNNING, CanaryStatus.PAUSED}:
            raise ValueError(f"Cannot rollback canary in status: {canary.status}")

        canary.status = CanaryStatus.ROLLED_BACK
        # H-Svc-4 修复：DateTime 列为 naive，写入前剥离 tzinfo
        canary.ended_at = datetime.now(timezone.utc).replace(tzinfo=None)
        canary.rollback_reason = reason
        # H-4 修复：commit() 会提交最外层事务而非仅释放 savepoint，破坏 auto_rollback_service
        # 的 begin_nested() 隔离。改用 flush() 仅将更改刷入 DB，由调用方管理事务提交。
        await db_session.flush()
        await db_session.refresh(canary)

        observability_collector.record_fallback(
            reason=f"canary_rollback: {reason}",
            model_version=canary.version,
            response_summary={"canary_id": canary_id, "rollback_reason": reason},
        )

        logger.info("Canary %d rolled back: %s", canary_id, reason)
        return canary

    async def complete_canary(
        self, db_session: AsyncSession, canary_id: int
    ) -> CanaryRecord:
        """Complete a successful canary deployment."""
        result = await db_session.execute(
            select(CanaryRecord).where(CanaryRecord.id == canary_id)
        )
        canary = result.scalar_one_or_none()

        if not canary:
            raise ValueError(f"Canary {canary_id} not found")

        if canary.status != CanaryStatus.RUNNING:
            raise ValueError(f"Cannot complete canary in status: {canary.status}")

        canary.status = CanaryStatus.COMPLETED
        # H-Svc-4 修复：DateTime 列为 naive，写入前剥离 tzinfo
        canary.ended_at = datetime.now(timezone.utc).replace(tzinfo=None)
        # H-4 修复：与 rollback_canary 保持一致，service 层使用 flush() 而非 commit()
        await db_session.flush()
        await db_session.refresh(canary)

        logger.info("Canary %d completed successfully", canary_id)
        return canary

    async def check_auto_rollback(
        self,
        db_session: AsyncSession | None,
        canary_id: int,
        metrics: dict[str, float],
    ) -> tuple[bool, str]:
        """Check if auto-rollback should be triggered.

        Args:
            db_session: Database session.
            canary_id: Canary record ID.
            metrics: Current metrics (fallback_rate, drift_alerts_per_hour, avg_latency_ms).

        Returns:
            Tuple of (should_rollback, reason).
        """
        # M20 修复：统一为 async def，确保始终返回 tuple[bool, str] 而非协程对象
        if db_session is None:
            return self._evaluate_rollback_metrics({}, metrics)

        result = await db_session.execute(
            select(CanaryRecord).where(CanaryRecord.id == canary_id)
        )
        canary = result.scalar_one_or_none()

        if not canary or canary.status != CanaryStatus.RUNNING:
            return False, "canary_not_running"

        thresholds = canary.auto_rollback_thresholds or {}
        return self._evaluate_rollback_metrics(thresholds, metrics)

    def _evaluate_rollback_metrics(
        self,
        thresholds: dict[str, float],
        metrics: dict[str, float],
    ) -> tuple[bool, str]:
        """Evaluate rollback thresholds without requiring database access."""
        if "fallback_rate" in metrics:
            max_rate = thresholds.get("max_fallback_rate", 0.05)
            if metrics["fallback_rate"] > max_rate:
                return (
                    True,
                    f"fallback_rate {metrics['fallback_rate']:.2%} exceeds threshold {max_rate:.2%}",
                )

        if "drift_alerts_per_hour" in metrics:
            max_alerts = thresholds.get("max_drift_alerts_per_hour", 10)
            if metrics["drift_alerts_per_hour"] > max_alerts:
                return (
                    True,
                    f"drift_alerts_per_hour {metrics['drift_alerts_per_hour']} exceeds threshold {max_alerts}",
                )

        if "avg_latency_ms" in metrics:
            max_latency = thresholds.get("max_avg_latency_ms", 500.0)
            if metrics["avg_latency_ms"] > max_latency:
                return (
                    True,
                    f"avg_latency_ms {metrics['avg_latency_ms']} exceeds threshold {max_latency}",
                )

        return False, "within_thresholds"

    def get_traffic_percentages(self) -> list[int]:
        """Get available traffic percentage options."""
        return self.DEFAULT_TRAFFIC_PERCENTAGES.copy()


# Global manager instance
canary_manager = CanaryManager()
