"""hyperparameter_tuning 缓存与早停测试 (P0-T1-3)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from app.ml import hyperparameter_tuning as ht

# 最小网格：2x2 = 4 组合，跑完足够快且缓存语义可完整验证
_MIN_GRID = {
    "hidden_dims": [[16], [8]],
    "dropout_rate": [0.0, 0.2],
    "learning_rate": [0.01],
    "weight_decay": [0.001],
    "batch_size": [32],
}

_X = np.random.RandomState(0).randn(40, 4)
_Y = np.random.RandomState(1).randint(0, 2, size=40)


class TestParamFingerprint:
    def test_deterministic(self):
        p1 = {"hidden_dims": [16, 8], "dropout_rate": 0.2, "learning_rate": 0.01}
        p2 = {"learning_rate": 0.01, "dropout_rate": 0.2, "hidden_dims": [16, 8]}
        assert ht._param_fingerprint(p1) == ht._param_fingerprint(p2)

    def test_distinguishes_params(self):
        p1 = {"dropout_rate": 0.2, "learning_rate": 0.01}
        p2 = {"dropout_rate": 0.4, "learning_rate": 0.01}
        assert ht._param_fingerprint(p1) != ht._param_fingerprint(p2)


class TestGridSearchCache:
    def test_resume_skips_cached_combos(self, tmp_path):
        """P0-T1-3: 第二次运行命中缓存，不再触发训练，最优参数与首次一致."""
        cache_file = Path(tmp_path) / "tuning_cache.json"
        calls = {"n": 0}

        def _fake_train(*_args, **_kwargs):
            calls["n"] += 1
            return {"best_val_f1": round(0.8 + calls["n"] * 0.02, 4)}

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(ht, "train_model", _fake_train)
            best_params_1, best_f1_1 = ht.grid_search(
                _X, _Y, _X, _Y, param_grid=_MIN_GRID, epochs=2, cache_file=cache_file
            )

        assert calls["n"] == 4
        assert cache_file.exists()
        entries = json.loads(cache_file.read_text(encoding="utf-8"))
        assert len(entries) == 4  # 2x2 网格全部落盘
        assert all("fingerprint" in e and "params" in e and "val_f1" in e for e in entries)

        # 第二次运行：train_model 不应再被调用
        with pytest.MonkeyPatch.context() as mp:
            def _fail(*_a, **_k):
                raise AssertionError("cached combo should not retrain")

            mp.setattr(ht, "train_model", _fail)
            best_params_2, best_f1_2 = ht.grid_search(
                _X, _Y, _X, _Y, param_grid=_MIN_GRID, epochs=2, cache_file=cache_file
            )

        assert best_params_1 == best_params_2
        assert best_f1_1 == best_f1_2

    def test_cache_keeps_training_without_cache_file(self):
        """P0-T1-3: 不传 cache_file 时行为与原先一致（每次全量训练）."""
        calls = {"n": 0}
        with pytest.MonkeyPatch.context() as mp:
            def _spy(*_a, **_k):
                calls["n"] += 1
                return {"best_val_f1": 0.85}

            mp.setattr(ht, "train_model", _spy)
            ht.grid_search(_X, _Y, _X, _Y, param_grid=_MIN_GRID, epochs=2)

        assert calls["n"] == 4

    def test_corrupt_cache_recovers(self, tmp_path):
        """P0-T1-3: 缓存文件损坏时告警并以空缓存继续训练，不中断."""
        cache_file = Path(tmp_path) / "tuning_cache.json"
        cache_file.write_text("{not valid json", encoding="utf-8")
        calls = {"n": 0}

        def _fake_train(*_args, **_kwargs):
            calls["n"] += 1
            return {"best_val_f1": round(0.8 + calls["n"] * 0.02, 4)}

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(ht, "train_model", _fake_train)
            best_params, best_f1 = ht.grid_search(
                _X, _Y, _X, _Y, param_grid=_MIN_GRID, epochs=2, cache_file=cache_file
            )

        assert calls["n"] == 4  # 损坏缓存不中断全量训练
        assert best_params  # 正常返回结果
        assert best_f1 > 0.0
        # 损坏文件被重写为合法 JSON
        entries = json.loads(cache_file.read_text(encoding="utf-8"))
        assert len(entries) == 4


class TestGridSearchEarlyStop:
    def test_early_stop_stops_at_threshold(self):
        """P0-T1-3: 最优 f1 达到阈值后提前终止搜索."""
        calls: list[dict] = []
        with pytest.MonkeyPatch.context() as mp:
            def _spy(*_a, **_k):
                calls.append(1)
                return {"best_val_f1": 0.99}

            mp.setattr(ht, "train_model", _spy)
            best_params, best_f1 = ht.grid_search(
                _X,
                _Y,
                _X,
                _Y,
                param_grid=_MIN_GRID,
                epochs=2,
                early_stop_f1=0.98,
            )

        # 首个组合即达阈值，只训练 1 次而非全部 4 次
        assert len(calls) == 1
        assert best_f1 == 0.99
        assert best_params

    def test_no_early_stop_by_default(self):
        """P0-T1-3: 默认不剪枝，全部组合评估完毕."""
        calls: list[dict] = []
        with pytest.MonkeyPatch.context() as mp:
            def _spy(*_a, **_k):
                calls.append(1)
                return {"best_val_f1": 0.99}

            mp.setattr(ht, "train_model", _spy)
            ht.grid_search(_X, _Y, _X, _Y, param_grid=_MIN_GRID, epochs=2)

        assert len(calls) == 4
