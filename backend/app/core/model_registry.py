from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ModelLifecycle(StrEnum):
    DEFAULT = "default"
    LIMITED_ACTIVE = "limited_active"
    CANDIDATE = "candidate"
    EXPERIMENTAL = "experimental"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


ACTIVE_LIFECYCLES: frozenset[str] = frozenset(
    {ModelLifecycle.DEFAULT, ModelLifecycle.LIMITED_ACTIVE}
)


# 统一模型 ID 命名规范：使用 lower_snake_case，并按业务域分组。
MODEL_PATHS: dict[str, str] = {
    "structured_logistic_regression_quick": "models/artifacts/structured_v1.20/structured_model_v1.20.pkl",
    "structured_logistic_regression_v1.20": "models/artifacts/structured_v1.20/structured_model_v1.20.pkl",
    "structured_scaler_v1.20": "models/artifacts/structured_v1.20/structured_scaler_v1.20.pkl",
    "structured_manifest_v1.20": "models/artifacts/structured_v1.20/structured_manifest_v1.20.json",
    "structured_random_forest_quick": "models/artifacts/depression_tabular/best_model.pkl",
    "structured_best_ensemble_quick": "models/artifacts/depression_tabular/best_model.pkl",
    "structured_best_threshold": "models/artifacts/depression_tabular/metrics.json",
    "text_bert_classifier": "models/text/bert_text_classifier",
    "text_improved_bilingual_model": "models/text/improved_bilingual_model.pkl",
    "text_improved_bilingual_tfidf": "models/text/improved_bilingual_tfidf.pkl",
    "text_depression_model": "models/artifacts/text_depression_classifier/text_model.pkl",
    "text_depression_tfidf": "models/artifacts/text_depression_classifier/text_tfidf.pkl",
    "fusion_dnn_best": "models/keras/dnn_fusion_model_best.keras",
    "fusion_cross_modal_best": "models/keras/cross_modal_fusion_model_best.keras",
    "fusion_transformer_best": "models/keras/transformer_fusion_model_best.keras",
    "physiological_risk_model": "models/physiological/physiological_model.pkl",
    "physiological_risk_scaler": "models/physiological/physiological_scaler.pkl",
    "physiological_model_v2_dl": "models/artifacts/physiological_optimized/model.json",
    "physiological_scaler_v2_dl": "models/artifacts/physiological_optimized/scaler.json",
    "physiological_features_v2_dl": "models/artifacts/physiological_optimized/feature_names.json",
    "structured_v1.21_binary_lr": "models/artifacts/structured_v1.21/model_binary_lr.pkl",
    "structured_v1.21_binary_rf": "models/artifacts/structured_v1.21/model_binary_rf.pkl",
    "structured_v1.21_scaler": "models/artifacts/structured_v1.21/scaler.pkl",
    "structured_v1.21_multiclass_lr": "models/artifacts/structured_v1.21/model_multiclass_lr.pkl",
    "structured_v1.21_multiclass_rf": "models/artifacts/structured_v1.21/model_multiclass_rf.pkl",
    "structured_v1.21_scaler_mc": "models/artifacts/structured_v1.21/scaler_multiclass.pkl",
    "structured_v1.21_manifest": "models/artifacts/structured_v1.21/manifest.json",
    "structured_v1.23_external_lr": "models/v1.23_external_lr/model.pkl",
    "structured_v1.23_external_scaler": "models/v1.23_external_lr/scaler.pkl",
    "structured_v1.24_adapter": "models/v1.24_adapter/score_adapter.pkl",
    "mmpsy_lite_model": "models/v1.25_mmpsy_lite/mmpsy_lite_model.pkl",
    "mmpsy_lite_scaler": "models/v1.25_mmpsy_lite/mmpsy_lite_scaler.pkl",
    "mmpsy_lite_gbdt": "models/v1.25_mmpsy_lite/mmpsy_lite_model_gbdt.pkl",
}


@dataclass(slots=True)
class ModelMetadata:
    name: str
    path: str
    version: str = "v1"
    enabled: bool = True
    supports_fusion: bool = False
    lifecycle: str = "experimental"
    feature_schema: dict[str, object] = field(default_factory=dict)
    artifact_metadata: dict[str, object] = field(default_factory=dict)


MODEL_REGISTRY: dict[str, ModelMetadata] = {
    model_id: ModelMetadata(
        name=model_id,
        path=path,
        supports_fusion=model_id.startswith("fusion_")
        or model_id.startswith("physiological_"),
    )
    for model_id, path in MODEL_PATHS.items()
}

