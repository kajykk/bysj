from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import (
    ModelFeedback,
    ModelRegistry,
    OperationLog,
    SystemConfig,
    WarningThreshold,
)
from app.models.intervention import InterventionTemplate
from app.models.risk import RiskAssessment, WarningNotification
from app.models.user import User

logger = logging.getLogger(__name__)

# ISS-078: 配置 key 白名单，仅允许以下 key 通过 upsert_config 写入
_ALLOWED_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "risk_threshold_low",
        "risk_threshold_medium",
        "risk_threshold_high",
        "max_export_rows",
        "session_timeout",
        "token_expiry",
        "notification_email_enabled",
        "notification_sms_enabled",
        "notification_webhook_url",
        "password_min_length",
        "password_require_special",
        "rate_limit_per_minute",
    }
)


class AdminService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_templates(self, page: int, page_size: int) -> dict:
        offset = (page - 1) * page_size
        stmt = (
            select(InterventionTemplate)
            .order_by(InterventionTemplate.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        total = (
            await self.db.execute(
                select(func.count()).select_from(InterventionTemplate)
            )
        ).scalar_one()
        return {
            "items": [
                {
                    "id": r.id,
                    "template_name": r.template_name,
                    "applicable_levels": r.applicable_levels,
                    "task_list": r.task_list,
                    "estimated_weeks": r.estimated_weeks,
                    "status": r.status,
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def upsert_template(
        self, payload: dict, admin_id: int | None = None, operator_role: str = "admin"
    ) -> int:
        template_id = payload.get("id")
        is_update = bool(template_id)
        if template_id:
            template = await self.db.get(InterventionTemplate, template_id)
            if template is None:
                raise ValueError("模板不存在")
            for key in [
                "template_name",
                "applicable_levels",
                "task_list",
                "estimated_weeks",
                "status",
            ]:
                if key in payload:
                    setattr(template, key, payload[key])
            await self.db.flush()
        else:
            template = InterventionTemplate(
                template_name=payload["template_name"],
                applicable_levels=payload.get("applicable_levels", []),
                task_list=payload.get("task_list", []),
                estimated_weeks=payload.get("estimated_weeks"),
                status=payload.get("status", "active"),
            )
            self.db.add(template)
            await self.db.flush()
        # ISS-076: 写入 OperationLog 审计日志
        if admin_id is not None:
            self.db.add(
                OperationLog(
                    operator_id=admin_id,
                    operator_role=operator_role,
                    action_type="admin.template.upsert",
                    target_type="template",
                    target_id=template.id,
                    detail=json.dumps(
                        {
                            "operator_id": admin_id,
                            "action": "update" if is_update else "create",
                            "template_name": template.template_name,
                            "status": template.status,
                        },
                        ensure_ascii=False,
                    )[:5000],
                )
            )
        await self.db.commit()
        await self.db.refresh(template)
        return template.id

    async def delete_template(
        self, template_id: int, admin_id: int, operator_role: str = "admin"
    ) -> None:
        """ISS-075: 硬删除干预模板并写入审计日志."""
        template = await self.db.get(InterventionTemplate, template_id)
        if template is None:
            raise ValueError("模板不存在")
        template_name = template.template_name
        await self.db.delete(template)
        self.db.add(
            OperationLog(
                operator_id=admin_id,
                operator_role=operator_role,
                action_type="admin.template.delete",
                target_type="template",
                target_id=template_id,
                detail=json.dumps(
                    {"operator_id": admin_id, "template_name": template_name},
                    ensure_ascii=False,
                )[:5000],
            )
        )
        await self.db.commit()

    async def list_thresholds(self) -> list[dict]:
        rows = (
            (
                await self.db.execute(
                    select(WarningThreshold).order_by(WarningThreshold.level.asc())
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": r.id,
                "level": r.level,
                "level_name": r.level_name,
                "min_score": r.min_score,
                "max_score": r.max_score,
                "color": r.color,
                "action_required": r.action_required,
            }
            for r in rows
        ]

    async def upsert_threshold(
        self,
        admin_id: int,
        payload: dict,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> int:
        row = (
            await self.db.execute(
                select(WarningThreshold).where(
                    WarningThreshold.level == payload["level"]
                )
            )
        ).scalar_one_or_none()
        from sqlalchemy.exc import IntegrityError as SAIntegrityError

        try:
            if row is None:
                # 使用显式字段构造而非 **payload 直接解包
                row = WarningThreshold(
                    level=payload["level"],
                    level_name=payload["level_name"],
                    min_score=payload["min_score"],
                    max_score=payload["max_score"],
                    color=payload["color"],
                    action_required=payload["action_required"],
                )
                self.db.add(row)
                await self.db.flush()
            else:
                for key in [
                    "level_name",
                    "min_score",
                    "max_score",
                    "color",
                    "action_required",
                ]:
                    if key in payload:
                        setattr(row, key, payload[key])
                await self.db.flush()
        except SAIntegrityError:
            # H-03 修复：并发 upsert 竞态，回滚后重试为 update
            await self.db.rollback()
            row = (
                await self.db.execute(
                    select(WarningThreshold).where(
                        WarningThreshold.level == payload["level"]
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise
            for key in [
                "level_name",
                "min_score",
                "max_score",
                "color",
                "action_required",
            ]:
                if key in payload:
                    setattr(row, key, payload[key])
            await self.db.flush()
        self.db.add(
            OperationLog(
                operator_id=admin_id,
                operator_role="admin",
                action_type="upsert_warning_threshold",
                target_type="warning_threshold",
                target_id=row.id,
                detail=f"level={row.level};request_id={request_id or '-'}",
                ip_address=ip_address,
            )
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row.id

    async def list_feedbacks(self, page: int, page_size: int) -> dict:
        offset = (page - 1) * page_size
        stmt = (
            select(ModelFeedback)
            .order_by(ModelFeedback.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        total = (
            await self.db.execute(select(func.count()).select_from(ModelFeedback))
        ).scalar_one()
        return {
            "items": [
                {
                    "id": r.id,
                    "counselor_id": r.counselor_id,
                    "user_id": r.user_id,
                    "assessment_id": r.assessment_id,
                    "agreed": r.agreed,
                    "reason": r.reason,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def list_configs(self) -> list[dict]:
        rows = (
            (
                await self.db.execute(
                    select(SystemConfig).order_by(SystemConfig.config_key.asc())
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": r.id,
                "config_key": r.config_key,
                "config_value": r.config_value,
                "description": r.description,
                "updated_by": r.updated_by,
            }
            for r in rows
        ]

    @staticmethod
    def _apply_log_filters(stmt, filters: dict):
        """L-Svc-7 修复：将公共过滤条件应用到任意日志查询语句。

        支持的 filters 键：action_types(list)、operator_role、target_type、start_time、end_time。
        """
        action_types = filters.get("action_types")
        if action_types:
            stmt = stmt.where(OperationLog.action_type.in_(action_types))
        if filters.get("operator_role"):
            stmt = stmt.where(OperationLog.operator_role == filters["operator_role"])
        if filters.get("target_type"):
            stmt = stmt.where(OperationLog.target_type == filters["target_type"])
        if filters.get("start_time"):
            stmt = stmt.where(OperationLog.created_at >= filters["start_time"])
        if filters.get("end_time"):
            stmt = stmt.where(OperationLog.created_at <= filters["end_time"])
        return stmt

    async def _query_logs(
        self, filters: dict, page: int, page_size: int
    ) -> tuple[list[OperationLog], int]:
        """L-Svc-7 修复：抽取 list_operation_logs/list_audit_logs 公共的过滤+分页+计数逻辑。"""
        offset = (page - 1) * page_size
        stmt = self._apply_log_filters(select(OperationLog), filters)
        count_stmt = self._apply_log_filters(
            select(func.count()).select_from(OperationLog), filters
        )
        stmt = (
            stmt.order_by(OperationLog.created_at.desc(), OperationLog.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        total = (await self.db.execute(count_stmt)).scalar_one()
        return rows, total

    @staticmethod
    def _log_item(r: OperationLog) -> dict:
        """L-Svc-7 修复：抽取日志条目序列化，供 list_operation_logs/list_audit_logs 复用。"""
        return {
            "id": r.id,
            "operator_id": r.operator_id,
            "operator_role": r.operator_role,
            "action_type": r.action_type,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "detail": r.detail,
            "ip_address": r.ip_address,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

    async def list_operation_logs(
        self,
        page: int,
        page_size: int,
        action_type: str | None = None,
        operator_role: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict:
        # L-Svc-7 修复：抽取公共过滤/分页逻辑至 _query_logs，避免与 list_audit_logs 重复
        filters = {
            "action_types": [action_type] if action_type else None,
            "operator_role": operator_role,
            "target_type": None,
            "start_time": start_time,
            "end_time": end_time,
        }
        rows, total = await self._query_logs(filters, page, page_size)
        return {
            "items": [self._log_item(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def export_operation_logs(
        self,
        action_type: str | None = None,
        operator_role: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict]:
        """ISS-080: 导出全部筛选条件下的操作日志（不分页），供前端生成 CSV."""
        filters = {
            "action_types": [action_type] if action_type else None,
            "operator_role": operator_role,
            "target_type": None,
            "start_time": start_time,
            "end_time": end_time,
        }
        stmt = self._apply_log_filters(select(OperationLog), filters)
        stmt = stmt.order_by(OperationLog.created_at.desc(), OperationLog.id.desc())
        rows = (await self.db.execute(stmt)).scalars().all()
        return [self._log_item(r) for r in rows]

    async def list_audit_logs(
        self,
        page: int,
        page_size: int,
        action_types: list[str] | None = None,
        operator_role: str | None = None,
        target_type: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict:
        """v1.32: 合规审计日志查询.

        与 list_operation_logs 的差异:
        - 接受多 action_type 过滤 (合规审计需要批量类型)
        - 额外 target_type 过滤
        - 返回合规统计 (按 action_type 分组)
        - 包含 retention 信息

        适合合规审计员做 GDPR/等保 2.0 审查。
        """
        # L-Svc-7 修复：抽取公共过滤/分页逻辑至 _query_logs / _apply_log_filters
        filters = {
            "action_types": action_types,
            "operator_role": operator_role,
            "target_type": target_type,
            "start_time": start_time,
            "end_time": end_time,
        }
        rows, total = await self._query_logs(filters, page, page_size)

        # 合规统计 - 按 action_type 聚合
        breakdown_stmt = self._apply_log_filters(
            select(OperationLog.action_type, func.count().label("cnt")).group_by(
                OperationLog.action_type
            ),
            filters,
        )
        breakdown_rows = (await self.db.execute(breakdown_stmt)).all()
        action_breakdown = {row[0]: int(row[1]) for row in breakdown_rows}

        # 最早/最晚日志时间 - 用于 retention 检查
        range_stmt = self._apply_log_filters(
            select(
                func.min(OperationLog.created_at).label("earliest"),
                func.max(OperationLog.created_at).label("latest"),
            ),
            filters,
        )
        earliest, latest = (await self.db.execute(range_stmt)).one()

        return {
            "items": [self._log_item(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "compliance": {
                "action_breakdown": action_breakdown,
                "earliest_log": earliest.isoformat() if earliest else None,
                "latest_log": latest.isoformat() if latest else None,
                "retention_days": 90,  # 与 archive_logs 保持一致
            },
        }

    async def upsert_config(self, admin_id: int, payload: dict) -> int:
        # ISS-078: 配置 key 白名单校验，防止任意 key 写入
        key = payload["config_key"]
        if key not in _ALLOWED_CONFIG_KEYS:
            raise ValueError(f"不支持的配置键: {key}（仅允许白名单内的配置项）")
        row = (
            await self.db.execute(
                select(SystemConfig).where(SystemConfig.config_key == key)
            )
        ).scalar_one_or_none()
        from sqlalchemy.exc import IntegrityError as SAIntegrityError

        try:
            if row is None:
                row = SystemConfig(
                    config_key=payload["config_key"],
                    config_value=payload["config_value"],
                    description=payload.get("description"),
                    updated_by=admin_id,
                )
                self.db.add(row)
            else:
                row.config_value = payload["config_value"]
                row.description = payload.get("description")
                row.updated_by = admin_id

            await self.db.flush()
        except SAIntegrityError:
            # H-03 修复：并发 upsert 竞态，回滚后重试为 update
            await self.db.rollback()
            row = (
                await self.db.execute(
                    select(SystemConfig).where(
                        SystemConfig.config_key == payload["config_key"]
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise
            row.config_value = payload["config_value"]
            row.description = payload.get("description")
            row.updated_by = admin_id
            await self.db.flush()
        self.db.add(
            OperationLog(
                operator_id=admin_id,
                operator_role="admin",
                action_type="upsert_system_config",
                target_type="system_config",
                target_id=row.id,
                detail=f"config_key={row.config_key}",
            )
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row.id

    async def get_stats(self) -> dict:
        total_users = (
            await self.db.execute(select(func.count()).select_from(User))
        ).scalar_one()
        total_counselors = (
            await self.db.execute(
                select(func.count()).select_from(User).where(User.role == "counselor")
            )
        ).scalar_one()
        # H-Svc-2 修复：DateTime 列为 naive，统一生成 naive UTC datetime 进行比较，避免 aware/naive 混用抛 TypeError
        today = datetime.now(UTC).replace(tzinfo=None).date()
        today_start = datetime.combine(today, datetime.min.time())
        # H-9 修复：补充 yesterday_* 字段，供前端 AdminDashboard 计算环比趋势。
        # yesterday_start 为昨日 00:00 UTC，用于计算昨日增量与累计快照。
        yesterday_start = datetime.combine(
            today - timedelta(days=1), datetime.min.time()
        )
        today_warning_stmt = (
            select(func.count())
            .select_from(WarningNotification)
            .where(WarningNotification.created_at >= today_start)
        )
        today_warnings = (await self.db.execute(today_warning_stmt)).scalar_one()
        today_unhandled_warnings = (
            await self.db.execute(
                select(func.count())
                .select_from(WarningNotification)
                .where(
                    WarningNotification.created_at >= today_start,
                    WarningNotification.is_handled.is_(False),
                )
            )
        ).scalar_one()
        total_assessments = (
            await self.db.execute(select(func.count()).select_from(RiskAssessment))
        ).scalar_one()
        # H-15 修复：high_risk_users 应统计高风险用户数（DISTINCT user_id），而非评估记录数
        high_risk_users = (
            await self.db.execute(
                select(func.count(func.distinct(RiskAssessment.user_id))).where(
                    RiskAssessment.risk_level >= 3
                )
            )
        ).scalar_one()
        total_templates = (
            await self.db.execute(
                select(func.count()).select_from(InterventionTemplate)
            )
        ).scalar_one()
        active_templates = (
            await self.db.execute(
                select(func.count())
                .select_from(InterventionTemplate)
                .where(InterventionTemplate.status == "active")
            )
        ).scalar_one()
        # H-9 修复：计算 yesterday_* 快照
        # yesterday_users / yesterday_assessments：截至昨日结束的累计值（created_at < today_start）
        # yesterday_warnings：昨日单日增量（yesterday_start <= created_at < today_start）
        # yesterday_templates：截至昨日结束的活跃模板数（无状态变更历史，以 created_at 近似）
        yesterday_users = (
            await self.db.execute(
                select(func.count())
                .select_from(User)
                .where(User.created_at < today_start)
            )
        ).scalar_one()
        yesterday_warnings = (
            await self.db.execute(
                select(func.count())
                .select_from(WarningNotification)
                .where(
                    WarningNotification.created_at >= yesterday_start,
                    WarningNotification.created_at < today_start,
                )
            )
        ).scalar_one()
        yesterday_assessments = (
            await self.db.execute(
                select(func.count())
                .select_from(RiskAssessment)
                .where(RiskAssessment.created_at < today_start)
            )
        ).scalar_one()
        yesterday_templates = (
            await self.db.execute(
                select(func.count())
                .select_from(InterventionTemplate)
                .where(
                    InterventionTemplate.status == "active",
                    InterventionTemplate.created_at < today_start,
                )
            )
        ).scalar_one()
        return {
            "total_users": total_users,
            "total_counselors": total_counselors,
            "today_warnings": today_warnings,
            "today_unhandled_warnings": today_unhandled_warnings,
            "total_assessments": total_assessments,
            "high_risk_users": high_risk_users,
            "total_templates": total_templates,
            "active_templates": active_templates,
            "yesterday_users": yesterday_users,
            "yesterday_warnings": yesterday_warnings,
            "yesterday_assessments": yesterday_assessments,
            "yesterday_templates": yesterday_templates,
        }

    async def list_models(self, page: int, page_size: int) -> dict:
        offset = (page - 1) * page_size
        stmt = (
            select(ModelRegistry)
            .order_by(ModelRegistry.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        total = (
            await self.db.execute(select(func.count()).select_from(ModelRegistry))
        ).scalar_one()
        return {
            "items": [
                {
                    "id": r.id,
                    "model_id": r.model_id,
                    "model_name": r.model_name,
                    "model_type": r.model_type,
                    "file_name": os.path.basename(r.file_path) if r.file_path else None,
                    "version": r.version,
                    "status": r.status,
                    "accuracy": r.accuracy,
                    "f1_score": r.f1_score,
                    "latency_ms": r.latency_ms,
                    "loaded_at": r.loaded_at.isoformat() if r.loaded_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def register_model(self, payload: dict) -> int:
        # 使用显式字段构造而非 **payload 直接解包
        model = ModelRegistry(
            model_id=payload["model_id"],
            model_name=payload.get("model_name", payload["model_id"]),
            model_type=payload.get("model_type", "unknown"),
            file_path=payload.get("file_path", ""),
            version=payload.get("version", "1.0.0"),
            status=payload.get("status", "inactive"),
            accuracy=payload.get("accuracy"),
            f1_score=payload.get("f1_score"),
            latency_ms=payload.get("latency_ms"),
        )
        self.db.add(model)
        from sqlalchemy.exc import IntegrityError as SAIntegrityError

        try:
            await self.db.flush()
        except SAIntegrityError:
            # H-Svc-17 修复：model_id 重复时 flush 抛 IntegrityError，回滚后抛业务异常。
            # 避免 commit() 在 PendingRollback 状态下抛 PendingRollbackError 掩盖原始错误。
            await self.db.rollback()
            raise ValueError("Model ID already exists")
        await self.db.commit()
        return model.id

    async def update_model(self, model_id_int: int, payload: dict) -> None:
        model = await self.db.get(ModelRegistry, model_id_int)
        if model is None:
            raise ValueError("模型不存在")
        for key in [
            "model_name",
            "model_type",
            "file_path",
            "version",
            "status",
            "accuracy",
            "f1_score",
            "latency_ms",
        ]:
            if key in payload:
                setattr(model, key, payload[key])
        await self.db.commit()

    async def activate_model(self, model_id_int: int) -> None:
        model = await self.db.get(ModelRegistry, model_id_int)
        if model is None:
            raise ValueError("模型不存在")
        model.status = "active"
        from datetime import UTC, datetime

        model.loaded_at = datetime.now(UTC).replace(tzinfo=None)
        await self.db.commit()

    async def archive_old_logs(self, days: int = 90) -> int:
        from datetime import UTC, datetime, timedelta

        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
        # C-04 修复：使用 DELETE 语句的 rowcount 替代 COUNT 结果，避免 COUNT 与实际删除行数不一致
        result = await self.db.execute(
            delete(OperationLog).where(OperationLog.created_at < cutoff)
        )
        await self.db.commit()
        # M-Svc-17 修复：rowcount 语义在 SQLite 与 PostgreSQL 间存在差异
        # （PostgreSQL 返回实际删除行数；SQLite 的 aiosqlite 驱动可能返回 -1 或 0
        # 表示无法确定）。此处返回值仅作日志参考，不保证精确等于实际删除行数。
        deleted = result.rowcount or 0
        logger.info(
            "archive_old_logs: rowcount=%d (dialect-dependent, may be -1/0 on SQLite), "
            "cutoff=%s, days=%d",
            deleted,
            cutoff.isoformat(),
            days,
        )
        return deleted
