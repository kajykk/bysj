from __future__ import annotations

import secrets
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.states import BindingStatus
from app.models.admin import OperationLog
from app.models.user import User, UserCounselorBinding


class BindingMixin:
    """用户-咨询师绑定与绑定码管理相关方法 Mixin。

    包含:
    - `_generate_bind_code` (staticmethod): 生成绑定码 (L-Svc-2 熵增强修复)
    - `_generate_unique_bind_code`: 生成唯一绑定码 (循环去重)
    - `get_or_create_bind_code`: 幂等获取/创建绑定码
    - `refresh_bind_code`: 强制作废旧码并生成新码 (M7 修复)
    - `bind_by_code`: 通过绑定码绑定用户 (C-Svc-3 FOR UPDATE 修复、H-01 用户锁、M21 placeholder 修复)
    - `get_user_binding`: 查询用户当前绑定
    - `unbind`: 用户解绑当前咨询师

    依赖主类 CounselorService 提供 `self.db`。
    """

    async def _generate_unique_bind_code(self) -> str:
        code = self._generate_bind_code()
        for _ in range(20):
            dup_stmt = select(UserCounselorBinding).where(
                UserCounselorBinding.bind_code == code
            )
            if not (await self.db.execute(dup_stmt)).scalar_one_or_none():
                return code
            code = self._generate_bind_code()
        raise ValueError("绑定码生成失败，请稍后重试")

    async def get_or_create_bind_code(self, counselor_id: int) -> str:
        stmt = (
            select(UserCounselorBinding)
            .where(
                UserCounselorBinding.counselor_id == counselor_id,
                UserCounselorBinding.user_id == counselor_id,
                UserCounselorBinding.status == BindingStatus.PLACEHOLDER,
            )
            .order_by(UserCounselorBinding.id.desc())
        )
        existing = (await self.db.execute(stmt)).scalars().first()
        if existing and existing.bind_code:
            return existing.bind_code

        code = await self._generate_unique_bind_code()

        if not existing:
            binding = UserCounselorBinding(
                counselor_id=counselor_id,
                user_id=counselor_id,
                bind_code=code,
                status=BindingStatus.PLACEHOLDER,
            )
            if hasattr(binding, "bound_at"):
                binding.bound_at = None
            if hasattr(binding, "unbound_at"):
                binding.unbound_at = None
            self.db.add(binding)
            self.db.add(
                OperationLog(
                    operator_id=counselor_id,
                    operator_role="counselor",
                    action_type="create_bind_code",
                    target_type="user_counselor_binding",
                    target_id=None,
                    detail=f"status=placeholder;bind_code={code}",
                )
            )
        else:
            existing.bind_code = code
            if existing.status not in {BindingStatus.ACTIVE, BindingStatus.PLACEHOLDER}:
                existing.status = BindingStatus.PLACEHOLDER
            self.db.add(
                OperationLog(
                    operator_id=counselor_id,
                    operator_role="counselor",
                    action_type="refresh_bind_code",
                    target_type="user_counselor_binding",
                    target_id=existing.id,
                    detail=f"status={existing.status};bind_code={code}",
                )
            )
        await self.db.commit()
        return code

    async def refresh_bind_code(self, counselor_id: int) -> str:
        """M7 修复：真正刷新绑定码 - 作废当前 bind_code 并生成新码.

        与 get_or_create_bind_code 的区别:
        - get_or_create: 幂等，若已有 bind_code 则直接返回
        - refresh: 强制作废当前 bind_code，生成新码并持久化
        """
        stmt = (
            select(UserCounselorBinding)
            .where(
                UserCounselorBinding.counselor_id == counselor_id,
                UserCounselorBinding.user_id == counselor_id,
                UserCounselorBinding.status == BindingStatus.PLACEHOLDER,
            )
            .order_by(UserCounselorBinding.id.desc())
        )
        existing = (await self.db.execute(stmt)).scalars().first()

        # 生成新码（_generate_unique_bind_code 会确保唯一性）
        new_code = await self._generate_unique_bind_code()

        if existing is None:
            # 无占位绑定，创建新的
            binding = UserCounselorBinding(
                counselor_id=counselor_id,
                user_id=counselor_id,
                bind_code=new_code,
                status=BindingStatus.PLACEHOLDER,
            )
            if hasattr(binding, "bound_at"):
                binding.bound_at = None
            if hasattr(binding, "unbound_at"):
                binding.unbound_at = None
            self.db.add(binding)
            self.db.add(
                OperationLog(
                    operator_id=counselor_id,
                    operator_role="counselor",
                    action_type="create_bind_code",
                    target_type="user_counselor_binding",
                    target_id=None,
                    detail=f"status=placeholder;bind_code={new_code};trigger=refresh",
                )
            )
        else:
            # 作废旧码：将旧 bind_code 标记为失效（设为 None 防止重复使用）
            old_code = existing.bind_code
            existing.bind_code = new_code
            if existing.status not in {BindingStatus.ACTIVE, BindingStatus.PLACEHOLDER}:
                existing.status = BindingStatus.PLACEHOLDER
            self.db.add(
                OperationLog(
                    operator_id=counselor_id,
                    operator_role="counselor",
                    action_type="refresh_bind_code",
                    target_type="user_counselor_binding",
                    target_id=existing.id,
                    detail=f"old_bind_code={old_code};new_bind_code={new_code};status={existing.status}",
                )
            )
        await self.db.commit()
        return new_code

    @staticmethod
    def _generate_bind_code() -> str:
        # L-Svc-2 修复：原 token_urlsafe(6)[:8] 仅约 48 bits 熵，抗穷举强度不足。
        # 增加输入字节数与输出长度至 bind_code CHECK 约束上限（10 字符），提升熵。
        return secrets.token_urlsafe(10)[:10].upper()

    async def bind_by_code(self, user_id: int, bind_code: str) -> dict:
        # C-Svc-3 修复：bind_code SELECT 加 with_for_update()，避免 TOCTOU 竞态。
        # 原实现仅锁定 user 行，未锁定 binding 行；当 bind_code 被并发使用时
        # （如同一咨询师给多个用户发放相同绑定码、或绑定码泄露后被并发消费），
        # 两个事务都能通过 binding.status IN (ACTIVE, PLACEHOLDER) 校验，
        # 都进入更新分支，造成绑定码被重复消费、placeholder 被多次激活等问题。
        # 加 FOR UPDATE 后，并发请求会串行化在 binding 行锁上；先获取锁的事务
        # 提交后，后获取锁的事务会读到最新 status，WHERE 子句中
        # status IN (ACTIVE, PLACEHOLDER) 不再匹配（已变为 INACTIVE），
        # scalar_one_or_none() 返回 None，触发“绑定码无效或已过期”错误。
        stmt = (
            select(UserCounselorBinding)
            .where(
                UserCounselorBinding.bind_code == bind_code,
                UserCounselorBinding.status.in_(
                    [BindingStatus.ACTIVE, BindingStatus.PLACEHOLDER]
                ),
            )
            .with_for_update()
        )
        binding = (await self.db.execute(stmt)).scalar_one_or_none()
        if binding is None:
            raise ValueError("绑定码无效或已过期")
        counselor_id = binding.counselor_id

        # H-01 修复：锁定用户行防止并发绑定（TOCTOU 竞态）
        user_lock = select(User).where(User.id == user_id).with_for_update()
        await self.db.execute(user_lock)

        active_stmt = (
            select(UserCounselorBinding)
            .where(
                UserCounselorBinding.user_id == user_id,
                UserCounselorBinding.status == BindingStatus.ACTIVE,
                UserCounselorBinding.counselor_id != user_id,
            )
            .order_by(UserCounselorBinding.bound_at.desc())
            .limit(1)
        )
        active_binding = (await self.db.execute(active_stmt)).scalars().first()
        if active_binding:
            if active_binding.counselor_id == counselor_id:
                raise ValueError("您已绑定该咨询师，无需重复绑定")
            raise ValueError("您已绑定其他咨询师，请先解绑后再绑定新咨询师")

        counselor = await self.db.get(User, counselor_id)
        if (
            not counselor
            or counselor.role != "counselor"
            or counselor.status != "active"
        ):
            raise ValueError("绑定的咨询师不存在或已停用")

        previous_status = binding.status
        if binding.status == BindingStatus.PLACEHOLDER:
            # M21 修复：修改 placeholder 的 user_id 可能违反 UniqueConstraint("user_id", "counselor_id")。
            # 先查询是否存在该 (user_id, counselor_id) 的历史 binding，若有则激活它而非修改 placeholder。
            existing_stmt = select(UserCounselorBinding).where(
                UserCounselorBinding.user_id == user_id,
                UserCounselorBinding.counselor_id == counselor_id,
            )
            existing_binding = (
                await self.db.execute(existing_stmt)
            ).scalar_one_or_none()
            if existing_binding is not None and existing_binding.id != binding.id:
                # 已存在历史 binding，激活它并将 placeholder 标记为已使用
                existing_binding.status = BindingStatus.ACTIVE
                existing_binding.bound_at = datetime.now(UTC).replace(tzinfo=None)
                if hasattr(existing_binding, "unbound_at"):
                    existing_binding.unbound_at = None
                # C-02 修复：bind_code 为 NOT NULL 且有 CHECK 约束(4-10 字符)，不能设为 None
                binding.bind_code = self._generate_bind_code()
                binding.status = BindingStatus.INACTIVE
                await self.db.flush()
                new_binding = existing_binding
            else:
                binding.user_id = user_id
                binding.status = BindingStatus.ACTIVE
                binding.bound_at = datetime.now(UTC).replace(tzinfo=None)
                if hasattr(binding, "unbound_at"):
                    binding.unbound_at = None
                await self.db.flush()
                new_binding = binding
        else:
            # 原 binding 已是 ACTIVE 状态：生成新占位码防止重复使用
            # C-02 修复：bind_code 为 NOT NULL 且有 CHECK 约束，不能设为 None
            binding.bind_code = self._generate_bind_code()
            new_binding = UserCounselorBinding(
                user_id=user_id,
                counselor_id=counselor_id,
                bind_code=self._generate_bind_code(),  # ACTIVE 绑定也需满足 NOT NULL 约束
                status=BindingStatus.ACTIVE,
            )
            self.db.add(new_binding)
            await self.db.flush()

        self.db.add(
            OperationLog(
                operator_id=user_id,
                operator_role="user",
                action_type="bind_counselor",
                target_type="user_counselor_binding",
                target_id=new_binding.id,
                detail=f"counselor_id={counselor_id};bind_code={bind_code};from_status={previous_status};to_status=active",
            )
        )
        await self.db.commit()
        await self.db.refresh(new_binding)

        counselor_profile_stmt = select(User).where(User.id == counselor_id)
        counselor_user = (
            await self.db.execute(counselor_profile_stmt)
        ).scalar_one_or_none()

        return {
            "binding_id": new_binding.id,
            "counselor_id": counselor_id,
            "counselor_name": (
                counselor_user.username if counselor_user else f"咨询师#{counselor_id}"
            ),
            "status": (
                new_binding.status.value
                if hasattr(new_binding.status, "value")
                else new_binding.status
            ),
            "bind_code_status": (
                new_binding.status.value
                if hasattr(new_binding.status, "value")
                else new_binding.status
            ),
            "bound_at": new_binding.bound_at.isoformat(),
        }

    async def get_user_binding(self, user_id: int) -> dict | None:
        stmt = (
            select(UserCounselorBinding)
            .where(
                UserCounselorBinding.user_id == user_id,
                UserCounselorBinding.status == BindingStatus.ACTIVE,
                UserCounselorBinding.counselor_id != user_id,
            )
            .order_by(UserCounselorBinding.bound_at.desc())
            .limit(1)
        )
        binding = (await self.db.execute(stmt)).scalars().first()
        if not binding:
            return None

        counselor = await self.db.get(User, binding.counselor_id)
        status_value = (
            binding.status.value if hasattr(binding.status, "value") else binding.status
        )
        return {
            "binding_id": binding.id,
            "counselor_id": binding.counselor_id,
            "counselor_name": (
                counselor.username if counselor else f"咨询师#{binding.counselor_id}"
            ),
            "bound_at": binding.bound_at.isoformat() if binding.bound_at else None,
            "status": status_value,
            "bind_code_status": status_value,
        }

    async def unbind(self, user_id: int) -> bool:
        stmt = (
            select(UserCounselorBinding)
            .where(
                UserCounselorBinding.user_id == user_id,
                UserCounselorBinding.status == BindingStatus.ACTIVE,
                UserCounselorBinding.counselor_id != user_id,
            )
            .order_by(UserCounselorBinding.bound_at.desc())
            .limit(1)
        )
        binding = (await self.db.execute(stmt)).scalars().first()
        if not binding:
            return False

        binding.status = BindingStatus.INACTIVE
        binding.unbound_at = datetime.now(UTC).replace(tzinfo=None)
        self.db.add(
            OperationLog(
                operator_id=user_id,
                operator_role="user",
                action_type="unbind_counselor",
                target_type="user_counselor_binding",
                target_id=binding.id,
                detail=f"counselor_id={binding.counselor_id};to_status=inactive",
            )
        )
        await self.db.commit()
        return True
