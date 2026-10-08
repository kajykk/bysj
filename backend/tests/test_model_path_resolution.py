"""模型路径解析防复发闸门 (2026-10-09).

背景（实测，非推测）:
    `settings.model_dir` 默认值为相对路径 ``"models"``，于是
    ``Path("models").parent == Path(".")``，使 ``LoadingMixin._abs_path`` 里
    原本「显式配置优先」的候选 1 退化成 **CWD 相对路径并被排在最前**，
    与代码注释声明的「CWD 相对路径垫底」恰好相反。后果：

        CWD=仓库根   models/keras/*_best.keras -> 命中仓库根影子目录 (2026-02 产物)
        CWD=backend  同一批 registry 路径      -> MISSING (回退启发式)

    即同一份代码、同一份 registry，fusion 是否加载 TF 权重取决于启动目录。
    部署侧权威源是 ``backend/models/``（backend/Dockerfile:197
    ``COPY models/ /app/models/``，compose 挂 ``./backend/models`` 且
    ``MODEL_DIR=/app/models`` 为绝对路径），故相对路径一律以 backend_root 为锚，
    且不再保留 CWD 相对兜底（它是影子目录唯一的加载入口）。

本模块用 tmp_path 自建"影子根目录"，因此**不依赖仓库里那份未入库的
models/ 是否存在** —— 改前必红、改后必绿，在 CI（仓库根 models/ 不存在）
下同样有效。
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.model_engine import loading as loading_mod
from app.core.model_engine.loading import LoadingMixin

BACKEND_ROOT = Path(loading_mod.__file__).resolve().parents[3]
REPO_ROOT = BACKEND_ROOT.parent

# 统一用 unbound 调用: _abs_path 不使用任何实例属性
_abs_path = LoadingMixin._abs_path


@pytest.fixture
def restore_model_dir():
    """保护 settings.model_dir，避免用例间互相污染。"""
    original = settings.model_dir
    yield
    settings.model_dir = original


def test_abs_path_must_not_resolve_into_cwd_shadow(tmp_path, monkeypatch, restore_model_dir):
    """核心闸门：CWD 下的"影子 models/"不得被命中。

    改前会命中（候选 1 退化为 CWD 相对且排第一），改后必须回落到受控目录。
    """
    shadow = tmp_path / "models" / "fake_shadow.pkl"
    shadow.parent.mkdir(parents=True, exist_ok=True)
    shadow.write_bytes(b"shadow")

    monkeypatch.chdir(tmp_path)

    resolved = _abs_path(None, "models/fake_shadow.pkl")

    assert resolved != shadow, (
        f"_abs_path 命中了 CWD 下的影子产物 {shadow}；模型来源必须受控于 model_dir / backend_root，不得随启动目录漂移"
    )
    assert resolved == BACKEND_ROOT / "models" / "fake_shadow.pkl"


def test_abs_path_stable_across_cwd(tmp_path, monkeypatch, restore_model_dir):
    """同一 registry 路径在"有影子"与"无影子"的 CWD 下必须解析到同一结果。

    注意：不能拿三个"都不存在"的 CWD 来比 —— 那种写法改前也会绿（三者都回落
    到同一个 candidate[0]），是假闸门。必须让其中一个 CWD 真的存在同名影子文件。
    """
    rel = "models/fake_stable.pkl"

    with_shadow = tmp_path / "with_shadow"
    (with_shadow / "models").mkdir(parents=True)
    (with_shadow / "models" / "fake_stable.pkl").write_bytes(b"shadow")

    no_shadow = tmp_path / "no_shadow"
    no_shadow.mkdir()

    monkeypatch.chdir(with_shadow)
    from_shadow = _abs_path(None, rel)

    monkeypatch.chdir(no_shadow)
    from_plain = _abs_path(None, rel)

    assert from_shadow == from_plain, (
        f"解析结果随 CWD 漂移: 有影子={from_shadow} 无影子={from_plain}；模型来源不得受启动目录是否存在同名文件影响"
    )
    assert from_shadow == BACKEND_ROOT / "models" / "fake_stable.pkl"


def test_abs_path_absolute_model_dir_unchanged(tmp_path, monkeypatch, restore_model_dir):
    """生产口径闸门：MODEL_DIR 为绝对路径时，解析结果必须仍是该目录下的文件。

    生产 compose 设 ``MODEL_DIR=/app/models``，此用例保证本修复不影响部署路径。
    """
    abs_dir = tmp_path / "app" / "models"
    abs_dir.mkdir(parents=True)
    target = abs_dir / "prod_model.pkl"
    target.write_bytes(b"prod")

    monkeypatch.setattr(settings, "model_dir", str(tmp_path / "app" / "models"))

    # raw 以 "models" 开头: 候选 1 为 model_dir.parent / raw
    assert _abs_path(None, "models/prod_model.pkl") == target
    # raw 不以 "models" 开头: 候选 1 为 model_dir / raw
    (abs_dir / "plain.pkl").write_bytes(b"prod")
    assert _abs_path(None, "plain.pkl") == abs_dir / "plain.pkl"


def test_abs_path_missing_file_warns_and_returns_controlled_path(tmp_path, monkeypatch, restore_model_dir, caplog):
    """缺失时返回受控候选而非 CWD 兜底，并留下可观测告警（禁止静默）。"""
    monkeypatch.chdir(tmp_path)

    with caplog.at_level(logging.WARNING):
        resolved = _abs_path(None, "models/does_not_exist.pkl")

    assert not resolved.exists()
    assert resolved == BACKEND_ROOT / "models" / "does_not_exist.pkl"
    assert "CWD-relative resolution is intentionally disabled" in caplog.text
