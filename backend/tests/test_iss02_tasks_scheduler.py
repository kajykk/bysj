"""ISS-02 第七轮: app.tasks.scheduler 纯逻辑聚焦测试.

覆盖点:
- _to_aware_utc (naive datetime → aware UTC 归一化)
- _cleanup_uploads_dir_impl (RES-P1-006 过期文件清理: 公共/非数字目录跳过, 旧文件删除, 空目录移除)
- _cleanup_experiment_artifacts_impl (RES-P1-007 训练产物保留最近 N 个, active 模型跳过)
通过 monkeypatch 注入临时目录与配置, 不依赖真实 uploads/ 配置或 model_registry.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta, timezone

from app.tasks.scheduler import (
    _cleanup_experiment_artifacts_impl,
    _cleanup_uploads_dir_impl,
    _to_aware_utc,
)


# ===== _to_aware_utc =====
def test_to_aware_utc_naive_becomes_utc():
    dt = datetime(2026, 1, 1, 12, 0, 0)  # naive
    out = _to_aware_utc(dt)
    assert out.tzinfo == timezone.utc
    assert out.year == 2026 and out.hour == 12


def test_to_aware_utc_aware_utc_unchanged():
    dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    out = _to_aware_utc(dt)
    assert out is dt


def test_to_aware_utc_aware_other_tz_unchanged():
    tz = timezone(timedelta(hours=8))
    dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=tz)
    out = _to_aware_utc(dt)
    assert out is dt
    assert out.tzinfo == tz


# ===== _cleanup_uploads_dir_impl (RES-P1-006) =====
def test_cleanup_uploads_removes_old_user_files(tmp_path, monkeypatch):
    base = tmp_path / "uploads"
    base.mkdir()
    (base / "audio").mkdir()      # 公共目录, 跳过
    (base / "content").mkdir()    # 公共目录, 跳过
    old_dir = base / "999"
    old_dir.mkdir()
    old_file = old_dir / "old.txt"
    old_file.write_text("x")
    non_digit = base / "abc"      # 非数字目录, 整体跳过
    non_digit.mkdir()
    (non_digit / "old.txt").write_text("x")
    new_dir = base / "100"
    new_dir.mkdir()
    new_file = new_dir / "new.txt"
    new_file.write_text("x")

    old_ts = (datetime.now() - timedelta(days=60)).timestamp()
    now_ts = datetime.now().timestamp()
    os.utime(old_file, (old_ts, old_ts))
    os.utime(new_file, (now_ts, now_ts))

    monkeypatch.setattr("app.api.v1.uploads._resolve_upload_dir", lambda: base)
    monkeypatch.setattr("app.api.v1.uploads.PUBLIC_DIRS", frozenset({"audio", "content"}))

    removed = _cleanup_uploads_dir_impl(max_age_days=30)

    assert removed == 1
    assert not old_file.exists()
    assert not old_dir.exists()                       # 空目录被移除
    assert new_file.exists()                          # 近期文件保留
    assert (base / "audio").exists()                  # 公共目录保留
    assert (base / "content").exists()
    assert (non_digit / "old.txt").exists()           # 非数字目录跳过, 文件保留


def test_cleanup_uploads_missing_dir_returns_zero(tmp_path, monkeypatch):
    missing = tmp_path / "does_not_exist"
    monkeypatch.setattr("app.api.v1.uploads._resolve_upload_dir", lambda: missing)
    monkeypatch.setattr("app.api.v1.uploads.PUBLIC_DIRS", frozenset({"audio", "content"}))
    assert _cleanup_uploads_dir_impl() == 0


# ===== _cleanup_experiment_artifacts_impl (RES-P1-007) =====
def test_cleanup_experiment_artifacts_keeps_recent(tmp_path, monkeypatch):
    trained = tmp_path / "trained"
    trained.mkdir()
    base_ts = datetime.now().timestamp()
    # 12 个目录, d00 mtime 最新, d11 最旧
    for i in range(12):
        d = trained / f"d{i:02d}"
        d.mkdir()
        (d / "m.bin").write_text("x")
        ts = base_ts - i * 60
        os.utime(d, (ts, ts))

    monkeypatch.setattr("app.core.config.settings.model_dir", str(tmp_path))
    # d11 内的文件被注册为 active 模型 → 应跳过重删
    monkeypatch.setattr(
        "app.core.model_registry.MODEL_PATHS",
        {"am": str(trained / "d11" / "m.bin")},
    )

    removed = _cleanup_experiment_artifacts_impl(keep_recent=10)

    # to_remove = d10, d11 (最旧 2 个); d11 含 active 文件 → 跳过 → removed==1
    assert removed == 1
    assert not (trained / "d10").exists()
    assert (trained / "d11").exists()
    assert (trained / "d00").exists()  # 最新保留


def test_cleanup_experiment_artifacts_under_limit_returns_zero(tmp_path, monkeypatch):
    trained = tmp_path / "trained"
    trained.mkdir()
    for i in range(3):
        d = trained / f"d{i:02d}"
        d.mkdir()
        (d / "m.bin").write_text("x")

    monkeypatch.setattr("app.core.config.settings.model_dir", str(tmp_path))
    monkeypatch.setattr("app.core.model_registry.MODEL_PATHS", {})

    assert _cleanup_experiment_artifacts_impl(keep_recent=10) == 0
