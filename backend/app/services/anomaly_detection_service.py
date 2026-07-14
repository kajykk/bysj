"""SEC-P1-005 修复：异常访问检测服务 (v1.40)

原问题: 系统缺少异常访问检测机制，无法及时发现撞库/爬虫/横向越权等可疑行为。
OperationLog 仅作为被动审计记录，无主动分析能力。

本模块提供 4 类异常检测器，由 Celery 周期任务 (tasks/anomaly_detection.py) 调用:

1. 高频访问检测 (high_frequency):
   同一用户 N 分钟内操作数 > threshold，可能为撞库/爬虫/暴力枚举。
   关联 alert_rules AR-303。

2. 非工作时间访问检测 (off_hours):
   22:00~06:00 (UTC) 期间管理员/咨询师角色的操作视为可疑 (潜在数据外泄)。
   关联 alert_rules AR-304。

3. 异地访问检测 (cross_region):
   同一用户 N 小时内不同 IP 数量 > threshold (可能账号被盗)。
   注: 当前无 GeoIP 解析，简化为基于 IP 数量的检测。
   关联 alert_rules AR-305。

4. 横向越权访问检测 (lateral):
   同一用户 N 分钟内访问的不同 target_type 数量 > threshold (横向越权迹象)。
   咨询师正常工作涉及多 target_type，阈值按 operator_role 区分。
   关联 alert_rules AR-306。

设计原则:
- 纯查询: 不直接写入数据库，由调用方 (Celery 任务) 负责持久化
- 幂等性: 同一时间窗口内重复扫描结果一致
- 时区安全: DB 列为 naive datetime，使用 _utcnow_naive() 避免时区错误
- 性能: 单次扫描最多返回 100 条 finding，避免内存爆炸
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.admin import OperationLog

logger = logging.getLogger(__name__)

# 单次扫描返回的最大 finding 数量，避免内存爆炸
MAX_FINDINGS_PER_SCAN = 100


def _utcnow_naive() -> datetime:
    """获取当前 UTC 时间 (naive datetime).

    OperationLog.created_at 是 naive datetime，与 aware datetime 相减会抛 TypeError。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class AnomalyFinding:
    """单条异常检测结果.

    Attributes:
        anomaly_type: 异常类型 (high_frequency / off_hours / cross_region / lateral)
        operator_id: 操作者 ID
        operator_role: 操作者角色
        detail: 详情 (JSON 字符串, 写入 OperationLog.detail)
        ip_address: 关联 IP (异地检测时为最新 IP, 其他可为 None)
        rule_id: 关联 alert_rules 规则 ID (AR-303~306)
        evidence: 调试用原始证据 (不写入 OperationLog, 仅供日志)
    """

    anomaly_type: str
    operator_id: int
    operator_role: str
    detail: str
    ip_address: str | None = None
    rule_id: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


# ── 各角色横向越权阈值覆盖 ──
# 咨询师正常工作会访问 user / consultation_record / user_upload 等多种 target_type，
# 阈值需高于普通用户
_LATERAL_THRESHOLD_BY_ROLE: dict[str, int] = {
    "admin": 8,
    "counselor": 7,
}


def _get_lateral_threshold(role: str) -> int:
    """根据角色获取横向越权阈值 (覆盖默认配置)."""
    return _LATERAL_THRESHOLD_BY_ROLE.get(
        role, settings.anomaly_lateral_target_type_threshold
    )


