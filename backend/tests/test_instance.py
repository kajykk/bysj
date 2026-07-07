"""v1.36: instance 工具单元测试."""

from __future__ import annotations

import os
from unittest.mock import patch


class TestGetInstanceId:
    def test_get_instance_id_format(self):
        """返回值应包含 hostname 和 pid, 形如 hostname-pid."""
        from app.core.instance import get_instance_id

        instance_id = get_instance_id()
        assert "-" in instance_id
        # 最后一段应是 pid
        assert instance_id.endswith(f"-{os.getpid()}")
        # 至少 2 段 (hostname-pid)
        parts = instance_id.rsplit("-", 1)
        assert len(parts) == 2
        assert parts[1].isdigit()
        assert int(parts[1]) == os.getpid()

    def test_get_instance_id_includes_real_hostname(self):
        """应包含真实 hostname."""
        from app.core.instance import get_instance_id

        instance_id = get_instance_id()
        # 真实 hostname (socket.gethostname 不会失败)
        import socket

        hostname = socket.gethostname()
        assert hostname in instance_id

    def test_get_instance_id_stable_within_process(self):
        """同一进程多次调用应返回相同值."""
        from app.core.instance import get_instance_id

        id1 = get_instance_id()
        id2 = get_instance_id()
        assert id1 == id2

    def test_get_instance_id_fallback_on_hostname_failure(self):
        """socket.gethostname 失败时, 降级为 unknown-<pid>."""
        from app.core.instance import get_instance_id

        with patch("socket.gethostname", side_effect=Exception("hostname error")):
            instance_id = get_instance_id()
            # 应包含 "unknown" 和 pid
            assert "unknown" in instance_id
            assert instance_id.endswith(f"-{os.getpid()}")

    def test_get_instance_id_fallback_on_empty_hostname(self):
        """hostname 返回空字符串时, 降级为 unknown-<pid>."""
        from app.core.instance import get_instance_id

        with patch("socket.gethostname", return_value=""):
            instance_id = get_instance_id()
            assert "unknown" in instance_id
            assert instance_id.endswith(f"-{os.getpid()}")

    def test_get_instance_id_pids_differ(self):
        """不同 pid 应得到不同 instance_id (验证逻辑正确)."""
        from app.core.instance import get_instance_id

        with patch("os.getpid", return_value=12345):
            id1 = get_instance_id()
        with patch("os.getpid", return_value=67890):
            id2 = get_instance_id()
        assert id1 != id2
        assert id1.endswith("-12345")
        assert id2.endswith("-67890")
