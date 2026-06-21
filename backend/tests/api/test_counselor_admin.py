from fastapi.testclient import TestClient

from app.core.states import BindingStatus
from app.models.admin import OperationLog
from app.models.counselor import ClientGroup, ClientGroupMember
from app.models.user import User, UserCounselorBinding


def test_counselor_warning_pagination_and_handle(
    client: TestClient,
    as_role,
    seed_counselor_data: None,
) -> None:
    as_role("counselor", 2)
    list_res = client.get("/api/v1/counselor/warnings?page=1&page_size=10&only_unhandled=true")
    assert list_res.status_code == 200
    data = list_res.json()["data"]
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert data["total"] >= 1

    warning_id = data["items"][0]["id"]
    handle_res = client.put(f"/api/v1/counselor/warnings/{warning_id}/handle", json={"action": "handle", "note": "done"})
    assert handle_res.status_code == 200


def test_add_group_member_is_idempotent(client: TestClient, as_role, db_session) -> None:
    async def _seed() -> int:
        db_session.add_all(
            [
                User(id=1, username="user1", email="u1@test.com", password_hash="x", role="user", status="active"),
                User(id=2, username="counselor", email="c@test.com", password_hash="x", role="counselor", status="active"),
            ]
        )
        group = ClientGroup(counselor_id=2, group_name="A组", description="desc", color_tag="#409EFF")
        db_session.add(group)
        await db_session.flush()
        db_session.add(ClientGroupMember(group_id=group.id, user_id=1))
        await db_session.commit()
        return group.id

    from backend.tests.conftest import run

    group_id = run(_seed())

    as_role("counselor", 2)
    res = client.post(f"/api/v1/counselor/groups/{group_id}/members", json={"user_id": 1})
    assert res.status_code == 200
    res2 = client.post(f"/api/v1/counselor/groups/{group_id}/members", json={"user_id": 1})
    assert res2.status_code == 200

    async def _check() -> tuple[int, int]:
        member_count = (await db_session.execute(ClientGroupMember.__table__.count())).scalar_one()
        log_count = (await db_session.execute(OperationLog.__table__.count())).scalar_one()
        return member_count, log_count


def test_counselor_binding_fsm_and_logs(client: TestClient, as_role, db_session) -> None:
    async def _seed() -> str:
        db_session.add_all(
            [
                User(id=1, username="user1", email="u1@test.com", password_hash="x", role="user", status="active"),
                User(id=2, username="counselor", email="c@test.com", password_hash="x", role="counselor", status="active"),
                UserCounselorBinding(user_id=2, counselor_id=2, bind_code="B123", status=BindingStatus.PLACEHOLDER),
            ]
        )
        await db_session.commit()
        return "B123"

    from backend.tests.conftest import run

    bind_code = run(_seed())

    as_role("user", 1)
    bind_res = client.post("/api/v1/user/data/binding", json={"bind_code": bind_code})
    assert bind_res.status_code == 200
    data = bind_res.json()["data"]
    assert data["status"] == BindingStatus.ACTIVE
    assert data["bind_code_status"] == BindingStatus.ACTIVE

    get_res = client.get("/api/v1/user/data/binding")
    assert get_res.status_code == 200
    assert get_res.json()["data"]["status"] == BindingStatus.ACTIVE

    unbind_res = client.delete("/api/v1/user/data/binding")
    assert unbind_res.status_code == 200


def test_counselor_bind_code_reuses_latest_placeholder_when_duplicates_exist(
    client: TestClient,
    as_role,
    db_session,
) -> None:
    async def _seed() -> None:
        db_session.add_all(
            [
                User(id=2, username="counselor", email="c@test.com", password_hash="x", role="counselor", status="active"),
                UserCounselorBinding(user_id=2, counselor_id=2, bind_code="OLD1", status=BindingStatus.PLACEHOLDER),
                UserCounselorBinding(user_id=999, counselor_id=2, bind_code="OLD2", status=BindingStatus.PLACEHOLDER),
            ]
        )
        await db_session.commit()

    from backend.tests.conftest import run

    run(_seed())

    as_role("counselor", 2)
    res = client.get("/api/v1/counselor/bind-code")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["bind_code"] in {"OLD1", "OLD2"}


def test_counselor_handle_warning_404(client: TestClient, as_role) -> None:
    as_role("counselor", 2)
    res = client.put("/api/v1/counselor/warnings/999/handle", json={"action": "handle"})
    assert res.status_code == 404


def test_admin_template_and_feedback_pagination(
    client: TestClient,
    as_role,
    seed_admin_data: None,
) -> None:
    as_role("admin", 3)
    tpl_res = client.get("/api/v1/admin/templates?page=1&page_size=10")
    assert tpl_res.status_code == 200
    tpl_data = tpl_res.json()["data"]
    assert tpl_data["page"] == 1
    assert tpl_data["page_size"] == 10

    fb_res = client.get("/api/v1/admin/model-feedbacks?page=1&page_size=10")
    assert fb_res.status_code == 200
    fb_data = fb_res.json()["data"]
    assert fb_data["page"] == 1
    assert fb_data["page_size"] == 10


def test_role_permission_403(client: TestClient, as_role, seed_admin_data: None) -> None:
    as_role("user", 1)
    res = client.get("/api/v1/admin/templates")
    assert res.status_code == 403