# Register v1.20 structured model with v1.20 training metadata
MODEL_REGISTRY["structured_logistic_regression_v1.20"] = ModelMetadata(
    name="structured_logistic_regression_v1.20",
    path="models/artifacts/structured_v1.20/structured_model_v1.20.pkl",
    version="v1.20",
    enabled=True,
    supports_fusion=False,
    lifecycle="default",
    feature_schema={
        "features": [
            "age",
            "cgpa",
            "stress_level",
            "sleep_duration",
            "social_support",
            "financial_pressure",
            "family_history",
            "academic_pressure",
            "exercise_frequency",
            "anxiety",
            "panic_attack",
            "treatment_seeking",
        ],
        "input_features": 12,
        "model_type": "LogisticRegression",
        "framework": "sklearn",
        "class_weight": "balanced",
    },
    artifact_metadata={
        "training_date": "2026-05-01",
        "random_seed": 42,
        "dataset_size": 10000,
        "test_accuracy": 0.9833,
        "test_f1": 0.9875,
        "test_roc_auc": 0.9991,
    },
)
# Register v1.21 real-data binary models (experimental)
MODEL_REGISTRY["structured_v1.21_binary_lr"] = ModelMetadata(
    name="structured_v1.21_binary_lr",
    path="models/artifacts/structured_v1.21/model_binary_lr.pkl",
    version="v1.21",
    enabled=True,
    supports_fusion=False,
    lifecycle="deprecated",
    feature_schema={
        "features": [
            "age",
            "gender",
            "study_year",
            "cgpa",
            "stress_level",
            "sleep_duration",
            "social_support",
            "financial_pressure",
            "family_history",
            "academic_pressure",
            "exercise_frequency",
            "anxiety",
            "panic_attack",
            "treatment_seeking",
        ],
        "input_features": 14,
        "model_type": "LogisticRegression",
        "framework": "sklearn",
        "class_weight": "balanced",
        "training_data": "real (student_mental_health_enhanced.csv)",
        "status": "experimental — Conditional Go",
    },
    artifact_metadata={
        "training_date": "2026-05-01",
        "random_seed": 42,
        "dataset_size": 1000,
        "test_f1": 0.6000,
        "test_recall": 0.9130,
        "test_roc_auc": 0.9401,
    },
)
MODEL_REGISTRY["structured_v1.21_binary_rf"] = ModelMetadata(
    name="structured_v1.21_binary_rf",
    path="models/artifacts/structured_v1.21/model_binary_rf.pkl",
    version="v1.21",
    enabled=True,
    supports_fusion=False,
    lifecycle="deprecated",
    feature_schema={
        "input_features": 14,
        "model_type": "RandomForestClassifier",
        "training_data": "real",
    },
    artifact_metadata={
        "training_date": "2026-05-01",
        "test_f1": 0.6829,
        "test_recall": 0.6087,
    },
)
MODEL_REGISTRY["structured_v1.21_multiclass_lr"] = ModelMetadata(
    name="structured_v1.21_multiclass_lr",
    path="models/artifacts/structured_v1.21/model_multiclass_lr.pkl",
    version="v1.21",
    enabled=False,
    supports_fusion=False,
    lifecycle="disabled",
    feature_schema={
        "features": [
            "age",
            "gender",
            "study_year",
            "cgpa",
            "sleep_duration",
            "social_support",
            "financial_pressure",
            "family_history",
            "academic_pressure",
            "exercise_frequency",
        ],
        "input_features": 10,
        "model_type": "LogisticRegression (Multinomial)",
        "status": "No-Go — disabled due to poor performance",
    },
    artifact_metadata={
        "test_accuracy": 0.1333,
        "high_critical_recall": 0.6154,
    },
)
MODEL_REGISTRY["structured_v1.21_multiclass_rf"] = ModelMetadata(
    name="structured_v1.21_multiclass_rf",
    path="models/artifacts/structured_v1.21/model_multiclass_rf.pkl",
    version="v1.21",
    enabled=False,
    supports_fusion=False,
    lifecycle="disabled",
    feature_schema={
        "input_features": 10,
        "model_type": "RandomForestClassifier",
        "status": "No-Go — disabled due to poor performance",
    },
    artifact_metadata={
        "test_accuracy": 0.3200,
        "high_critical_recall": 0.1154,
    },
)
# Register v2 physiological model with detailed metadata
MODEL_REGISTRY["physiological_model_v2_dl"] = ModelMetadata(
    name="physiological_model_v2_dl",
    path="models/artifacts/physiological_optimized/model.json",
    version="v1.2-depresjon-optimized",
    enabled=True,
    supports_fusion=True,
    feature_schema={
        "input_features": 13,
        "hidden_dims": [64, 32, 16],
        "dropout_rate": 0.3,
        "use_batch_norm": True,
        "architecture": "MLP",
        "framework": "numpy",
    },
    artifact_metadata={
        "training_date": "2026-05-07",
        "dataset": "Depresjon (clinical, n=1029)",
        "test_f1": 0.9530,
        "test_accuracy": 0.9660,
        "test_roc_auc": 0.9940,
        "test_auprc": 0.9737,
        "best_epoch": 108,
        "model_parameters": 3745,
        "loss_function": "BCE",
    },
)
# Register v1.23 external clinical-label LR model (experimental)
MODEL_REGISTRY["structured_v1.23_external_lr"] = ModelMetadata(
    name="structured_v1.23_external_lr",
    path="models/v1.23_external_lr/model.pkl",
    version="v1.23",
    enabled=True,
    supports_fusion=False,
    lifecycle="experimental",
    feature_schema={
        "features": [
            "age",
            "gender",
            "cgpa",
            "stress_level",
            "sleep_duration",
            "social_support",
            "financial_pressure",
            "family_history",
            "academic_pressure",
            "exercise_frequency",
            "anxiety",
            "panic_attack",
        ],
        "input_features": 12,
        "model_type": "LogisticRegression",
        "framework": "sklearn",
        "training_data": "external (Kaggle+Mendeley aligned, Mendeley sample_weight=5.0x)",
        "status": "experimental — candidate model, not yet default",
    },
    artifact_metadata={
        "training_date": "2026-05-02",
        "random_seed": 42,
        "dataset_size": 19916,
        "test_auc": 0.9131,
        "test_f1": 0.8589,
        "test_recall": 0.8733,
        "phq9_pearson_r": 0.6826,
    },
)
# Register v1.24 adapter (score migration safety net)
MODEL_REGISTRY["structured_v1.24_adapter"] = ModelMetadata(
    name="structured_v1.24_adapter",
    path="models/v1.24_adapter/score_adapter.pkl",
    version="v1.24",
    enabled=True,
    supports_fusion=False,
    lifecycle="limited_active",
    feature_schema={
        "input_features": 12,
        "model_type": "ScoreAdapter (piecewise_monotonic)",
        "framework": "python",
        "adapter_type": "piecewise_monotonic",
        "mean_abs_delta": 4.37,
        "auc_loss": 0.0196,
    },
    artifact_metadata={
        "training_date": "2026-05-02",
        "clamp_delta": 20,
        "smooth_buffer": 3,
        "status": "candidate — shadow mode, not yet default",
    },
)

