"""ROUND_16 探针 B：结构化侧 T1 DCA/ECE + T3 公平性评估与缓解 + T2 融合 fixture 消融.

用法（backend 目录下）:
    .venv/Scripts/python.exe tests/tools/probe_p2_40_round16_struct.py

产出: tests/tools/probe_p2_40_round16_struct_result.json（运行时读数，按需入库）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

OUT = Path(__file__).resolve().parent / "probe_p2_40_round16_struct_result.json"

V123_DIR = BACKEND_ROOT / "models" / "v1.23_external_lr"
TEXT_DIR = BACKEND_ROOT / "models" / "text"
FIXTURE = REPO_ROOT / "datasets" / "fusion" / "fusion_test_scenarios_v2.json"
TEST_CSV = REPO_ROOT / "data" / "processed" / "v1_23_external" / "test.csv"


def load_v123_feature_order() -> list[str]:
    schema = json.loads((V123_DIR / "feature_schema.json").read_text(encoding="utf-8"))
    return [f["name"] for f in schema["features"]]


def main() -> None:
    result: dict[str, object] = {"probe": "p2_40_round16_struct", "sections": {}}

    # ── T1 结构化侧：v1.23 外部留出集 DCA / ECE / 校准 ────────────────────
    from app.ml.model_validation import (
        compute_brier_score,
        compute_ece,
        decision_curve_analysis,
    )
    from sklearn.metrics import roc_auc_score

    model = joblib.load(V123_DIR / "model.pkl")
    preprocessor = joblib.load(V123_DIR / "preprocessor.pkl")
    # S-02 兼容补丁：与生产加载器（app/core/model_engine/loading.py）同一手法——
    # sklearn 1.8.0 的 SimpleImputer.transform 引用 _fill_dtype，旧 pickle 缺失该属性。
    # 递归遍历（Pipeline.named_steps / ColumnTransformer.transformers_ / 嵌套），
    # 因为 SimpleImputer 通常嵌在 ColumnTransformer 里，不是 Pipeline 直接 step。
    def _patch_imputers(est: object, _seen: set[int] | None = None) -> int:
        seen = _seen if _seen is not None else set()
        if id(est) in seen:
            return 0
        seen.add(id(est))
        patched = 0
        if (
            est.__class__.__name__ == "SimpleImputer"
            and not hasattr(est, "_fill_dtype")
            and hasattr(est, "_fit_dtype")
        ):
            est._fill_dtype = est._fit_dtype  # type: ignore[attr-defined]
            patched += 1
        for attr in ("named_steps", "transformers_", "transformers", "steps", "estimators_"):
            children = getattr(est, attr, None)
            if not children:
                continue
            items = children.values() if hasattr(children, "values") else children
            for child in items:
                child = child[1] if isinstance(child, tuple) and len(child) >= 2 else child
                if child.__class__.__module__.startswith("sklearn"):
                    patched += _patch_imputers(child, seen)
        return patched

    _n_patched = _patch_imputers(model) + _patch_imputers(preprocessor)
    feats = load_v123_feature_order()
    test_df = pd.read_csv(TEST_CSV)
    X = test_df[feats].copy()

    if hasattr(model, "predict_proba") and hasattr(model, "named_steps"):
        # model.pkl 自带完整 Pipeline
        p = model.predict_proba(X)[:, 1]
        pipe_desc = "model.pkl (full Pipeline)"
    else:
        p = model.predict_proba(preprocessor.transform(X))[:, 1]
        pipe_desc = "preprocessor.pkl + model.pkl"

    y = test_df["depression_binary"].astype(int).values
    print(f"[s02-patch] imputers patched: {_n_patched}")
    dca = decision_curve_analysis(y, p)
    result["sections"]["t1_structured"] = {
        "data": "data/processed/v1_23_external/test.csv (external holdout)",
        "pipeline": pipe_desc,
        "n": int(len(y)),
        "positive_rate": round(float(y.mean()), 4),
        "auroc": round(float(roc_auc_score(y, p)), 4),
        "brier": round(compute_brier_score(y, p), 4),
        "ece": round(compute_ece(y, p), 4),
        "dca_summary": dca["summary"],
        "dca_prevalence": dca["prevalence"],
    }

    # ── T3 公平性：性别分组评估（assessment）与缓解建议（mitigation，未启用）──
    from app.ml.fairness_mitigation import suggest_group_thresholds, suggest_sample_reweights
    from app.ml.model_validation import compute_fairness_metrics

    gender = test_df["gender"].map({0: "female", 1: "male"}).fillna("unknown").values
    y_pred = (p >= 0.5).astype(int)
    fairness = compute_fairness_metrics(y, y_pred, p, gender)
    result["sections"]["t3_fairness_assessment"] = {
        "group_by": "gender",
        "per_group": fairness.get("per_group"),
        "disparities": fairness.get("disparities"),
        "suppressed_groups": fairness.get("suppressed_groups", fairness.get("_suppressed")),
    }
    mitigation = {
        "group_thresholds": suggest_group_thresholds(y, p, gender),
        "sample_reweights": suggest_sample_reweights(y, gender),
    }
    result["sections"]["t3_fairness_mitigation"] = mitigation

    # ── T2 融合 fixture 消融（in-sample 警示：权重即在该文件上挑选）──────────
    from app.core.model_engine import ModelEngine
    from app.ml.fusion_ablation import run_ablation
    from app.ml.fusion_engine import FusionEngine

    scenarios = json.loads(FIXTURE.read_text(encoding="utf-8"))
    # 同队列纪律：只保留三模态齐全的场景（fixture 49 条含 7 种 payload 形态：
    # 全模态 21 条 + 各种单/双模态设计场景 28 条）。缺任一模态的场景不掺入
    # ΔAUROC 对比（否则臂之间队列不同，Δ 无意义）
    scenarios = [
        s
        for s in scenarios
        if {"features", "text", "physiological"} <= set(s["payload"].keys())
    ]
    n_dropped = 49 - len(scenarios)
    tfidf = joblib.load(TEXT_DIR / "improved_bilingual_tfidf.pkl")
    text_model = joblib.load(TEXT_DIR / "improved_bilingual_model.pkl")
    engine = ModelEngine()
    fusion = FusionEngine()

    arms: dict[str, list[float]] = {"structured": [], "text": [], "physiological": [], "fusion": []}
    labels: list[int] = []
    physio_failures = 0
    for s in scenarios:
        payload = s["payload"]
        labels.append(int(s["label"]))
        sf = {k: payload["features"][k] for k in feats}
        if hasattr(model, "named_steps"):
            p_struct = float(model.predict_proba(pd.DataFrame([sf]))[0, 1])
        else:
            p_struct = float(model.predict_proba(preprocessor.transform(pd.DataFrame([sf])))[0, 1])
        p_text = float(text_model.predict_proba(tfidf.transform([payload["text"]]))[0, 1])
        try:
            physio_score_0100 = engine._predict_physiological_sync(payload["physiological"])
            p_physio = float(physio_score_0100) / 100.0
        except Exception:
            physio_failures += 1
            p_physio = 0.5  # 失败即中性分，如实记账失败数
        fused = fusion.fuse(
            {
                "structured": p_struct * 100.0,
                "text": p_text * 100.0,
                "physiological": p_physio * 100.0,
            }
        )
        arms["structured"].append(p_struct)
        arms["text"].append(p_text)
        arms["physiological"].append(p_physio)
        arms["fusion"].append(float(fused["risk_score"]) / 100.0)

    ablation = run_ablation(
        np.asarray(labels),
        {k: np.asarray(v) for k, v in arms.items()},
        base_arm="structured",
        groups=None,
        in_sample=True,
        source="datasets/fusion/fusion_test_scenarios_v2.json (49 条设计场景; 融合权重历史上于同文件 in-sample 挑选, optimize_fusion_weights.py)",
    )
    result["sections"]["t2_fusion_fixture_ablation"] = {
        "ablation": ablation.to_dict(),
        "physio_failures": physio_failures,
        "scenarios_total": 49,
        "scenarios_used": len(scenarios),
        "scenarios_dropped_single_modality": n_dropped,
        "caveat": "fixture 为设计样本(非自然队列); 权重 in-sample; CI 覆盖 0 即无显著增量, 如实报",
    }
    result["sections"]["t2_cohort_disjointness"] = {
        "structured": "aligned_features.csv / Student Depression Dataset (PHQ-9 条目, 无文本无生理)",
        "text": "chinese_depression_corpus_v1.csv + reddit cleaned (文本, 无结构/生理测量)",
        "physiological": "WESAD 风格 13 维可穿戴特征 (第三方队列)",
        "finding": "三个模态训练队列受试者不相交 ⇒ 自然队列上的融合增量 ΔAUROC 无法量化; fixture 结果仅证明消融机制可用",
    }

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:4000])
    print(f"\n[written] {OUT}")


if __name__ == "__main__":
    main()
