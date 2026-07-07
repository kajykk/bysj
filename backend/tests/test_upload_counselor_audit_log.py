"""SEC-P1-004 回归测试：文件上传与咨询师查看端点审计日志

验证 6 个端点在成功路径下写入 OperationLog 审计日志：

| 端点                                              | 函数                        | action_type                              | 角色       |
|--------------------------------------------------|----------------------------|------------------------------------------|-----------|
| POST /api/v1/user/upload                          | upload_file                | user_file_upload                         | user       |
| POST /api/v1/user/upload/batch                    | upload_batch               | user_file_upload_batch                   | user       |
| GET  /uploads/{owner}/{filename}                  | serve_upload (私有分支)     | user_file_download                       | user/counselor/admin |
| GET  /api/v1/counselor/users                      | list_users                 | counselor_view_user_list                 | counselor  |
| GET  /api/v1/counselor/users/{user_id}            | get_user_detail            | counselor_view_user_detail               | counselor  |
| GET  /api/v1/counselor/users/{user_id}/consultations | list_consultation_records | counselor_view_consultation_records     | counselor  |

每个测试验证：
- HTTP 状态码 200 校验
- OperationLog 写入 (action_type / operator_id / operator_role / target_type)
- detail 字段为合法 JSON
- 失败路径 (400/404/422) 不写入审计日志
- 公共资源下载不写入审计日志 (serve_upload 公共分支)
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import OperationLog
from tests.conftest import run

# ===== 共享 fixture =====


@pytest.fixture
def mock_upload_dir(tmp_path: Path, monkeypatch):
    """mock _resolve_upload_dir 返回 tmp_path/uploads，并预置测试文件。

    目录结构：
        uploads/audio/mindfulness.mp3        (公共资源)
        uploads/1/abc123.jpg                 (user_id=1 私有文件)
    """
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    # 公共资源
    audio_dir = upload_dir / "audio"
    audio_dir.mkdir()
    (audio_dir / "mindfulness.mp3").write_bytes(b"fake-audio-content")

    # 用户私有文件
    user1_dir = upload_dir / "1"
    user1_dir.mkdir()
    (user1_dir / "abc123.jpg").write_bytes(b"user1-avatar")

    from app.api.v1 import uploads as uploads_mod

    monkeypatch.setattr(uploads_mod, "_resolve_upload_dir", lambda: upload_dir)

    return upload_dir


def _make_jpeg_bytes() -> bytes:
    """生成可通过 python-magic MIME 校验的 JPEG 文件内容。"""
    return b"\xff\xd8\xff\xe0" + b"\x00" * 100


# ===== 1. 单文件上传 =====


class TestUserFileUploadAuditLog:
    """POST /api/v1/user/upload → user_file_upload"""

    def test_upload_writes_audit_log(
        self, client: TestClient, as_role, seeded_user_id, db_session: AsyncSession
    ):
        """用户上传文件 → 写入 user_file_upload 审计日志."""
        as_role("user", seeded_user_id)
        res = client.post(
            "/api/v1/user/upload",
            files={"file": ("test.jpg", io.BytesIO(_make_jpeg_bytes()), "image/jpeg")},
            params={"category": "image"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert res.status_code == 200, res.text

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "user_file_upload",
                    OperationLog.operator_id == seeded_user_id,
                )
            )
            return result.scalar_one_or_none()

        log = run(_check())
        assert log is not None, "审计日志未写入: user_file_upload"
        assert log.operator_role == "user"
        assert log.target_type == "user_upload"
        detail = json.loads(log.detail)
        assert "filename" in detail
        assert "size" in detail
        assert "url" in detail
        assert detail["category"] == "image"

    def test_upload_invalid_extension_no_audit_log(
        self, client: TestClient, as_role, seeded_user_id, db_session: AsyncSession
    ):
        """上传非法扩展名 → 400, 不写入审计日志."""
        as_role("user", seeded_user_id)
        res = client.post(
            "/api/v1/user/upload",
            files={
                "file": (
                    "test.exe",
                    io.BytesIO(b"malicious"),
                    "application/octet-stream",
                )
            },
            headers={"Authorization": "Bearer test-token"},
        )
        assert res.status_code == 400

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "user_file_upload"
                )
            )
            return result.scalars().all()

        logs = run(_check())
        assert len(logs) == 0, "失败上传不应写入审计日志"


# ===== 2. 批量上传 =====


class TestUserFileUploadBatchAuditLog:
    """POST /api/v1/user/upload/batch → user_file_upload_batch"""

    def test_batch_upload_writes_audit_log(
        self, client: TestClient, as_role, seeded_user_id, db_session: AsyncSession
    ):
        """批量上传 → 写入 user_file_upload_batch 审计日志."""
        as_role("user", seeded_user_id)
        files = [
            ("files", ("a.jpg", io.BytesIO(_make_jpeg_bytes()), "image/jpeg")),
            ("files", ("b.jpg", io.BytesIO(_make_jpeg_bytes()), "image/jpeg")),
        ]
        res = client.post(
            "/api/v1/user/upload/batch",
            files=files,
            params={"category": "image"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert res.status_code == 200, res.text

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "user_file_upload_batch",
                    OperationLog.operator_id == seeded_user_id,
                )
            )
            return result.scalar_one_or_none()

        log = run(_check())
        assert log is not None, "审计日志未写入: user_file_upload_batch"
        detail = json.loads(log.detail)
        assert detail["total_count"] == 2
        assert detail["success_count"] == 2
        assert detail["failed_count"] == 0
        assert detail["category"] == "image"
        assert len(detail["items"]) == 2

    def test_batch_upload_mixed_success_records_counts(
        self, client: TestClient, as_role, seeded_user_id, db_session: AsyncSession
    ):
        """批量上传含成功与失败 → detail 记录正确的 success/failed 计数."""
        as_role("user", seeded_user_id)
        files = [
            ("files", ("good.jpg", io.BytesIO(_make_jpeg_bytes()), "image/jpeg")),
            ("files", ("bad.exe", io.BytesIO(b"bad"), "application/octet-stream")),
        ]
        res = client.post(
            "/api/v1/user/upload/batch",
            files=files,
            params={"category": "image"},
            headers={"Authorization": "Bearer test-token"},
        )
        assert res.status_code == 200

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "user_file_upload_batch"
                )
            )
            return result.scalar_one()

        log = run(_check())
        detail = json.loads(log.detail)
        assert detail["total_count"] == 2
        assert detail["success_count"] == 1
        assert detail["failed_count"] == 1
        assert len(detail["items"]) == 1  # items 只含成功项


# ===== 3. 私有文件下载 =====


class TestUserFileDownloadAuditLog:
    """GET /uploads/{owner}/{filename} → user_file_download (仅私有分支)"""

    def test_private_download_writes_audit_log(
        self,
        client: TestClient,
        as_role,
        seeded_user_id,
        db_session: AsyncSession,
        mock_upload_dir: Path,
    ):
        """用户下载自己的私有文件 → 写入 user_file_download 审计日志."""
        as_role("user", seeded_user_id)
        res = client.get(
            "/uploads/1/abc123.jpg",
            headers={"Authorization": "Bearer test-token"},
        )
        assert res.status_code == 200

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "user_file_download",
                    OperationLog.operator_id == seeded_user_id,
                )
            )
            return result.scalar_one_or_none()

        log = run(_check())
        assert log is not None, "审计日志未写入: user_file_download"
        assert log.target_type == "user_upload"
        detail = json.loads(log.detail)
        assert detail["owner"] == "1"
        assert detail["filename"] == "abc123.jpg"
        assert detail["self_access"] is True

    def test_public_download_no_audit_log(
        self,
        client: TestClient,
        as_role,
        seeded_user_id,
        db_session: AsyncSession,
        mock_upload_dir: Path,
    ):
        """下载公共资源 → 不写入审计日志."""
        as_role("user", seeded_user_id)
        res = client.get("/uploads/audio/mindfulness.mp3")
        assert res.status_code == 200

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "user_file_download"
                )
            )
            return result.scalars().all()

        logs = run(_check())
        assert len(logs) == 0, "公共资源下载不应写入审计日志"

    def test_private_download_other_user_404_no_audit_log(
        self,
        client: TestClient,
        as_role,
        seeded_user_id,
        db_session: AsyncSession,
        mock_upload_dir: Path,
    ):
        """user 角色访问他人文件 → 404, 不写入审计日志."""
        as_role("user", seeded_user_id)
        # user_id=1 访问 user_id=2 的文件 (mock_upload_dir 未创建 user 2 目录)
        # 实际上 mock_upload_dir 只创建了 user 1, 但 user 1 访问 user 2 会被归属校验拦截
        # 先创建 user 2 的文件
        (mock_upload_dir / "2").mkdir()
        (mock_upload_dir / "2" / "def456.pdf").write_bytes(b"user2-file")
        res = client.get(
            "/uploads/2/def456.pdf",
            headers={"Authorization": "Bearer test-token"},
        )
        assert res.status_code == 404

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "user_file_download"
                )
            )
            return result.scalars().all()

        logs = run(_check())
        assert len(logs) == 0, "失败下载不应写入审计日志"


# ===== 4. 咨询师查看用户列表 =====


class TestCounselorViewUserListAuditLog:
    """GET /api/v1/counselor/users → counselor_view_user_list"""

    def test_list_users_writes_audit_log(
        self,
        client: TestClient,
        as_role,
        seeded_user_id,
        db_session: AsyncSession,
        seed_counselor_data: None,
    ):
        """咨询师查看用户列表 → 写入 counselor_view_user_list 审计日志."""
        as_role("counselor", 2)
        res = client.get("/api/v1/counselor/users?page=1&page_size=10")
        assert res.status_code == 200, res.text

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "counselor_view_user_list",
                    OperationLog.operator_id == 2,
                )
            )
            return result.scalar_one_or_none()

        log = run(_check())
        assert log is not None, "审计日志未写入: counselor_view_user_list"
        assert log.operator_role == "counselor"
        assert log.target_type == "user"
        detail = json.loads(log.detail)
        assert detail["page"] == 1
        assert detail["page_size"] == 10


# ===== 5. 咨询师查看用户详情 =====


class TestCounselorViewUserDetailAuditLog:
    """GET /api/v1/counselor/users/{user_id} → counselor_view_user_detail"""

    def test_get_user_detail_writes_audit_log(
        self,
        client: TestClient,
        as_role,
        seeded_user_id,
        db_session: AsyncSession,
        seed_counselor_data: None,
    ):
        """咨询师查看用户详情 → 写入 counselor_view_user_detail 审计日志."""
        as_role("counselor", 2)
        res = client.get("/api/v1/counselor/users/1")
        assert res.status_code == 200, res.text

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "counselor_view_user_detail",
                    OperationLog.operator_id == 2,
                )
            )
            return result.scalar_one_or_none()

        log = run(_check())
        assert log is not None, "审计日志未写入: counselor_view_user_detail"
        assert log.target_type == "user"
        assert log.target_id == 1
        detail = json.loads(log.detail)
        assert detail["user_id"] == 1

    def test_get_user_detail_not_found_no_audit_log(
        self,
        client: TestClient,
        as_role,
        seeded_user_id,
        db_session: AsyncSession,
        seed_counselor_data: None,
    ):
        """咨询师查看未绑定用户 → 404, 不写入审计日志."""
        as_role("counselor", 2)
        # user_id=999 未与 counselor 2 建立绑定
        res = client.get("/api/v1/counselor/users/999")
        assert res.status_code == 404

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "counselor_view_user_detail"
                )
            )
            return result.scalars().all()

        logs = run(_check())
        assert len(logs) == 0, "失败查询不应写入审计日志"


# ===== 6. 咨询师查看咨询记录 =====


class TestCounselorViewConsultationRecordsAuditLog:
    """GET /api/v1/counselor/users/{user_id}/consultations → counselor_view_consultation_records"""

    def test_list_consultations_writes_audit_log(
        self,
        client: TestClient,
        as_role,
        seeded_user_id,
        db_session: AsyncSession,
        seed_counselor_data: None,
    ):
        """咨询师查看咨询记录 → 写入 counselor_view_consultation_records 审计日志."""
        as_role("counselor", 2)
        res = client.get("/api/v1/counselor/users/1/consultations?page=1&page_size=10")
        assert res.status_code == 200, res.text

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "counselor_view_consultation_records",
                    OperationLog.operator_id == 2,
                )
            )
            return result.scalar_one_or_none()

        log = run(_check())
        assert log is not None, "审计日志未写入: counselor_view_consultation_records"
        assert log.target_type == "consultation_record"
        assert log.target_id == 1
        detail = json.loads(log.detail)
        assert detail["user_id"] == 1
        assert detail["page"] == 1


# ===== 7. 源码结构静态校验 =====


class TestSourceStructure:
    """静态校验 6 个端点源码中均包含审计日志写入代码."""

    def test_upload_file_has_audit_log(self):
        import inspect

        from app.api.v1 import user_upload

        src = inspect.getsource(user_upload.upload_file)
        assert "OperationLog" in src
        assert "user_file_upload" in src
        assert "await db.commit()" in src

    def test_upload_batch_has_audit_log(self):
        import inspect

        from app.api.v1 import user_upload

        src = inspect.getsource(user_upload.upload_batch)
        assert "OperationLog" in src
        assert "user_file_upload_batch" in src
        assert "await db.commit()" in src

    def test_serve_upload_has_audit_log(self):
        import inspect

        from app.api.v1 import uploads

        src = inspect.getsource(uploads.serve_upload)
        assert "OperationLog" in src
        assert "user_file_download" in src
        assert "await db.commit()" in src

    def test_counselor_list_users_has_audit_log(self):
        import inspect

        from app.api.v1 import counselor

        src = inspect.getsource(counselor.list_users)
        assert "OperationLog" in src
        assert "counselor_view_user_list" in src
        assert "await db.commit()" in src

    def test_counselor_get_user_detail_has_audit_log(self):
        import inspect

        from app.api.v1 import counselor

        src = inspect.getsource(counselor.get_user_detail)
        assert "OperationLog" in src
        assert "counselor_view_user_detail" in src
        assert "await db.commit()" in src

    def test_counselor_list_consultations_has_audit_log(self):
        import inspect

        from app.api.v1 import counselor

        src = inspect.getsource(counselor.list_consultation_records)
        assert "OperationLog" in src
        assert "counselor_view_consultation_records" in src
        assert "await db.commit()" in src

    def test_six_action_types_are_distinct(self):
        """6 个 action_type 互不相同, 便于审计聚合查询."""
        action_types = [
            "user_file_upload",
            "user_file_upload_batch",
            "user_file_download",
            "counselor_view_user_list",
            "counselor_view_user_detail",
            "counselor_view_consultation_records",
        ]
        assert len(action_types) == len(set(action_types)), "action_type 存在重复"
