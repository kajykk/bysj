"""
v1.25 mmpsy-lite 后端综合测试脚本
覆盖 Phase 4 (Engine), Phase 5 (Registry), Phase 6 (Schema/Service), Phase 8 (Config)
"""

import sys
import os
import warnings
import asyncio
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    print(f"  [{status}] {name}{' — ' + detail if detail else ''}")

print("=" * 60)
print("v1.25 mmpsy-lite Backend Comprehensive Test Suite")
print("=" * 60)

# ── Phase 5: Registry ──
print("\n── Phase 5: Registry Tests ──")

try:
    from app.core.model_registry import MODEL_REGISTRY, MODEL_PATHS
    check("TP-REG-01a: MODEL_REGISTRY import", True)

    check("TP-REG-01b: mmpsy_lite_model in MODEL_REGISTRY",
          "mmpsy_lite_model" in MODEL_REGISTRY)

    if "mmpsy_lite_model" in MODEL_REGISTRY:
        entry = MODEL_REGISTRY["mmpsy_lite_model"]
        check("TP-REG-01c: lifecycle == candidate",
              entry.lifecycle == "candidate",
              f"actual={entry.lifecycle}")
        check("TP-REG-01d: excluded_inputs == ['phq9_score']",
              entry.feature_schema.get("excluded_inputs") == ["phq9_score"],
              f"actual={entry.feature_schema.get('excluded_inputs')}")
        check("TP-REG-01e: input_features == 17",
              entry.feature_schema.get("input_features") == 17,
              f"actual={entry.feature_schema.get('input_features')}")

    check("TP-REG-02a: mmpsy_lite_scaler in MODEL_REGISTRY",
          "mmpsy_lite_scaler" in MODEL_REGISTRY)
    if "mmpsy_lite_scaler" in MODEL_REGISTRY:
        s_entry = MODEL_REGISTRY["mmpsy_lite_scaler"]
        check("TP-REG-02b: scaler lifecycle == candidate",
              s_entry.lifecycle == "candidate",
              f"actual={s_entry.lifecycle}")

    check("TP-REG-02c: MODEL_PATHS mmpsy_lite_scaler path",
          "mmpsy_lite_scaler" in MODEL_PATHS,
          f"keys={list(MODEL_PATHS.keys())}")

except Exception as e:
    check("Phase 5: Registry import/checks", False, str(e))

# ── Phase 8: Config ──
print("\n── Phase 8: Config Tests ──")

try:
    from app.core.config import settings
    check("TP-CFG-01a: settings import", True)

    threshold = settings.route_feature_coverage_threshold
    check("TP-CFG-01b: route_feature_coverage_threshold == 0.80",
          abs(threshold - 0.80) < 0.001,
          f"actual={threshold}")

    min_len = settings.route_lite_min_text_length
    check("TP-CFG-01c: route_lite_min_text_length == 20",
          min_len == 20,
          f"actual={min_len}")

except Exception as e:
    check("Phase 8: Config checks", False, str(e))

# ── Phase 4: Engine ──
print("\n── Phase 4: Model Engine Tests ──")

try:
    from app.core.model_engine import LiteFeatureExtractor, LITE_FEATURE_ORDER
    check("TP-ENG-01a: LiteFeatureExtractor import", True)
    check("TP-ENG-01b: LITE_FEATURE_ORDER import",
          isinstance(LITE_FEATURE_ORDER, list) and len(LITE_FEATURE_ORDER) == 17,
          f"len={len(LITE_FEATURE_ORDER) if isinstance(LITE_FEATURE_ORDER, list) else type(LITE_FEATURE_ORDER)}")

    ext = LiteFeatureExtractor()
    result = ext.extract("失眠睡不着，考试压力大")
    check("TP-ENG-01c: extract returns dict", isinstance(result, dict))
    check("TP-ENG-01d: total_keywords >= 1",
          result.get("total_keywords", 0) >= 1,
          f"total_keywords={result.get('total_keywords')}")
    check("TP-ENG-01e: keyword_counts['sleep_problem'] >= 1",
          result.get("keyword_counts", {}).get("sleep_problem", 0) >= 1,
          f"sleep_problem={result.get('keyword_counts', {}).get('sleep_problem')}")

    # Test self_harm_crisis ×2 weighting
    sh_result = ext.extract("想死的心都有了，不想活了")
    check("TP-ENG-01f: self_harm_crisis ×2 weighting",
          sh_result.get("keyword_counts", {}).get("self_harm_crisis", 0) >= 2,
          f"self_harm_crisis={sh_result.get('keyword_counts', {}).get('self_harm_crisis')}")

