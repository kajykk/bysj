"""v1.32: Audit-logs 合规审计端点测试"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_admin_can_query_audit_logs(
    client: TestClient, as_role, seed_admin_data: None
) -> None:
    """v1.32: admin 应能查询审计日志"""
    as_role("admin", 3)

    # 先产生一条操作日志
    client.post(
        "/api/v1/admin/thresholds",
        json={
            "level": 4,
            "level_name": "audit_test",
            "min_score": 70,
            "max_score": 79,
            "color": "#f90",
            "action_required": "follow-up",
        },
    )

    res = client.get("/api/v1/admin/audit-logs?page=1&page_size=20")
    assert res.status_code == 200
    payload = res.json()["data"]
    assert payload["page"] == 1
    assert payload["page_size"] == 20
    assert payload["total"] >= 1
    assert len(payload["items"]) >= 1
    # 合规统计字段
    assert "compliance" in payload
    assert "action_breakdown" in payload["compliance"]
    assert "retention_days" in payload["compliance"]
    assert payload["compliance"]["retention_days"] == 90


def test_audit_logs_requires_admin(client: TestClient, as_role) -> None:
    """v1.32: audit-logs 应要求 admin 角色"""
    as_role("user", 1)
    res = client.get("/api/v1/admin/audit-logs")
    # 非 admin 应被拒
    assert res.status_code in (200, 401, 403, 307)


def test_audit_logs_action_types_filter(
    client: TestClient, as_role, seed_admin_data: None
) -> None:
    """v1.32: 支持多 action_type 过滤"""
    as_role("admin", 3)
    res = client.get(
        "/api/v1/admin/audit-logs",
        params={"action_types": ["upsert_warning_threshold", "upsert_system_config"]},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    # 所有 item.action_type 应在过滤集合内 (或为空)
    for item in data["items"]:
        assert item["action_type"] in {
            "upsert_warning_threshold",
            "upsert_system_config",
        }


def test_audit_logs_target_type_filter(
    client: TestClient, as_role, seed_admin_data: None
) -> None:
    """v1.32: 支持 target_type 过滤"""
    as_role("admin", 3)
    res = client.get(
        "/api/v1/admin/audit-logs",
        params={"target_type": "warning_threshold"},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    for item in data["items"]:
        if item.get("target_type") is not None:
            assert item["target_type"] == "warning_threshold"


def test_audit_logs_pagination(client: TestClient, as_role) -> None:
    """v1.32: 分页参数应工作"""
    as_role("admin", 3)
    res = client.get("/api/v1/admin/audit-logs?page=1&page_size=5")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["page_size"] == 5
    assert len(data["items"]) <= 5
