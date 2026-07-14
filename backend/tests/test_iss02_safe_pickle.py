"""ISS-02 coverage for app.core.safe_pickle (B614-relevant security module).

Focus: exercise every validation branch in safe_pickle without depending on the
heavy `joblib` / `torch` packages. We inject lightweight fake modules into
sys.modules so the real third-party loader calls are intercepted deterministically;
the module's own security logic (path traversal, size cap, hash check, production
enforcement of require_hash / weights_only) is what we actually assert.
"""
from __future__ import annotations

import hashlib
import sys
import types
from pathlib import Path

import pytest

from app.core import safe_pickle


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def fake_loaders(monkeypatch):
    """Inject fake joblib/torch modules; record the torch.load kwargs."""
    calls: dict[str, list] = {"joblib": [], "torch": []}

    fj = types.ModuleType("joblib")

    def _joblib_load(p, **kw):
        calls["joblib"].append(str(p))
        return {"loaded": True, "via": "joblib"}

    fj.load = _joblib_load

    ft = types.ModuleType("torch")

    def _torch_load(p, **kw):
        calls["torch"].append(kw)
        return {"loaded": True, "via": "torch"}

    ft.load = _torch_load

    monkeypatch.setitem(sys.modules, "joblib", fj)
    monkeypatch.setitem(sys.modules, "torch", ft)
    return calls


@pytest.fixture
def failing_loaders(monkeypatch):
    """Fake joblib/torch whose .load raises, to cover the failure wrappers."""
    fj = types.ModuleType("joblib")

    def _joblib_load(p, **kw):
        raise RuntimeError("boom")

    fj.load = _joblib_load

    ft = types.ModuleType("torch")

    def _torch_load(p, **kw):
        raise RuntimeError("boom")

    ft.load = _torch_load

    monkeypatch.setitem(sys.modules, "joblib", fj)
    monkeypatch.setitem(sys.modules, "torch", ft)


