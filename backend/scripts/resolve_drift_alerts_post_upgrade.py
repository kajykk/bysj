"""T-P0-03: 模型升级后漂移告警根因治理脚本.

根因分析 (2026-07-25):
====================
3 条 CRITICAL DriftAlert (structured PSI=8.39 / text PSI=3.95 / fusion PSI=12.41)
是模型优化 v2.0 (S0-S4, 2026-07-23~25 完成) 后的误报:

- drift_monitoring_service 每 1h 执行一次, 比较基线窗口 (7 天前) 与当前窗口 (24h) 的
  RiskAssessment 评分分布
- 基线窗口 (~2026-07-18 ~ 2026-07-24) 包含旧模型预测
- 当前窗口 (~2026-07-24 ~ 2026-07-25) 包含 v2.0 优化后新模型预测
- 模型版本切换导致预测分布根本性变化 → PSI 极高 (>2.0)
- 这是跨模型版本比较, 不是真实数据漂移

治理措施:
========
1. 解决 3 条 CRITICAL 告警 (标记 resolved_at + 记录根因)
2. drift_monitoring_service 已增加 PSI>2.0 守卫:
   - severity 限制为 HIGH (不自动升级 CRITICAL)
   - details 标注 possible_model_version_mismatch=True
3. 后续 (T-P1+): 在 RiskAssessment 上增加 model_version 字段, 仅在同版本内比较

使用:
    cd backend
    python scripts/resolve_drift_alerts_post_upgrade.py            # 预演 (dry-run)
    python scripts/resolve_drift_alerts_post_upgrade.py --apply    # 实际执行
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

# 确保可以导入 app 模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.monitoring import DriftAlert  # noqa: E402

# 3 条已知 CRITICAL 告警的模态 (model_version 字段存的是模态名)
ALERTS_TO_RESOLVE_MODALITIES = ["structured", "text", "fusion"]

RESOLUTION_REASON = (
    "T-P0-03: 模型优化 v2.0 (S0-S4, 2026-07-23~25) 后的跨版本比较误报. "
    "基线窗口含旧模型预测, 当前窗口含 v2.0 新模型预测, 导致 PSI 极高. "
    "此为模型版本切换的预期分布变化, 非真实数据漂移. "
    "已为 drift_monitoring_service 增加 PSI>2.0 守卫防止再次误报."
)


async def list_unresolved_alerts(db) -> list[DriftAlert]:
    """列出所有未解决的 prediction_drift 告警."""
    stmt = (
        select(DriftAlert)
        .where(
            DriftAlert.drift_type == "prediction_drift",
            DriftAlert.resolved_at.is_(None),
        )
        .order_by(DriftAlert.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def resolve_alerts(apply: bool = False) -> None:
    """解决 3 条 CRITICAL 漂移告警."""
    print("=" * 70)
    print("T-P0-03: 模型升级后漂移告警根因治理")
    print("=" * 70)
    print()
    print("根因: 模型优化 v2.0 后基线窗口(旧模型)与当前窗口(新模型)跨版本比较")
    print("治理: 解决 3 条 CRITICAL 告警 + 已增加 PSI>2.0 守卫")
    print()

    async with AsyncSessionLocal() as db:
        # 1. 列出当前未解决告警
        unresolved = await list_unresolved_alerts(db)
        print(f"当前未解决 prediction_drift 告警数: {len(unresolved)}")
        for alert in unresolved:
            print(
                f"  - id={alert.id} modality={alert.model_version} "
                f"feature={alert.feature_name} PSI={alert.metric_value} "
                f"severity={alert.severity} created_at={alert.created_at}"
            )
        print()

        if not unresolved:
            print("[INFO] 无未解决告警, 无需治理.")
            return

        # 2. 筛选目标模态的告警
        target_alerts = [
            a for a in unresolved
            if a.model_version in ALERTS_TO_RESOLVE_MODALITIES
        ]
        print(
            f"目标模态 {ALERTS_TO_RESOLVE_MODALITIES} 匹配告警数: "
            f"{len(target_alerts)}"
        )

        if not target_alerts:
            print("[INFO] 无匹配告警, 无需治理.")
            return

        # 3. 解决告警
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for alert in target_alerts:
            alert.resolved_at = now
            details = dict(alert.details) if alert.details else {}
            details["resolution_reason"] = RESOLUTION_REASON
            details["resolved_by"] = (
                "scripts/resolve_drift_alerts_post_upgrade.py (T-P0-03)"
            )
            details["resolved_at_utc"] = now.isoformat()
            alert.details = details
            print(
                f"[{'APPLY' if apply else 'DRY-RUN'}] 解决 id={alert.id} "
                f"modality={alert.model_version} PSI={alert.metric_value}"
            )

        # 4. 提交 (仅 apply 模式)
        if apply:
            await db.commit()
            print()
            print(f"[OK] 已提交, 共解决 {len(target_alerts)} 条告警")
        else:
            await db.rollback()
            print()
            print(f"[DRY-RUN] 预演完成, 预计解决 {len(target_alerts)} 条告警")
            print("[DRY-RUN] 加 --apply 参数实际执行")

    # 5. 验证 (新 session)
    print()
    print("验证: 重新查询未解决告警")
    async with AsyncSessionLocal() as db:
        remaining = await list_unresolved_alerts(db)
    print(f"剩余未解决 prediction_drift 告警数: {len(remaining)}")
    for alert in remaining:
        print(
            f"  - id={alert.id} modality={alert.model_version} "
            f"PSI={alert.metric_value} severity={alert.severity}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="T-P0-03: 解决模型升级后的漂移告警误报"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际执行 (默认 dry-run)",
    )
    args = parser.parse_args()
    asyncio.run(resolve_alerts(apply=args.apply))
