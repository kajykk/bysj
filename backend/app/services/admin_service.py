from __future__ import annotations

import os
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import ModelFeedback, ModelRegistry, OperationLog, SystemConfig, WarningThreshold
from app.models.intervention import InterventionTemplate
from app.models.risk import RiskAssessment, WarningNotification
from app.models.user import User


class AdminService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_templates(self, page: int, page_size: int) -> dict:
        offset = (page - 1) * page_size
        stmt = select(InterventionTemplate).order_by(InterventionTemplate.id.desc()).offset(offset).limit(page_size)
        rows = (await self.db.execute(stmt)).scalars().all()
        total = (await self.db.execute(select(func.count()).select_from(InterventionTemplate))).scalar_one()
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

    async def upsert_template(self, payload: dict) -> int:
        template_id = payload.get("id")
        if template_id:
            template = await self.db.get(InterventionTemplate, template_id)
            if template is None:
                raise ValueError("模板不存在")
            for key in ["template_name", "applicable_levels", "task_list", "estimated_weeks", "status"]:
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
        await self.db.commit()
        await self.db.refresh(template)
        return template.id

    async def list_thresholds(self) -> list[dict]:
        rows = (await self.db.execute(select(WarningThreshold).order_by(WarningThreshold.level.asc()))).scalars().all()
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
        row = (await self.db.execute(select(WarningThreshold).where(WarningThreshold.level == payload["level"]))).scalar_one_or_none()
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
            for key in ["level_name", "min_score", "max_score", "color", "action_required"]:
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
        stmt = select(ModelFeedback).order_by(ModelFeedback.created_at.desc()).offset(offset).limit(page_size)
        rows = (await self.db.execute(stmt)).scalars().all()
        total = (await self.db.execute(select(func.count()).select_from(ModelFeedback))).scalar_one()
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
        rows = (await self.db.execute(select(SystemConfig).order_by(SystemConfig.config_key.asc()))).scalars().all()
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

    async def list_operation_logs(
        self,
        page: int,
        page_size: int,
        action_type: str | None = None,
        operator_role: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict:
        offset = (page - 1) * page_size
        stmt = select(OperationLog)
        count_stmt = select(func.count()).select_from(OperationLog)

        if action_type:
            stmt = stmt.where(OperationLog.action_type == action_type)
            count_stmt = count_stmt.where(OperationLog.action_type == action_type)
        if operator_role:
            stmt = stmt.where(OperationLog.operator_role == operator_role)
            count_stmt = count_stmt.where(OperationLog.operator_role == operator_role)
        if start_time:
            stmt = stmt.where(OperationLog.created_at >= start_time)
            count_stmt = count_stmt.where(OperationLog.created_at >= start_time)
        if end_time:
            stmt = stmt.where(OperationLog.created_at <= end_time)
            count_stmt = count_stmt.where(OperationLog.created_at <= end_time)

        stmt = stmt.order_by(OperationLog.created_at.desc(), OperationLog.id.desc()).offset(offset).limit(page_size)
        rows = (await self.db.execute(stmt)).scalars().all()
        total = (await self.db.execute(count_stmt)).scalar_one()
        return {
            "items": [
                {
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
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

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
        offset = (page - 1) * page_size
        stmt = select(OperationLog)
        count_stmt = select(func.count()).select_from(OperationLog)

        if action_types:
            stmt = stmt.where(OperationLog.action_type.in_(action_types))
            count_stmt = count_stmt.where(OperationLog.action_type.in_(action_types))
        if operator_role:
            stmt = stmt.where(OperationLog.operator_role == operator_role)
            count_stmt = count_stmt.where(OperationLog.operator_role == operator_role)
        if target_type:
            stmt = stmt.where(OperationLog.target_type == target_type)
            count_stmt = count_stmt.where(OperationLog.target_type == target_type)
        if start_time:
            stmt = stmt.where(OperationLog.created_at >= start_time)
            count_stmt = count_stmt.where(OperationLog.created_at >= start_time)
        if end_time:
            stmt = stmt.where(OperationLog.created_at <= end_time)
            count_stmt = count_stmt.where(OperationLog.created_at <= end_time)

        stmt = stmt.order_by(OperationLog.created_at.desc(), OperationLog.id.desc()).offset(offset).limit(page_size)
        rows = (await self.db.execute(stmt)).scalars().all()
        total = (await self.db.execute(count_stmt)).scalar_one()

        # 合规统计 - 按 action_type 聚合
        # M23 修复：将 action_types、operator_role、target_type 过滤条件同样应用到 breakdown_stmt
        breakdown_stmt = (
            select(OperationLog.action_type, func.count().label("cnt"))
            .group_by(OperationLog.action_type)
        )
        if action_types:
            breakdown_stmt = breakdown_stmt.where(OperationLog.action_type.in_(action_types))
        if operator_role:
            breakdown_stmt = breakdown_stmt.where(OperationLog.operator_role == operator_role)
        if target_type:
            breakdown_stmt = breakdown_stmt.where(OperationLog.target_type == target_type)
        if start_time:
            breakdown_stmt = breakdown_stmt.where(OperationLog.created_at >= start_time)
        if end_time:
            breakdown_stmt = breakdown_stmt.where(OperationLog.created_at <= end_time)
        breakdown_rows = (await self.db.execute(breakdown_stmt)).all()
        action_breakdown = {row[0]: int(row[1]) for row in breakdown_rows}

        # 最早/最晚日志时间 - 用于 retention 检查
        # M23 修复：将 action_types、operator_role、target_type 过滤条件同样应用到 range_stmt
        range_stmt = select(
            func.min(OperationLog.created_at).label("earliest"),
            func.max(OperationLog.created_at).label("latest"),
        )
        if action_types:
            range_stmt = range_stmt.where(OperationLog.action_type.in_(action_types))
        if operator_role:
            range_stmt = range_stmt.where(OperationLog.operator_role == operator_role)
        if target_type:
            range_stmt = range_stmt.where(OperationLog.target_type == target_type)
        if start_time:
            range_stmt = range_stmt.where(OperationLog.created_at >= start_time)
        if end_time:
            range_stmt = range_stmt.where(OperationLog.created_at <= end_time)
        earliest, latest = (await self.db.execute(range_stmt)).one()

        return {
            "items": [
                {
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
                for r in rows
            ],
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
        row = (await self.db.execute(select(SystemConfig).where(SystemConfig.config_key == payload["config_key"]))).scalar_one_or_none()
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
        total_users = (await self.db.execute(select(func.count()).select_from(User))).scalar_one()
        total_counselors = (await self.db.execute(select(func.count()).select_from(User).where(User.role == "counselor"))).scalar_one()
        today = datetime.now(UTC).date()
        today_start = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        today_warning_stmt = select(func.count()).select_from(WarningNotification).where(WarningNotification.created_at >= today_start)
        today_warnings = (await self.db.execute(today_warning_stmt)).scalar_one()
        today_unhandled_warnings = (await self.db.execute(
            select(func.count()).select_from(WarningNotification).where(
                WarningNotification.created_at >= today_start,
                WarningNotification.is_handled.is_(False),
            )
        )).scalar_one()
        total_assessments = (await self.db.execute(select(func.count()).select_from(RiskAssessment))).scalar_one()
        high_risk_users = (await self.db.execute(
            select(func.count()).select_from(RiskAssessment).where(RiskAssessment.risk_level >= 3)
        )).scalar_one()
        total_templates = (await self.db.execute(select(func.count()).select_from(InterventionTemplate))).scalar_one()
        active_templates = (await self.db.execute(
            select(func.count()).select_from(InterventionTemplate).where(InterventionTemplate.status == "active")
        )).scalar_one()
        return {
            "total_users": total_users,
            "total_counselors": total_counselors,
            "today_warnings": today_warnings,
            "today_unhandled_warnings": today_unhandled_warnings,
            "total_assessments": total_assessments,
            "high_risk_users": high_risk_users,
            "total_templates": total_templates,
            "active_templates": active_templates,
        }

    async def list_models(self, page: int, page_size: int) -> dict:
        offset = (page - 1) * page_size
        stmt = select(ModelRegistry).order_by(ModelRegistry.id.desc()).offset(offset).limit(page_size)
        rows = (await self.db.execute(stmt)).scalars().all()
        total = (await self.db.execute(select(func.count()).select_from(ModelRegistry))).scalar_one()
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
        await self.db.flush()
        await self.db.commit()
        return model.id

    async def update_model(self, model_id_int: int, payload: dict) -> None:
        model = await self.db.get(ModelRegistry, model_id_int)
        if model is None:
            raise ValueError("模型不存在")
        for key in ["model_name", "model_type", "file_path", "version", "status", "accuracy", "f1_score", "latency_ms"]:
            if key in payload:
                setattr(model, key, payload[key])
        await self.db.commit()

    async def activate_model(self, model_id_int: int) -> None:
        model = await self.db.get(ModelRegistry, model_id_int)
        if model is None:
            raise ValueError("模型不存在")
        model.status = "active"
        from datetime import UTC, datetime

        model.loaded_at = datetime.now(UTC)
        await self.db.commit()

    async def archive_old_logs(self, days: int = 90) -> int:
        from datetime import UTC, datetime, timedelta

        cutoff = datetime.now(UTC) - timedelta(days=days)
        # M15 修复：使用批量 DELETE 代替逐条删除，避免循环内 await self.db.delete(log)
        count_stmt = select(func.count()).select_from(OperationLog).where(OperationLog.created_at < cutoff)
        count = (await self.db.execute(count_stmt)).scalar_one()
        if count > 0:
            await self.db.execute(delete(OperationLog).where(OperationLog.created_at < cutoff))
            await self.db.commit()
        return count