async def detect_high_frequency(db: AsyncSession) -> list[AnomalyFinding]:
    """检测高频访问.

    查询 N 分钟内每个用户的操作数，超过 threshold 的视为异常。
    返回的 ip_address 为该用户最近一次操作的 IP (便于追踪)。
    """
    if not settings.anomaly_detection_enabled:
        return []

    window_minutes = settings.anomaly_high_freq_window_minutes
    threshold = settings.anomaly_high_freq_threshold
    cutoff = _utcnow_naive() - timedelta(minutes=window_minutes)

    # 按用户分组统计操作数，过滤超阈值的
    stmt = (
        select(
            OperationLog.operator_id,
            OperationLog.operator_role,
            func.count(OperationLog.id).label("op_count"),
        )
        .where(
            and_(
                OperationLog.created_at >= cutoff,
                OperationLog.operator_id.isnot(None),
            )
        )
        .group_by(OperationLog.operator_id, OperationLog.operator_role)
        .having(func.count(OperationLog.id) > threshold)
        .limit(MAX_FINDINGS_PER_SCAN)
    )
    rows = (await db.execute(stmt)).all()

    findings: list[AnomalyFinding] = []
    for operator_id, operator_role, op_count in rows:
        # 查询该用户最近一次操作的 IP (取 cutoff 之后的最新一条)
        latest_stmt = (
            select(OperationLog.ip_address)
            .where(
                and_(
                    OperationLog.operator_id == operator_id,
                    OperationLog.created_at >= cutoff,
                )
            )
            .order_by(OperationLog.created_at.desc())
            .limit(1)
        )
        latest_ip = (await db.execute(latest_stmt)).scalar_one_or_none()

        detail = json.dumps(
            {
                "anomaly_type": "high_frequency",
                "window_minutes": window_minutes,
                "op_count": int(op_count),
                "threshold": threshold,
                "operator_role": operator_role,
            },
            ensure_ascii=False,
        )

        findings.append(
            AnomalyFinding(
                anomaly_type="high_frequency",
                operator_id=operator_id,
                operator_role=operator_role or "unknown",
                detail=detail,
                ip_address=latest_ip,
                rule_id="AR-303",
                evidence={"op_count": int(op_count), "window_minutes": window_minutes},
            )
        )

    return findings


async def detect_off_hours(db: AsyncSession) -> list[AnomalyFinding]:
    """检测非工作时间访问.

    查询最近扫描间隔 (anomaly_scan_interval_seconds) 内、且发生在
    22:00~06:00 (UTC) 的管理员/咨询师操作。

    注: beat 默认 5 分钟一次扫描，所以查询窗口为最近 5 分钟。
    使用 group_by (而非 PostgreSQL 的 DISTINCT ON) 兼容 SQLite/PostgreSQL,
    每个用户取一条最近样本。
    """
    if not settings.anomaly_detection_enabled:
        return []

    start_hour = settings.anomaly_off_hours_start
    end_hour = settings.anomaly_off_hours_end
    # 扫描窗口 = beat 间隔 + 60s 缓冲，避免漏检
    scan_window = settings.anomaly_scan_interval_seconds + 60
    cutoff = _utcnow_naive() - timedelta(seconds=scan_window)

    # SQLite 使用 strftime 提取小时; PostgreSQL 使用 to_char
    # OperationLog.created_at 是 SQLite 默认 datetime 存储，使用 strftime 兼容
    # 22:00~06:00 = hour >= 22 OR hour < 6
    # 使用 group_by (兼容 SQLite/PostgreSQL), 每个用户取一条样本
    hour_expr = func.strftime("%H", OperationLog.created_at)
    stmt = (
        select(
            OperationLog.operator_id,
            OperationLog.operator_role,
            OperationLog.ip_address,
            OperationLog.action_type,
            OperationLog.target_type,
            OperationLog.created_at,
        )
        .where(
            and_(
                OperationLog.created_at >= cutoff,
                OperationLog.operator_id.isnot(None),
                OperationLog.operator_role.in_(["admin", "counselor"]),
                # hour >= 22 OR hour < 6 (字符串比较，零填充)
                or_(hour_expr >= f"{start_hour:02d}", hour_expr < f"{end_hour:02d}"),
            )
        )
        # 按 operator 分组, 取组内任意一条 (SQLite 不支持 DISTINCT ON)
        .group_by(OperationLog.operator_id, OperationLog.operator_role)
        .limit(MAX_FINDINGS_PER_SCAN)
    )
    rows = (await db.execute(stmt)).all()

    findings: list[AnomalyFinding] = []
    for (
        operator_id,
        operator_role,
        ip_address,
        action_type,
        target_type,
        created_at,
    ) in rows:
        detail = json.dumps(
            {
                "anomaly_type": "off_hours",
                "off_hours_window": f"{start_hour:02d}:00~{end_hour:02d}:00 UTC",
                "action_type": action_type,
                "target_type": target_type,
                "operator_role": operator_role,
                "occurred_at": created_at.isoformat() if created_at else None,
            },
            ensure_ascii=False,
        )

        findings.append(
            AnomalyFinding(
                anomaly_type="off_hours",
                operator_id=operator_id,
                operator_role=operator_role or "unknown",
                detail=detail,
                ip_address=ip_address,
                rule_id="AR-304",
                evidence={
                    "action_type": action_type,
                    "occurred_at": created_at.isoformat() if created_at else None,
                },
            )
        )

    return findings


