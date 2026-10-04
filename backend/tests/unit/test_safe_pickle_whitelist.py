"""AUDIT-2026-10-01 (P0-2)：反序列化类白名单的回归测试。

背景（已实测复现）：``joblib.load`` 等价于执行文件内的字节码。改动前，一个引用
``os.system`` 的恶意 pickle 放在受信目录内（通过路径白名单）会被**正常加载并执行**
（实测：哨兵文件被创建）。现在受限 Unpickler 会把这类引用拒绝为 ``ModelUnpicklingError``。

本文件同时钉住**兼容性**：合法 joblib/sklearn 工件必须仍能正常加载。
（完整兼容性另由「50/50 真实工件全部可加载」的批量验证覆盖，见报告 §零·六。）
"""

from __future__ import annotations

import os
import pathlib

import joblib
import numpy as np
import pytest

from app.core.safe_pickle import (
    ModelUnpicklingError,
    is_allowed_global,
    safe_joblib_load,
)

# ── 白名单判定 ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "module,name",
    [
        ("os", "system"),
        ("nt", "system"),  # Windows 上 os.system 实际解析为 nt.system
        ("posix", "system"),
        ("builtins", "eval"),
        ("builtins", "exec"),
        ("builtins", "__import__"),
        ("builtins", "open"),
        ("builtins", "compile"),
        ("subprocess", "Popen"),
        ("ctypes", "CDLL"),
        ("shutil", "rmtree"),
        ("importlib", "import_module"),
    ],
)
def test_dangerous_globals_are_denied(module, name):
    assert is_allowed_global(module, name) is False


@pytest.mark.parametrize(
    "module,name",
    [
        ("numpy", "ndarray"),
        ("numpy.core.multiarray", "_reconstruct"),
        ("numpy._core.multiarray", "_reconstruct"),
        ("numpy.random._pickle", "__randomstate_ctor"),
        ("sklearn.linear_model._logistic", "LogisticRegression"),
        ("sklearn.preprocessing._data", "StandardScaler"),
        ("joblib.numpy_pickle", "NumpyArrayWrapper"),
        ("xgboost.sklearn", "XGBClassifier"),
        ("catboost.core", "CatBoostClassifier"),
        ("app.core.score_adapter", "ScoreAdapter"),
    ],
)
def test_expected_ml_globals_are_allowed(module, name):
    assert is_allowed_global(module, name) is True


def test_builtins_only_allows_primitives():
    for safe in ("slice", "bytearray", "tuple", "dict"):
        assert is_allowed_global("builtins", safe) is True
    for unsafe in ("eval", "exec", "open", "__import__", "globals", "locals", "getattr"):
        assert is_allowed_global("builtins", unsafe) is False


def test_non_string_inputs_are_denied():
    assert is_allowed_global(None, "system") is False  # type: ignore[arg-type]
    assert is_allowed_global("os", None) is False  # type: ignore[arg-type]


# ── 恶意工件：必须被拒绝，且代码不得执行 ────────────────────────────


def _write_malicious(tmp: pathlib.Path, name: str, func, args) -> pathlib.Path:
    """生成一个「反序列化即执行 func(*args)」的 pickle。"""

    class _Evil:
        def __reduce__(self):
            return (func, args)

    path = tmp / name
    with open(path, "wb") as fh:
        joblib.dump(_Evil(), fh)  # 用 joblib 写出，与真实工件同为 joblib 格式
    return path


def test_os_system_payload_is_rejected_and_not_executed(tmp_path):
    sentinel = tmp_path / "pwned.txt"
    payload = _write_malicious(
        tmp_path,
        "evil_ossystem.pkl",
        os.system,
        (f'cmd /c echo pwned > "{sentinel}"',),
    )

    with pytest.raises(ModelUnpicklingError, match="白名单"):
        # trusted_root=tmp_path：路径校验通过，唯一拦住它的就是白名单
        safe_joblib_load(payload, trusted_root=tmp_path, require_hash=False, model_id="evil")

    assert not sentinel.exists(), "恶意载荷被执行了——白名单失效"


def test_builtins_eval_payload_is_rejected(tmp_path):
    payload = _write_malicious(tmp_path, "evil_eval.pkl", eval, ("1 + 1",))

    with pytest.raises(ModelUnpicklingError):
        safe_joblib_load(payload, trusted_root=tmp_path, require_hash=False, model_id="evil")


def test_model_unpickling_error_is_not_swallowed_as_valueerror(tmp_path):
    """拒绝必须上抛为 ModelUnpicklingError（安全事件），而不是被包装成普通 ValueError。"""
    payload = _write_malicious(tmp_path, "evil2.pkl", os.system, ("echo x",))
    with pytest.raises(ModelUnpicklingError):
        safe_joblib_load(payload, trusted_root=tmp_path, require_hash=False)


# ── 兼容性：合法工件仍须可加载 ──────────────────────────────────────


def test_legitimate_sklearn_pickle_still_loads(tmp_path):
    from sklearn.linear_model import LogisticRegression

    rng = np.random.default_rng(0)
    X = rng.normal(size=(40, 4))
    y = (X[:, 0] > 0).astype(int)
    model = LogisticRegression().fit(X, y)

    path = tmp_path / "legit.pkl"
    joblib.dump(model, path)

    loaded = safe_joblib_load(path, trusted_root=tmp_path, require_hash=False)
    assert hasattr(loaded, "predict")
    np.testing.assert_array_equal(loaded.predict(X), model.predict(X))


def test_legitimate_numpy_arrays_still_load(tmp_path):
    path = tmp_path / "legit_arrays.pkl"
    payload = {"a": np.arange(10), "b": {"c": np.zeros(3)}}
    joblib.dump(payload, path)

    loaded = safe_joblib_load(path, trusted_root=tmp_path, require_hash=False)
    np.testing.assert_array_equal(loaded["a"], np.arange(10))
    np.testing.assert_array_equal(loaded["b"]["c"], np.zeros(3))


def test_compressed_joblib_files_still_load(tmp_path):
    """实测仓库里有 joblib 压缩格式工件；受限 Unpickler 必须同时支持。"""
    path = tmp_path / "legit_compressed.pkl"
    joblib.dump({"x": np.arange(5)}, path, compress=3)

    loaded = safe_joblib_load(path, trusted_root=tmp_path, require_hash=False)
    np.testing.assert_array_equal(loaded["x"], np.arange(5))


# ── 原有防护不得回退 ───────────────────────────────────────────────


def test_path_whitelist_still_enforced(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    inside = tmp_path / "trusted"
    inside.mkdir()
    path = outside / "m.pkl"
    joblib.dump({"ok": 1}, path)

    with pytest.raises(ValueError, match="受信目录"):
        safe_joblib_load(path, trusted_root=inside, require_hash=False)


def test_oversized_file_still_rejected(tmp_path):
    path = tmp_path / "big.pkl"
    joblib.dump({"x": np.arange(100)}, path)

    with pytest.raises(ValueError, match="过大"):
        safe_joblib_load(path, trusted_root=tmp_path, require_hash=False, max_bytes=10)
