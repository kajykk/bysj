"""v1.24 ScoreAdapter — piecewise monotonic score adapter.

S-02 (V4 ML 优化): 从 scripts/modeling/v1_24/04_train_adapter.py 抽取 ScoreAdapter 类
到 app/core/, 使生产代码可直接从 score_adapter_config.json 动态构建 adapter,
无需依赖缺失的 score_adapter.pkl 文件。

适配器逻辑：
- 将 v1.23 raw score 与 v1.20 base score 的 delta 按分段斜率缩放
- 在分段边界附近做平滑过渡
- 限制单次调整幅度不超过 clamp_delta
"""

from __future__ import annotations

from typing import Any


class ScoreAdapter:
    """分段单调评分适配器。

    从 config dict 构建，config 格式：
    {
        "version": "v1.24",
        "type": "piecewise_monotonic",
        "segments": [{"range": [lo, hi], "slope": float}, ...],
        "clamp": int,
        "smooth": int
    }
    """

    def __init__(self, config: dict[str, Any]):
        self.version = config["version"]
        self.segments = config["segments"]
        self.clamp_delta = config["clamp"]
        self.buffer = config["smooth"]

    def transform(self, v1_20_score: float, v1_23_raw_score: float) -> dict[str, Any]:
        delta = v1_23_raw_score - v1_20_score
        seg = self._find_segment(v1_20_score)
        adjusted = v1_20_score + delta * seg["slope"]
        adjusted = max(
            v1_20_score - self.clamp_delta,
            min(v1_20_score + self.clamp_delta, adjusted),
        )
        if self._near_boundary(v1_20_score, seg):
            adjusted = self._smooth(v1_20_score, delta, seg)
        diff = abs(adjusted - v1_20_score)
        return {
            "score": round(adjusted, 2),
            "delta": round(adjusted - v1_23_raw_score, 2),
            "safe_label": self._label(diff),
        }

    def _find_segment(self, score: float) -> dict[str, Any]:
        for seg in self.segments:
            lo, hi = seg["range"]
            if lo <= score <= hi:
                return seg
        return self.segments[-1]

    def _near_boundary(self, score: float, seg: dict[str, Any]) -> bool:
        lo, hi = seg["range"]
        return abs(score - lo) <= self.buffer or abs(score - hi) <= self.buffer

    def _smooth(
        self, score: float, delta: float, seg: dict[str, Any]
    ) -> float:
        idx = -1
        for i, s in enumerate(self.segments):
            if s is seg:
                idx = i
                break
        if idx < 0:
            return score + delta * seg["slope"]

        result = score + delta * seg["slope"]
        lo, hi = seg["range"]
        if abs(score - lo) <= self.buffer and idx > 0:
            neighbor = self.segments[idx - 1]
            t = (score - (lo - self.buffer)) / (2 * self.buffer)
            t = max(0.0, min(1.0, t))
            neighbor_val = score + delta * neighbor["slope"]
            result = result * t + neighbor_val * (1 - t)
        elif abs(score - hi) <= self.buffer and idx < len(self.segments) - 1:
            neighbor = self.segments[idx + 1]
            t = (score - (hi - self.buffer)) / (2 * self.buffer)
            t = max(0.0, min(1.0, t))
            neighbor_val = score + delta * neighbor["slope"]
            result = result * (1 - t) + neighbor_val * t

        return max(
            score - self.clamp_delta,
            min(score + self.clamp_delta, result),
        )

    def _label(self, diff: float) -> str:
        if diff <= 5:
            return "stable"
        if diff <= 15:
            return "slight_diff"
        if diff <= 25:
            return "marked_diff"
        return "review"