MODEL_REGISTRY["mmpsy_lite_model"] = ModelMetadata(
    name="mmpsy_lite_model",
    path="models/v1.25_mmpsy_lite/mmpsy_lite_model.pkl",
    version="v1.25",
    enabled=True,
    supports_fusion=False,
    lifecycle="limited_active",
    feature_schema={
        "features": [
            "gad7_score",
            "total_keywords",
            "unique_categories",
            "age",
            "gender",
            "cgpa",
            "text_length",
            "chinese_ratio",
            "text_quality_flag",
            "coverage_density",
        ],
        "input_features": 17,
        "model_type": "CalibratedClassifierCV(LogisticRegression)",
        "framework": "sklearn",
        "class_weight": "balanced",
        "excluded_inputs": ["phq9_score"],
        "label": "phq9_binary",
    },
    artifact_metadata={
        "training_date": "2026-05-02",
        "random_seed": 42,
        "dataset": "mmpsy",
        "dataset_size": 1275,
        "positive_ratio": 0.202,
    },
)

MODEL_REGISTRY["mmpsy_lite_scaler"] = ModelMetadata(
    name="mmpsy_lite_scaler",
    path="models/v1.25_mmpsy_lite/mmpsy_lite_scaler.pkl",
    version="v1.25",
    enabled=True,
    lifecycle="limited_active",
)


def normalize_model_id(model_id: str) -> str:
    return model_id.strip()


def register_model(
    model_id: str,
    path: str,
    *,
    version: str = "v1",
    enabled: bool = True,
    supports_fusion: bool = False,
    feature_schema: dict[str, object] | None = None,
    artifact_metadata: dict[str, object] | None = None,
) -> ModelMetadata:
    metadata = ModelMetadata(
        name=model_id,
        path=path,
        version=version,
        enabled=enabled,
        supports_fusion=supports_fusion,
        feature_schema=feature_schema or {},
        artifact_metadata=artifact_metadata or {},
    )
    MODEL_REGISTRY[model_id] = metadata
    MODEL_PATHS[model_id] = path
    return metadata


def get_model_info(model_id: str) -> ModelMetadata | None:
    return MODEL_REGISTRY.get(normalize_model_id(model_id))


def resolve_model_path(model_id: str) -> str:
    metadata = get_model_info(model_id)
    if metadata is not None:
        return metadata.path
    return MODEL_PATHS[normalize_model_id(model_id)]


def is_model_enabled(model_id: str) -> bool:
    metadata = get_model_info(model_id)
    return False if metadata is None else metadata.enabled


def get_active_models(
    lifecycle_filter: frozenset[str] | None = None,
) -> list[tuple[str, ModelMetadata]]:
    allowed = lifecycle_filter if lifecycle_filter is not None else ACTIVE_LIFECYCLES
    return [
        (mid, meta)
        for mid, meta in MODEL_REGISTRY.items()
        if meta.lifecycle in allowed and meta.enabled
    ]


def list_models_by_lifecycle() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for mid, meta in MODEL_REGISTRY.items():
        result.setdefault(meta.lifecycle, []).append(mid)
    return result
