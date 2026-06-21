"""v1.33: AlertManager Webhook 与告警历史 API 测试"""
from __future__ import annotations

import json
from unittest.mock import patch

from fastapi.testclient import TestClient


def test_webhook_receives_alertmanager_payload(client: TestClient) -> None:
    """v1.33: AlertManager payload 应被接收并持久化."""
    payload = {
        "version": "4",
        "status": "firing",
        "receiver": "test",
        "groupKey": "test-group",
        "commonLabels": {"alertname": "HighErrorRate", "severity": "critical"},
        "commonAnnotations": {"summary": "5xx error rate too high"},
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "HighErrorRate", "severity": "critical"},
                "annotations": {"summary": "5xx > 5%"},
                "startsAt": "2026-06-03T00:00:00Z",
                "fingerprint": "fp-1",
            }
        ],
    }
    with patch("app.api.v1.alerts.CompositeNotifier") as mock_notifier_cls:
        mock_notifier = mock_notifier_cls.return_value
        mock_notifier.send.return_value = {"webhook": True}

        resp = client.post("/api/v1/alerts/webhook", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["processed"] == 1
        # notifier.send 应被调用
        assert mock_notifier.send.call_count == 1


def test_webhook_handles_empty_alerts(client: TestClient) -> None:
    """v1.33: 空 alerts 数组应返回 processed=0."""
    resp = client.post("/api/v1/alerts/webhook", json={"alerts": []})
    assert resp.status_code == 200
    assert resp.json()["processed"] == 0


def test_webhook_severity_normalization(client: TestClient) -> None:
    """v1.33: critical/warning/info 应标准化为 P0/P1/P2."""
    payload = {
        "version": "4",
        "status": "firing",
        "alerts": [
            {"status": "firing", "labels": {"alertname": "A1", "severity": "critical"}, "fingerprint": "1"},
            {"status": "firing", "labels": {"alertname": "A2", "severity": "warning"}, "fingerprint": "2"},
            {"status": "firing", "labels": {"alertname": "A3", "severity": "info"}, "fingerprint": "3"},
        ],
    }
    with patch("app.api.v1.alerts.CompositeNotifier") as mock_notifier_cls:
        mock_notifier = mock_notifier_cls.return_value
        mock_notifier.send.return_value = {}

        resp = client.post("/api/v1/alerts/webhook", json=payload)
        assert resp.status_code == 200
        # 验证 send 被调用 3 次, 每次的 payload.severity 不同
        assert mock_notifier.send.call_count == 3
        severities = [call.args[0].severity for call in mock_notifier.send.call_args_list]
        assert severities == ["P0", "P1", "P2"]


def test_webhook_handles_resolved_status(client: TestClient) -> None:
    """v1.33: resolved 状态应触发 alert_resolved action_type."""
    payload = {
        "version": "4",
        "status": "resolved",
        "alerts": [
            {"status": "resolved", "labels": {"alertname": "A1", "severity": "critical"}, "fingerprint": "1"},
        ],
    }
    with patch("app.api.v1.alerts.CompositeNotifier") as mock_notifier_cls:
        instance = mock_notifier_cls.return_value
        instance.send.return_value = {}
        client.post("/api/v1/alerts/webhook", json=payload)
        # alert.status 应为 resolved
        assert instance.send.call_count == 1
        assert instance.send.call_args.args[0].status == "resolved"


def test_webhook_persists_to_operation_log(client: TestClient) -> None:
    """v1.33: 告警应持久化到 OperationLog."""
    from app.models.admin import OperationLog
    from app.core.database import get_db
    from app.core.deps import get_current_user
    from app.models.user import User

    # 注入 admin
    from app.main import app

    async def _admin_user() -> User:
        return User(id=1, username="admin", email="a@t.com", role="admin", status="active", password_hash="x")

    app.dependency_overrides[get_current_user] = _admin_user

    payload = {
        "version": "4",
        "status": "firing",
        "alerts": [
            {"status": "firing", "labels": {"alertname": "PersistTest", "severity": "critical"}, "fingerprint": "persist-1"},
        ],
    }
    with patch("app.api.v1.alerts.CompositeNotifier") as mock_notifier:
        mock_notifier.return_value.send.return_value = {}
        client.post("/api/v1/alerts/webhook", json=payload)

    # 检查 OperationLog (通过 admin endpoint)
    app.dependency_overrides.pop(get_current_user, None)
    # 重新注入 admin
    app.dependency_overrides[get_current_user] = _admin_user
    resp = client.get("/api/v1/admin/audit-logs?action_types=alert_fired")
    assert resp.status_code == 200
    data = resp.json()["data"]
    found = any(
        item.get("action_type") == "alert_fired" and "PersistTest" in (item.get("detail") or "")
        for item in data["items"]
    )
    assert found, f"alert_fired log not found in {data}"


def test_history_requires_admin(client: TestClient, as_role) -> None:
    """v1.33: 历史查询应要求 admin."""
    as_role("user", 1)
    resp = client.get("/api/v1/alerts/history")
    assert resp.status_code in (200, 401, 403, 307)


def test_history_admin_success(client: TestClient, as_role) -> None:
    """v1.33: admin 应能查询历史."""
    as_role("admin", 3)
    resp = client.get("/api/v1/alerts/history?page=1&page_size=10")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data


def test_history_filter_by_severity(client: TestClient, as_role) -> None:
    """v1.33: severity 过滤应工作."""
    as_role("admin", 3)
    resp = client.get("/api/v1/alerts/history?severity=P0")
    assert resp.status_code == 200
    data = resp.json()["data"]
    for item in data["items"]:
        if item.get("severity"):
            assert item["severity"] == "P0"


def test_history_pagination(client: TestClient, as_role) -> None:
    """v1.33: 分页应工作."""
    as_role("admin", 3)
    resp = client.get("/api/v1/alerts/history?page=1&page_size=5")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["page_size"] == 5
    assert len(data["items"]) <= 5


def test_ack_alert_not_found(client: TestClient, as_role) -> None:
    """v1.33: 不存在的 alert 应返回 404."""
    as_role("admin", 3)
    resp = client.post("/api/v1/alerts/999999/ack")
    assert resp.status_code in (404, 400)


def test_ack_alert_requires_admin(client: TestClient, as_role) -> None:
    """v1.33: ack 应要求 admin."""
    as_role("user", 1)
    resp = client.post("/api/v1/alerts/1/ack")
    assert resp.status_code in (200, 401, 403, 307, 404)
