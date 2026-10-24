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
from app.core.database import _is_sqlite
from app.core.degradation import record_silent_degradation
from app.core.contracts import (USER_ROLE_ADMIN, USER_ROLE_COUNSELOR)
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


async def _batch_latest_ips(
    db: AsyncSession,
    cutoff: datetime,
    operator_ids: list[int],
) -> dict[int, str | None]:
    """P1-24 修复：一次查询取多个 operator 各自的最新 IP。

    替代原「循环内逐人一条 `SELECT ip ... ORDER BY created_at DESC LIMIT 1`」：
    MAX_FINDINGS_PER_SCAN=100 时就是 100 次往返，且与上面的聚合查询同模式、
    同过滤条件，本可合并。写法沿用 detect_off_hours 既有的 window 函数方案
    （H-AUDIT-01：SQLite / PostgreSQL 双端兼容，不依赖松散 GROUP BY）。

    排序增加 `id DESC` 兜底：同一秒批量插入时 created_at 相同，原实现的
    `LIMIT 1` 取哪一条不确定，两次扫描可能给出不同 IP（违反幂等性原则）。
    """
    if not operator_ids:
        return {}

    inner = (
        select(
            OperationLog.operator_id,
            OperationLog.ip_address,
            func.row_number()
            .over(
                partition_by=OperationLog.operator_id,
                order_by=(OperationLog.created_at.desc(), OperationLog.id.desc()),
            )
            .label("_rn"),
        )
        .where(
            and_(
                OperationLog.created_at >= cutoff,
                OperationLog.operator_id.in_(operator_ids),
            )
        )
        .subquery()
    )
    stmt = select(inner.c.operator_id, inner.c.ip_address).where(inner.c._rn == 1)
    rows = (await db.execute(stmt)).all()
    return {operator_id: ip for operator_id, ip in rows}


