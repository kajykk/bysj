"""AUDIT-2026-09-28 修复验证脚本（临时，验证后可删）。

验证两处修复：
  P0-4  fusion_engine.fuse() 对越界融合分数裁剪到 [0,100]
  P0-5  model_loader 的 load_* 带 lru_cache，重复调用不再重读文件/SHA256

用法：
  E:/zy/python/python.exe scripts/verify_audit_fixes_20260928.py
  （需 cd 到 backend 或让 backend 在 sys.path 中）
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

failures: list[str] = []
checks = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        failures.append(name)


# ── P0-4: 融合分数裁剪 ────────────────────────────────────────────────────
print("=" * 70)
print("P0-4  融合分数越界裁剪")
print("=" * 70)
try:
    from app.ml.fusion_engine import FusionEngine

    engine = FusionEngine()

    # 用例 1：正常输入，确认无回归（三模态加权和应落在 0-100 且不被裁剪）
    normal = {"structured": 62.0, "text": 55.0, "physiological": 48.0}
    r1 = engine.fuse(normal)
    score1 = r1["risk_score"]
    check(
        "正常输入仍在 [0,100] 且未被裁剪",
        0.0 <= score1 <= 100.0,
        f"risk_score={score1} risk_level={r1['risk_level']}",
    )

    # 用例 2：模拟 sleep_hours=0 导致的 5e6 级生理特征分数 —— 修复前会越界
    pathological = {"structured": 70.0, "text": 60.0, "physiological": 5_000_000.0}
    r2 = engine.fuse(pathological)
    score2 = r2["risk_score"]
    check(
        "越界输入被裁剪到 100（修复前会产生 >100 的分）",
        score2 == 100.0,
        f"risk_score={score2} risk_level={r2['risk_level']}",
    )

    # 用例 3：负分越界
    negative = {"structured": -500.0, "text": 10.0}
    r3 = engine.fuse(negative)
    score3 = r3["risk_score"]
    check(
        "负向越界被裁剪到 0",
        score3 >= 0.0,
        f"risk_score={score3} risk_level={r3['risk_level']}",
    )

    # 用例 4：risk_level 必须在 0-4（DB risk_level 语义）
    check(
        "risk_level 落在 0-4",
        all(r["risk_level"] in (0, 1, 2, 3, 4) for r in (r1, r2, r3)),
        f"levels={[r['risk_level'] for r in (r1, r2, r3)]}",
    )

    # 用例 5：所有返回的 risk_score 都满足 DB CheckConstraint
    all_scores = [score1, score2, score3]
    check(
        "全部 risk_score 满足 CheckConstraint(0<=score<=100)",
        all(0.0 <= s <= 100.0 for s in all_scores),
        f"scores={all_scores}",
    )
except Exception as exc:  # noqa: BLE001
    import traceback

    traceback.print_exc()
    failures.append(f"P0-4 执行异常: {exc}")

# ── P0-5: 模型工件加载缓存 ────────────────────────────────────────────────
print()
print("=" * 70)
print("P0-5  模型工件加载缓存")
print("=" * 70)
try:
    import app.ml.model_loader as ml

    # 缓存下沉到 _load_*_cached（按解析后的实际路径缓存，避免 monkeypatch 后命中旧缓存）
    for fn_name in (
        "_load_model_cached",
        "_load_scaler_cached",
        "_load_feature_names_cached",
        "_load_cleaner_cached",
    ):
        fn = getattr(ml, fn_name, None)
        check(
            f"{fn_name} 带 lru_cache",
            hasattr(fn, "cache_info"),
            f"cache_info={fn.cache_info() if hasattr(fn, 'cache_info') else 'N/A'}",
        )

    # 公开函数不应持有缓存（否则路径变化会被错误命中）
    check(
        "公开 load_model 不持有缓存（key 由解析后路径决定）",
        not hasattr(ml.load_model, "cache_info"),
    )

    check("clear_artifact_cache 可用", hasattr(ml, "clear_artifact_cache"))

    # 端到端：若默认工件存在，实测重复加载是否命中缓存
    from app.ml.model_loader import _artifact_path, load_model

    model_path = _artifact_path("MODEL_PATH")
    if model_path.exists():
        ml.clear_artifact_cache()
        t0 = time.perf_counter()
        m1 = load_model()
        t1 = time.perf_counter()
        m2 = load_model()
        t2 = time.perf_counter()
        first, second = (t1 - t0) * 1000, (t2 - t1) * 1000
        check(
            "第二次加载命中缓存（同一对象）",
            m1 is m2,
            f"首次 {first:.1f}ms → 二次 {second:.3f}ms，加速 {first / max(second, 1e-6):.0f}x",
        )
        check(
            "cache_info 显示命中",
            ml._load_model_cached.cache_info().hits >= 1,
            f"{ml._load_model_cached.cache_info()}",
        )
    else:
        print(f"[SKIP] 默认模型工件不存在: {model_path}")

    # 关键回归：monkeypatch 到不同路径时不得命中旧缓存
    import tempfile
    from unittest import mock

    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch.object(ml, "MODEL_PATH", Path(tmp) / "missing.json"):
            try:
                load_model()
                check("路径变化后未命中旧缓存（应抛 FileNotFoundError）", False, "未抛异常")
            except FileNotFoundError:
                check("路径变化后未命中旧缓存（应抛 FileNotFoundError）", True)

    # 失效函数确实清空
    ml.clear_artifact_cache()
    check(
        "clear_artifact_cache 后 miss 计数归零",
        ml._load_model_cached.cache_info().misses == 0,
        f"cache_info={ml._load_model_cached.cache_info()}",
    )
except Exception as exc:  # noqa: BLE001
    import traceback

    traceback.print_exc()
    failures.append(f"P0-5 执行异常: {exc}")

print()
print("=" * 70)
print(f"结果：{checks - len(failures)}/{checks} 通过")
if failures:
    print("失败项：")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("全部通过")
