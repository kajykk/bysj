from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.states import BindingStatus
from app.models.admin import OperationLog
from app.models.counselor import ClientGroup, ClientGroupMember
from app.models.user import UserCounselorBinding


class GroupMixin:
    """客户分组管理相关方法 Mixin。

    包含:
    - `create_group`: 创建客户分组 (含审计日志)
    - `list_groups`: 列出分组 (M13 修复：聚合查询消除 N+1)
    - `add_group_member`: 添加分组成员 (M9 修复：IDOR 防护，校验绑定关系)

    依赖主类 CounselorService 提供 `self.db`。
    """

    async def create_group(
        self,
        counselor_id: int,
        group_name: str,
        description: str | None,
        color_tag: str,
    ) -> int:
        group = ClientGroup(
            counselor_id=counselor_id,
            group_name=group_name,
            description=description,
            color_tag=color_tag,
        )
        self.db.add(group)
        await self.db.flush()
        self.db.add(
            OperationLog(
                operator_id=counselor_id,
                operator_role="counselor",
                action_type="create_client_group",
                target_type="client_group",
                target_id=group.id,
                detail=f"group_name={group_name}",
            )
        )
        await self.db.commit()
        await self.db.refresh(group)
        return group.id

    async def list_groups(self, counselor_id: int, page: int, page_size: int) -> dict:
        offset = (page - 1) * page_size
        stmt = (
            select(ClientGroup)
            .where(ClientGroup.counselor_id == counselor_id)
            .order_by(ClientGroup.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        total = (
            await self.db.execute(
                select(func.count())
                .select_from(ClientGroup)
                .where(ClientGroup.counselor_id == counselor_id)
            )
        ).scalar_one()

        # M13 修复：用一次聚合查询替代循环内逐条 COUNT，消除 N+1
        group_ids = [g.id for g in rows]
        count_map: dict[int, int] = {}
        if group_ids:
            count_rows = (
                await self.db.execute(
                    select(ClientGroupMember.group_id, func.count())
                    .where(ClientGroupMember.group_id.in_(group_ids))
                    .group_by(ClientGroupMember.group_id)
                )
            ).all()
            count_map = {row[0]: int(row[1]) for row in count_rows}

        return {
            "items": [
                {
                    "id": g.id,
                    "group_name": g.group_name,
                    "description": g.description,
                    "color_tag": g.color_tag,
                    "user_count": count_map.get(g.id, 0),
                }
                for g in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def add_group_member(
        self, counselor_id: int, group_id: int, user_id: int
    ) -> bool:
        group = await self.db.get(ClientGroup, group_id)
        if group is None or group.counselor_id != counselor_id:
            return False

        # M9 修复（IDOR）：校验被添加的用户是否与该咨询师有活跃绑定关系
        # 防止咨询师将任意用户 ID 添加到自己的分组
        binding_stmt = select(UserCounselorBinding).where(
            UserCounselorBinding.counselor_id == counselor_id,
            UserCounselorBinding.user_id == user_id,
            UserCounselorBinding.status == BindingStatus.ACTIVE,
        )
        binding = (await self.db.execute(binding_stmt)).scalar_one_or_none()
        if binding is None:
            # 用户未与该咨询师建立绑定关系，拒绝添加
            return False

        existing_stmt = select(ClientGroupMember).where(
            ClientGroupMember.group_id == group_id,
            ClientGroupMember.user_id == user_id,
        )
        existing = (await self.db.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            return True

        self.db.add(ClientGroupMember(group_id=group_id, user_id=user_id))
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            return True

        self.db.add(
            OperationLog(
                operator_id=counselor_id,
                operator_role="counselor",
                action_type="add_group_member",
                target_type="client_group_member",
                target_id=None,
                detail=f"group_id={group_id},user_id={user_id};status=added",
            )
        )
        await self.db.commit()
        return True
