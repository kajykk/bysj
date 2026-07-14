from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.models.admin import OperationLog
from app.models.intervention import InterventionTemplate

if TYPE_CHECKING:
    pass


class TemplateMixin:
    """干预模板管理相关方法 Mixin。

    包含干预模板的列表查询、创建/更新 (upsert)、硬删除逻辑，
    并在变更时写入 OperationLog 审计日志。

    依赖主类 AdminService 提供 `self.db`。
    """

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
                    ),
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
                ),
            )
        )
        await self.db.commit()
