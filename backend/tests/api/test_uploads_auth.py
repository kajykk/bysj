"""SEC-P0-001 修复测试：/uploads/* 鉴权路由

覆盖场景：
1. 公共资源 (audio/content) 无需鉴权可访问
2. 公共资源白名单外目录返回 404 (不暴露存在性)
3. 用户私有文件无 token 返回 401
4. user 角色访问自己文件 200
5. user 角色访问他人文件 404 (不暴露存在性)
6. counselor 角色访问任意用户文件 200
7. admin 角色访问任意用户文件 200
8. 路径遍历攻击被拦截
9. 非法文件名被拦截
10. ``?token=`` query 参数鉴权 200 (浏览器原生标签 fallback)
11. 无效 token 返回 401
12. 路径遍历 ``..`` 被拦截
13. null 字节注入被拦截
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_upload_dir(tmp_path: Path, monkeypatch):
    """mock _resolve_upload_dir 返回 tmp_path/uploads，并预置测试文件。

    目录结构：
        uploads/audio/mindfulness.mp3        (公共资源)
        uploads/content/guide.pdf            (公共资源)
        uploads/1/abc123.jpg                 (user_id=1 私有文件)
        uploads/2/def456.pdf                 (user_id=2 私有文件)
    """
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    # 公共资源
    audio_dir = upload_dir / "audio"
    audio_dir.mkdir()
    (audio_dir / "mindfulness.mp3").write_bytes(b"fake-audio-content")

    content_dir = upload_dir / "content"
    content_dir.mkdir()
    (content_dir / "guide.pdf").write_bytes(b"fake-pdf-content")

    # 用户私有文件
    user1_dir = upload_dir / "1"
    user1_dir.mkdir()
    (user1_dir / "abc123.jpg").write_bytes(b"user1-avatar")
    (user1_dir / "report.pdf").write_bytes(b"user1-report")

    user2_dir = upload_dir / "2"
    user2_dir.mkdir()
    (user2_dir / "def456.pdf").write_bytes(b"user2-report")

    from app.api.v1 import uploads as uploads_mod

    monkeypatch.setattr(uploads_mod, "_resolve_upload_dir", lambda: upload_dir)

    return upload_dir


class TestPublicUpload:
    """公共资源路由测试。"""

    def test_public_audio_no_auth(self, client: TestClient, mock_upload_dir: Path):
        """公共音频资源无需鉴权可访问。"""
        resp = client.get("/uploads/audio/mindfulness.mp3")
        assert resp.status_code == 200
        assert resp.content == b"fake-audio-content"

    def test_public_content_no_auth(self, client: TestClient, mock_upload_dir: Path):
        """公共内容资源无需鉴权可访问。"""
        resp = client.get("/uploads/content/guide.pdf")
        assert resp.status_code == 200
        assert resp.content == b"fake-pdf-content"

    def test_public_non_whitelisted_dir_returns_404(
        self, client: TestClient, mock_upload_dir: Path
    ):
        """非白名单目录 (如 'private') 返回 404，不暴露存在性。"""
        # 在 uploads/private/ 下放文件
        (mock_upload_dir / "private").mkdir()
        (mock_upload_dir / "private" / "secret.txt").write_bytes(b"secret")
        resp = client.get("/uploads/private/secret.txt")
        assert resp.status_code == 404

    def test_public_nonexistent_file_returns_404(
        self, client: TestClient, mock_upload_dir: Path
    ):
        """公共目录下不存在的文件返回 404。"""
        resp = client.get("/uploads/audio/nonexistent.mp3")
        assert resp.status_code == 404

    def test_public_path_traversal_blocked(
        self, client: TestClient, mock_upload_dir: Path
    ):
        """公共路径遍历攻击被拦截。

        尝试 /uploads/audio/../../../etc/passwd 应返回 400 或 404。
        """
        resp = client.get("/uploads/audio/../../../etc/passwd")
        # Starlette 会先规范化 URL，可能返回 404 或 400
        assert resp.status_code in (400, 404)


class TestPrivateUploadAuth:
    """用户私有文件鉴权测试。"""

    def test_private_no_token_returns_401(
        self, client: TestClient, mock_upload_dir: Path
    ):
        """私有文件无 token 返回 401。"""
        resp = client.get("/uploads/1/abc123.jpg")
        assert resp.status_code == 401

    def test_private_user_access_own_file(
        self, client: TestClient, mock_upload_dir: Path, as_role
    ):
        """user 角色访问自己的文件返回 200。"""
        as_role("user", user_id=1)
        # conftest 中 auth_headers 是 "Bearer test-token"，override_user_dependency 会接受
        resp = client.get(
            "/uploads/1/abc123.jpg", headers={"Authorization": "Bearer test-token"}
        )
        assert resp.status_code == 200
        assert resp.content == b"user1-avatar"

    def test_private_user_access_other_users_file_returns_404(
        self, client: TestClient, mock_upload_dir: Path, as_role
    ):
        """user 角色访问他人文件返回 404 (不暴露存在性)。"""
        as_role("user", user_id=1)
        resp = client.get(
            "/uploads/2/def456.pdf", headers={"Authorization": "Bearer test-token"}
        )
        # 不暴露 403，统一返回 404
        assert resp.status_code == 404

    def test_private_counselor_access_any_user(
        self, client: TestClient, mock_upload_dir: Path, as_role
    ):
        """counselor 角色可访问任意用户文件。"""
        as_role("counselor", user_id=99)
        # counselor 访问 user_id=1 的文件
        resp = client.get(
            "/uploads/1/abc123.jpg", headers={"Authorization": "Bearer test-token"}
        )
        assert resp.status_code == 200
        assert resp.content == b"user1-avatar"
        # counselor 访问 user_id=2 的文件
        resp = client.get(
            "/uploads/2/def456.pdf", headers={"Authorization": "Bearer test-token"}
        )
        assert resp.status_code == 200
        assert resp.content == b"user2-report"

    def test_private_admin_access_any_user(
        self, client: TestClient, mock_upload_dir: Path, as_role
    ):
        """admin 角色可访问任意用户文件。"""
        as_role("admin", user_id=99)
        resp = client.get(
            "/uploads/1/abc123.jpg", headers={"Authorization": "Bearer test-token"}
        )
        assert resp.status_code == 200
        resp = client.get(
            "/uploads/2/def456.pdf", headers={"Authorization": "Bearer test-token"}
        )
        assert resp.status_code == 200

    def test_private_query_token_fallback(
        self, client: TestClient, mock_upload_dir: Path, as_role
    ):
        """?token= query 参数鉴权 (浏览器原生标签 fallback)。"""
        as_role("user", user_id=1)
        # 不带 Authorization header，仅用 ?token=
        resp = client.get("/uploads/1/abc123.jpg?token=test-token")
        assert resp.status_code == 200
        assert resp.content == b"user1-avatar"

    def test_private_invalid_token_returns_401(
        self, client: TestClient, mock_upload_dir: Path, as_role, monkeypatch
    ):
        """无效 token 返回 401。

        conftest 的 override_user_dependency 默认接受 "test-token"，
        这里通过修改 fixture 使其抛 401，模拟无效 token。
        """
        # 临时移除 override，让真实 get_current_user 处理（会因 token 无效抛 401）
        from app.core.deps import get_current_user
        from app.main import app

        # 保存原 override
        original = app.dependency_overrides.get(get_current_user)
        app.dependency_overrides.pop(get_current_user, None)
        try:
            resp = client.get(
                "/uploads/1/abc123.jpg",
                headers={"Authorization": "Bearer invalid-token-xyz"},
            )
            assert resp.status_code == 401
        finally:
            if original is not None:
                app.dependency_overrides[get_current_user] = original

    def test_private_nonexistent_file_returns_404(
        self, client: TestClient, mock_upload_dir: Path, as_role
    ):
        """用户访问自己目录下不存在的文件返回 404。"""
        as_role("user", user_id=1)
        resp = client.get(
            "/uploads/1/nonexistent.jpg", headers={"Authorization": "Bearer test-token"}
        )
        assert resp.status_code == 404

    def test_private_nonexistent_user_returns_404(
        self, client: TestClient, mock_upload_dir: Path, as_role
    ):
        """访问不存在用户的文件返回 404 (user 角色访问他人) 或 404 (admin 角色文件不存在)。"""
        as_role("user", user_id=1)
        resp = client.get(
            "/uploads/9999/any.jpg", headers={"Authorization": "Bearer test-token"}
        )
        assert resp.status_code == 404


class TestPrivateUploadSecurity:
    """私有文件路径安全测试。"""

    def test_path_traversal_dotdot_blocked(
        self, client: TestClient, mock_upload_dir: Path, as_role
    ):
        """路径遍历 .. 被拦截。"""
        as_role("user", user_id=1)
        # 尝试通过 filename 包含 .. 来逃逸
        # 由于 _SAFE_FILENAME_RE 限制，filename 必须是 UUID.ext 格式
        # 这里直接构造非法 filename
        resp = client.get(
            "/uploads/1/..%2f..%2fetc%2fpasswd",
            headers={"Authorization": "Bearer test-token"},
        )
        # 由于 URL 编码，FastAPI 会解码为 ../../etc/passwd，被 _SAFE_FILENAME_RE 拒绝
        assert resp.status_code in (400, 404)

    def test_null_byte_in_filename_blocked(
        self, client: TestClient, mock_upload_dir: Path, as_role
    ):
        """filename 包含 null 字节被拦截。"""
        as_role("user", user_id=1)
        # httpx 不允许 URL 中包含 null 字节，这里测试 _safe_join 内部逻辑
        from pathlib import Path

        from fastapi import HTTPException

        from app.api.v1.uploads import _safe_join

        with pytest.raises(HTTPException) as exc_info:
            _safe_join(Path("/tmp"), "1", "ab\x00c.jpg")
        assert exc_info.value.status_code == 400

    def test_invalid_filename_rejected(
        self, client: TestClient, mock_upload_dir: Path, as_role
    ):
        """非法文件名格式被拒绝（含路径分隔符、特殊字符等）。"""
        as_role("user", user_id=1)
        # filename 含 /
        resp = client.get(
            "/uploads/1/sub/dir/file.jpg",
            headers={"Authorization": "Bearer test-token"},
        )
        # 由于 filename 是 :path 类型，会接收 sub/dir/file.jpg
        # _SAFE_FILENAME_RE 仅匹配最后一段，但 _safe_join 会限制在 user_id 目录下
        # 应返回 404 (因为 uploads/1/sub/dir/file.jpg 不存在)
        assert resp.status_code in (400, 404)

    def test_filename_with_special_chars_rejected(
        self, client: TestClient, mock_upload_dir: Path, as_role
    ):
        """含特殊字符的文件名被拒绝。"""
        as_role("user", user_id=1)
        # 含空格的文件名
        resp = client.get(
            "/uploads/1/ab c.jpg", headers={"Authorization": "Bearer test-token"}
        )
        assert resp.status_code == 400
        # 含点开头的隐藏文件
        resp = client.get(
            "/uploads/1/.env", headers={"Authorization": "Bearer test-token"}
        )
        assert resp.status_code in (400, 404)


class TestUploadRoutingLogic:
    """路由分发逻辑测试。"""

    def test_non_numeric_non_public_owner_returns_404(
        self, client: TestClient, mock_upload_dir: Path
    ):
        """owner 既不是数字也不在公共白名单 → 404。"""
        resp = client.get("/uploads/foobar/somefile.txt")
        assert resp.status_code == 404

    def test_empty_owner_returns_404(self, client: TestClient, mock_upload_dir: Path):
        """空 owner 路径返回 404。"""
        resp = client.get("/uploads/")
        assert resp.status_code in (404, 405)

    def test_safe_join_allows_normal_path(self, tmp_path: Path):
        """_safe_join 允许正常路径。"""
        from app.api.v1.uploads import _safe_join

        base = tmp_path / "uploads"
        base.mkdir()
        result = _safe_join(base, "1", "abc123.jpg")
        assert result == (base / "1" / "abc123.jpg").resolve()

    def test_safe_join_blocks_dotdot(self, tmp_path: Path):
        """_safe_join 拦截 .. 路径段。"""
        from fastapi import HTTPException

        from app.api.v1.uploads import _safe_join

        base = tmp_path / "uploads"
        base.mkdir()
        with pytest.raises(HTTPException) as exc_info:
            _safe_join(base, "1", "../../../etc/passwd")
        assert exc_info.value.status_code == 400

    def test_safe_join_blocks_null_byte(self, tmp_path: Path):
        """_safe_join 拦截 null 字节。"""
        from fastapi import HTTPException

        from app.api.v1.uploads import _safe_join

        base = tmp_path / "uploads"
        base.mkdir()
        with pytest.raises(HTTPException) as exc_info:
            _safe_join(base, "1", "ab\x00c.jpg")
        assert exc_info.value.status_code == 400

    def test_filename_regex(self):
        """_SAFE_FILENAME_RE 正则匹配测试。"""
        from app.api.v1.uploads import _SAFE_FILENAME_RE

        # 合法文件名
        assert _SAFE_FILENAME_RE.match("abc123.jpg")
        assert _SAFE_FILENAME_RE.match("abcdef123456.png")
        assert _SAFE_FILENAME_RE.match("uuid-1-2-3.pdf")
        assert _SAFE_FILENAME_RE.match("A_B_C.mp3")

        # 非法文件名
        assert not _SAFE_FILENAME_RE.match(".env")  # 点开头
        assert not _SAFE_FILENAME_RE.match("ab c.jpg")  # 含空格
        assert not _SAFE_FILENAME_RE.match("ab/c.jpg")  # 含路径分隔符
        assert not _SAFE_FILENAME_RE.match("ab\\c.jpg")  # 含反斜杠
        assert not _SAFE_FILENAME_RE.match("abc")  # 无扩展名
        assert not _SAFE_FILENAME_RE.match("abc.verylongextension")  # 扩展名过长


class TestUploadDirResolution:
    """upload_dir 解析测试。"""

    def test_resolve_upload_dir_returns_backend_uploads(self):
        """_resolve_upload_dir 返回 backend/uploads/。"""
        from app.api.v1.uploads import _resolve_upload_dir

        result = _resolve_upload_dir()
        # 应该是 backend/uploads/
        assert result.name == "uploads"
        assert result.parent.name == "backend" or result.parent.parent.name == "backend"

    def test_public_dirs_whitelist(self):
        """PUBLIC_DIRS 白名单内容正确。"""
        from app.api.v1.uploads import PUBLIC_DIRS

        assert "audio" in PUBLIC_DIRS
        assert "content" in PUBLIC_DIRS
        # 私有目录不应在白名单
        assert "1" not in PUBLIC_DIRS
        assert "private" not in PUBLIC_DIRS