except Exception as e:
    check("Phase 4: Extractor tests", False, str(e))

# ── Model Engine predict_lite / routing tests ──
print("\n── Phase 4: predict_lite & Routing Tests ──")

try:
    from app.core.model_engine import ModelEngine
    import tempfile
    import shutil
    import json

    # Check model files exist
    models_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "models", "v1.25_mmpsy_lite")
    lite_model_path = os.path.join(models_dir, "mmpsy_lite_model.pkl")
    lite_scaler_path = os.path.join(models_dir, "mmpsy_lite_scaler.pkl")

    model_exists = os.path.exists(lite_model_path)
    scaler_exists = os.path.exists(lite_scaler_path)
    check("TP-MODEL-01: mmpsy_lite_model.pkl exists", model_exists)
    check("TP-MODEL-02: mmpsy_lite_scaler.pkl exists", scaler_exists)

    async def run_engine_tests():
        engine = ModelEngine()

        # TP-ENG-02: predict_lite normal input
        try:
            r = await engine.predict_lite(gad7_score=15, audio_transcript="失眠睡不着考试压力大心情很差每天都很难过")
            if r:
                check("TP-ENG-02a: predict_lite returns result", True)
                check("TP-ENG-02b: risk_score in [0, 100]",
                      0 <= r.get("risk_score", -1) <= 100,
                      f"risk_score={r.get('risk_score')}")
                check("TP-ENG-02c: risk_level in {0,1,2,3,4}",
                      r.get("risk_level", -1) in {0, 1, 2, 3, 4},
                      f"risk_level={r.get('risk_level')}")
                check("TP-ENG-02d: model_used contains mmpsy_lite",
                      "mmpsy_lite" in str(r.get("model_used", "")),
                      f"model_used={r.get('model_used')}")
                check("TP-ENG-02e: model_family == lite",
                      r.get("model_family") == "lite",
                      f"model_family={r.get('model_family')}")
                check("TP-ENG-02f: fallback_used == False",
                      r.get("fallback_used") == False,
                      f"fallback_used={r.get('fallback_used')}")
            else:
                check("TP-ENG-02: predict_lite empty result", False)
        except Exception as e:
            check("TP-ENG-02: predict_lite error", False, str(e))

        # TP-ENG-03: predict_lite short text fallback
        try:
            r = await engine.predict_lite(gad7_score=15, audio_transcript="a")
            if r:
                check("TP-ENG-03a: short text → fallback",
                      r.get("model_family") == "fallback",
                      f"model_family={r.get('model_family')}")
                check("TP-ENG-03b: fallback_used == True",
                      r.get("fallback_used") == True,
                      f"fallback_used={r.get('fallback_used')}")
                check("TP-ENG-03c: fallback_reason contains text_insufficient",
                      "text_insufficient" in str(r.get("fallback_reason", "")),
                      f"fallback_reason={r.get('fallback_reason')}")
            else:
                check("TP-ENG-03: short text empty result", False)
        except Exception as e:
            check("TP-ENG-03: short text error", False, str(e))

        # TP-ENG-04: model missing fallback
        if model_exists:
            backup_path = lite_model_path + ".test_bak"
            try:
                shutil.move(lite_model_path, backup_path)
                fresh_engine = ModelEngine()
                r = await fresh_engine.predict_lite(gad7_score=15,
                    audio_transcript="失眠睡不着压力大" * 5)
                if r:
                    check("TP-ENG-04a: model missing → fallback",
                          r.get("fallback_used") == True,
                          f"fallback_used={r.get('fallback_used')}")
                else:
                    check("TP-ENG-04: model missing empty result", False)
            except Exception as e:
                check("TP-ENG-04: model missing error", False, str(e))
            finally:
                if os.path.exists(backup_path):
                    shutil.move(backup_path, lite_model_path)
        else:
            check("TP-ENG-04: SKIP (model file not found)", True, "SKIP")

        # TP-ENG-05: routing → structured (high coverage)
        try:
            full_features = {
                "age": 22, "gender": 1, "cgpa": 3.2, "sleep_duration": 7,
                "exercise_frequency": 3, "social_support": 4, "stress_level": 6,
                "anxiety": 8, "family_history": 0, "panic_attack": 1,
                "treatment_seeking": 0, "academic_pressure": 7,
                "financial_pressure": 5, "study_year": 3,
                "gad7_score": 15, "phq9_score": 18,
                "audio_transcript": "失眠睡不着考试压力大" * 5
            }
            result = await engine.predict_structured(full_features)
            ri = result.get("routing_info", {})
            check("TP-ENG-05a: routing → structured",
                  ri.get("selected_model_family") == "structured",
                  f"family={ri.get('selected_model_family')}")
            check("TP-ENG-05b: confidence_band == high",
                  ri.get("prediction_confidence_band") == "high",
                  f"band={ri.get('prediction_confidence_band')}")
        except Exception as e:
            check("TP-ENG-05: routing structured error", False, str(e))

        # TP-ENG-06: routing → lite (GAD-7 + text)
        try:
            lite_features = {
                "gad7_score": 15,
                "audio_transcript": "失眠睡不着，考试压力大" * 3
            }
            result = await engine.predict_structured(lite_features)
            ri = result.get("routing_info", {})
            check("TP-ENG-06a: routing → lite",
                  ri.get("selected_model_family") == "lite",
                  f"family={ri.get('selected_model_family')}")
            check("TP-ENG-06b: confidence_band == medium",
                  ri.get("prediction_confidence_band") == "medium",
                  f"band={ri.get('prediction_confidence_band')}")
            check("TP-ENG-06c: model_used == mmpsy_lite_model",
                  "mmpsy_lite" in str(result.get("model_used", "")),
                  f"model_used={result.get('model_used')}")
        except Exception as e:
            check("TP-ENG-06: routing lite error", False, str(e))

        # TP-ENG-07: routing → anxiety_only (only GAD-7)
        try:
            gad7_only = {"gad7_score": 15}
            result = await engine.predict_structured(gad7_only)
            ri = result.get("routing_info", {})
            check("TP-ENG-07a: routing → anxiety_only",
                  ri.get("selected_model_family") == "anxiety_only",
                  f"family={ri.get('selected_model_family')}")
            check("TP-ENG-07b: confidence_band == low",
                  ri.get("prediction_confidence_band") == "low",
                  f"band={ri.get('prediction_confidence_band')}")
            check("TP-ENG-07c: fallback_used == True",
                  result.get("fallback_used") == True,
                  f"fallback_used={result.get('fallback_used')}")
        except Exception as e:
            check("TP-ENG-07: routing anxiety_only error", False, str(e))

        # TP-ENG-08: routing → insufficient (empty input)
        try:
            empty_features = {}
            result = await engine.predict_structured(empty_features)
            ri = result.get("routing_info", {})
            check("TP-ENG-08a: routing → insufficient",
                  ri.get("selected_model_family") == "insufficient",
                  f"family={ri.get('selected_model_family')}")
            check("TP-ENG-08b: risk_score is None for insufficient",
                  result.get("risk_score") is None,
                  f"risk_score={result.get('risk_score')}")
            check("TP-ENG-08c: warning non-empty",
                  bool(result.get("warning")),
                  f"warning={result.get('warning')}")
        except Exception as e:
            check("TP-ENG-08: routing insufficient error", False, str(e))

        # TP-ENG-09: all paths return routing_info with 5 fields
        try:
            # Test each path has complete routing_info
            for path_name, features in [
                ("structured", {"age": 22, "gender": 1, "cgpa": 3.2, "sleep_duration": 7,
                    "exercise_frequency": 3, "social_support": 4, "stress_level": 6,
                    "anxiety": 8, "family_history": 0, "panic_attack": 1,
                    "treatment_seeking": 0, "academic_pressure": 7,
                    "financial_pressure": 5, "study_year": 3,
                    "gad7_score": 15, "phq9_score": 18,
                    "audio_transcript": "失眠睡不着考试压力大" * 5}),
                ("lite", {"gad7_score": 15, "audio_transcript": "失眠睡不着考试压力大" * 3}),
                ("anxiety_only", {"gad7_score": 15}),
                ("insufficient", {})
            ]:
                result = await engine.predict_structured(features)
                ri = result.get("routing_info")
                has_ri = ri is not None
                fields_ok = (has_ri and
                    "selected_model_id" in ri and
                    "selected_model_family" in ri and
                    "routing_reason" in ri and
                    "feature_coverage_ratio" in ri and
                    "prediction_confidence_band" in ri)
                check(f"TP-ENG-09: {path_name} routing_info exists + 5 fields",
                      fields_ok,
                      f"ri={ri}")
        except Exception as e:
            check("TP-ENG-09: routing_info completeness", False, str(e))

    asyncio.run(run_engine_tests())

