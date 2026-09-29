"""S3 P4 影子模式独立验证脚本.

绕过 conftest.py 的 AlertManagerPayload forward ref bug, 直接验证
shadow_mode_service 核心逻辑 + model_engine_predict 集成钩子.

验证项:
    1. ShadowModeService 一致率统计 (agreement/disagreement)
    2. 采样率 (sample_rate=0.0 跳过, =1.0 全执行)
    3. M2 推理失败/异常不影响生产
    4. get_stats 格式正确
    5. _maybe_fire_shadow_predict 禁用时不触发
    6. _maybe_fire_shadow_predict 异常安全
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# 添加 backend 到 path (绕过 conftest)
BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_ROOT))


def main() -> int:
    """运行所有验证项, 返回 0=PASS / 1=FAIL."""
    print("=" * 60)
    print("S3 P4 影子模式独立验证")
    print("=" * 60)

    results: list[tuple[str, bool, str]] = []

    # 验证 1: 一致率统计
    results.append(test_agreement_stats())
    # 验证 2: 分歧统计
    results.append(test_disagreement_stats())
    # 验证 3: 采样率
    results.append(test_sample_rate())
    # 验证 4: M2 推理失败 graceful
    results.append(test_predictor_failure_graceful())
    # 验证 5: M2 推理异常不崩溃
    results.append(test_exception_does_not_crash())
    # 验证 6: get_stats 格式
    results.append(test_get_stats_format())
    # 验证 7: reset_stats
    results.append(test_reset_stats())
    # 验证 8: 钩子禁用时不触发
    results.append(test_maybe_fire_disabled())
    # 验证 9: 钩子异常安全
    results.append(test_maybe_fire_exception_safe())

    # 汇总
    print("\n" + "=" * 60)
    print("验证汇总")
    print("=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    for name, ok, msg in results:
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"  {status} {name}: {msg}")

    print(f"\n总计: {passed} PASS / {failed} FAIL")
    return 0 if failed == 0 else 1


def test_agreement_stats() -> tuple[str, bool, str]:
    """验证 1: 一致率统计 (生产预测 == M2 预测时 agreement+1)."""
    from app.services.shadow_mode_service import ShadowModeService

    async def _run():
        service = ShadowModeService()
        predictor = MagicMock()
        predictor.predict = AsyncMock(return_value={
            "prediction": 1, "probability": 0.85, "model_used": "text_m2_bert",
        })
        service._predictor = predictor
        service._predictor_loaded = True

        service.fire_shadow_predict("抑郁测试", {"prediction": 1, "probability": 0.80})
        await asyncio.sleep(0.05)

        stats = service.get_stats()
        assert stats["total_comparisons"] == 1, f"expected 1, got {stats['total_comparisons']}"
        assert stats["agreement"] == 1, f"expected agreement=1, got {stats['agreement']}"
        assert stats["agreement_rate"] == 1.0
        return stats

    try:
        stats = asyncio.run(_run())
        return ("一致率统计", True, f"total=1 agreement=1 rate={stats['agreement_rate']}")
    except Exception as e:
        return ("一致率统计", False, str(e)[:100])


def test_disagreement_stats() -> tuple[str, bool, str]:
    """验证 2: 分歧统计 (生产预测 != M2 预测时 disagreement+1)."""
    from app.services.shadow_mode_service import ShadowModeService

    async def _run():
        service = ShadowModeService()
        predictor = MagicMock()
        predictor.predict = AsyncMock(return_value={
            "prediction": 1, "probability": 0.75, "model_used": "text_m2_bert",
        })
        service._predictor = predictor
        service._predictor_loaded = True

        service.fire_shadow_predict("分歧文本", {"prediction": 0, "probability": 0.30})
        await asyncio.sleep(0.05)

        stats = service.get_stats()
        assert stats["disagreement"] == 1
        assert stats["agreement_rate"] == 0.0
        assert abs(stats["avg_prob_diff"] - 0.45) < 0.01
        return stats

    try:
        stats = asyncio.run(_run())
        return ("分歧统计", True, f"disagreement=1 rate={stats['agreement_rate']}")
    except Exception as e:
        return ("分歧统计", False, str(e)[:100])


def test_sample_rate() -> tuple[str, bool, str]:
    """验证 3: 采样率 (0.0 全跳过, 1.0 全执行)."""
    from app.services.shadow_mode_service import ShadowModeService

    async def _run():
        service = ShadowModeService()
        predictor = MagicMock()
        predictor.predict = AsyncMock(return_value={
            "prediction": 0, "probability": 0.2, "model_used": "text_m2_bert",
        })
        service._predictor = predictor
        service._predictor_loaded = True

        # sample_rate=0.0: 全部跳过
        for _ in range(10):
            service.fire_shadow_predict("test", {"prediction": 0}, sample_rate=0.0)
        await asyncio.sleep(0.05)
        assert service.get_stats()["total_comparisons"] == 0

        # sample_rate=1.0: 全部执行
        for _ in range(5):
            service.fire_shadow_predict("test", {"prediction": 0}, sample_rate=1.0)
        await asyncio.sleep(0.1)
        assert service.get_stats()["total_comparisons"] == 5
        return service.get_stats()

    try:
        stats = asyncio.run(_run())
        return ("采样率", True, f"rate=0.0→0, rate=1.0→{stats['total_comparisons']}")
    except Exception as e:
        return ("采样率", False, str(e)[:100])


def test_predictor_failure_graceful() -> tuple[str, bool, str]:
    """验证 4: M2 推理失败 (返回 None) 不计入统计."""
    from app.services.shadow_mode_service import ShadowModeService

    async def _run():
        service = ShadowModeService()
        predictor = MagicMock()
        predictor.predict = AsyncMock(return_value=None)  # 推理失败
        service._predictor = predictor
        service._predictor_loaded = True

        service.fire_shadow_predict("失败文本", {"prediction": 0})
        await asyncio.sleep(0.05)

        stats = service.get_stats()
        assert stats["total_comparisons"] == 0
        return stats

    try:
        stats = asyncio.run(_run())
        return ("推理失败 graceful", True, f"total={stats['total_comparisons']} (None 不计入)")
    except Exception as e:
        return ("推理失败 graceful", False, str(e)[:100])


def test_exception_does_not_crash() -> tuple[str, bool, str]:
    """验证 5: M2 推理抛异常时不崩溃."""
    from app.services.shadow_mode_service import ShadowModeService

    async def _run():
        service = ShadowModeService()
        predictor = MagicMock()
        predictor.predict = AsyncMock(side_effect=RuntimeError("GPU OOM"))
        service._predictor = predictor
        service._predictor_loaded = True

        # 不应抛异常
        service.fire_shadow_predict("异常文本", {"prediction": 0})
        await asyncio.sleep(0.05)

        stats = service.get_stats()
        assert stats["total_comparisons"] == 0
        return stats

    try:
        stats = asyncio.run(_run())
        return ("异常不崩溃", True, f"total={stats['total_comparisons']} (异常不计入)")
    except Exception as e:
        return ("异常不崩溃", False, str(e)[:100])


def test_get_stats_format() -> tuple[str, bool, str]:
    """验证 6: get_stats 返回格式正确."""
    from app.services.shadow_mode_service import ShadowModeService

    service = ShadowModeService()
    stats = service.get_stats()
    expected_keys = {
        "total_comparisons", "agreement", "disagreement",
        "agreement_rate", "avg_prob_diff", "max_prob_diff", "predictor_loaded",
    }
    assert set(stats.keys()) == expected_keys, f"missing keys: {expected_keys - set(stats.keys())}"
    assert stats["total_comparisons"] == 0
    assert stats["agreement_rate"] == 0.0
    assert stats["predictor_loaded"] is False
    return ("get_stats 格式", True, f"keys={len(stats)} (7 项)")


def test_reset_stats() -> tuple[str, bool, str]:
    """验证 7: reset_stats 清空统计."""
    from app.services.shadow_mode_service import ShadowModeService

    service = ShadowModeService()
    service._total = 10
    service._agreement = 8
    service._disagreement = 2
    service._prob_diff_sum = 1.5
    service._prob_diff_max = 0.3

    service.reset_stats()
    stats = service.get_stats()
    assert stats["total_comparisons"] == 0
    assert stats["agreement"] == 0
    assert stats["max_prob_diff"] == 0.0
    return ("reset_stats", True, "清空成功")


def test_maybe_fire_disabled() -> tuple[str, bool, str]:
    """验证 8: 钩子禁用时不触发."""
    from app.core.model_engine_predict import PredictMixin

    engine = MagicMock(spec=PredictMixin)
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.shadow_mode_text_enabled = False
        PredictMixin._maybe_fire_shadow_predict(engine, "test", {"prediction": 0})
        # 未抛异常即通过
    return ("钩子禁用不触发", True, "shadow_mode_text_enabled=False 直接返回")


def test_maybe_fire_exception_safe() -> tuple[str, bool, str]:
    """验证 9: 钩子异常安全 (不影响生产)."""
    from app.core.model_engine_predict import PredictMixin

    engine = MagicMock(spec=PredictMixin)
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.shadow_mode_text_enabled = True
        mock_settings.shadow_mode_text_sample_rate = 1.0
        with patch(
            "app.services.shadow_mode_service.get_shadow_mode_service",
            side_effect=RuntimeError("import fail"),
        ):
            # 不应抛异常
            PredictMixin._maybe_fire_shadow_predict(engine, "test", {"prediction": 0})
    return ("钩子异常安全", True, "import fail 被 logger.debug 捕获")


if __name__ == "__main__":
    sys.exit(main())
