from __future__ import annotations

from sqlalchemy import func, select

from app.core.contracts import normalize_risk_level, resolve_warning_status
from app.core.states import BindingStatus
from app.models.admin import OperationLog
from app.models.counselor import ConsultationRecord
from app.models.risk import WarningNotification
from app.models.user import UserCounselorBinding


class ConsultationMixin:
    """咨询记录管理相关方法 Mixin。

    包含:
    - `create_consultation_record`: 创建咨询记录 (含绑定校验、预警归属校验、审计日志)
    - `update_consultation_record`: 更新咨询记录 (含 warning_id 变更时的归属校验)
    - `list_consultation_records`: 列出咨询记录 (含预警状态/风险等级聚合展示)

    依赖主类 CounselorService 提供 `self.db`。
    """

    async def create_consultation_record(
        self, counselor_id: int, user_id: int, payload: dict
    ) -> int:
        binding_stmt = select(UserCounselorBinding).where(
            UserCounselorBinding.counselor_id == counselor_id,
            UserCounselorBinding.user_id == user_id,
            UserCounselorBinding.status == BindingStatus.ACTIVE,
        )
        binding = (await self.db.execute(binding_stmt)).scalar_one_or_none()
        if binding is None:
            raise ValueError("当前用户未绑定到该咨询师")

        warning_id = payload.get("warning_id")
        if warning_id is not None:
            warning = await self.db.get(WarningNotification, warning_id)
            if (
                warning is None
                or warning.user_id != user_id
                or warning.counselor_id != counselor_id
            ):
                raise ValueError("预警不存在或不属于当前咨询师用户关系")

        record = ConsultationRecord(
            counselor_id=counselor_id,
            user_id=user_id,
            warning_id=warning_id,
            main_topics=payload.get("main_topics"),
            client_status=payload.get("client_status"),
            interventions=payload.get("interventions"),
            next_plan=payload.get("next_plan"),
            notes=payload.get("notes"),
        )
        self.db.add(record)
        await self.db.flush()
        self.db.add(
            OperationLog(
                operator_id=counselor_id,
                operator_role="counselor",
                action_type="create_consultation_record",
                target_type="consultation_record",
                target_id=record.id,
                detail=f"user_id={user_id};warning_id={warning_id or '-'}",
            )
        )
        await self.db.commit()
        await self.db.refresh(record)
        return record.id

    async def update_consultation_record(
        self, counselor_id: int, user_id: int, record_id: int, payload: dict
    ) -> bool:
        record = await self.db.get(ConsultationRecord, record_id)
        if (
            record is None
            or record.counselor_id != counselor_id
            or record.user_id != user_id
        ):
            return False
        if "warning_id" in payload and payload.get("warning_id") != record.warning_id:
            warning_id = payload.get("warning_id")
            if warning_id is not None:
                warning = await self.db.get(WarningNotification, warning_id)
                if (
                    warning is None
                    or warning.user_id != record.user_id
                    or warning.counselor_id != counselor_id
                ):
                    raise ValueError("预警不存在或不属于当前咨询师用户关系")
            record.warning_id = warning_id
        for field in (
            "main_topics",
            "client_status",
            "interventions",
            "next_plan",
            "notes",
        ):
            if field in payload:
                setattr(record, field, payload[field])
        self.db.add(
            OperationLog(
                operator_id=counselor_id,
                operator_role="counselor",
                action_type="update_consultation_record",
                target_type="consultation_record",
                target_id=record.id,
                detail=f"user_id={record.user_id}",
            )
        )
        await self.db.commit()
        return True

    async def list_consultation_records(
        self, counselor_id: int, user_id: int, page: int, page_size: int
    ) -> dict:
        offset = (page - 1) * page_size
        stmt = (
            select(ConsultationRecord)
            .where(
                ConsultationRecord.counselor_id == counselor_id,
                ConsultationRecord.user_id == user_id,
            )
            .order_by(ConsultationRecord.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        count_stmt = (
            select(func.count())
            .select_from(ConsultationRecord)
            .where(
                ConsultationRecord.counselor_id == counselor_id,
                ConsultationRecord.user_id == user_id,
            )
        )
        total = (await self.db.execute(count_stmt)).scalar_one()

        warning_ids = [r.warning_id for r in rows if r.warning_id is not None]
        warning_map: dict[int, WarningNotification] = {}
        if warning_ids:
            warning_rows = (
                (
                    await self.db.execute(
                        select(WarningNotification).where(
                            WarningNotification.id.in_(warning_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )
            warning_map = {w.id: w for w in warning_rows}

        return {
            "items": [
                {
                    "id": r.id,
                    "warning_id": r.warning_id,
                    "warning_status": (
                        resolve_warning_status(
                            warning_map[r.warning_id].is_handled,
                            warning_map[r.warning_id].handle_action,
                        )
                        if r.warning_id in warning_map
                        else None
                    ),
                    "warning_risk_level": (
                        normalize_risk_level(warning_map[r.warning_id].current_level)
                        if r.warning_id in warning_map
                        else None
                    ),
                    "main_topics": r.main_topics,
                    "client_status": r.client_status,
                    "interventions": r.interventions,
                    "next_plan": r.next_plan,
                    "notes": r.notes,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
