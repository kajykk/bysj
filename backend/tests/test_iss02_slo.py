"""ISS-02 覆盖率提升：app/core/slo.py 聚焦测试.

SLO/SLI 与错误预算计算（稳定性度量）。用假 Histogram/metric 对象驱动纯计算函数。
prometheus_client 现已安装（ISS-02 期间补装），可正常导入。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core import slo


class _FakeHistogram:
    """模拟 prometheus Histogram：collect() 返回 [(labels, bucket_data)]。"""

    def __init__(self, buckets, samples):
        # buckets: 单调边界列表 (含 inf)
        self.buckets = list(buckets)
        # samples: {boundary: cumulative_count, "__count__": total}
        self._samples = dict(samples)

    def collect(self):
        bucket_data = {b: self._samples.get(b, 0) for b in self.buckets}
        bucket_data["_count"] = self._samples.get("__count__", 0)
        return [(dict(status=""), bucket_data)]


def _fake_requests(samples):
    """samples: [(status_label, count), ...]"""

    class _M:
        def collect(self):
            return [(dict(status=s), c) for s, c in samples]

    return _M()


def _hist_no_data():
    class _M:
        def collect(self):
            return []

    return _M()


class TestComputeP99:
    def test_p99_basic(self):
        h = _FakeHistogram(
            buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.5, 1.0, float("inf")],
            samples={
                0.005: 10,
                0.01: 20,
                0.025: 40,
                0.05: 60,
                0.1: 80,
                0.5: 95,
                1.0: 100,
                "__count__": 100,
            },
        )
        # 99% of 100 = 99 → 第一个累积 >=99 的 bucket 是 1.0
        assert slo._compute_p99(h) == 1.0

    def test_p99_empty_returns_none(self):
        assert slo._compute_p99(_hist_no_data()) is None

    def test_p99_zero_count_returns_none(self):
        h = _FakeHistogram(buckets=[0.5, float("inf")], samples={0.5: 0, "__count__": 0})
        assert slo._compute_p99(h) is None


class TestComputeAvailability:
    def test_all_success(self):
        import app.core.slo as slo_mod

        m = _fake_requests([("200", 1000), ("404", 50)])
        monkeypatch_metric(slo_mod, "http_requests_total", m)
        avail, total, errs = slo_mod._compute_availability()
        assert avail == 1.0
        assert total == 1050
        assert errs == 0

    def test_with_5xx(self):
        import app.core.slo as slo_mod

        m = _fake_requests([("200", 900), ("500", 100)])
        monkeypatch_metric(slo_mod, "http_requests_total", m)
        avail, total, errs = slo_mod._compute_availability()
        assert errs == 100
        assert abs(avail - (900 / 1000)) < 1e-9


class TestComputeSli:
    def test_zero_requests_perfect(self, monkeypatch):
        import app.core.slo as slo_mod

        monkeypatch.setattr(slo_mod, "http_requests_total", _fake_requests([]))
        monkeypatch.setattr(slo_mod, "http_request_duration_seconds", _hist_no_data())
        monkeypatch.setattr(
            slo_mod, "model_inference_duration_seconds", _hist_no_data()
        )
        res = slo_mod.compute_sli()
        assert res.availability == 1.0
        assert res.error_budget_remaining_ratio == 1.0
        assert res.error_budget_burn_rate == 0.0
        assert res.p99_latency_seconds is None

    def test_with_errors_consumes_budget(self, monkeypatch):
        import app.core.slo as slo_mod

        # 1% 错误率（恰好等于允许错误率 0.1%? 这里 10/1000=1% > 0.1%）→ 预算耗尽
        monkeypatch.setattr(
            slo_mod, "http_requests_total", _fake_requests([("200", 990), ("500", 10)])
        )
        monkeypatch.setattr(slo_mod, "http_request_duration_seconds", _hist_no_data())
        monkeypatch.setattr(
            slo_mod, "model_inference_duration_seconds", _hist_no_data()
        )
        res = slo_mod.compute_sli()
        # 实际错误率 1%，允许 0.1% → burn_rate=10，remaining 下限 -1
        assert res.error_budget_burn_rate > 1
        assert res.error_budget_remaining_ratio <= 0


def monkeypatch_metric(module, name, obj):
    setattr(module, name, obj)


def test_constants():
    assert slo.SLO_AVAILABILITY_TARGET == 0.999
    assert slo.SLO_LATENCY_TARGET == 0.99
    assert slo.SLO_LATENCY_THRESHOLD_SECONDS == 0.5
    assert slo.SLO_MODEL_INFERENCE_LATENCY_THRESHOLD_SECONDS == 2.0
