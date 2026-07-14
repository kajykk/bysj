"""RES-P0-001 测试: ModelEngine.models 无界缓存 → LRU(maxsize=20).

验证要点:
1. LRU 基本行为: 命中移到 MRU, 超限淘汰 LRU
2. _cache_get / _cache_put 线程安全
3. _load_model / _load_model_async 集成 LRU
4. maxsize=0 禁用淘汰 (向后兼容)
5. 监控指标 cache_evictions / cache_maxsize 暴露
6. 配置项 model_cache_maxsize 生效
"""

from __future__ import annotations

import inspect
import threading
from collections import OrderedDict
from unittest.mock import patch

import pytest


class TestLRUCacheBasic:
    """测试 LRU 缓存基本行为."""

    def test_cache_get_returns_none_on_miss(self):
        """未命时应返回 None."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)
        engine.models = OrderedDict()
        engine._cache_lock = threading.Lock()
        engine._cache_maxsize = 20
        engine._cache_evictions = 0

        assert engine._cache_get("nonexistent") is None

    def test_cache_put_then_get_hits(self):
        """写入后读取应命中."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)
        engine.models = OrderedDict()
        engine._cache_lock = threading.Lock()
        engine._cache_maxsize = 20
        engine._cache_evictions = 0

        engine._cache_put("model_a", {"weights": [1, 2, 3]})
        assert engine._cache_get("model_a") == {"weights": [1, 2, 3]}

    def test_cache_put_none_is_noop(self):
        """写入 None 应被忽略 (避免缓存空模型)."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)
        engine.models = OrderedDict()
        engine._cache_lock = threading.Lock()
        engine._cache_maxsize = 20
        engine._cache_evictions = 0

        engine._cache_put("model_none", None)
        assert "model_none" not in engine.models
        assert engine._cache_get("model_none") is None

    def test_lru_evicts_oldest_when_exceeding_maxsize(self):
        """超过 maxsize 时应淘汰最旧 (LRU) 的模型."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)
        engine.models = OrderedDict()
        engine._cache_lock = threading.Lock()
        engine._cache_maxsize = 3
        engine._cache_evictions = 0

        # 写入 4 个模型, 第一个应被淘汰
        engine._cache_put("m1", "model1")
        engine._cache_put("m2", "model2")
        engine._cache_put("m3", "model3")
        engine._cache_put("m4", "model4")

        assert len(engine.models) == 3
        assert "m1" not in engine.models  # 最旧的被淘汰
        assert "m2" in engine.models
        assert "m3" in engine.models
        assert "m4" in engine.models
        assert engine._cache_evictions == 1

    def test_lru_access_moves_to_mru(self):
        """访问后应移到 MRU, 避免被淘汰."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)
        engine.models = OrderedDict()
        engine._cache_lock = threading.Lock()
        engine._cache_maxsize = 3
        engine._cache_evictions = 0

        engine._cache_put("m1", "model1")
        engine._cache_put("m2", "model2")
        engine._cache_put("m3", "model3")

        # 访问 m1, 移到 MRU
        engine._cache_get("m1")

        # 写入 m4, 应淘汰 m2 (最久未使用), 而非 m1
        engine._cache_put("m4", "model4")

        assert len(engine.models) == 3
        assert "m1" in engine.models  # m1 被访问过, 保留
        assert "m2" not in engine.models  # m2 是新的 LRU, 被淘汰
        assert "m3" in engine.models
        assert "m4" in engine.models

    def test_lru_repeated_put_updates_value_and_mru(self):
        """重复写入同一 key 应更新值并移到 MRU."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)
        engine.models = OrderedDict()
        engine._cache_lock = threading.Lock()
        engine._cache_maxsize = 2
        engine._cache_evictions = 0

        engine._cache_put("m1", "old")
        engine._cache_put("m2", "model2")
        engine._cache_put("m1", "new")  # 更新 m1

        assert engine._cache_get("m1") == "new"
        assert len(engine.models) == 2

        # 写入 m3, 应淘汰 m2 (m1 刚被更新为 MRU)
        engine._cache_put("m3", "model3")
        assert "m1" in engine.models
        assert "m2" not in engine.models


