"""跨租户隔离回归测试（AUDIT-2026-10-08 P1-3/ P1-4 / P1-5）。

覆盖本轮修复的三处**数据泄露**性质缺陷：

======  ==========================  ==========================================
编号    位置                          原缺陷
======  ==========================  ==========================================
P1-3    ``review.list_assignable_   裸 ``select(User)``，无 tenant_id 过滤 →
        counselors``                  跨租户咨询师名单泄露（含姓名/手机号 PII）
P1-4    ``CrisisEventService.        裸 ``select(CrisisEvent)``，无租户过滤 →
        get_crisis_events``           跨租户危机事件泄露（input_summary /
                                       crisis_keywords，最高敏感级）
P1-5    ``uploads.serve_upload``    counselor 角色可读**任意**用户私有文件，
                                       既不校验 tenant 也不校验咨询绑定
======  ==========================  ==========================================

为什么这三处值得单独成文件：
1. 都是「跨租户/跨主体看到不属于你的数据」，属数据泄露而非正确性缺陷；
2. 三处的修法**不共用同一个工具函数** —— ``User`` 表有 ``tenant_id`` 列可直接用
   ``tenant_scoped_query``；``CrisisEvent`` 表**没有** ``tenant_id`` 列，必须
   JOIN ``User`` 并改用 ``tenant_scoped_filter``；``uploads`` 走的是绑定关系
   （``UserCounselorBinding``）而非租户列。统一抽象会掩盖这个结构差异。

**回退验证**：``git stash`` 掉生产代码后本文件应大量失败（见各类 docstring
内嵌的预期），恢复后全绿。断言针对**行为**（跨租户不可见）而非源码字面，
因此不与具体实现写法耦合。
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.states import BindingStatus
from app.models.user import User, UserCounselorBinding
from app.schemas.review import CrisisEventCreate, CrisisEventFilter
from app.services.review_service import CrisisEventService


@pytest.fixture
def two_tenants(db_session):
    """构造两个租户、三个用户、一条咨询绑定（跨租户用户无绑定）。

    租户布局：
    - tenant 1: user id=1（受测用户）、counselor id=2
    - tenant 2: user id=100（他租户用户）
    -绑定：counselor 2 —— user 1（tenant 1 内，合法）

    异步 fixture：db_session 绑定的 async session 只能在事件循环内await，
    用同步 ``asyncio.run`` 会撞 "cannot be called from a running event loop"。
    """
    from app.core.pii_crypto import compute_blind_index
    from app.core.security import get_password_hash

    pwd = get_password_hash("testpass123")

    def _mk(uid: int, username: str, role: str, tenant: int) -> User:
        email = f"{username}@test.com"
        return User(
            id=uid,
            username=username,
            email=email,
            email_hash=compute_blind_index(email, "email"),
            password_hash=pwd,
            role=role,
            status="active",
            tenant_id=tenant,
        )

    async def _seed():
        db_session.add_all(
            [
                _mk(1, "t1_student", "user", 1),
                _mk(2, "t1_counselor", "counselor", 1),
                _mk(3, "t1_admin", "admin", 1),
                _mk(100, "t2_student", "user", 2),
            ]
        )
        await db_session.flush()
        db_session.add(
            UserCounselorBinding(
                user_id=1,
                counselor_id=2,
                bind_code="BIND001",
                status=BindingStatus.ACTIVE,
            )
        )
        await db_session.commit()

    return run(_seed())


def run(coro):
    """同步跑完协程（仅供同步 fixture 使用；异步测试请直接 await）。"""
    import asyncio

    return asyncio.run(coro)


@pytest.fixture
def run_async():
    """把协程同步跑完 —— 与 conftest.run 同语义，供同步测试函数使用。"""
    import asyncio

    return asyncio.run


# ---------------------------------------------------------------------------
# P1-3：可分配咨询师名单的租户隔离
# ---------------------------------------------------------------------------


class TestAssignableCounselorsTenantIsolation:
    """``GET /reviews/assignable-counselors`` 的租户隔离。

    原实现是裸 ``select(User)``。租户 A 的管理员能拿到租户 B 全部在岗咨询师的
    姓名 / 手机号（``UserBrief`` 含 PII），且列表受 ``_MAX_ASSIGNABLE_COUNSELORS``
    截断 —— 跨租户数据还会挤占本租户的候选名额。

    ⚠ 断言直接**调用端点函数本身**（而非在测试里复刻一遍查询构造）：
    早期版本写成「测试内自己调``tenant_scoped_query`` 验证 SQL 含tenant_id」，
    结果在改前代码上也全绿 —— 它验证的是工具函数，不是被修的端点，属假绿。
    端点一旦退回裸 ``select``，下面的调用就会把他租户咨询师返回出来。
    """

    @staticmethod
    async def _call_endpoint(db_session, current_user):
        from app.api.v1.review import list_assignable_counselors

        return await list_assignable_counselors(
            request=None,
            current_user=current_user,
            db=db_session,
        )

    async def test_other_tenant_counselor_not_listed(self, db_session, two_tenants):
        """跨租户隔离的行为断言：租户 1 管理员看不到租户 2 的咨询师。

        改前该查询无 tenant_id 条件 → 两个租户的咨询师都会被返回。
        """
        from app.core.pii_crypto import compute_blind_index
        from app.core.security import get_password_hash

        pwd = get_password_hash("testpass123")
        email = "t2_counselor@test.com"
        db_session.add(
            User(
                id=200,
                username="t2_counselor",
                email=email,
                email_hash=compute_blind_index(email, "email"),
                password_hash=pwd,
                role="counselor",
                status="active",
                tenant_id=2,
            )
        )
        await db_session.commit()

        admin_t1 = (await db_session.execute(select(User).where(User.id == 3))).scalar_one()

        result = await self._call_endpoint(db_session, admin_t1)
        ids = [item["id"] for item in result["data"]["items"]]

        assert 200 not in ids, "租户 1 的咨询师名单泄露了租户 2 的咨询师"

    async def test_own_tenant_counselor_still_listed(self, db_session, two_tenants):
        """本租户咨询师必须仍可见 —— 防止把过滤写过头（过度收紧同样是缺陷）。"""
        admin_t1 = (await db_session.execute(select(User).where(User.id == 3))).scalar_one()

        result = await self._call_endpoint(db_session, admin_t1)
        ids = [item["id"] for item in result["data"]["items"]]
        assert 2 in ids, "本租户咨询师被误过滤（过度收紧）"

    async def test_non_admin_rejected(self, db_session, two_tenants):
        """非管理员仍返回 403 —— 本轮改动不应放宽角色校验。"""
        from fastapi import HTTPException

        student = (await db_session.execute(select(User).where(User.id == 1))).scalar_one()

        with pytest.raises(HTTPException) as exc:
            await self._call_endpoint(db_session, student)
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# P1-4：危机事件的租户隔离（需JOIN User）
# ---------------------------------------------------------------------------


class TestCrisisEventsTenantIsolation:
    """``CrisisEventService.get_crisis_events`` 的租户隔离。

    ``crisis_events`` 表**本身没有 tenant_id 列**，租户归属只能沿 ``user_id``
    关联 ``users.tenant_id`` 推导 —— 这是本轮与 P1-3 最大的结构差异。
    """

    async def test_other_tenant_events_hidden(self, db_session, two_tenants):
        """租户 1 管理员查询时，不应看到租户 2 用户的危机事件。

        改前无任何租户过滤 → ``total`` 会包含他租户记录。
        """
        service = CrisisEventService(db_session)

        # 本租户（tenant 1, user 1）
        await service.record_crisis_event(
            CrisisEventCreate(
                user_id=1,
                trigger_source="text",
                crisis_keywords=["本租户"],
                crisis_score=0.5,
                input_summary="tenant1 summary",
            )
        )
        # 他租户（tenant 2, user 100）
        await service.record_crisis_event(
            CrisisEventCreate(
                user_id=100,
                trigger_source="text",
                crisis_keywords=["他租户"],
                crisis_score=0.9,
                input_summary="tenant2 summary",
            )
        )

        result_t1 = await service.get_crisis_events(CrisisEventFilter(), tenant_id=1)
        assert result_t1["total"] == 1, "租户 1 查询结果混入了他租户危机事件"
        assert result_t1["items"][0]["user_id"] == 1
        assert "本租户" in result_t1["items"][0]["crisis_keywords"]
        assert "他租户" not in str(result_t1), "泄露了他租户的 crisis_keywords"

        result_t2 = await service.get_crisis_events(CrisisEventFilter(), tenant_id=2)
        assert result_t2["total"] == 1
        assert result_t2["items"][0]["user_id"] == 100

    async def test_tenant_id_is_required(self, db_session, two_tenants):
        """``tenant_id`` 是**必填** —— 漏传必须 TypeError，而不是静默返回全量。

        这是本处的刻意设计：危机数据敏感度最高，宁可让调用方编译不过，
        也不接受「忘记传租户 → 默认租户 1 → 静默返回」。
        """
        import inspect

        service = CrisisEventService(db_session)
        sig = inspect.signature(service.get_crisis_events)
        assert "tenant_id" in sig.parameters
        assert sig.parameters["tenant_id"].default is inspect.Parameter.empty, (
            "tenant_id 必须必填；给默认值等于给跨租户读取留后门"
        )

        with pytest.raises(TypeError):
            await service.get_crisis_events(CrisisEventFilter())

    async def test_filters_still_apply_under_tenant_scope(self, db_session, two_tenants):
        """加租户 JOIN 后既有的状态过滤仍生效（防止 JOIN 改写破坏过滤语义）。"""
        service = CrisisEventService(db_session)
        await service.record_crisis_event(
            CrisisEventCreate(user_id=1, trigger_source="text", crisis_keywords=["kw"], crisis_score=0.5)
        )
        await service.record_crisis_event(
            CrisisEventCreate(
                user_id=100,
                trigger_source="text",
                crisis_keywords=["kw"],
                crisis_score=0.5,
            )
        )

        # 状态过滤：不存在状态 → 空
        empty = await service.get_crisis_events(CrisisEventFilter(status="nonexistent"), tenant_id=1)
        assert empty["total"] == 0

        # 分页：page_size=1 → 本租户恰好 1 条，total 不受分页影响
        paged = await service.get_crisis_events(CrisisEventFilter(page=1, page_size=1), tenant_id=1)
        assert paged["total"] == 1
        assert len(paged["items"]) == 1

    async def test_count_matches_tenant_scope(self, db_session, two_tenants):
        """``count_query`` 走 ``query.subquery()`` —— JOIN 后 total 不得虚高。"""
        service = CrisisEventService(db_session)
        for uid in (1, 100, 100):
            await service.record_crisis_event(
                CrisisEventCreate(
                    user_id=uid,
                    trigger_source="text",
                    crisis_keywords=["kw"],
                    crisis_score=0.5,
                )
            )
        # 租户 1 只有 user 1 的1 条；其余 2 条属租户 2
        r = await service.get_crisis_events(CrisisEventFilter(), tenant_id=1)
        assert r["total"] == 1
        r2 = await service.get_crisis_events(CrisisEventFilter(), tenant_id=2)
        assert r2["total"] == 2


# ---------------------------------------------------------------------------
# P1-5：counselor 文件访问的绑定校验
# ---------------------------------------------------------------------------


class TestCounselorFileAccessBinding:
    """``GET /uploads/{user_id}/{filename}`` 对 counselor 的绑定校验。

    文件名是 UUID（不可猜），但 **user_id 是连续整数**（极易枚举）——
    这正是「角色白名单」式鉴权在此处不成立的原因。
    """

    @staticmethod
    def _make_uploads(tmp_path, monkeypatch):
        """构造 uploads 目录：user 1 有私有文件。

        REV-2026-10-20：这里必须用 ``monkeypatch.setattr``，不能裸赋值。
        裸赋值会永久改写 ``app.api.v1.uploads._resolve_upload_dir``，
        污染后续测试（本轮回溯时 ``test_rev_s3`` 因此在全量运行下 404，
        单独运行却全绿）。
        """
        from app.api.v1 import uploads as uploads_mod

        upload_dir = tmp_path / "uploads"
        user_dir = upload_dir / "1"
        user_dir.mkdir(parents=True)
        (user_dir / "assessment.mp3").write_bytes(b"private-audio")
        monkeypatch.setattr(uploads_mod, "_resolve_upload_dir", lambda: upload_dir)
        return upload_dir

    @staticmethod
    def _fake_request():
        """最小 request 替身。

        ``serve_upload`` 内的限流器会调 ``get_real_client_ip(request)``，
        它直接读 ``request.client.host`` —— 传 ``None`` 会在到达本轮断言前
        就 AttributeError。这里只提供被读取的属性，不做过度构造。
        """

        class _Client:
            host = "127.0.0.1"

        class _Req:
            client = _Client()

        return _Req()

    @pytest.mark.anyio
    async def test_bound_counselor_allowed(self, db_session, two_tenants, tmp_path, monkeypatch):
        """已建立 active 绑定的咨询师**可以**访问该用户文件（防止把门关死）。"""
        from app.api.v1 import uploads as uploads_mod
        from app.core.contracts import USER_ROLE_COUNSELOR

        self._make_uploads(tmp_path, monkeypatch)
        monkeypatch.setattr(uploads_mod, "_resolve_upload_dir", lambda: tmp_path / "uploads")

        # 绑定确实存在于 fixture 中（counselor 2 <-> user 1, active）
        binding = (
            await db_session.execute(
                select(UserCounselorBinding).where(
                    UserCounselorBinding.counselor_id == 2,
                    UserCounselorBinding.user_id == 1,
                    UserCounselorBinding.status == BindingStatus.ACTIVE,
                )
            )
        ).scalar_one_or_none()
        assert binding is not None, "fixture 前提失效：绑定未建成"

        counselor = (await db_session.execute(select(User).where(User.id == 2))).scalar_one()
        assert counselor.role == USER_ROLE_COUNSELOR

        resp = await uploads_mod.serve_upload(
            request=self._fake_request(),
            owner="1",
            filename="assessment.mp3",
            current_user=counselor,
            db=db_session,
        )
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_unbound_counselor_denied(self, db_session, two_tenants, tmp_path, monkeypatch):
        """**未**绑定的咨询师访问用户文件 → 404（不暴露存在性）。

        改前：counselor 对任意 user_id 都返回 200。
        """
        from fastapi import HTTPException

        from app.api.v1 import uploads as uploads_mod

        self._make_uploads(tmp_path, monkeypatch)
        monkeypatch.setattr(uploads_mod, "_resolve_upload_dir", lambda: tmp_path / "uploads")

        counselor = (await db_session.execute(select(User).where(User.id == 2))).scalar_one()
        # 先解绑，构造「无绑定」场景
        binding = (
            await db_session.execute(
                select(UserCounselorBinding).where(
                    UserCounselorBinding.counselor_id == 2,
                    UserCounselorBinding.user_id == 1,
                )
            )
        ).scalar_one()
        binding.status = BindingStatus.INACTIVE
        await db_session.commit()

        with pytest.raises(HTTPException) as exc:
            await uploads_mod.serve_upload(
                request=self._fake_request(),
                owner="1",
                filename="assessment.mp3",
                current_user=counselor,
                db=db_session,
            )
        # 统一 404：既表示「无绑定」也表示「文件不存在」，不可据此探测绑定关系
        assert exc.value.status_code == 404

    @pytest.mark.anyio
    async def test_unbound_status_not_sufficient(self, db_session, two_tenants, tmp_path, monkeypatch):
        """已解绑（status != active）的历史绑定不得放行 —— 须查 status 而非仅查存在。"""
        from fastapi import HTTPException

        from app.api.v1 import uploads as uploads_mod

        self._make_uploads(tmp_path, monkeypatch)
        monkeypatch.setattr(uploads_mod, "_resolve_upload_dir", lambda: tmp_path / "uploads")

        counselor = (await db_session.execute(select(User).where(User.id == 2))).scalar_one()
        binding = (
            await db_session.execute(
                select(UserCounselorBinding).where(
                    UserCounselorBinding.counselor_id == 2,
                    UserCounselorBinding.user_id == 1,
                )
            )
        ).scalar_one()
        binding.status = BindingStatus.INACTIVE
        await db_session.commit()

        with pytest.raises(HTTPException) as exc:
            await uploads_mod.serve_upload(
                request=self._fake_request(),
                owner="1",
                filename="assessment.mp3",
                current_user=counselor,
                db=db_session,
            )
        assert exc.value.status_code == 404

    @pytest.mark.anyio
    async def test_counselor_own_file_allowed(self, db_session, two_tenants, tmp_path, monkeypatch):
        """咨询师访问**自己**的文件无需绑定（绑定表只管 user 侧，不含自身文件）。"""
        from app.api.v1 import uploads as uploads_mod

        upload_dir = tmp_path / "uploads"
        own_dir = upload_dir / "2"
        own_dir.mkdir(parents=True)
        (own_dir / "my.mp3").write_bytes(b"own-audio")
        monkeypatch.setattr(uploads_mod, "_resolve_upload_dir", lambda: upload_dir)

        counselor = (await db_session.execute(select(User).where(User.id == 2))).scalar_one()

        resp = await uploads_mod.serve_upload(
            request=self._fake_request(),
            owner="2",
            filename="my.mp3",
            current_user=counselor,
            db=db_session,
        )
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_admin_unaffected(self, db_session, two_tenants, tmp_path, monkeypatch):
        """admin 的跨用户读取能力**不受本次收紧影响**（平台管理职责）。"""
        from app.api.v1 import uploads as uploads_mod

        self._make_uploads(tmp_path, monkeypatch)
        monkeypatch.setattr(uploads_mod, "_resolve_upload_dir", lambda: tmp_path / "uploads")

        admin = (await db_session.execute(select(User).where(User.id == 3))).scalar_one_or_none()
        if admin is None:
            admin = User(
                id=3,
                username="t1_admin",
                email="t1_admin@test.com",
                email_hash="x" * 64,
                password_hash="x",
                role="admin",
                status="active",
                tenant_id=1,
            )
            db_session.add(admin)
            await db_session.commit()

        resp = await uploads_mod.serve_upload(
            request=self._fake_request(),
            owner="1",
            filename="assessment.mp3",
            current_user=admin,
            db=db_session,
        )
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_missing_db_fails_closed_for_counselor(self, db_session, two_tenants, tmp_path, monkeypatch):
        """``db`` 不可用时 counselor 跨用户访问必须拒绝（fail-closed），不得放行。"""
        from fastapi import HTTPException

        from app.api.v1 import uploads as uploads_mod

        self._make_uploads(tmp_path, monkeypatch)
        monkeypatch.setattr(uploads_mod, "_resolve_upload_dir", lambda: tmp_path / "uploads")

        counselor = (await db_session.execute(select(User).where(User.id == 2))).scalar_one()

        with pytest.raises(HTTPException) as exc:
            await uploads_mod.serve_upload(
                request=self._fake_request(),
                owner="1",
                filename="assessment.mp3",
                current_user=counselor,
                db=None,
            )
        assert exc.value.status_code == 404