async def detect_cross_region(db: AsyncSession) -> list[AnomalyFinding]:
    """检测异地访问 (基于 IP 数量).

    查询 N 小时内每个用户访问的不同 IP 数量，超过 threshold 的视为异常。
    返回的 ip_address 为该用户最新 IP。
    """
    if not settings.anomaly_detection_enabled:
        return []

    window_hours = settings.anomaly_cross_region_window_hours
    threshold = settings.anomaly_cross_region_ip_threshold
    cutoff = _utcnow_naive() - timedelta(hours=window_hours)

    # 按用户分组统计 distinct IP 数量
    stmt = (
        select(
            OperationLog.operator_id,
            OperationLog.operator_role,
            func.count(func.distinct(OperationLog.ip_address)).label("ip_count"),
        )
        .where(
            and_(
                OperationLog.created_at >= cutoff,
                OperationLog.operator_id.isnot(None),
                OperationLog.ip_address.isnot(None),
            )
        )
        .group_by(OperationLog.operator_id, OperationLog.operator_role)
        .having(func.count(func.distinct(OperationLog.ip_address)) > threshold)
        .limit(MAX_FINDINGS_PER_SCAN)
    )
    rows = (await db.execute(stmt)).all()

    findings: list[AnomalyFinding] = []
    for operator_id, operator_role, ip_count in rows:
        # 查询该用户使用的所有 IP (最多 10 个，供调查)
        ip_list_stmt = (
            select(OperationLog.ip_address)
            .where(
                and_(
                    OperationLog.operator_id == operator_id,
                    OperationLog.created_at >= cutoff,
                    OperationLog.ip_address.isnot(None),
                )
            )
            .distinct()
            .limit(10)
        )
        ip_list = list((await db.execute(ip_list_stmt)).scalars().all())

        # 查询最新 IP (取 cutoff 之后的最新一条)
        latest_stmt = (
            select(OperationLog.ip_address)
            .where(
                and_(
                    OperationLog.operator_id == operator_id,
                    OperationLog.created_at >= cutoff,
                )
            )
            .order_by(OperationLog.created_at.desc())
            .limit(1)
        )
        latest_ip = (await db.execute(latest_stmt)).scalar_one_or_none()

        detail = json.dumps(
            {
                "anomaly_type": "cross_region",
                "window_hours": window_hours,
                "ip_count": int(ip_count),
                "threshold": threshold,
                "ip_list": ip_list,
                "operator_role": operator_role,
            },
            ensure_ascii=False,
        )

        findings.append(
            AnomalyFinding(
                anomaly_type="cross_region",
                operator_id=operator_id,
                operator_role=operator_role or "unknown",
                detail=detail,
                ip_address=latest_ip,
                rule_id="AR-305",
                evidence={"ip_count": int(ip_count), "ip_list": ip_list},
            )
        )

    return findings