class TestLRUCacheMaxsizeZero:
    """测试 maxsize=0 禁用淘汰 (向后兼容)."""

    def test_maxsize_zero_disables_eviction(self):
        """maxsize=0 时不应淘汰, 无限缓存."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)
        engine.models = OrderedDict()
        engine._cache_lock = threading.Lock()
        engine._cache_maxsize = 0
        engine._cache_evictions = 0

        # 写入超过 20 个模型, 都应保留
        for i in range(25):
            engine._cache_put(f"m{i}", f"model{i}")

        assert len(engine.models) == 25
        assert engine._cache_evictions == 0


class TestLRUCacheThreadSafety:
    """测试 LRU 缓存线程安全."""

    def test_concurrent_cache_put_no_corruption(self):
        """并发写入不应导致数据损坏."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)
        engine.models = OrderedDict()
        engine._cache_lock = threading.Lock()
        engine._cache_maxsize = 50  # 足够大避免淘汰
        engine._cache_evictions = 0

        def writer(start: int) -> None:
            for i in range(start, start + 10):
                engine._cache_put(f"m{i}", f"model{i}")

        threads = [threading.Thread(target=writer, args=(i * 10,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 50 个模型都应成功写入
        assert len(engine.models) == 50
        # 所有模型都能正确读取
        for i in range(50):
            assert engine._cache_get(f"m{i}") == f"model{i}"

    def test_concurrent_get_put_no_deadlock(self):
        """并发读写不应死锁."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)
        engine.models = OrderedDict()
        engine._cache_lock = threading.Lock()
        engine._cache_maxsize = 20
        engine._cache_evictions = 0

        # 预填充
        for i in range(10):
            engine._cache_put(f"m{i}", f"model{i}")

        stop = threading.Event()

        def reader() -> None:
            while not stop.is_set():
                engine._cache_get("m5")

        def writer() -> None:
            i = 100
            while not stop.is_set():
                engine._cache_put(f"m{i}", f"model{i}")
                i += 1

        t1 = threading.Thread(target=reader)
        t2 = threading.Thread(target=writer)
        t1.start()
        t2.start()

        # 运行 100ms 后停止 (如果死锁会卡住 join)
        stop.set()
        t1.join(timeout=2.0)
        t2.join(timeout=2.0)

        assert not t1.is_alive(), "reader 线程死锁"
        assert not t2.is_alive(), "writer 线程死锁"


class TestLoadModelIntegration:
    """测试 _load_model / _load_model_async 集成 LRU."""

    @pytest.mark.asyncio
    async def test_load_model_async_uses_cache_get(self):
        """_load_model_async 缓存命中时应使用 _cache_get (不重新加载)."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)
        engine.models = OrderedDict()
        engine._cache_lock = threading.Lock()
        engine._cache_maxsize = 20
        engine._cache_evictions = 0
        engine.model_load_stats = {}

        # 预填充缓存
        engine._cache_put("test_model", {"weights": 42})

        from collections import defaultdict

        engine.model_load_stats = defaultdict(
            lambda: {
                "loads": 0,
                "cache_hits": 0,
                "first_load_ms": 0.0,
                "last_load_ms": 0.0,
            }
        )

        # 缓存命中, 不应调用 _load_model
        with patch.object(engine, "_load_model") as mock_load:
            result = await engine._load_model_async("test_model")
            assert result == {"weights": 42}
            mock_load.assert_not_called()
            assert engine.model_load_stats["test_model"]["cache_hits"] == 1

    @pytest.mark.asyncio
    async def test_load_model_async_miss_falls_through_to_load(self):
        """_load_model_async 缓存未命中时应调用 _load_model."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)
        engine.models = OrderedDict()
        engine._cache_lock = threading.Lock()
        engine._cache_maxsize = 20
        engine._cache_evictions = 0

        from collections import defaultdict

        engine.model_load_stats = defaultdict(
            lambda: {
                "loads": 0,
                "cache_hits": 0,
                "first_load_ms": 0.0,
                "last_load_ms": 0.0,
            }
        )

        # 缓存未命中, 应调用 _load_model
        with patch.object(
            engine, "_load_model", return_value={"loaded": True}
        ) as mock_load:
            result = await engine._load_model_async("new_model")
            assert result == {"loaded": True}
            mock_load.assert_called_once_with("new_model")

    def test_load_model_uses_cache_put(self):
        """_load_model 加载后应通过 _cache_put 写入缓存."""
        from pathlib import Path

        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)
        engine.models = OrderedDict()
        engine._cache_lock = threading.Lock()
        engine._cache_maxsize = 20
        engine._cache_evictions = 0

        from collections import defaultdict

        engine.model_load_stats = defaultdict(
            lambda: {
                "loads": 0,
                "cache_hits": 0,
                "first_load_ms": 0.0,
                "last_load_ms": 0.0,
            }
        )

        # mock _load_model 内部的磁盘加载部分, 验证调用 _cache_put
        # safe_joblib_load 是函数内延迟导入, 需 patch 源模块
        # _abs_path 需返回真实 Path 对象 (有 .suffix 和 .exists() 方法)
        fake_path = Path("fake_model.pkl")
        with patch.object(engine, "_cache_put") as mock_put, patch.object(
            engine, "_cache_get", return_value=None
        ), patch(
            "app.core.model_engine.MODEL_PATHS", {"fake_model": "fake.pkl"}
        ), patch(
            "app.core.model_engine.is_model_enabled", return_value=True
        ), patch(
            "app.core.model_engine.resolve_model_path", return_value="fake.pkl"
        ), patch.object(
            engine, "_abs_path", return_value=fake_path
        ), patch.object(
            Path, "exists", return_value=True
        ), patch(
            "app.core.model_engine._compute_file_sha256", return_value="fake_hash"
        ), patch(
            "app.core.model_engine._verify_file_hash"
        ), patch(
            "app.core.safe_pickle.safe_joblib_load", return_value={"weights": 123}
        ):
            result = engine._load_model("fake_model")
            assert result == {"weights": 123}
            mock_put.assert_called_once_with("fake_model", {"weights": 123})


class TestMonitoringSnapshot:
    """测试监控快照包含 LRU 指标."""

    def test_snapshot_includes_cache_evictions(self):
        """monitoring snapshot 应包含 cache_evictions 和 cache_maxsize."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine.__new__(ModelEngine)
        engine.models = OrderedDict()
        engine._cache_lock = threading.Lock()
        engine._cache_maxsize = 20
        engine._cache_evictions = 5
        engine.model_load_stats = {}
        engine.predict_stats = {}
        engine.monitoring_counters = {}
        # RES-P3-003: 类型从 list 改为 deque(maxlen=500), 保持测试一致性
        from collections import deque

        engine.monitoring_score_deltas = deque(maxlen=500)
        engine._routing_stats = {
            "structured": 0,
            "lite": 0,
            "anxiety_only": 0,
            "insufficient": 0,
        }
        engine._fallback_count = 0
        engine._crisis_override_count = 0
        engine._monitoring_lock = threading.Lock()
        engine._start_time = 0

        snapshot = engine.get_metrics_snapshot()
        assert snapshot["cache_evictions"] == 5
        assert snapshot["cache_maxsize"] == 20
        assert snapshot["cache_size"] == 0


class TestSourceCodeCheck:
    """源码静态检查: 验证 LRU 实现关键特征."""

    def test_models_is_ordered_dict(self):
        """self.models 应为 OrderedDict 类型."""
        from app.core import model_engine

        source = inspect.getsource(model_engine.ModelEngine.__init__)
        assert "OrderedDict" in source, "__init__ 应使用 OrderedDict 初始化 self.models"

    def test_cache_get_and_put_exist(self):
        """应有 _cache_get 和 _cache_put 方法."""
        from app.core.model_engine import ModelEngine

        assert hasattr(ModelEngine, "_cache_get"), "应有 _cache_get 方法"
        assert hasattr(ModelEngine, "_cache_put"), "应有 _cache_put 方法"

    def test_cache_get_uses_move_to_end(self):
        """_cache_get 应调用 move_to_end (LRU MRU 更新)."""
        from app.core import model_engine

        source = inspect.getsource(model_engine.ModelEngine._cache_get)
        assert "move_to_end" in source, "_cache_get 应调用 move_to_end 更新 MRU"

    def test_cache_put_uses_popitem_for_eviction(self):
        """_cache_put 应使用 popitem(last=False) 淘汰 LRU."""
        from app.core import model_engine

        source = inspect.getsource(model_engine.ModelEngine._cache_put)
        assert (
            "popitem(last=False)" in source
        ), "_cache_put 应使用 popitem(last=False) 淘汰 LRU"

    def test_load_model_does_not_directly_assign_to_models(self):
        """_load_model 不应直接 self.models[id] = model, 应通过 _cache_put."""
        from app.core import model_engine

        source = inspect.getsource(model_engine.ModelEngine._load_model)
        # 不应出现直接赋值 self.models[model_id] = model
        assert (
            "self.models[model_id] = model" not in source
        ), "_load_model 不应直接赋值 self.models, 应通过 _cache_put"
        # 应调用 _cache_put
        assert "_cache_put" in source

    def test_load_model_async_uses_cache_get(self):
        """_load_model_async 应使用 _cache_get 而非直接 in 检查."""
        from app.core import model_engine

        source = inspect.getsource(model_engine.ModelEngine._load_model_async)
        assert "_cache_get" in source, "_load_model_async 应使用 _cache_get"
        # 不应直接 in 检查 self.models
        assert (
            "if model_id in self.models:" not in source
        ), "_load_model_async 不应直接检查 model_id in self.models"


class TestConfigSetting:
    """测试配置项 model_cache_maxsize 生效."""

    def test_config_has_model_cache_maxsize(self):
        """config.py 应有 model_cache_maxsize 配置项."""
        from app.core.config import settings

        assert hasattr(
            settings, "model_cache_maxsize"
        ), "settings 应有 model_cache_maxsize"
        assert settings.model_cache_maxsize == 20, "默认值应为 20"

    def test_engine_reads_maxsize_from_config(self):
        """ModelEngine 应从 settings 读取 model_cache_maxsize."""
        from app.core.model_engine import ModelEngine

        engine = ModelEngine()
        assert engine._cache_maxsize == 20
        # 清理预加载的模型 (避免影响其他测试)
        engine.models.clear()
