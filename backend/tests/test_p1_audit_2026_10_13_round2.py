"""AUDIT-2026-10-13 P1 第三轮闸门：#16 / #19 / #21。

- #16 ``add_group_member`` 重复 insert 只回滚 savepoint，不回滚调用方整个事务。
  闸门守「同事务里其它待提交改动**仍然存活**」，这是改前唯一会丢的东西。
- #19 ``pytorch_mlp`` 检查点在 ``weights_only=True`` 下仍可加载。
  **本条是「实测推翻报告」后的锁定闸门**：报告称「生产 100% 不可用」，实测
  torch 2.11 下 weights_only=True 加载正常。故不改动实现，只加闸门 —— 一旦
  将来有人往检查点里塞非 primitive 元信息（如自定义类/模块对象），
  weights_only=True 会加载失败，CI 立刻红。
- #21 审计日志 ``operator_role`` 不得硬编码：服务层必填、调用方如实传。
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.admin import OperationLog
from app.models.counselor import ClientGroup, ClientGroupMember
from app.models.user import User, UserCounselorBinding
from app.core.states import BindingStatus
from app.services.counselor_service_group import GroupMixin


# ── #16：savepoint 而非全事务回滚 ────────────────────────────────────────


class _GroupServiceHost(GroupMixin):
    """把 GroupMixin 单独挂出来，避开 CounselorService 的完整依赖。"""

    def __init__(self, db) -> None:  # noqa: ANN001
        self.db = db


@pytest.mark.asyncio
class TestAddGroupMemberUsesSavepoint:
    """P1-16：并发重复 insert 时不得回滚调用方事务里的其它改动。"""

    async def test_duplicate_insert_preserves_earlier_pending_change(self, db_session):
        """改前 ``await self.db.rollback()`` 会把整事务回滚 → 先前 flush 的行丢失。"""
        # 造一条「调用方在此之前已 flush 的待提交改动」：新建分组
        group = ClientGroup(counselor_id=1, group_name="pending-group")
        db_session.add(group)
        await db_session.flush()
        preexisting_group_id = group.id

        db_session.add(
            UserCounselorBinding(
                counselor_id=1,
                user_id=1,
                status=BindingStatus.ACTIVE,
                bind_code="BIND1",
            )
        )
        await db_session.flush()

        service = _GroupServiceHost(db_session)

        # 强制让成员 insert 触发 IntegrityError（模拟并发重复插入）
        calls = {"n": 0}
        original_flush = db_session.flush

        async def _flush_then_fail(*args, **kwargs):  # noqa: ANN002, ANN003
            calls["n"] += 1
            if calls["n"] == 1:
                raise IntegrityError("INSERT INTO client_group_members", {}, Exception("UNIQUE constraint failed"))
            return await original_flush(*args, **kwargs)

        db_session.flush = _flush_then_fail  # type: ignore[method-assign]
        try:
            result = await service.add_group_member(1, preexisting_group_id, 1)
        finally:
            db_session.flush = original_flush  # type: ignore[method-assign]

        assert result is True, "唯一键冲突应按幂等成功处理"

        await db_session.commit()

        # 关键断言：调用方先前 flush 的分组**仍然存在**
        survived = (
            await db_session.execute(
                select(ClientGroup).where(ClientGroup.id == preexisting_group_id)
            )
        ).scalar_one_or_none()
        assert survived is not None, (
            "重复 insert 回滚了整个事务，导致调用方先前 flush 的改动丢失 "
            "（应只回滚到 savepoint）"
        )

    async def test_successful_insert_still_adds_member_and_audit(self, db_session):
        """正常路径不回归：成员写入 + 审计日志都落库。"""
        group = ClientGroup(counselor_id=1, group_name="ok-group")
        db_session.add(group)
        await db_session.flush()

        # 绑定关系（add_group_member 要求活跃绑定）
        db_session.add(
            UserCounselorBinding(
                counselor_id=1,
                user_id=1,
                status=BindingStatus.ACTIVE,
                bind_code="BIND2",
            )
        )
        await db_session.flush()

        service = _GroupServiceHost(db_session)
        assert await service.add_group_member(1, group.id, 1) is True
        await db_session.commit()

        member = (
            await db_session.execute(
                select(ClientGroupMember).where(ClientGroupMember.group_id == group.id)
            )
        ).scalar_one_or_none()
        assert member is not None

        audit = (
            await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "add_group_member"
                )
            )
        ).scalar_one_or_none()
        assert audit is not None


# ── #19：检查点在 weights_only=True 下必须仍可加载 ───────────────────────


class TestPytorchCheckpointLoadsUnderWeightsOnly:
    """P1-19 锁定闸门：报告称「生产 100% 不可用」，实测不成立，故此闸门防回归。

    生产环境 ``safe_torch_load`` 会把 ``weights_only`` 强制为 True（ISS-046）。
    只要检查点里只有 primitive 类型（int/float/bool/list）+ state_dict，
    torch 的 weights_only 反序列化器就能加载。若将来有人往检查点塞自定义对象，
    本闸门会红 —— 那正是需要改成 JSON 侧车的信号。
    """

    def test_checkpoint_loads_with_weights_only_true(self, tmp_path):
        torch = pytest.importorskip("torch", reason="PyTorch 未安装")

        from app.ml.pytorch_mlp import PyTorchMLP

        model = PyTorchMLP(
            input_dim=8, hidden_dims=[16, 8], dropout_rate=0.1, use_batch_norm=True
        )
        ckpt = tmp_path / "m.pt"
        model.save(ckpt)

        raw = torch.load(ckpt, map_location="cpu", weights_only=True)
        assert raw["input_dim"] == 8
        assert raw["hidden_dims"] == [16, 8]

        # 完整 load() 路径也必须在生产语义（weights_only 被强制 True）下可用
        reloaded = PyTorchMLP.load(ckpt, trusted_root=tmp_path)
        assert reloaded.input_dim == 8


# ── #21：审计日志 operator_role 不得硬编码 ───────────────────────────────


class TestAuditOperatorRoleIsNotHardcoded:
    """P1-21：操作者角色必须如实记录（super_admin 不能被记成 admin）。"""

    def test_write_crisis_audit_log_requires_operator_role(self):
        """必填关键字参数：漏传直接 TypeError，不给静默兜底。"""
        import inspect

        from app.services.review_service import CrisisEventService

        sig = inspect.signature(CrisisEventService._write_crisis_audit_log)
        param = sig.parameters["operator_role"]
        assert param.kind is inspect.Parameter.KEYWORD_ONLY
        assert param.default is inspect.Parameter.empty

    def test_upsert_config_requires_admin_role(self):
        import inspect

        from app.services.admin_service_config import ConfigMixin

        param = inspect.signature(ConfigMixin.upsert_config).parameters["admin_role"]
        assert param.default is inspect.Parameter.empty

    def test_upsert_threshold_requires_admin_role(self):
        import inspect

        from app.services.admin_service_threshold import ThresholdMixin

        param = inspect.signature(ThresholdMixin.upsert_threshold).parameters[
            "admin_role"
        ]
        assert param.default is inspect.Parameter.empty

    def test_no_hardcoded_admin_role_left_in_api_layer(self):
        """全仓 API 层不得再出现 ``operator_role="admin"`` 字面量。

        这条是**源码扫描**闸门，用于兜住「新增端点时又抄了一遍硬编码」。
        它守的是字面量而非行为，故与上面的签名闸门互为补充。
        """
        from pathlib import Path

        api_root = Path(__file__).resolve().parents[1] / "app" / "api"
        offenders = []
        for py in api_root.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            if 'operator_role="admin"' in text:
                offenders.append(str(py.relative_to(api_root)))
        assert not offenders, f"API 层仍有硬编码 operator_role: {offenders}"

    async def test_crisis_audit_log_records_actual_role(self, db_session):
        """咨询师处置危机 → 审计角色必须是 counselor，不是 admin。"""
        from app.models.review import CrisisEvent
        from app.services.review_service import CrisisEventService

        event = CrisisEvent(
            user_id=1,
            status="detected",
            trigger_source="text",
            crisis_score=80.0,
        )
        db_session.add(event)
        await db_session.flush()

        service = CrisisEventService(db_session)
        await service._write_crisis_audit_log(
            operator_id=1,
            action_type="crisis_event_handle",
            event_id=event.id,
            detail={"action": "notify_counselor"},
            operator_role="counselor",
        )
        await db_session.commit()

        log = (
            await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "crisis_event_handle"
                )
            )
        ).scalar_one_or_none()
        assert log is not None
        assert log.operator_role == "counselor"