async def detect_lateral_access(db: AsyncSession) -> list[AnomalyFinding]:
    """检测横向越权访问.

    查询 N 分钟内每个用户访问的不同 target_type 数量，超过 threshold 的视为异常。
    阈值按 operator_role 区分 (咨询师正常工作涉及多 target_type)。
    """
    if not settings.anomaly_detection_enabled:
        return []

    window_minutes = settings.anomaly_lateral_window_minutes
    cutoff = _utcnow_naive() - timedelta(minutes=window_minutes)

    # 先查询所有 (operator_id, operator_role, target_type_count) 组合
    # 因为 having 子句的阈值因角色而异，无法在 SQL 中统一过滤
    stmt = (
        select(
            OperationLog.operator_id,
            OperationLog.operator_role,
            func.count(func.distinct(OperationLog.target_type)).label(
                "target_type_count"
            ),
        )
        .where(
            and_(
                OperationLog.created_at >= cutoff,
                OperationLog.operator_id.isnot(None),
                OperationLog.target_type.isnot(None),
            )
        )
        .group_by(OperationLog.operator_id, OperationLog.operator_role)
        .limit(MAX_FINDINGS_PER_SCAN * 2)  # 多取一些，因为还要在 Python 中过滤
    )
    rows = (await db.execute(stmt)).all()

    findings: list[AnomalyFinding] = []
    for operator_id, operator_role, target_type_count in rows:
        role = operator_role or "unknown"
        threshold = _get_lateral_threshold(role)
        if int(target_type_count) <= threshold:
            continue

        # 查询该用户访问的所有 target_type (供调查)
        target_types_stmt = (
            select(OperationLog.target_type)
            .where(
                and_(
                    OperationLog.operator_id == operator_id,
                    OperationLog.created_at >= cutoff,
                    OperationLog.target_type.isnot(None),
                )
            )
            .distinct()
            .limit(20)
        )
        target_types = list((await db.execute(target_types_stmt)).scalars().all())

        # 查询最新 IP
        latest_stmt = (
            select(OperationLog.ip_address)
            .where(
                and_(
                    OperationLog.operator_id == operator_id,
                    OperationLog.created_at >= cutoff,
                )
            )
            .order_by(OperationLog.created_at.desc())
            .limit(1)
        )
        latest_ip = (await db.execute(latest_stmt)).scalar_one_or_none()

        detail = json.dumps(
            {
                "anomaly_type": "lateral",
                "window_minutes": window_minutes,
                "target_type_count": int(target_type_count),
                "threshold": threshold,
                "target_types": target_types,
                "operator_role": role,
            },
            ensure_ascii=False,
        )

        findings.append(
            AnomalyFinding(
                anomaly_type="lateral",
                operator_id=operator_id,
                operator_role=role,
                detail=detail,
                ip_address=latest_ip,
                rule_id="AR-306",
                evidence={
                    "target_type_count": int(target_type_count),
                    "target_types": target_types,
                },
            )
        )

        if len(findings) >= MAX_FINDINGS_PER_SCAN:
            break

    return findings


async def detect_all(db: AsyncSession) -> list[AnomalyFinding]:
    """聚合执行所有检测器.

    检测顺序: high_frequency → off_hours → cross_region → lateral
    单次扫描最多返回 4 * MAX_FINDINGS_PER_SCAN 条 finding。

    Returns:
        所有检测器合并后的 finding 列表
    """
    if not settings.anomaly_detection_enabled:
        logger.debug("[anomaly] detection disabled, skip scan")
        return []

    all_findings: list[AnomalyFinding] = []

    # 高频访问检测
    try:
        findings = await detect_high_frequency(db)
        all_findings.extend(findings)
        if findings:
            logger.info("[anomaly] high_frequency detected %d anomalies", len(findings))
    except Exception as exc:
        logger.error(
            "[anomaly] high_frequency detection failed: %s", exc, exc_info=True
        )

    # 非工作时间检测
    try:
        findings = await detect_off_hours(db)
        all_findings.extend(findings)
        if findings:
            logger.info("[anomaly] off_hours detected %d anomalies", len(findings))
    except Exception as exc:
        logger.error("[anomaly] off_hours detection failed: %s", exc, exc_info=True)

    # 异地访问检测
    try:
        findings = await detect_cross_region(db)
        all_findings.extend(findings)
        if findings:
            logger.info("[anomaly] cross_region detected %d anomalies", len(findings))
    except Exception as exc:
        logger.error("[anomaly] cross_region detection failed: %s", exc, exc_info=True)

    # 横向越权检测
    try:
        findings = await detect_lateral_access(db)
        all_findings.extend(findings)
        if findings:
            logger.info("[anomaly] lateral detected %d anomalies", len(findings))
    except Exception as exc:
        logger.error("[anomaly] lateral detection failed: %s", exc, exc_info=True)

    return all_findings


__all__ = [
    "AnomalyFinding",
    "detect_high_frequency",
    "detect_off_hours",
    "detect_cross_region",
    "detect_lateral_access",
    "detect_all",
]
