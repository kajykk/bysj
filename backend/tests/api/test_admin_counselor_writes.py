from __future__ import annotations

from app.core.security import create_access_token


def test_admin_template_write_requires_admin(client, as_role) -> None:
    as_role("counselor", 2)
    resp = client.post(
        "/api/v1/admin/templates",
        json={
            "template_name": "A",
            "applicable_levels": [2],
            "task_list": [{"task_name": "呼吸训练", "task_type": "meditation"}],
            "estimated_weeks": 4,
            "status": "active",
        },
    )
    assert resp.status_code == 403


def test_admin_threshold_write_requires_admin(client, seeded_user_id: int) -> None:
    token = create_access_token({"sub": str(seeded_user_id), "role": "user"})
    resp = client.post(
        "/api/v1/admin/thresholds",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "level": 1,
            "level_name": "L1",
            "min_score": 0,
            "max_score": 20,
            "color": "#f00",
            "action_required": "observe",
        },
    )
    assert resp.status_code in (302, 307, 308, 403)


def test_counselor_bind_code_requires_counselor(client, as_role) -> None:
    as_role("user", 1)
    resp = client.get("/api/v1/counselor/bind-code")
    assert resp.status_code == 403
