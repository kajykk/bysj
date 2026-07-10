"""Tests for app/utils/checksum.py.

Covers SHA256 sidecar generation used by model save/load flows.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from app.utils.checksum import _compute_sha256, write_sha256_sidecar


class TestComputeSha256:
    """Test _compute_sha256 internal helper."""

    def test_compute_sha256_small_file(self, tmp_path: Path) -> None:
        """Small file SHA256 should match hashlib directly."""
        target = tmp_path / "small.bin"
        target.write_bytes(b"hello world")

        result = _compute_sha256(target)
        expected = hashlib.sha256(b"hello world").hexdigest()

        assert result == expected
        assert len(result) == 64  # SHA256 hex length

    def test_compute_sha256_empty_file(self, tmp_path: Path) -> None:
        """Empty file should produce SHA256 of empty bytes."""
        target = tmp_path / "empty.bin"
        target.write_bytes(b"")

        result = _compute_sha256(target)
        expected = hashlib.sha256(b"").hexdigest()

        assert result == expected

    def test_compute_sha256_large_file_uses_chunks(self, tmp_path: Path) -> None:
        """File larger than 8192 bytes should still produce correct hash (multi-chunk)."""
        target = tmp_path / "large.bin"
        # 20000 bytes > 8192 chunk size used in _compute_sha256
        payload = b"x" * 20000
        target.write_bytes(payload)

        result = _compute_sha256(target)
        expected = hashlib.sha256(payload).hexdigest()

        assert result == expected


class TestWriteSha256Sidecar:
    """Test write_sha256_sidecar public function."""

    def test_writes_sidecar_file_with_correct_format(self, tmp_path: Path) -> None:
        """Sidecar file should contain '<sha256>  <filename>\\n' (sha256sum format)."""
        target = tmp_path / "model.pkl"
        target.write_bytes(b"binary content")

        sha = write_sha256_sidecar(target)

        sidecar = tmp_path / "model.pkl.sha256"
        assert sidecar.exists()
        content = sidecar.read_text(encoding="utf-8")
        expected_hash = hashlib.sha256(b"binary content").hexdigest()
        # Format: "<sha256>  <filename>\n" (two spaces, matching sha256sum output)
        assert content == f"{expected_hash}  {target.name}\n"
        assert sha == expected_hash

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        """Should accept str path (not only Path)."""
        target = tmp_path / "data.json"
        target.write_bytes(b"{}")

        result = write_sha256_sidecar(str(target))

        sidecar = tmp_path / "data.json.sha256"
        assert sidecar.exists()
        assert result == hashlib.sha256(b"{}").hexdigest()

    def test_returns_sha256_of_input_file(self, tmp_path: Path) -> None:
        """Return value should be the SHA256 of the source file."""
        target = tmp_path / "artifact.bin"
        payload = b"\x00\x01\x02\x03"
        target.write_bytes(payload)

        result = write_sha256_sidecar(target)

        assert result == hashlib.sha256(payload).hexdigest()