@pytest.fixture(autouse=True)
def non_production_settings(monkeypatch):
    """Default to a non-production env so require_hash/weights_only are not forced."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "app_env", "test")
    return settings


def _write_file(path: Path, content: bytes = b"hello-model-bytes") -> str:
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


# --------------------------------------------------------------------------- #
# _compute_sha256
# --------------------------------------------------------------------------- #
def test_compute_sha256_matches_hashlib(tmp_path):
    p = tmp_path / "m.bin"
    data = b"the quick brown fox" * 13
    p.write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()
    assert safe_pickle._compute_sha256(p) == expected


# --------------------------------------------------------------------------- #
# _validate_path
# --------------------------------------------------------------------------- #
def test_validate_path_no_root_returns_resolved(tmp_path):
    p = tmp_path / "m.pkl"
    p.write_bytes(b"x")
    resolved = safe_pickle._validate_path(p)
    assert resolved == p.resolve()


def test_validate_path_under_trusted_root_ok(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    p = root / "sub" / "m.pkl"
    p.parent.mkdir()
    p.write_bytes(b"x")
    resolved = safe_pickle._validate_path(p, trusted_root=root)
    assert resolved == p.resolve()


def test_validate_path_outside_trusted_root_rejected(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    evil = tmp_path / "evil.pkl"
    evil.write_bytes(b"x")
    with pytest.raises(ValueError, match="不在受信目录"):
        safe_pickle._validate_path(evil, trusted_root=root)


def test_validate_path_dotdot_traversal_rejected(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    # a path that resolves outside root via ".."
    p = root / ".." / "escape.pkl"
    with pytest.raises(ValueError, match="不在受信目录"):
        safe_pickle._validate_path(p, trusted_root=root)


def test_validate_path_must_exist_true_missing_raises(tmp_path):
    p = tmp_path / "missing.pkl"
    with pytest.raises(FileNotFoundError):
        safe_pickle._validate_path(p, must_exist=True)


def test_validate_path_must_exist_false_missing_ok(tmp_path):
    p = tmp_path / "missing.pkl"
    resolved = safe_pickle._validate_path(p, trusted_root=None, must_exist=False)
    assert resolved == p.resolve()


# --------------------------------------------------------------------------- #
# _validate_size
# --------------------------------------------------------------------------- #
def test_validate_size_ok(tmp_path):
    p = tmp_path / "m.pkl"
    content = b"abcdef"
    p.write_bytes(content)
    assert safe_pickle._validate_size(p) == len(content)


def test_validate_size_empty_rejected(tmp_path):
    p = tmp_path / "m.pkl"
    p.write_bytes(b"")
    with pytest.raises(ValueError, match="模型文件为空"):
        safe_pickle._validate_size(p)


def test_validate_size_too_large_rejected(tmp_path):
    p = tmp_path / "m.pkl"
    p.write_bytes(b"abcdef")
    with pytest.raises(ValueError, match="模型文件过大"):
        safe_pickle._validate_size(p, max_bytes=3)


# --------------------------------------------------------------------------- #
# safe_joblib_load
# --------------------------------------------------------------------------- #
def test_joblib_load_success_no_hash(tmp_path, fake_loaders):
    p = tmp_path / "m.joblib"
    _write_file(p)
    result = safe_pickle.safe_joblib_load(p, require_hash=False)
    assert result == {"loaded": True, "via": "joblib"}
    assert fake_loaders["joblib"] == [str(p.resolve())]


def test_joblib_load_require_hash_from_sha256_file(tmp_path, fake_loaders):
    p = tmp_path / "m.joblib"
    h = _write_file(p)
    (tmp_path / "m.joblib.sha256").write_text(f"{h}  m.joblib\n")
    result = safe_pickle.safe_joblib_load(p, require_hash=True)
    assert result == {"loaded": True, "via": "joblib"}


def test_joblib_load_expected_hash_match(tmp_path, fake_loaders):
    p = tmp_path / "m.joblib"
    h = _write_file(p)
    result = safe_pickle.safe_joblib_load(p, expected_hash=h, require_hash=False)
    assert result == {"loaded": True, "via": "joblib"}


def test_joblib_load_expected_hash_mismatch(tmp_path):
    p = tmp_path / "m.joblib"
    _write_file(p)
    with pytest.raises(ValueError, match="哈希校验失败"):
        safe_pickle.safe_joblib_load(p, expected_hash="deadbeef" * 8, require_hash=False)


def test_joblib_load_require_hash_without_source_raises(tmp_path):
    p = tmp_path / "m.joblib"
    _write_file(p)
    with pytest.raises(ValueError, match="要求哈希校验但未提供"):
        safe_pickle.safe_joblib_load(p, require_hash=True)


def test_joblib_load_require_hash_false_in_production_forced(tmp_path, monkeypatch, fake_loaders):
    from app.core.config import settings

    monkeypatch.setattr(settings, "app_env", "production")
    p = tmp_path / "m.joblib"
    _write_file(p)
    # caller passes require_hash=False, but production must force it -> no hash -> error
    with pytest.raises(ValueError, match="要求哈希校验但未提供"):
        safe_pickle.safe_joblib_load(p, require_hash=False)


def test_joblib_load_path_traversal_rejected(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    evil = tmp_path / "evil.joblib"
    _write_file(evil)
    with pytest.raises(ValueError, match="不在受信目录"):
        safe_pickle.safe_joblib_load(evil, trusted_root=root, require_hash=False)


def test_joblib_load_deserialize_failure_wrapped(tmp_path, failing_loaders):
    p = tmp_path / "m.joblib"
    _write_file(p)
    with pytest.raises(ValueError, match="反序列化失败"):
        safe_pickle.safe_joblib_load(p, require_hash=False)


# --------------------------------------------------------------------------- #
# safe_torch_load
# --------------------------------------------------------------------------- #
def test_torch_load_success_weights_only(tmp_path, fake_loaders):
    p = tmp_path / "ckpt.pt"
    _write_file(p)
    result = safe_pickle.safe_torch_load(p, weights_only=True, require_hash=False)
    assert result == {"loaded": True, "via": "torch"}
    assert fake_loaders["torch"][0]["weights_only"] is True


def test_torch_load_expected_hash_match(tmp_path, fake_loaders):
    p = tmp_path / "ckpt.pt"
    h = _write_file(p)
    result = safe_pickle.safe_torch_load(p, expected_hash=h, require_hash=False)
    assert result == {"loaded": True, "via": "torch"}


def test_torch_load_expected_hash_mismatch(tmp_path):
    p = tmp_path / "ckpt.pt"
    _write_file(p)
    with pytest.raises(ValueError, match="哈希校验失败"):
        safe_pickle.safe_torch_load(p, expected_hash="deadbeef" * 8, require_hash=False)


def test_torch_load_require_hash_from_sha256_file(tmp_path, fake_loaders):
    p = tmp_path / "ckpt.pt"
    h = _write_file(p)
    (tmp_path / "ckpt.pt.sha256").write_text(h)
    result = safe_pickle.safe_torch_load(p, require_hash=True)
    assert result == {"loaded": True, "via": "torch"}


def test_torch_load_require_hash_without_source_raises(tmp_path):
    p = tmp_path / "ckpt.pt"
    _write_file(p)
    with pytest.raises(ValueError, match="要求哈希校验但未提供"):
        safe_pickle.safe_torch_load(p, require_hash=True)


def test_torch_load_weights_only_false_in_production_forced(tmp_path, monkeypatch, fake_loaders):
    from app.core.config import settings

    monkeypatch.setattr(settings, "app_env", "production")
    p = tmp_path / "ckpt.pt"
    _write_file(p)
    # caller passes weights_only=False; production must force True
    safe_pickle.safe_torch_load(p, weights_only=False, require_hash=False)
    assert fake_loaders["torch"][0]["weights_only"] is True


def test_torch_load_path_traversal_rejected(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    evil = tmp_path / "evil.pt"
    _write_file(evil)
    with pytest.raises(ValueError, match="不在受信目录"):
        safe_pickle.safe_torch_load(evil, trusted_root=root, require_hash=False)


def test_torch_load_failure_wrapped(tmp_path, failing_loaders):
    p = tmp_path / "ckpt.pt"
    _write_file(p)
    with pytest.raises(ValueError, match="加载失败"):
        safe_pickle.safe_torch_load(p, require_hash=False)
