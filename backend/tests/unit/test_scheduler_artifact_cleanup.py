"""P0-FIX-2026-10-11: 实验产物清理的 active 模型保护集必须覆盖**目录型**模型。

背景（来自 2026-10-11 全量源码审查）：

``_cleanup_experiment_artifacts_impl`` 的保护集只收集
``str(Path(model_path).resolve())``（对 BERT 来说这是一个**目录**），而比对侧
``for file_path in entry.rglob("*"): if file_path.is_file():`` 只遍历**文件**。
目录路径永远不等于文件路径 → 保护判定恒 False → ``shutil.rmtree`` 直接删除
**正在服务的模型目录**（BERT 走 ``AutoTokenizer.from_pretrained(model_path)``
目录加载，见 ``core/model_engine/loading.py``），线上推理 503 且模型文件物理删除
不可恢复。这是该函数删除前的最后一道闸，失效后与「未加保护」等价。

修复：保护集拆成「文件集 + 目录集」，目录侧改用前缀匹配，并先校验 entry 自身。
"""

from __future__ import annotations

import sys

import pytest

from app.tasks import scheduler as scheduler_module
from app.tasks.scheduler import _cleanup_experiment_artifacts_impl


@pytest.fixture
def trained_root(tmp_path, monkeypatch):
    """构造 settings.model_dir/trained，并把产物清理指向它。"""
    model_dir = tmp_path / "models"
    trained = model_dir / "trained"
    trained.mkdir(parents=True)

    class _Settings:
        pass

    settings = _Settings()
    settings.model_dir = str(model_dir)
    monkeypatch.setattr(scheduler_module, "settings", settings, raising=False)
    # _cleanup_experiment_artifacts_impl 内部是 `from app.core.config import settings`
    from app.core import config as config_module

    monkeypatch.setattr(config_module, "settings", settings, raising=False)
    # P0-FIX-2026-10-11 (测试自身加固)：必须同时替换 sys.modules 里的模块对象。
    # tests/test_pytorch_optional_dependency.py 会`del sys.modules["app.core.config"]`，
    # 之后再`from app.core.config import settings` 会**重新导入**出一个全新的模块对象，
    # 只patch 旧对象的属性对重新导入的那份无效 → 实测表现为「应清理 2 个旧产物，实际 0」
    # （model_dir 退回真实目录，trained/ 不存在，函数首行直接 return 0）。
    # 这类"删除 sys.modules 以模拟缺依赖"的写法会污染后续所有依赖该模块的单例状态，
    # 因此凡是patch 模块级单例（settings/MODEL_PATHS）的测试都必须连 sys.modules 一起换。
    monkeypatch.setitem(sys.modules, "app.core.config", config_module)
    return trained


def _make_artifacts(trained: "object", n: int, prefix: str = "run"):
    """创建 n 个产物目录，每个含一个权重文件，返回目录列表。"""
    dirs = []
    for i in range(n):
        d = trained / f"{prefix}-{i}"
        d.mkdir()
        (d / "model.bin").write_text("x")
        dirs.append(d)
    return dirs


def test_active_directory_model_is_not_deleted(trained_root, monkeypatch):
    """注册路径是**目录**时，该目录不得被清理（修复前会被误删）。"""
    dirs = _make_artifacts(trained_root, 3, prefix="run")
    active_dir = dirs[0]  # 最新的一个（mtime 最大）→ 本应被 keep_recent 保留

    # 但把它显式注册为 active 模型（目录型），且让它落入 to_remove
    # 方法：让它不是 mtime 最大的那个，从而进入 to_remove
    import os
    import time

    oldest = min(dirs, key=lambda p: p.stat().st_mtime)
    os.utime(oldest, (time.time() - 1000, time.time() - 1000))
    for p in dirs:
        if p is not oldest:
            os.utime(p, (time.time(), time.time()))

    monkeypatch.setattr(
        scheduler_module,
        "MODEL_PATHS",
        {"text_m2_bert": str(oldest)},
        raising=False,
    )
    # _cleanup_experiment_artifacts_impl 内部是 `from app.core.model_registry import MODEL_PATHS`
    from app.core import model_registry as registry_module

    monkeypatch.setattr(registry_module, "MODEL_PATHS", {"text_m2_bert": str(oldest)}, raising=False)

    removed = _cleanup_experiment_artifacts_impl(keep_recent=1)

    assert oldest.exists(), (
        "目录型 active 模型目录被误删 —— 修复前保护集只比对文件，"
        "目录路径永远命中不到，shutil.rmtree 会删除在服模型"
    )
    assert removed >= 1, "非 active 的旧产物仍应被清理"


def test_active_file_model_is_not_deleted(trained_root, monkeypatch):
    """注册路径是**文件**时（原路径），保护逻辑仍应生效（回归保护）。"""
    dirs = _make_artifacts(trained_root, 3, prefix="run")

    import os
    import time

    oldest = min(dirs, key=lambda p: p.stat().st_mtime)
    os.utime(oldest, (time.time() - 1000, time.time() - 1000))
    for p in dirs:
        if p is not oldest:
            os.utime(p, (time.time(), time.time()))

    active_file = oldest / "model.bin"
    from app.core import model_registry as registry_module

    monkeypatch.setattr(
        scheduler_module,
        "MODEL_PATHS",
        {"structured_v1": str(active_file)},
        raising=False,
    )
    monkeypatch.setattr(
        registry_module, "MODEL_PATHS", {"structured_v1": str(active_file)}, raising=False
    )

    _cleanup_experiment_artifacts_impl(keep_recent=1)

    assert oldest.exists(), "文件型 active 模型所在目录不得被删除"
    assert active_file.exists()


def test_unprotected_old_artifacts_are_cleaned(trained_root, monkeypatch):
    """没有 active 模型时，超出的旧产物应正常被清理（修复不得过度保护）。"""
    dirs = _make_artifacts(trained_root, 3, prefix="run")

    import os
    import time

    sorted_dirs = sorted(dirs, key=lambda p: p.stat().st_mtime)
    for i, p in enumerate(sorted_dirs):
        os.utime(p, (time.time() - (1000 - i * 100), time.time() - (1000 - i * 100)))

    from app.core import model_registry as registry_module

    monkeypatch.setattr(scheduler_module, "MODEL_PATHS", {}, raising=False)
    monkeypatch.setattr(registry_module, "MODEL_PATHS", {}, raising=False)

    removed = _cleanup_experiment_artifacts_impl(keep_recent=1)

    assert removed == 2, f"应清理 2 个旧产物，实际 {removed}"
    assert not sorted_dirs[0].exists()
    assert not sorted_dirs[1].exists()
    assert sorted_dirs[2].exists(), "最新的产物应保留"