except Exception as e:
    check("Phase 4: Engine runtime tests", False, str(e))

# ── Phase 6: Schema + Service ──
print("\n── Phase 6: Schema / Service Tests ──")

try:
    from app.schemas.model_predict import RoutingInfo
    check("TP-SCH-01a: RoutingInfo import", True)

    ri_default = RoutingInfo()
    check("TP-SCH-01b: RoutingInfo() default construct",
          ri_default.selected_model_id is None and
          ri_default.selected_model_family is None and
          ri_default.routing_reason is None and
          ri_default.feature_coverage_ratio is None and
          ri_default.prediction_confidence_band is None)

    ri_lite = RoutingInfo(
        selected_model_id="mmpsy_lite_model",
        selected_model_family="lite",
        routing_reason="lite_fallback",
        feature_coverage_ratio=0.12,
        prediction_confidence_band="medium"
    )
    check("TP-SCH-01c: RoutingInfo full construct",
          ri_lite.selected_model_family == "lite")

    # Test type validation
    try:
        RoutingInfo(feature_coverage_ratio="not_a_float")
        check("TP-SCH-01d: type validation rejects string for float field", False)
    except Exception:
        check("TP-SCH-01d: type validation rejects string for float field", True)

    # TP-SVC-01: Service routing log (via engine directly, service is a thin wrapper)
    async def run_svc_test():
        from app.core.model_engine import ModelEngine
        engine = ModelEngine()
        result = await engine.predict_structured({"gad7_score": 15,
            "audio_transcript": "失眠睡不着考试压力大心情差" * 3})
        ri = result.get("routing_info")
        check("TP-SVC-01a: predict_tabular result returned", True)
        check("TP-SVC-01b: result contains routing_info",
              ri is not None,
              f"routing_info keys={list(ri.keys()) if ri else None}")
        check("TP-SVC-01c: routing family is lite",
              ri.get("selected_model_family") == "lite" if ri else False,
              f"family={ri.get('selected_model_family') if ri else None}")

    try:
        asyncio.run(run_svc_test())
    except Exception as e:
        check("TP-SVC-01: service routing test error", False, str(e))

except Exception as e:
    check("Phase 6: Schema/Service tests", False, str(e))

# ── Summary ──
print("\n" + "=" * 60)
print("Test Summary")
print("=" * 60)
passed = sum(1 for _, status, _ in results if status == "PASS")
failed = sum(1 for _, status, _ in results if status == "FAIL")
print(f"  Total: {len(results)} | Passed: {passed} | Failed: {failed}")
if failed > 0:
    print("\n  Failed tests:")
    for name, status, detail in results:
        if status == "FAIL":
            print(f"    - {name}: {detail}")
print("=" * 60)
