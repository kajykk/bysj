"""``model_registry_v2`` 的写盘原子性与并发安全回归测试。

AUDIT-2026-10-08 (P2-registry-atomic)

## 实测缺陷复现记录（改前，Windows + CPython）

| # | 场景 | 改前实测 |
|---|---|---|
| A | 写入中途失败（磁盘满 / 进程被杀） | 磁盘留下 30 字节半截 JSON；重启加载后 registry 为 **0** 条（改前 5 条）；**下一次任意写操作把空表写回** → 5 条训练资产永久丢失 |
| B | 8 线程 × 20 次并发注册 | 期望 160，实际落盘 **100**，60 条静默丢失（Windows 独占打开 → ``PermissionError``） |
| C | 并发 promote（read-modify-write） | 第二个线程读到已被改过的 ``staging``，判定 ``staging -> staging`` 非法返回 ``None`` → 调用方误判激活失败 |
| D | 注册表文件已损坏 | 只 warning 就让 registry 为空，**损坏文件留在原地**，下一次写入直接覆盖 → 连人工恢复的机会都没有 |

## 为什么「A」的后果是丢资产而不是丢一次写

模型文件本身已经存盘，但 ``resolve_model_path``（``model_registry.py:331``）
只认注册表里 **PRODUCTION** 状态的记录。记录一旦从注册表消失，那份训练产物
就永远不会被激活 —— 磁盘上占着空间，推理链上看不见。
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

import pytest

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

import app.core.model_registry_v2 as mrv2  # noqa: E402
from app.core.model_registry_v2 import (  # noqa: E402
    ModelRegistryV2,
    ModelStatus,
    ModelType,
)


def _reg(registry: ModelRegistryV2, model_id: str, **kw):
    return registry.register_model(
        model_id=model_id,
        name=model_id,
        version="v1",
        model_type=ModelType.XGBOOST,
        **kw,
    )


def _disk_models(path: Path) -> dict:
    return json.loads(Path(path).read_text()).get("models", {})


def _tmp_files(directory: Path) -> list[str]:
    return sorted(f.name for f in directory.iterdir() if f.suffix == ".tmp")


@pytest.fixture
def reg(tmp_path):
    """每个用例一个独立注册表，落盘到 tmp_path。"""
    path = tmp_path / "registry.json"
    return ModelRegistryV2(registry_path=str(path)), path


# ═══════════════════════════════════════════════════════════════════════
# 1. 原子写：任何阶段失败都不得损伤已有磁盘文件
# ═══════════════════════════════════════════════════════════════════════


class TestAtomicWrite:
    """``_save_registry`` 的中间态不得对外可见。

    改前实现是 ``open(path, "w")`` —— 该调用**先 truncate 再写**，中间态
    （半截 JSON）直接在 registry_path 上可见，且会被后续读取者当成「注册表
    变空」。原子写把它改成「写同目录 tmp → fsync → os.replace」。
    """

    def test_serialize_failure_leaves_disk_intact(self, reg, monkeypatch):
        """序列化阶段失败：已有文件一条不少。"""
        registry, path = reg
        for i in range(5):
            _reg(registry, f"model_{i}")

        def _boom(*_a, **_k):
            raise TypeError("Object of type set is not JSON serializable")

        monkeypatch.setattr(mrv2.json, "dumps", _boom)
        with pytest.raises(TypeError):
            _reg(registry, "model_new")

        assert len(_disk_models(path)) == 5, "序列化失败不应损伤已落盘的 5 条记录"
        assert _tmp_files(path.parent) == [], "失败后不得留下 tmp 垃圾"

    def test_replace_failure_leaves_disk_intact(self, reg, monkeypatch):
        """``os.replace`` 失败：已有文件一条不少。"""
        registry, path = reg
        for i in range(3):
            _reg(registry, f"m{i}")

        def _boom(*_a, **_k):
            raise OSError(5, "Access is denied")

        monkeypatch.setattr(mrv2.os, "replace", _boom)
        with pytest.raises(OSError):
            _reg(registry, "m_new")

        assert len(_disk_models(path)) == 3
        assert _tmp_files(path.parent) == []

    def test_write_failure_leaves_disk_intact(self, reg, monkeypatch):
        """fsync 阶段失败（模拟磁盘满）：已有文件一条不少。"""
        registry, path = reg
        for i in range(3):
            _reg(registry, f"m{i}")

        real_fsync = os.fsync

        def _boom(fd):
            real_fsync(fd)
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(mrv2.os, "fsync", _boom)
        with pytest.raises(OSError):
            _reg(registry, "m_new")

        assert len(_disk_models(path)) == 3
        assert _tmp_files(path.parent) == []

    def test_no_tmp_leftover_on_success(self, reg):
        """正常写入后同目录不得残留 tmp 文件。"""
        registry, path = reg
        for i in range(10):
            _reg(registry, f"m{i}")
        assert _tmp_files(path.parent) == []
        assert len(_disk_models(path)) == 10

    def test_write_is_all_or_nothing(self, reg):
        """核心不变量：任何时刻读盘都必须是完整合法的 JSON。

        在写操作进行的同时反复读取，只要出现一次 JSONDecodeError 就说明
        原子性没做到。这里用「读线程 + 写线程」逼近真实并发。

        已知平台限制（实测 Windows）：``os.replace`` 在**目标文件正被其他
        句柄打开**时会抛 ``PermissionError [WinError 5]``。所以读线程持续
        持句柄地读，会让部分写操作失败 —— 这**不是**数据损坏：失败时
        ``register_model`` 会回滚内存且磁盘原文件完好（见本类前三个用例）。
        因此这里只把「读到半截 JSON」判为失败，把 replace 的占用冲突视为
        平台噪声。
        """
        registry, path = reg
        _reg(registry, "seed")
        stop = threading.Event()
        broken: list[str] = []

        def _reader():
            while not stop.is_set():
                try:
                    json.loads(path.read_text(encoding="utf-8"))
                except (FileNotFoundError, OSError):
                    pass
                except json.JSONDecodeError as exc:
                    broken.append(str(exc))

        reader = threading.Thread(target=_reader, daemon=True)
        reader.start()
        try:
            for i in range(50):
                try:
                    _reg(registry, f"m{i}")
                except PermissionError:
                    # 见 docstring：目标被读方占用，非数据损坏
                    continue
        finally:
            stop.set()
            reader.join(timeout=5)

        assert not broken, f"读方观测到半截 JSON（非原子写）: {broken[:3]}"
        # 无论多少次写失败，磁盘上留下的都必须是合法且自洽的表
        disk = _disk_models(path)
        assert "seed" in disk, "已确认落盘的 seed 记录不得丢失"


# ═══════════════════════════════════════════════════════════════════════
# 2. 并发写：不得静默丢失训练资产
# ═══════════════════════════════════════════════════════════════════════


class TestConcurrentWrites:
    """并发注册 / 状态流转的完整性。

    改前实测 8 线程 × 20 次注册只落盘 100/160 —— 这不是「偶发抖动」，
    而是 Windows 上 ``open(path, "w")`` 独占打开导致的系统性丢失。
    """

    def test_concurrent_register_loses_nothing(self, reg):
        """8 线程 × 20 次注册，内存与磁盘都必须是 160。"""
        registry, path = reg
        errors: list[str] = []

        def _worker(t: int):
            try:
                for i in range(20):
                    _reg(registry, f"t{t}_m{i}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{type(exc).__name__}: {exc}")

        threads = [threading.Thread(target=_worker, args=(t,)) for t in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"并发注册抛异常: {errors[:3]}"
        assert len(registry.registry) == 160, "内存丢失注册记录"
        assert len(_disk_models(path)) == 160, "磁盘丢失注册记录"

    def test_concurrent_activate_has_no_phantom_failure(self, reg, monkeypatch):
        """并发 activate：不得出现「实际已生效但返回 None」的幽灵失败。"""
        registry, path = reg
        _reg(registry, "m1", status=ModelStatus.CANDIDATE)
        monkeypatch.setattr(mrv2, "_registry_instance", registry)

        results: list = []
        gate = threading.Lock()

        def _activator():
            r = mrv2.activate_training_model("m1")
            with gate:
                results.append(r)

        threads = [threading.Thread(target=_activator) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r is not None for r in results), "并发激活出现幽灵失败（返回 None）"
        assert all(r.status == ModelStatus.PRODUCTION for r in results)
        assert registry.get_model("m1").status == ModelStatus.PRODUCTION
        assert _disk_models(path)["m1"]["status"] == "production"

    def test_concurrent_activate_rollback_keeps_memory_disk_consistent(self, reg, monkeypatch):
        """activate 与 rollback 交错：内存与磁盘最终状态必须一致。"""
        registry, path = reg
        _reg(registry, "m2", status=ModelStatus.CANDIDATE)
        monkeypatch.setattr(mrv2, "_registry_instance", registry)

        def _act():
            mrv2.activate_training_model("m2")

        def _roll():
            mrv2.rollback_training_model("m2")

        threads = [threading.Thread(target=_act) for _ in range(4)]
        threads += [threading.Thread(target=_roll) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        mem = registry.get_model("m2").status
        disk = _disk_models(path)["m2"]["status"]
        assert mem.value == disk, f"内存 {mem} 与磁盘 {disk} 不一致"


# ═══════════════════════════════════════════════════════════════════════
# 3. 损坏文件的处置：旁路而非静默覆盖
# ═══════════════════════════════════════════════════════════════════════


class TestCorruptRegistryFile:
    """加载失败时不得把损坏文件留在原地等下一次写入覆盖。

    改前：损坏 → warning → 空表 → 下一次写入覆盖损坏文件 → 原件彻底消失。
    这是「A」场景里资产不可恢复的真正原因：原子写防住了**新**损坏，
    旁路则保住**已**损坏文件里还能抢救的记录。
    """

    def test_corrupt_file_is_quarantined(self, tmp_path):
        """损坏文件被改名旁路，且内容可事后读回。"""
        path = tmp_path / "registry.json"
        corrupt_content = '{"version": "2.0", "models": {'
        path.write_text(corrupt_content, encoding="utf-8")

        registry = ModelRegistryV2(registry_path=str(path))

        assert len(registry.registry) == 0
        backups = sorted(tmp_path.glob("registry.json.corrupt-*"))
        assert backups, "损坏文件未被旁路备份（会被下一次写入静默覆盖）"
        assert backups[0].read_text(encoding="utf-8") == corrupt_content
        assert not path.exists(), "损坏文件不应留在 registry_path 上"

    def test_new_registry_can_be_rebuilt_after_quarantine(self, tmp_path):
        """旁路之后进程仍可正常写入新表（不能因为备份而卡死）。"""
        path = tmp_path / "registry.json"
        path.write_text("{broken", encoding="utf-8")

        registry = ModelRegistryV2(registry_path=str(path))
        _reg(registry, "rebuilt")

        assert len(_disk_models(path)) == 1
        assert path.exists()

    def test_broken_record_quarantines_file(self, tmp_path):
        """合法 JSON 但记录结构损坏 → 同样旁路，不静默丢弃。"""
        path = tmp_path / "registry.json"
        path.write_text(
            json.dumps({"version": "2.0", "models": {"m1": {"model_id": "m1"}}}),
            encoding="utf-8",
        )

        registry = ModelRegistryV2(registry_path=str(path))
        assert len(registry.registry) == 0
        assert sorted(tmp_path.glob("registry.json.corrupt-*")), "结构损坏未旁路"


# ═══════════════════════════════════════════════════════════════════════
# 4. 单例：并发首次调用不得产生两个实例
# ═══════════════════════════════════════════════════════════════════════


class TestGlobalSingleton:
    """``get_registry()`` 的单例创建竞态。"""

    def test_concurrent_first_call_returns_same_instance(self, monkeypatch):
        """并发首次调用必须拿到同一个实例。

        改前是裸的 if-None-then-create：两个线程各建一个实例，各自
        ``_load_registry`` 到不同快照，后赋值者胜出 —— 前者期间完成的注册
        被整体丢弃。
        """
        monkeypatch.setattr(mrv2, "_registry_instance", None)
        seen: list[int] = []
        gate = threading.Lock()

        def _grab():
            r = mrv2.get_registry()
            with gate:
                seen.append(id(r))

        threads = [threading.Thread(target=_grab) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(seen)) == 1, "并发首次调用创建了多个 registry 实例"
