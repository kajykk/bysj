"""文件上传安全测试"""
import pytest
from fastapi.testclient import TestClient
from io import BytesIO


class TestUploadSecurity:
    """文件上传安全测试"""

    def test_upload_valid_image(self, client: TestClient, auth_headers: dict):
        """测试有效图片上传"""
        # 创建一个简单的JPEG文件头
        data = {
            "file": ("test.jpg", BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 100), "image/jpeg")
        }
        response = client.post("/api/v1/user/upload", files=data, headers=auth_headers)
        assert response.status_code == 200

    def test_upload_invalid_extension(self, client: TestClient, auth_headers: dict):
        """测试非法扩展名被拒绝"""
        data = {
            "file": ("test.exe", BytesIO(b"malicious content"), "application/octet-stream")
        }
        response = client.post("/api/v1/user/upload", files=data, headers=auth_headers)
        assert response.status_code == 400

    def test_upload_oversized_file(self, client: TestClient, auth_headers: dict):
        """测试超大文件被拒绝"""
        # 21MB的数据
        large_content = b"x" * (21 * 1024 * 1024)
        data = {
            "file": ("large.jpg", BytesIO(large_content), "image/jpeg")
        }
        response = client.post("/api/v1/user/upload", files=data, headers=auth_headers)
        assert response.status_code == 400 or response.status_code == 413

    def test_upload_path_traversal(self, client: TestClient, auth_headers: dict):
        """测试路径遍历攻击 (v1.31: 接受 200/400, 验证路径分隔符被剥离)."""
        data = {
            "file": ("../../../etc/passwd.jpg", BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 100), "image/jpeg")
        }
        response = client.post("/api/v1/user/upload", files=data, headers=auth_headers)
        # v1.31: 接受 200 (有效图片) 或 400 (无效内容), 关键是不应出现路径注入
        assert response.status_code in (200, 400, 422)
        if response.status_code == 200:
            result = response.json()
            assert "/" not in result["data"]["filename"]
            assert "\\" not in result["data"]["filename"]

    def test_upload_batch_limit(self, client: TestClient, auth_headers: dict):
        """测试批量上传数量限制"""
        # 创建11个文件（超过限制的10个）
        files = []
        for i in range(11):
            files.append(
                ("files", (f"test{i}.jpg", BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 100), "image/jpeg"))
            )
        response = client.post("/api/v1/user/upload/batch", files=files, headers=auth_headers)
        assert response.status_code == 400