async def _batch_distinct_values(
    db: AsyncSession,
    cutoff: datetime,
    operator_ids: list[int],
    column: Any,
    per_operator_limit: int,
) -> dict[int, list[Any]]:
    """P1-24 修复：一次查询取每个 operator 的去重 `column` 值（每人最多 K 个）。

    替代原「循环内逐人一条 `SELECT ... DISTINCT LIMIT K`」。两层 window：
    第一层按 (operator, value) 去重，第二层在 operator 内排名取前 K。
    与原实现一致不过滤 operator 之外的条件，仅把 N 次往返压成 1 次。

    排序按值本身：原 `.distinct()` 无 ORDER BY，取哪些值不确定；
    改为按值排序后结果确定（幂等），且调用方写入 JSON 前可稳定比对。
    """
    if not operator_ids:
        return {}

    # 第一层：按 (operator, value) 去重
    dedup = (
        select(
            OperationLog.operator_id,
            column.label("_value"),
            func.row_number()
            .over(
                partition_by=[OperationLog.operator_id, column],
                order_by=OperationLog.id.desc(),
            )
            .label("_dedup_rn"),
        )
        .where(
            and_(
                OperationLog.created_at >= cutoff,
                OperationLog.operator_id.in_(operator_ids),
                column.isnot(None),
            )
        )
        .subquery()
    )
    # 第二层：operator 内排名，取前 K
    ranked = (
        select(
            dedup.c.operator_id,
            dedup.c._value,
            func.row_number()
            .over(partition_by=dedup.c.operator_id, order_by=dedup.c._value)
            .label("_rank"),
        )
        .where(dedup.c._dedup_rn == 1)
        .subquery()
    )
    stmt = (
        select(ranked.c.operator_id, ranked.c._value).where(
            ranked.c._rank <= per_operator_limit
        )
    )

    result: dict[int, list[Any]] = {}
    for operator_id, value in (await db.execute(stmt)).all():
        result.setdefault(operator_id, []).append(value)
    return result


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

    # P1-24 修复：一次性取回全部 operator 的最新 IP，替代循环内逐人查询
    latest_ips = await _batch_latest_ips(
        db, cutoff, [row[0] for row in rows]
    )

    findings: list[AnomalyFinding] = []
    for operator_id, operator_role, op_count in rows:
        latest_ip = latest_ips.get(operator_id)

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

    # H-AUDIT-01: PostgreSQL 使用 to_char, SQLite 使用 strftime (与 monitoring.py 一致)
    # 此前无条件使用 strftime, 在 PostgreSQL 生产环境抛 "function strftime does not exist"
    if _is_sqlite:
        hour_expr = func.strftime("%H", OperationLog.created_at)
    else:
        hour_expr = func.to_char(OperationLog.created_at, "HH24")
    # H-AUDIT-01: 每用户取最近一条样本. 原实现依赖 SQLite 松散 GROUP BY
    # (SELECT 非分组列), PostgreSQL 严格模式直接报错. 改用 window 函数, 双端兼容.
    window_expr = (
        func.row_number()
        .over(
            partition_by=[OperationLog.operator_id, OperationLog.operator_role],
            order_by=(OperationLog.created_at.desc(), OperationLog.id.desc()),
        )
        .label("_rn")
    )
    inner = (
        select(
            OperationLog.operator_id,
            OperationLog.operator_role,
            OperationLog.ip_address,
            OperationLog.action_type,
            OperationLog.target_type,
            OperationLog.created_at,
            window_expr,
        )
        .where(
            and_(
                OperationLog.created_at >= cutoff,
                OperationLog.operator_id.isnot(None),
                OperationLog.operator_role.in_([USER_ROLE_ADMIN, USER_ROLE_COUNSELOR]),
                # hour >= 22 OR hour < 6 (字符串比较，零填充)
                or_(hour_expr >= f"{start_hour:02d}", hour_expr < f"{end_hour:02d}"),
            )
        )
        .subquery()
    )
    stmt = (
        select(
            inner.c.operator_id,
            inner.c.operator_role,
            inner.c.ip_address,
            inner.c.action_type,
            inner.c.target_type,
            inner.c.created_at,
        )
        .where(inner.c._rn == 1)
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

    # P1-24 修复：IP 清单与最新 IP 各一次批量查询，替代循环内逐人各一条
    operator_ids = [row[0] for row in rows]
    ip_lists = await _batch_distinct_values(
        db, cutoff, operator_ids, OperationLog.ip_address, 10
    )
    latest_ips = await _batch_latest_ips(db, cutoff, operator_ids)

    findings: list[AnomalyFinding] = []
    for operator_id, operator_role, ip_count in rows:
        # 该用户使用的 IP (最多 10 个，供调查)
        ip_list = ip_lists.get(operator_id, [])

        # 最新 IP (取 cutoff 之后的最新一条)
        latest_ip = latest_ips.get(operator_id)

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

    # P1-24 修复：先按角色阈值过滤出真正的 finding，再一次性批量取详情。
    # 原实现在过滤前就为每一行发 2 条查询，多数是白跑（阈值因角色而异，
    # 无法在 SQL 的 HAVING 里统一表达，只能 Python 侧过滤）。
    candidates: list[tuple[int, str, int]] = []
    for operator_id, operator_role, target_type_count in rows:
        role = operator_role or "unknown"
        threshold = _get_lateral_threshold(role)
        if int(target_type_count) <= threshold:
            continue
        candidates.append((operator_id, role, int(target_type_count)))

    operator_ids = [c[0] for c in candidates]
    target_type_lists = await _batch_distinct_values(
        db, cutoff, operator_ids, OperationLog.target_type, 20
    )
    latest_ips = await _batch_latest_ips(db, cutoff, operator_ids)

    findings: list[AnomalyFinding] = []
    for operator_id, role, target_type_count in candidates:
        # 该用户访问的所有 target_type (供调查)
        target_types = target_type_lists.get(operator_id, [])

        # 最新 IP
        latest_ip = latest_ips.get(operator_id)

        detail = json.dumps(
            {
                "anomaly_type": "lateral",
                "window_minutes": window_minutes,
                "target_type_count": target_type_count,
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
                    "target_type_count": target_type_count,
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
        # P2-35 第八批：该检测器失败 → 高频撞库/爬虫整类漏检，调用方只看到 findings
        # 变少（无异常与检测器宕机无法区分），必须计数。
        record_silent_degradation("services.anomaly_detection.high_frequency_detection_failed")

    # 非工作时间检测
    try:
        findings = await detect_off_hours(db)
        all_findings.extend(findings)
        if findings:
            logger.info("[anomaly] off_hours detected %d anomalies", len(findings))
    except Exception as exc:
        logger.error("[anomaly] off_hours detection failed: %s", exc, exc_info=True)
        # P2-35 第八批：非工作时间访问整类漏检（潜在数据外泄），必须计数。
        record_silent_degradation("services.anomaly_detection.off_hours_detection_failed")

    # 异地访问检测
    try:
        findings = await detect_cross_region(db)
        all_findings.extend(findings)
        if findings:
            logger.info("[anomaly] cross_region detected %d anomalies", len(findings))
    except Exception as exc:
        logger.error("[anomaly] cross_region detection failed: %s", exc, exc_info=True)
        # P2-35 第八批：异地访问整类漏检（账号被盗迹象），必须计数。
        record_silent_degradation("services.anomaly_detection.cross_region_detection_failed")

    # 横向越权检测
    try:
        findings = await detect_lateral_access(db)
        all_findings.extend(findings)
        if findings:
            logger.info("[anomaly] lateral detected %d anomalies", len(findings))
    except Exception as exc:
        logger.error("[anomaly] lateral detection failed: %s", exc, exc_info=True)
        # P2-35 第八批：横向越权整类漏检，必须计数。
        record_silent_degradation("services.anomaly_detection.lateral_detection_failed")

    return all_findings


__all__ = [
    "AnomalyFinding",
    "detect_high_frequency",
    "detect_off_hours",
    "detect_cross_region",
    "detect_lateral_access",
    "detect_all",
]
