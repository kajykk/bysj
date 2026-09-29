"""P1 推理缓存基准测试 (S3 P1 验收).

验收标准: 缓存命中路径单模态 P95 < 100ms.

测试场景:
1. cache_get 命中延迟 (相同 key 重复读, 模拟生产热路径)
2. cache_get 未命中延迟 (随机不存在的 key)
3. cache_set 延迟 (写缓存, 含 JSON 序列化)
4. 端到端模拟 (cache_get 命中 + dict 反序列化, 模拟 ModelPredictService.predict_text 命中路径)
5. TTL=0 禁用缓存基线 (无缓存开销)

输出:
- 控制台: P50/P95/P99/mean/max + 是否达标
- JSON: models/experiments/p1_cache_benchmark_<timestamp>.json

环境要求:
- Redis 可达 (默认 redis://localhost:6379/0)
- 不依赖 app.main, 避免触发 conftest 加载链问题
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Windows DLL 兼容 (与 conftest 一致)
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

# JWT/PII 测试密钥 (与 conftest 一致, 避免 settings 校验失败)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci-only")
os.environ.setdefault(
    "PII_ENCRYPTION_KEY", "test-pii-key-for-unit-tests-only-not-for-production"
)
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_app.db")

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.cache import cache_get, cache_set, make_cache_key  # noqa: E402
from app.core.config import settings  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS_DIR = PROJECT_ROOT / "models" / "experiments"
EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)

# 模拟真实 predict_text 结果大小 (含 ml_result + text_analysis + crisis_result)
_SAMPLE_RESULT: dict[str, Any] = {
    "prediction": 1,
    "probability": 0.7823,
    "risk_score": 78.23,
    "risk_level": 3,
    "model_used": "text_depression_model",
    "model_version": "v1.20",
    "fallback_used": False,
    "confidence": 0.842,
    "sentiment_label": "negative",
    "sentiment_score": 0.7823,
    "distress_score": 78.23,
    "crisis_score": 0.12,
    "crisis_detected": False,
    "crisis_keywords": [],
    "risk_factors": ["negative_emotion", "sleep_issue", "social_withdrawal"],
    "protective_factors": ["help_seeking"],
    "data_quality": {
        "missing_fields": [],
        "confidence_penalty": 0.0,
        "quality_level": "complete",
    },
}


def _percentiles(samples_ms: list[float]) -> dict[str, float]:
    """计算 P50/P95/P99/mean/max."""
    if not samples_ms:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0, "max": 0.0, "n": 0}
    s = sorted(samples_ms)
    n = len(s)

    def _pct(p: float) -> float:
        idx = max(0, min(n - 1, int(round((p / 100.0) * (n - 1)))))
        return s[idx]

    return {
        "p50": round(_pct(50), 3),
        "p95": round(_pct(95), 3),
        "p99": round(_pct(99), 3),
        "mean": round(statistics.mean(s), 3),
        "max": round(s[-1], 3),
        "n": n,
    }


async def _bench_cache_get_hit(n: int) -> tuple[list[float], str]:
    """基准 1: cache_get 命中 (相同 key 重复读, 热路径)."""
    cache_key = make_cache_key("ml:text", {"text": "benchmark_hit_fixed_text"})
    await cache_set(cache_key, _SAMPLE_RESULT, ttl=300)
    # 预热一次
    await cache_get(cache_key)

    samples: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        await cache_get(cache_key)
        samples.append((time.perf_counter() - t0) * 1000.0)
    return samples, cache_key


async def _bench_cache_get_miss(n: int) -> list[float]:
    """基准 2: cache_get 未命中 (随机 key)."""
    samples: list[float] = []
    for i in range(n):
        key = make_cache_key("ml:text", {"text": f"miss_unique_{i}_{time.time_ns()}"})
        t0 = time.perf_counter()
        await cache_get(key)
        samples.append((time.perf_counter() - t0) * 1000.0)
    return samples


async def _bench_cache_set(n: int) -> list[tuple[float, str]]:
    """基准 3: cache_set 写入 (含 JSON 序列化)."""
    samples: list[tuple[float, str]] = []
    for i in range(n):
        key = make_cache_key("ml:text", {"text": f"set_bench_{i}"})
        t0 = time.perf_counter()
        await cache_set(key, _SAMPLE_RESULT, ttl=300)
        samples.append(((time.perf_counter() - t0) * 1000.0, key))
    return samples


async def _bench_end_to_end_hit(n: int) -> list[float]:
    """基准 4: 端到端模拟命中路径.

    模拟 ModelPredictService.predict_text 缓存命中时的完整路径:
    - text.strip() (CPU)
    - make_cache_key (CPU, sha256)
    - cache_get (Redis)
    - 返回 result (无 model_engine 调用)
    """
    text = "我感到很沮丧,最近睡不好,也不想见人" * 3  # 真实长度文本
    cache_key = make_cache_key("ml:text", {"text": text.strip()})
    await cache_set(cache_key, _SAMPLE_RESULT, ttl=300)
    await cache_get(cache_key)  # 预热

    samples: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        # 模拟 predict_text 入口的轻量操作
        cleaned = text.strip()
        key = make_cache_key("ml:text", {"text": cleaned})
        cached = await cache_get(key)
        # 命中分支直接返回 (无 model_engine 调用)
        assert cached is not None
        samples.append((time.perf_counter() - t0) * 1000.0)
    return samples


async def _bench_no_cache_baseline(n: int) -> list[float]:
    """基准 5: TTL=0 禁用缓存的开销基线 (单次 make_cache_key 调用).

    用于对比: 即使 TTL=0 不读写 Redis, 仍有 make_cache_key 的 sha256 开销.
    但实际代码在 TTL=0 时直接跳过 make_cache_key (if _ML_INFERENCE_CACHE_TTL > 0),
    所以这里仅测空 asyncio overhead, 作为下界参考.
    """
    samples: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        # 模拟 TTL=0 时: 仅 if 判断, 不进入 cache 分支
        if 0 > 0:  # 永不成立的等价表达式 (避免被优化)
            await cache_get("never")
        samples.append((time.perf_counter() - t0) * 1000.0)
    return samples


async def run_benchmark(n: int = 500) -> dict[str, Any]:
    """运行完整基准套件."""
    print(f"\n=== P1 推理缓存基准测试 (N={n} per scenario) ===")
    print(f"Redis URL: {settings.redis_url}")
    print(f"ml_inference_cache_ttl (settings): {settings.ml_inference_cache_ttl}s")
    print()

    # 检查 Redis 连通性
    from app.core.cache import _get_redis_client

    client = await _get_redis_client()
    redis_ok = client is not None
    print(f"Redis 连通: {redis_ok}")
    if not redis_ok:
        print("⚠️  Redis 不可达, 基准将退化为内存缓存路径 (仍可验收 P95)")
    print()

    results: dict[str, Any] = {}

    # 场景 1: cache_get 命中
    print("[1/5] cache_get 命中 (热路径)...")
    t_start = time.perf_counter()
    samples_hit, hit_key = await _bench_cache_get_hit(n)
    elapsed = time.perf_counter() - t_start
    pct = _percentiles(samples_hit)
    results["cache_get_hit"] = pct
    print(
        f"  P50={pct['p50']:.3f}ms  P95={pct['p95']:.3f}ms  P99={pct['p99']:.3f}ms  "
        f"mean={pct['mean']:.3f}ms  max={pct['max']:.3f}ms  (total {elapsed:.2f}s)"
    )

    # 场景 2: cache_get 未命中
    print("[2/5] cache_get 未命中 (随机 key)...")
    t_start = time.perf_counter()
    samples_miss = await _bench_cache_get_miss(n)
    elapsed = time.perf_counter() - t_start
    pct = _percentiles(samples_miss)
    results["cache_get_miss"] = pct
    print(
        f"  P50={pct['p50']:.3f}ms  P95={pct['p95']:.3f}ms  P99={pct['p99']:.3f}ms  "
        f"mean={pct['mean']:.3f}ms  max={pct['max']:.3f}ms  (total {elapsed:.2f}s)"
    )

    # 场景 3: cache_set
    print("[3/5] cache_set 写入 (含 JSON 序列化)...")
    t_start = time.perf_counter()
    samples_set_pairs = await _bench_cache_set(n)
    elapsed = time.perf_counter() - t_start
    samples_set = [s for s, _ in samples_set_pairs]
    pct = _percentiles(samples_set)
    results["cache_set"] = pct
    print(
        f"  P50={pct['p50']:.3f}ms  P95={pct['p95']:.3f}ms  P99={pct['p99']:.3f}ms  "
        f"mean={pct['mean']:.3f}ms  max={pct['max']:.3f}ms  (total {elapsed:.2f}s)"
    )

    # 场景 4: 端到端命中 (验收目标)
    print("[4/5] 端到端命中路径 (predict_text 入口 → cache_get → 返回)...")
    t_start = time.perf_counter()
    samples_e2e = await _bench_end_to_end_hit(n)
    elapsed = time.perf_counter() - t_start
    pct = _percentiles(samples_e2e)
    results["end_to_end_hit"] = pct
    print(
        f"  P50={pct['p50']:.3f}ms  P95={pct['p95']:.3f}ms  P99={pct['p99']:.3f}ms  "
        f"mean={pct['mean']:.3f}ms  max={pct['max']:.3f}ms  (total {elapsed:.2f}s)"
    )

    # 场景 5: TTL=0 基线
    print("[5/5] TTL=0 禁用缓存基线 (仅 asyncio overhead)...")
    t_start = time.perf_counter()
    samples_nocache = await _bench_no_cache_baseline(n)
    elapsed = time.perf_counter() - t_start
    pct = _percentiles(samples_nocache)
    results["no_cache_baseline"] = pct
    print(
        f"  P50={pct['p50']:.3f}ms  P95={pct['p95']:.3f}ms  P99={pct['p99']:.3f}ms  "
        f"mean={pct['mean']:.3f}ms  max={pct['max']:.3f}ms  (total {elapsed:.2f}s)"
    )

    # 验收
    e2e_p95 = results["end_to_end_hit"]["p95"]
    acceptance = {
        "target_p95_ms": 100.0,
        "e2e_hit_p95_ms": e2e_p95,
        "meets_target": e2e_p95 < 100.0,
        "margin_ms": round(100.0 - e2e_p95, 3),
    }
    print()
    print("=== 验收 ===")
    print(
        f"端到端命中 P95 = {e2e_p95:.3f}ms  目标 < 100ms  →  "
        f"{'✅ PASS' if acceptance['meets_target'] else '❌ FAIL'}"
        f"  (margin {acceptance['margin_ms']:+.3f}ms)"
    )

    return {
        "experiment_id": f"p1_cache_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "task": "S3 P1 推理缓存基准验收",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "redis_url": settings.redis_url,
        "redis_reachable": redis_ok,
        "ml_inference_cache_ttl_s": settings.ml_inference_cache_ttl,
        "n_samples_per_scenario": n,
        "scenarios": results,
        "acceptance": acceptance,
        "notes": (
            "缓存命中路径 P95 < 100ms 即达标. "
            "未命中路径延迟由模型推理决定 (BERT 200ms+, TF-IDF 5-20ms), "
            "不在 P1 验收范围 (P1 仅验收缓存命中加速比). "
            "实际生产 predict_text 命中率取决于请求文本重复度."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="P1 推理缓存基准测试")
    parser.add_argument(
        "--n", type=int, default=500, help="每个场景的样本数 (默认 500)"
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="输出 JSON 路径 (默认 models/experiments/p1_cache_benchmark_<ts>.json)",
    )
    args = parser.parse_args()

    result = asyncio.run(run_benchmark(n=args.n))

    out_path = (
        Path(args.out)
        if args.out
        else EXPERIMENTS_DIR / f"{result['experiment_id']}.json"
    )
    out_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n结果已保存: {out_path}")

    # 退出码: 验收通过 0, 失败 1
    sys.exit(0 if result["acceptance"]["meets_target"] else 1)


if __name__ == "__main__":
    main()
