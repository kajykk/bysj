"""REV-2026-10-20 S3 回归：绑定 / 详情 / 私有文件下载的租户边界。

改前三条链路各自缺一层租户校验，拼成一条完整的越权链：

1. ``BindingMixin.bind_by_code`` 只校验咨询师角色与状态，不比对两端
   ``tenant_id`` ⇒ 租户 B 的用户拿到租户 A 咨询师的绑定码即可建立 ACTIVE 绑定；
2. ``CounselorService.get_user_detail`` 只校验绑定关系存在（同文件
   ``list_my_users`` 却显式加了 ``tenant_scoped_filter``，两套口径）⇒
   历史遗留的跨租户绑定仍能读到抑郁风险评分、评估历史、问卷与干预计划；
3. ``uploads.serve_upload`` 的 admin 分支直接放行 ⇒ 租户 B 的 admin 知道
   ``user_id`` 与文件名即可下载他租户的量表 PDF / 音频。

断言打的是真实服务函数与真实文件，不用 dependency_overrides（附录 C）。
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.core.states import BindingStatus
from app.models.user import User, UserCounselorBinding
from app.services.counselor_service import CounselorService


def _mk(uid: int, username: str, role: str, tenant: int) -> User:
    from app.core.pii_crypto import compute_blind_index
    from app.core.security import get_password_hash

    email = f"{username}@test.com"
    return User(
        id=uid,
        username=username,
        email=email,
        email_hash=compute_blind_index(email, "email"),
        password_hash=get_password_hash("testpass123"),
        role=role,
        status="active",
        tenant_id=tenant,
    )


@pytest.fixture
async def tenants(db_session):
    """租户 1：用户 1 + 咨询师 2；租户 2：咨询师 3。"""
    db_session.add_all(
        [
            _mk(1, "s3_student", "user", 1),
            _mk(2, "s3_counselor", "counselor", 1),
            _mk(3, "s3_other_counselor", "counselor", 2),
        ]
    )
    await db_session.flush()
    # 他租户咨询师的占位绑定码：用户 1 若拿它绑定即为跨租户
    db_session.add(
        UserCounselorBinding(
            user_id=3,
            counselor_id=3,
            bind_code="XTENANT2",
            status=BindingStatus.PLACEHOLDER,
        )
    )
    await db_session.commit()
    return db_session


async def test_bind_by_code_rejects_cross_tenant_counselor(tenants):
    service = CounselorService(tenants)

    with pytest.raises(ValueError) as excinfo:
        await service.bind_by_code(1, "XTENANT2")

    # 错误信息与"咨询师不存在"一致，不泄露他租户咨询师存在性
    assert "不存在或已停用" in str(excinfo.value)
    # 断言副作用：没有产生 ACTIVE 绑定
    from sqlalchemy import select

    active = (
        await tenants.execute(
            select(UserCounselorBinding).where(
                UserCounselorBinding.user_id == 1,
                UserCounselorBinding.counselor_id == 3,
                UserCounselorBinding.status == BindingStatus.ACTIVE,
            )
        )
    ).scalars().all()
    assert active == []


async def test_bind_by_code_allows_same_tenant(tenants):
    service = CounselorService(tenants)
    code = await service.get_or_create_bind_code(2)

    result = await service.bind_by_code(1, code)

    assert result["counselor_id"] == 2
    assert result["status"] == "active"


async def test_get_user_detail_rejects_dangling_cross_tenant_binding(tenants):
    """历史脏数据：绑定行存在但两端不同租户，详情查询必须拒绝。

    绑定接口的修复只拦"新绑定"；已存在的跨租户行靠详情层的 tenant 过滤兜底。
    """
    tenants.add(
        UserCounselorBinding(
            user_id=1,
            counselor_id=3,
            bind_code="LEGACY01",
            status=BindingStatus.ACTIVE,
        )
    )
    await tenants.commit()

    service = CounselorService(tenants)
    # 咨询师 3 的真实租户是 2，请求租户即 2 → 目标用户不在该租户 ⇒ None
    assert await service.get_user_detail(3, 1, tenant_id=2) is None
    # 同租户正常路径不受影响
    tenants.add(
        UserCounselorBinding(
            user_id=1,
            counselor_id=2,
            bind_code="LEGACY02",
            status=BindingStatus.ACTIVE,
        )
    )
    await tenants.commit()
    assert await service.get_user_detail(2, 1, tenant_id=1) is not None


async def test_uploads_admin_branch_is_tenant_scoped(tenants, tmp_path, monkeypatch):
    """admin 只能下载本租户用户的私有文件；super_admin 保留平台级访问。"""
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    (tmp_path / "1").mkdir()
    filename = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.pdf"
    (tmp_path / "1" / filename).write_bytes(b"%PDF-1.4 test")

    from app.api.v1.uploads import serve_upload

    admin_t2 = _mk(20, "s3_admin_t2", "admin", 2)
    with pytest.raises(HTTPException) as excinfo:
        await serve_upload(
            request=None,
            owner="1",
            filename=filename,
            current_user=admin_t2,
            db=tenants,
        )
    # 文件真实存在，404 只能来自租户校验（改前会返回 FileResponse）
    assert excinfo.value.status_code == 404

    admin_t1 = _mk(21, "s3_admin_t1", "admin", 1)
    resp = await serve_upload(
        request=None,
        owner="1",
        filename=filename,
        current_user=admin_t1,
        db=tenants,
    )
    assert isinstance(resp, FileResponse)

    super_admin = _mk(22, "s3_super", "super_admin", 2)
    resp = await serve_upload(
        request=None,
        owner="1",
        filename=filename,
        current_user=super_admin,
        db=tenants,
    )
    assert isinstance(resp, FileResponse)
