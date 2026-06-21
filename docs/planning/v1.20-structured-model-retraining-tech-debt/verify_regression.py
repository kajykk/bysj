"""v1.20 回归验证: CrisisDetector + FusionPriorityEngine + 业务逻辑"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "backend"))
os.environ["STRUCTURED_MODEL_MODE"] = "primary"

results: list[tuple[str, bool, str]] = []

def check(name: str, condition: bool, detail: str = ""):
    results.append((name, condition, detail))
    status = "✅" if condition else "❌"
    print(f"  {status} {name}: {detail}" if detail else f"  {status} {name}")


def test_crisis_detector():
    print("\n--- 8.2 CrisisDetector ---")
    from app.core.crisis_detector import CrisisDetector
    cd = CrisisDetector()
    check("CrisisDetector loads", cd is not None)

    high_crisis = "我想自杀，活着没有意义了，撑不下去了"
    res = cd.scan(high_crisis)
    check("High crisis text detected", res.get("crisis_detected", False) is True,
          f"crisis_detected={res.get('crisis_detected')}, score={res.get('crisis_score')}")

    low_text = "今天心情不太好，但我会好起来的"
    res2 = cd.scan(low_text)
    check("Low risk text NOT crisis", res2.get("crisis_detected", False) is False,
          f"crisis_detected={res2.get('crisis_detected')}")

    res3 = cd.scan("")
    check("Empty text handled", isinstance(res3, dict), f"crisis_detected={res3.get('crisis_detected')}")

    score = cd.get_crisis_score(high_crisis)
    check("get_crisis_score works", isinstance(score, (int, float)) and score > 0, f"score={score}")


def test_text_analyzer():
    print("\n--- 8.2 TextAnalyzer ---")
    from app.ml.text_analyzer import TextAnalyzer
    ta = TextAnalyzer()
    check("TextAnalyzer loads", ta is not None)

    try:
        res = ta.analyze("I've been feeling very depressed lately and can't sleep.")
        check("Text analyze returns result", isinstance(res, dict),
              f"keys={list(res.keys())[:4] if res else 'empty'}")
    except Exception as e:
        check("Text analyze", False, str(e))


def test_fusion_engine():
    print("\n--- 8.3 FusionPriorityEngine ---")
    from app.ml.fusion_priority_engine import FusionPriorityEngine
    fpe = FusionPriorityEngine()
    check("FusionPriorityEngine loads", fpe is not None)

    try:
        structured = {"risk_score": 50, "risk_level": 2, "probability": 0.5}
        text = {"risk_score": 60, "risk_level": 2, "probability": 0.6, "crisis_detected": False}
        physio = {}
        res = fpe.apply_priority_rules(structured, text, physio, 55.0, 2)
        check("Fusion apply_priority_rules works", isinstance(res, dict),
              f"risk_level={res.get('risk_level')}, review_required={res.get('review_required')}")

        text_crisis = {"risk_score": 60, "risk_level": 2, "probability": 0.6, "crisis_detected": True}
        res2 = fpe.apply_priority_rules(structured, text_crisis, physio, 55.0, 2)
        check("Crisis override triggers review", res2.get("review_required", False) is True,
              f"crisis_override={res2.get('crisis_override')}")

    except Exception as e:
        check("Fusion combine", False, str(e))


def test_model_engine():
    print("\n--- 8.3 ModelEngine ---")
    from app.core.model_engine import ModelEngine
    engine = ModelEngine()
    check("ModelEngine loads", engine is not None)
    check("CrisisDetector attached", engine.crisis_detector is not None)
    check("TextAnalyzer attached", engine.text_analyzer is not None)
    check("FusionPriorityEngine attached", engine.fusion_priority_engine is not None)


def test_business_models():
    print("\n--- 8.4 Business Models ---")
    try:
        from app.models.review import ReviewTask
        check("ReviewTask model import", True, f"model={ReviewTask.__name__}")
    except Exception as e:
        check("ReviewTask model import", False, str(e))

    try:
        from app.models.review import CrisisEvent
        check("CrisisEvent model import", True, f"model={CrisisEvent.__name__}")
    except Exception as e:
        check("CrisisEvent model import", False, str(e))

    try:
        from app.schemas.review import ReviewTaskCreate, CrisisEventCreate
        check("ReviewTaskCreate schema", True)
    except Exception as e:
        check("ReviewTaskCreate schema", False, str(e))


def test_config_and_thresholds():
    print("\n--- Config & Thresholds ---")
    from app.core.config import settings
    check("STRUCTURED_MODEL_MODE", getattr(settings, "structured_model_mode", None) in ("primary", "fallback"),
          f"value={getattr(settings, 'structured_model_mode', 'N/A')}")

    from app.core.risk_thresholds import MODALITY_RISK_THRESHOLDS
    st = MODALITY_RISK_THRESHOLDS["structured"]
    check("Structured thresholds set",
          st["mild"] == 15 and st["moderate"] == 45 and st["high"] == 85 and st["critical"] == 98,
          f"mild={st['mild']}, mod={st['moderate']}, high={st['high']}, crit={st['critical']}")


def test_alembic_state():
    print("\n--- Alembic Final ---")
    import subprocess
    alembic_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "backend")
    r = subprocess.run(["alembic", "heads"], capture_output=True, text=True, cwd=alembic_dir)
    lines = [l for l in r.stdout.strip().split("\n") if l and not l.startswith("(")]
    single_head = len(lines) <= 1
    check("Alembic single head", single_head,
          f"heads={[l.strip()[:16] for l in lines]}")


async def main():
    print("=" * 60)
    print("v1.20 综合回归验证")
    print("=" * 60)

    test_crisis_detector()
    test_text_analyzer()
    test_fusion_engine()
    test_model_engine()
    test_business_models()
    test_config_and_thresholds()
    test_alembic_state()

    passed = sum(1 for _, c, _ in results if c)
    total = len(results)
    print(f"\n{'=' * 60}")
    print(f"RESULTS: {passed}/{total} passed")
    if passed == total:
        print("✅ ALL REGRESSION CHECKS PASSED")
    else:
        print("❌ SOME CHECKS FAILED:")
        for name, cond, detail in results:
            if not cond:
                print(f"  - {name}: {detail}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
