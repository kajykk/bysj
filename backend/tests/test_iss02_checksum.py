"""ISS-02 / WF-1: app.utils.checksum 覆盖率补齐（原 0%）。

聚焦 SHA256 侧车校验工具的三个函数：
- ``_compute_sha256``
- ``write_sha256_sidecar``
- ``cleanup_stale_sidecars``
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from app.utils.checksum import (
    _compute_sha256,
    cleanup_stale_sidecars,
    write_sha256_sidecar,
)


def test_compute_sha256_matches_hashlib(tmp_path: Path) -> None:
    f = tmp_path / "data.bin"
    content = b"hello-depression-warning-system"
    f.write_bytes(content)
    got = _compute_sha256(f)
    assert got == hashlib.sha256(content).hexdigest()
    assert len(got) == 64


def test_compute_sha256_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "empty.bin"
    f.write_bytes(b"")
    assert _compute_sha256(f) == hashlib.sha256(b"").hexdigest()


def test_write_sha256_sidecar_creates_file(tmp_path: Path) -> None:
    f = tmp_path / "model.json"
    f.write_text("{}", encoding="utf-8")
    sha = write_sha256_sidecar(f)
    expected = hashlib.sha256(b"{}").hexdigest()
    assert sha == expected
    sidecar = f.with_suffix(f.suffix + ".sha256")  # model.json.sha256
    assert sidecar.exists()
    assert sidecar.read_text(encoding="utf-8") == f"{expected}  model.json\n"


def test_write_sha256_sidecar_accepts_str(tmp_path: Path) -> None:
    f = tmp_path / "weights.bin"
    f.write_bytes(b"x")
    sha = write_sha256_sidecar(str(f))
    assert sha == hashlib.sha256(b"x").hexdigest()
    assert (tmp_path / "weights.bin.sha256").exists()


def test_write_sha256_sidecar_multibyte_content(tmp_path: Path) -> None:
    f = tmp_path / "text.txt"
    content = "抑郁预警系统".encode("utf-8")
    f.write_bytes(content)
    assert write_sha256_sidecar(f) == hashlib.sha256(content).hexdigest()


def test_cleanup_stale_sidecars_removes_orphans(tmp_path: Path) -> None:
    (tmp_path / "model.json").write_text("{}", encoding="utf-8")
    # 匹配侧车（主文件存在）-> 保留
    (tmp_path / "model.json.sha256").write_text("abc  model.json\n", encoding="utf-8")
    # 孤儿侧车（无主文件）-> 删除
    (tmp_path / "old_model.json.sha256").write_text(
        "dead  old_model.json\n", encoding="utf-8"
    )
    removed = cleanup_stale_sidecars(tmp_path)
    assert removed == 1
    assert (tmp_path / "model.json.sha256").exists()
    assert not (tmp_path / "old_model.json.sha256").exists()


def test_cleanup_stale_sidecars_no_orphans(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text("1", encoding="utf-8")
    (tmp_path / "a.json.sha256").write_text("x  a.json\n", encoding="utf-8")
    assert cleanup_stale_sidecars(tmp_path) == 0


def test_cleanup_stale_sidecars_missing_directory(tmp_path: Path) -> None:
    assert cleanup_stale_sidecars(tmp_path / "does_not_exist") == 0
