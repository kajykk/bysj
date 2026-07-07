"""v1.35: AlertManager sync 模块测试.

v1.36: 增加 T1.2 - am_sync 记录同步结果到 OperationLog 测试.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.monitoring.am_sync import (
    delete_silence,
    local_to_am_format,
    pull_silences,
    push_silence,
)

# ===== push_silence (v1.36: async) =====


async def test_push_silence_no_am_url() -> None:
    """v1.35: 无 AM URL 应返回 None."""
    with patch("app.monitoring.am_sync._get_am_url", return_value=None):
        result = await push_silence({"matchers": []})
        assert result is None


async def test_push_silence_success() -> None:
    """v1.35: 推送成功应返回 AM 数据."""
    with patch(
        "app.monitoring.am_sync._get_am_url", return_value="http://am:9093"
    ), patch("app.monitoring.am_sync._HTTP_SESSION.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"silenceID": "am-uuid-123"}
        mock_post.return_value = mock_resp

        result = await push_silence({"matchers": [{"name": "alertname", "value": "X"}]})
        assert result is not None
        assert result["silenceID"] == "am-uuid-123"
        called_url = mock_post.call_args.args[0]
        assert "/api/v2/silences" in called_url


async def test_push_silence_uses_auth() -> None:
    """v1.35: 应使用配置的 AM 认证."""
    with patch(
        "app.monitoring.am_sync._get_am_url", return_value="http://am:9093"
    ), patch(
        "app.monitoring.am_sync._get_am_auth", return_value=("user", "pwd")
    ), patch(
        "app.monitoring.am_sync._HTTP_SESSION.post"
    ) as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"silenceID": "x"}
        mock_post.return_value = mock_resp

        await push_silence({"matchers": []})
        auth = mock_post.call_args.kwargs["auth"]
        assert auth == ("user", "pwd")


async def test_push_silence_5xx_returns_none() -> None:
    """v1.35: 5xx 应返回 None."""
    with patch(
        "app.monitoring.am_sync._get_am_url", return_value="http://am:9093"
    ), patch("app.monitoring.am_sync._HTTP_SESSION.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "internal error"
        mock_post.return_value = mock_resp

        result = await push_silence({"matchers": []})
        assert result is None


async def test_push_silence_network_error() -> None:
    """v1.35: 网络异常应返回 None."""
    with patch(
        "app.monitoring.am_sync._get_am_url", return_value="http://am:9093"
    ), patch(
        "app.monitoring.am_sync._HTTP_SESSION.post", side_effect=Exception("network")
    ):
        result = await push_silence({"matchers": []})
        assert result is None


# ===== delete_silence (v1.36: async) =====


async def test_delete_silence_no_url() -> None:
    """v1.35: 无 AM URL 应返回 False."""
    with patch("app.monitoring.am_sync._get_am_url", return_value=None):
        result = await delete_silence("am-uuid")
        assert result is False


async def test_delete_silence_empty_id() -> None:
    """v1.35: 空 ID 应返回 False."""
    with patch("app.monitoring.am_sync._get_am_url", return_value="http://am:9093"):
        result = await delete_silence("")
        assert result is False


async def test_delete_silence_success() -> None:
    """v1.35: 删除成功应返回 True."""
    with patch(
        "app.monitoring.am_sync._get_am_url", return_value="http://am:9093"
    ), patch("app.monitoring.am_sync._HTTP_SESSION.delete") as mock_delete:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_delete.return_value = mock_resp
        result = await delete_silence("am-uuid-123")
        assert result is True
        called_url = mock_delete.call_args.args[0]
        assert "am-uuid-123" in called_url


async def test_delete_silence_404() -> None:
    """v1.35: 404 应返回 False."""
    with patch(
        "app.monitoring.am_sync._get_am_url", return_value="http://am:9093"
    ), patch("app.monitoring.am_sync._HTTP_SESSION.delete") as mock_delete:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_delete.return_value = mock_resp
        result = await delete_silence("am-uuid-notfound")
        assert result is False


# ===== pull_silences (v1.36: async) =====


async def test_pull_silences_no_url() -> None:
    """v1.35: 无 AM URL 应返回 None."""
    with patch("app.monitoring.am_sync._get_am_url", return_value=None):
        result = await pull_silences()
        assert result is None


async def test_pull_silences_success() -> None:
    """v1.35: 拉取成功应返回列表."""
    with patch(
        "app.monitoring.am_sync._get_am_url", return_value="http://am:9093"
    ), patch("app.monitoring.am_sync._HTTP_SESSION.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"silenceID": "am-1"}, {"silenceID": "am-2"}]
        mock_get.return_value = mock_resp
        result = await pull_silences()
        assert result is not None
        assert len(result) == 2
        # params dict should include silenced=True
        params = mock_get.call_args.kwargs["params"]
        assert params.get("silenced") == "true"


async def test_pull_silences_empty() -> None:
    """v1.35: 无静默应返回空列表."""
    with patch(
        "app.monitoring.am_sync._get_am_url", return_value="http://am:9093"
    ), patch("app.monitoring.am_sync._HTTP_SESSION.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = None  # AM 可能返回 null
        mock_get.return_value = mock_resp
        result = await pull_silences()
        assert result == []


# ===== local_to_am_format =====


def test_local_to_am_format_basic() -> None:
    """v1.35: 本地转 AM 格式."""
    now = datetime.now(timezone.utc)
    later = now + timedelta(hours=2)
    result = local_to_am_format(
        silence_id=1,
        name="test",
        matcher={"alertname": "X", "severity": "P0"},
        starts_at=now,
        ends_at=later,
        comment="maintenance",
    )
    assert "matchers" in result
    assert len(result["matchers"]) == 2
    assert result["matchers"][0]["name"] == "alertname"
    assert result["matchers"][0]["isRegex"] is False
    assert result["createdBy"] == "dws-backend:1"
    assert result["comment"] == "maintenance"


def test_local_to_am_format_no_comment() -> None:
    """v1.35: 无 comment 时使用 name."""
    now = datetime.now(timezone.utc)
    result = local_to_am_format(
        silence_id=1,
        name="my-silence",
        matcher={},
        starts_at=now,
        ends_at=now,
        comment=None,
    )
    assert result["comment"] == "my-silence"


def test_local_to_am_format_empty_matcher() -> None:
    """v1.35: 空 matcher 应生成空 matchers 列表."""
    now = datetime.now(timezone.utc)
    result = local_to_am_format(
        silence_id=1,
        name="x",
        matcher={},
        starts_at=now,
        ends_at=now,
        comment=None,
    )
    assert result["matchers"] == []


# ===== v1.36: T1.2 am_sync 记录同步 (TC-DATA-002) =====


async def test_am_sync_success_logged() -> None:
    """v1.36 T1.2: 推送成功写入 OperationLog (am_sync_success)."""
    db = MagicMock()
    db.add = MagicMock()

    with patch(
        "app.monitoring.am_sync._get_am_url", return_value="http://am:9093"
    ), patch("app.monitoring.am_sync._HTTP_SESSION.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"silenceID": "am-uuid-123"}
        mock_post.return_value = mock_resp

        await push_silence({"matchers": []}, db=db)

    assert db.add.called
    log_obj = db.add.call_args.args[0]
    assert log_obj.action_type == "am_sync_success"
    assert log_obj.target_type == "alert_silence"
    assert log_obj.operator_role == "system"
    assert log_obj.operator_id is None


async def test_am_sync_failed_logged() -> None:
    """v1.36 T1.2: 推送失败写入 OperationLog (am_sync_failed)."""
    db = MagicMock()
    db.add = MagicMock()

    with patch(
        "app.monitoring.am_sync._get_am_url", return_value="http://am:9093"
    ), patch("app.monitoring.am_sync._HTTP_SESSION.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "internal error"
        mock_post.return_value = mock_resp

        await push_silence({"matchers": []}, db=db)

    assert db.add.called
    log_obj = db.add.call_args.args[0]
    assert log_obj.action_type == "am_sync_failed"


async def test_am_sync_log_includes_am_silence_id() -> None:
    """v1.36 T1.2: detail 包含 am_silence_id (成功时)."""
    import json as json_mod

    db = MagicMock()
    db.add = MagicMock()

    with patch(
        "app.monitoring.am_sync._get_am_url", return_value="http://am:9093"
    ), patch("app.monitoring.am_sync._HTTP_SESSION.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"silenceID": "am-uuid-xyz"}
        mock_post.return_value = mock_resp

        await push_silence({"matchers": []}, db=db)

    log_obj = db.add.call_args.args[0]
    detail = json_mod.loads(log_obj.detail)
    assert detail["am_silence_id"] == "am-uuid-xyz"
    assert detail["operation"] == "push_silence"
    assert "duration_ms" in detail
    assert isinstance(detail["duration_ms"], int)
    assert detail["duration_ms"] >= 0


async def test_am_sync_log_failure_does_not_block_sync() -> None:
    """v1.36 T1.2: 写日志失败不影响同步返回值."""
    db = MagicMock()
    db.add = MagicMock(side_effect=Exception("db unavailable"))

    with patch(
        "app.monitoring.am_sync._get_am_url", return_value="http://am:9093"
    ), patch("app.monitoring.am_sync._HTTP_SESSION.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"silenceID": "am-uuid-789"}
        mock_post.return_value = mock_resp

        # 写日志抛异常, 但 push_silence 仍应返回成功结果
        result = await push_silence({"matchers": []}, db=db)
        assert result is not None
        assert result["silenceID"] == "am-uuid-789"
