"""AUDIT-2026-10-06 (P1-5 / P1-4): 上传安全的假闸门测试。

两处都是"实现了但等于没生效"：

- **P1-5 解压炸弹**：`strip_image_exif` 用 `list(img.getdata())` 全量取像素，
  原实现没有任何像素数上限 —— 几百 KB 的构造 PNG 解压后可达 GB 级，
  20MB 上传大小限制形同虚设，单请求即可打爆 worker 内存。
- **P1-4 ClamAV fail-open**：`ERROR` / clamd 不可达 / 任意异常三路都 `return True`，
  而 `enable_clamav_scan` 默认 False —— 病毒扫描在默认部署下完全不生效，
  调用方却拿到 (True, ...) 这个"安全"返回值。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.file_security_service import (
    _MAX_IMAGE_PIXELS,
    scan_with_clamav,
    strip_image_exif,
)


def _write_png(path: Path, size: tuple[int, int]) -> Path:
    """写一张指定尺寸的极小体积 PNG（用纯色，压缩后只有几 KB）。"""
    from PIL import Image

    Image.new("RGB", size, color=(10, 20, 30)).save(path, format="PNG")
    return path


class TestDecompressionBombGuard:
    """像素数上限必须在 getdata() 之前拦下。"""

    def test_normal_image_still_processed(self, tmp_path: Path) -> None:
        """正常照片（2MP）不受影响 —— 防止把功能写死成拒绝一切。"""
        p = _write_png(tmp_path / "ok.png", (1600, 1200))
        safe, msg = strip_image_exif(p)
        assert safe is True, msg
        assert p.exists()

    def test_oversized_image_rejected(self, tmp_path: Path) -> None:
        """超过像素上限的图片被拒绝（而不是先把内存吃光再说）。"""
        # 7000x7000 = 49MP > 25MP 上限；纯色 PNG 压缩后仍只有几十 KB
        p = _write_png(tmp_path / "bomb.png", (7000, 7000))
        assert p.stat().st_size < 200_000, "构造图本身必须足够小，才说明防护有效"
        safe, msg = strip_image_exif(p)
        assert safe is False
        assert "too large" in msg.lower()

    def test_pillow_max_pixels_is_set(self) -> None:
        """Pillow 全局上限必须被设置（第二道防线）。"""
        from PIL import Image

        assert Image.MAX_IMAGE_PIXELS == _MAX_IMAGE_PIXELS


class TestClamavFailClosed:
    """默认 fail-closed：扫不出来 ≠ 干净。"""

    def _file(self, tmp_path: Path) -> Path:
        f = tmp_path / "a.txt"
        f.write_bytes(b"hello")
        return f

    def test_disabled_scan_still_passes(self, tmp_path: Path) -> None:
        """未启用扫描时行为不变（默认关闭，不阻断上传）。"""
        with patch("app.core.config.settings.enable_clamav_scan", False):
            safe, msg = scan_with_clamav(self._file(tmp_path))
        assert safe is True
        assert "disabled" in msg

    def test_error_status_is_not_allowed(self, tmp_path: Path) -> None:
        """clamd 返回 ERROR（"这一条我扫不出来"）不得放行。"""
        fake_clamd = type("C", (), {})()
        inst = type(
            "Inst",
            (),
            {
                "scan": staticmethod(lambda p: {p: ("ERROR", "cannot parse")}),
            },
        )()
        with patch("app.core.config.settings.enable_clamav_scan", True), \
             patch("app.core.config.settings.clamav_fail_open", False), \
             patch.dict("sys.modules", {"clamd": fake_clamd}), \
             patch("clamd.ClamdNetworkSocket", return_value=inst, create=True):
            safe, msg = scan_with_clamav(self._file(tmp_path))
        assert safe is False
        assert "error" in msg.lower()

    def test_found_status_is_blocked(self, tmp_path: Path) -> None:
        """FOUND（命中病毒）必须拒绝 —— 这是原有能力，防回归。"""
        fake_clamd = type("C", (), {})()
        inst = type(
            "Inst",
            (),
            {"scan": staticmethod(lambda p: {p: ("FOUND", "Eicar-Test-Signature")})},
        )()
        with patch("app.core.config.settings.enable_clamav_scan", True), \
             patch.dict("sys.modules", {"clamd": fake_clamd}), \
             patch("clamd.ClamdNetworkSocket", return_value=inst, create=True):
            safe, msg = scan_with_clamav(self._file(tmp_path))
        assert safe is False
        assert "virus" in msg.lower()

    @pytest.mark.parametrize(
        "exc_name", ["ConnectionError", "TimeoutError"]
    )
    def test_daemon_unreachable_is_fail_closed(self, tmp_path: Path, exc_name: str) -> None:
        """clamd 不可达默认拒绝；显式 fail-open 才放行。"""

        class _FakeClamd:
            ConnectionError = ConnectionError
            ClamdNetworkSocket = None
            ClamdUnixSocket = None

        with patch("app.core.config.settings.enable_clamav_scan", True), \
             patch("app.core.config.settings.clamav_fail_open", False), \
             patch.dict("sys.modules", {"clamd": _FakeClamd}), \
             patch("clamd.ClamdNetworkSocket", create=True) as ctor:
            ctor.side_effect = getattr(__builtins__, exc_name, ConnectionError)("down")
            safe, msg = scan_with_clamav(self._file(tmp_path))
        assert safe is False
        assert "unavailable" in msg.lower() or "not reachable" in msg.lower()

    def test_fail_open_opt_in_allows(self, tmp_path: Path) -> None:
        """运维显式承担风险时才放行。"""

        class _FakeClamd:
            ConnectionError = ConnectionError
            ClamdNetworkSocket = None
            ClamdUnixSocket = None

        with patch("app.core.config.settings.enable_clamav_scan", True), \
             patch("app.core.config.settings.clamav_fail_open", True), \
             patch.dict("sys.modules", {"clamd": _FakeClamd}), \
             patch("clamd.ClamdNetworkSocket", create=True) as ctor:
            ctor.side_effect = ConnectionError("down")
            safe, msg = scan_with_clamav(self._file(tmp_path))
        assert safe is True
        assert "fail-open" in msg


class TestConfigDefault:
    def test_clamav_fail_open_defaults_false(self) -> None:
        """默认必须是 fail-closed，否则「默认部署扫描失效」的老问题复发。"""
        from app.core.config import Settings

        assert Settings.model_construct().clamav_fail_open is False
