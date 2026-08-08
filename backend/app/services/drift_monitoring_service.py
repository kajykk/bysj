"""S4 P3: 漂移监测服务 — 连接 DriftDetector → DriftAlert 表 + PSI/KL Gauge.

将漂移检测接入生产监控闭环:
1. 从 RiskAssessment 表读取各模态评分 (structured/text/physiological/risk_score)
2. 用 DriftDetector 计算 PSI/KL (baseline 窗口 vs current 窗口)
3. PSI/KL 写入 model_drift_psi/model_drift_kl Gauge (供 Grafana 展示)
4. PSI > 0.25 时写入 DriftAlert 表 (供 AutoRollbackService 触发回滚)

这是 S4 P3 的关键闭环: drift detection → DriftAlert → auto-rollback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import CanaryRecord, CanaryStatus, DriftAlert, DriftSeverity
from app.models.risk import RiskAssessment
from app.services.drift_detector import DriftDetector

logger = logging.getLogger(__name__)

# 漂移阈值 (与 metrics.py model_drift_psi 文档一致)
PSI_WARNING = 0.1
PSI_DRIFT = 0.25
# T-P0-03: PSI > 2.0 通常意味着分布根本性变化 (如模型版本切换), 而非真实数据漂移.
# 此阈值下将 severity 限制为 HIGH 并标注 possible_model_version_mismatch, 等待人工确认.
PSI_SUSPECTED_VERSION_MISMATCH = 2.0

# 各模态对应的 RiskAssessment 列名
MODALITY_COLUMNS: dict[str, str] = {
    "structured": "structured_score",
    "text": "text_score",
    "physiological": "physiological_score",
    "fusion": "risk_score",
}


@dataclass
class DriftCheckResult:
    """单模态漂移检测结果."""

    modality: str
    feature: str
    psi: float
    kl: float
    baseline_n: int
    current_n: int
    alert_created: bool


class DriftMonitoringService:
    """周期性漂移监测服务.

    由 celery beat 每小时触发, 计算 4 个模态的预测分布漂移.
    """

    def __init__(self, detector: DriftDetector | None = None) -> None:
        self.detector = detector or DriftDetector()

    async def check_all_modalities(
        self,
        db_session: AsyncSession,
        baseline_days: int = 7,
        current_hours: int = 24,
    ) -> list[DriftCheckResult]:
        """检查所有模态的漂移状态.

        Args:
            db_session: 数据库会话.
            baseline_days: 基线窗口的天数 (baseline_end = now - current_hours).
            current_hours: 当前窗口的小时数.

        Returns:
            各模态的漂移检测结果列表.
        """
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        current_start = now_naive - timedelta(hours=current_hours)
        baseline_end = current_start
        baseline_start = baseline_end - timedelta(days=baseline_days)

        results: list[DriftCheckResult] = []

        for modality, column_name in MODALITY_COLUMNS.items():
            try:
                result = await self._check_modality(
                    db_session=db_session,
                    modality=modality,
                    column_name=column_name,
                    baseline_start=baseline_start,
                    baseline_end=baseline_end,
                    current_start=current_start,
                    now=now_naive,
                )
                results.append(result)
            except Exception:
                logger.exception(
                    "漂移检测失败 modality=%s column=%s", modality, column_name
                )
                results.append(
                    DriftCheckResult(
                        modality=modality,
                        feature=column_name,
                        psi=0.0,
                        kl=0.0,
                        baseline_n=0,
                        current_n=0,
                        alert_created=False,
                    )
                )

        self._push_to_gauge(results)
        return results

    async def _check_modality(
        self,
        db_session: AsyncSession,
        modality: str,
        column_name: str,
        baseline_start: datetime,
        baseline_end: datetime,
        current_start: datetime,
        now: datetime,
    ) -> DriftCheckResult:
        """检查单个模态的漂移."""
        column = getattr(RiskAssessment, column_name)

        # 基线窗口数据
        baseline_stmt = (
            select(column)
            .where(
                RiskAssessment.created_at >= baseline_start,
                RiskAssessment.created_at < baseline_end,
                column.isnot(None),
            )
        )
        baseline_result = await db_session.execute(baseline_stmt)
        baseline_values = [float(v) for v in baseline_result.scalars().all() if v is not None]

        # 当前窗口数据
        current_stmt = (
            select(column)
            .where(
                RiskAssessment.created_at >= current_start,
                RiskAssessment.created_at <= now,
                column.isnot(None),
            )
        )
        current_result = await db_session.execute(current_stmt)
        current_values = [float(v) for v in current_result.scalars().all() if v is not None]

        baseline_n = len(baseline_values)
        current_n = len(current_values)

        # 数据不足时跳过 (需要至少 30 个样本才有统计意义)
        if baseline_n < 30 or current_n < 30:
            logger.info(
                "漂移检测跳过 modality=%s: baseline_n=%d current_n=%d (需≥30)",
                modality, baseline_n, current_n,
            )
            return DriftCheckResult(
                modality=modality,
                feature=column_name,
                psi=0.0,
                kl=0.0,
                baseline_n=baseline_n,
                current_n=current_n,
                alert_created=False,
            )

        psi = self.detector.calculate_psi(baseline_values, current_values)
        kl = self.detector.calculate_kl(baseline_values, current_values)

        logger.info(
            "漂移检测 modality=%s: PSI=%.4f KL=%.4f (baseline=%d current=%d)",
            modality, psi, kl, baseline_n, current_n,
        )

        # PSI > 0.25 时写入 DriftAlert (去重: 同模态+特征未解决的告警不重复插入)
        alert_created = False
        if psi > PSI_DRIFT:
            alert_created = await self._create_drift_alert(
                db_session=db_session,
                modality=modality,
                feature=column_name,
                psi=psi,
                kl=kl,
                baseline_n=baseline_n,
                current_n=current_n,
            )

        return DriftCheckResult(
            modality=modality,
            feature=column_name,
            psi=psi,
            kl=kl,
            baseline_n=baseline_n,
            current_n=current_n,
            alert_created=alert_created,
        )

    async def _create_drift_alert(
        self,
        db_session: AsyncSession,
        modality: str,
        feature: str,
        psi: float,
        kl: float,
        baseline_n: int,
        current_n: int,
    ) -> bool:
        """创建 DriftAlert 记录 (去重).

        T-P0-03: 当 PSI > PSI_SUSPECTED_VERSION_MISMATCH (2.0) 时, 极可能是
        模型版本切换导致的跨版本比较 (如 v2.0 优化后基线窗口含旧模型预测),
        而非真实数据漂移. 此时:
        - **不创建 DriftAlert** (避免告警风暴, 每小时检测会重复触发)
        - PSI/KL 仍推送到 Prometheus Gauge (Grafana 可视化不受影响)
        - 记录 warning 日志供人工排查
        - 不触发 AutoRollbackService 回滚 (DriftAlert 表无新增记录)

        根因: PSI > 2.0 在统计学上意味着分布根本性变化 (真实数据漂移 PSI 通常
        在 0.25-1.0 之间), 几乎必然是版本切换/数据管道问题. 真实漂移由 0.25 < PSI ≤ 2.0
        区间的告警覆盖, 不需要 PSI > 2.0 的告警.

        治理历史:
        - 2026-07-24: id=4,5,6 CRITICAL 告警 (PSI 8.39/3.95/12.41) 已 resolved
          (跨版本比较误报)
        - 2026-07-24: id=7,8,9 HIGH 告警 (PSI 8.34/3.92/12.42) 为守卫降级产物,
          本应不创建. 本次修复后此类告警不再产生.
        """
        # T-P0-03: 检测可能的模型版本失配 — 直接跳过告警创建
        suspected_version_mismatch = psi > PSI_SUSPECTED_VERSION_MISMATCH
        if suspected_version_mismatch:
            logger.warning(
                "T-P0-03: 检测到疑似模型版本失配 modality=%s PSI=%.4f (>%.1f), "
                "不创建 DriftAlert (避免告警风暴). PSI/KL 仍推送 Gauge 供 Grafana 可视化. "
                "需人工排查基线窗口是否含旧模型预测.",
                modality, psi, PSI_SUSPECTED_VERSION_MISMATCH,
            )
            return False

        # 检查是否已有未解决的告警 (仅对真实漂移 PSI ≤ 2.0 启用去重)
        existing_stmt = (
            select(DriftAlert)
            .where(
                DriftAlert.feature_name == feature,
                DriftAlert.drift_type == "prediction_drift",
                DriftAlert.resolved_at.is_(None),
            )
            .order_by(DriftAlert.created_at.desc())
            .limit(1)
        )
        existing_result = await db_session.execute(existing_stmt)
        existing = existing_result.scalar_one_or_none()

        if existing is not None:
            logger.info(
                "漂移告警已存在 modality=%s feature=%s (id=%d), 跳过",
                modality, feature, existing.id,
            )
            return False

        severity = DriftSeverity.CRITICAL if psi > 0.5 else DriftSeverity.HIGH

        # 查询当前运行中的金丝雀版本用于 model_version 归属.
        # 修复: 此前将 modality 存入 model_version, 导致 auto_rollback_service 按
        # canary.version 匹配时恒为 0, 漂移维度自动回滚静默失效.
        # modality 归属仍在 details["modality"] 中.
        running_canary_stmt = (
            select(CanaryRecord.version)
            .where(CanaryRecord.status == CanaryStatus.RUNNING)
            .order_by(CanaryRecord.started_at.desc())
            .limit(1)
        )
        canary_version = (
            await db_session.execute(running_canary_stmt)
        ).scalar_one_or_none()

        alert = DriftAlert(
            model_version=canary_version,
            feature_name=feature,
            drift_type="prediction_drift",
            severity=severity,
            metric_value=round(psi, 4),
            threshold=PSI_DRIFT,
            details={
                "psi": round(psi, 4),
                "kl": round(kl, 4),
                "baseline_n": baseline_n,
                "current_n": current_n,
                "modality": modality,
                "possible_model_version_mismatch": False,
            },
        )
        db_session.add(alert)
        await db_session.flush()

        logger.warning(
            "漂移告警已创建 modality=%s feature=%s PSI=%.4f severity=%s alert_id=%d",
            modality, feature, psi, severity, alert.id,
        )
        return True

    async def resolve_alerts_for_modality(
        self,
        db_session: AsyncSession,
        modality: str,
        reason: str,
    ) -> int:
        """解决指定模态的所有未解决 DriftAlert.

        T-P0-03: 用于模型升级后清理跨版本比较导致的误报告警.

        Args:
            db_session: 数据库会话.
            modality: 模态名 (structured/text/physiological/fusion).
            reason: 解决原因 (写入 details.resolution_reason).

        Returns:
            已解决的告警数量.
        """
        stmt = (
            select(DriftAlert)
            .where(
                DriftAlert.model_version == modality,
                DriftAlert.drift_type == "prediction_drift",
                DriftAlert.resolved_at.is_(None),
            )
        )
        result = await db_session.execute(stmt)
        alerts = list(result.scalars().all())

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for alert in alerts:
            alert.resolved_at = now
            # 保留原 details, 追加解决信息
            details = dict(alert.details) if alert.details else {}
            details["resolution_reason"] = reason
            details["resolved_by"] = "drift_monitoring_service.resolve_alerts_for_modality"
            alert.details = details

        logger.info(
            "T-P0-03: 已解决 %d 条 modality=%s 的未解决漂移告警, reason=%s",
            len(alerts), modality, reason,
        )
        return len(alerts)

    def _push_to_gauge(self, results: list[DriftCheckResult]) -> None:
        """将 PSI/KL 推送到 Prometheus Gauge (供 Grafana 展示)."""
        try:
            from app.core.metrics import model_drift_kl, model_drift_psi

            for r in results:
                model_drift_psi.set(
                    float(r.psi), modality=r.modality, feature=r.feature
                )
                model_drift_kl.set(
                    float(r.kl), modality=r.modality, feature=r.feature
                )
        except Exception:
            logger.debug("推送 PSI/KL 到 Gauge 失败 (metrics 模块未加载?)", exc_info=True)


# 单例
drift_monitoring_service = DriftMonitoringService()
