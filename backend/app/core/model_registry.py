from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ModelLifecycle(StrEnum):
    DEFAULT = "default"
    LIMITED_ACTIVE = "limited_active"
    CANDIDATE = "candidate"
    EXPERIMENTAL = "experimental"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"
    # 2026-11 (D5)：已退役。对应制品不存在/不再交付，仅保留注册表信息用于历史追溯，
    # 永不被 get_active_models 选中，也不得被生产引用。
    RETIRED = "retired"


ACTIVE_LIFECYCLES: frozenset[str] = frozenset({ModelLifecycle.DEFAULT, ModelLifecycle.LIMITED_ACTIVE})

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# ── 2026-11 (D5)：生产必需制品与死条目治理 ──
# 生产部署必需制品（相对 backend/）。生产环境缺失任一即启动失败；
# 开发/测试环境允许降级，但必须在 /health 显式暴露并打告警（见 app.main.lifespan）。
DEPLOYMENT_REQUIRED_ARTIFACTS: dict[str, str] = {
    "structured_v1.23_external_lr": "models/v1.23_external_lr/model.pkl",
    "physiological_model_v2_dl": "models/artifacts/physiological_optimized/model.json",
    "physiological_scaler_v2_dl": "models/artifacts/physiological_optimized/scaler.json",
    "text_improved_bilingual_model": "models/text/improved_bilingual_model.pkl",
    "text_improved_bilingual_tfidf": "models/text/improved_bilingual_tfidf.pkl",
    "mmpsy_lite_model": "models/v1.25_mmpsy_lite/mmpsy_lite_model.pkl",
}

# 指向不存在文件的死条目：保留 ID 以兼容历史引用（model_compatibility / 实验对比），
# 但明确标注为「不可解析 + retired」，不得作为生产产物，也不得进入交付镜像。
# 复核时间 2026-11：以下路径在 backend/ 下均不存在（含 D6 决定不纳入交付的融合 DNN）。
UNRESOLVABLE_MODEL_IDS: frozenset[str] = frozenset(
    {
        "fusion_dnn_best",
        "fusion_cross_modal_best",
        "fusion_transformer_best",
        "physiological_risk_model",
        "physiological_risk_scaler",
        "structured_random_forest_quick",
        "structured_best_ensemble_quick",
        "structured_best_threshold",
    }
)

# 非文件承载条目：注册表有 ID，但对应权重并不以独立文件形式交付。
# 2026-11 复核：`structured_v1.23_external_scaler` 指向 models/v1.23_external_lr/scaler.pkl，
# 该文件不存在——**v1.23 的缩放器已内嵌在 model.pkl 的 sklearn Pipeline 内**，
# 无需也不应单独加载，故标记 resolvable=False（保留 ID 以兼容历史引用）。
NON_FILE_BACKED_MODEL_IDS: frozenset[str] = frozenset(
    {
        "structured_v1.23_external_scaler",
    }
)


DEPLOYMENT_MANIFEST_FILENAME = "DEPLOYMENT_MANIFEST.json"
DEPLOYMENT_MANIFEST_SCHEMA = "dws-deployment-artifacts/v1"


def _artifact_candidates(base: Path, relative_path: str) -> list[Path]:
    """解析制品的候选路径：MODEL_DIR 挂载点优先，其次仓库 backend/models。"""
    candidates = [base / relative_path]
    if relative_path.startswith("models/"):
        candidates.append(base / relative_path[len("models/") :])
    candidates.append(BACKEND_ROOT / relative_path)
    return candidates


def _resolve_artifact(base: Path, relative_path: str) -> Path | None:
    for candidate in _artifact_candidates(base, relative_path):
        if candidate.is_file():
            return candidate
    return None


def compute_sha256(file_path: str | Path) -> str:
    """流式计算 SHA256（与 safe_pickle 的校验口径一致）。"""
    digest = hashlib.sha256()
    with open(file_path, "rb") as handle:
        while chunk := handle.read(64 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def build_deployment_manifest(model_dir: str | Path) -> dict[str, Any]:
    """生成部署制品清单（含每条制品的字节数与 sha256）。

    供 `scripts/artifact_manifest.py` 调用；清单本身应与制品一同分发，
    启动期 `audit_deployment_artifacts` 以此核对完整性。
    """
    base = Path(model_dir)
    if not base.is_absolute():
        base = BACKEND_ROOT / base
    artifacts: list[dict[str, Any]] = []
    missing: list[str] = []
    for model_id, relative_path in DEPLOYMENT_REQUIRED_ARTIFACTS.items():
        resolved = _resolve_artifact(base, relative_path)
        if resolved is None:
            missing.append(model_id)
            continue
        artifacts.append(
            {
                "model_id": model_id,
                "path": relative_path,
                "bytes": resolved.stat().st_size,
                "sha256": compute_sha256(resolved),
            }
        )
    if missing:
        raise FileNotFoundError(
            "无法生成制品清单，以下必需制品缺失: " + ", ".join(missing)
        )
    return {
        "schema": DEPLOYMENT_MANIFEST_SCHEMA,
        "algorithm": "sha256",
        "generated_at": "2026-11-03",
        "artifacts": artifacts,
    }


def audit_deployment_artifacts(
    model_dir: str | Path,
    *,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """校验生产必需制品：存在性 + 清单哈希一致性。

    返回 ``{"present", "missing", "hash_mismatch", "unverified", "manifest_status"}``。
    只返回模型 ID，不泄露绝对路径或摘要之外的信息。
    - 清单缺失：``manifest_status="missing"``，全部制品记为 unverified；
    - 清单存在但条目缺失：该制品 unverified（不误报为 mismatch）；
    - 哈希不一致：进入 ``hash_mismatch``。
    ``manifest`` 参数仅供测试/负向用例注入，生产应从清单文件读取。
    """
    base = Path(model_dir)
    if not base.is_absolute():
        base = BACKEND_ROOT / base

    manifest_status = "ok"
    if manifest is None:
        manifest_path = base / DEPLOYMENT_MANIFEST_FILENAME
        if not manifest_path.is_file():
            manifest_path = BACKEND_ROOT / "models" / DEPLOYMENT_MANIFEST_FILENAME
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                manifest = None
                manifest_status = "invalid"
        else:
            manifest_status = "missing"
    elif manifest.get("schema") != DEPLOYMENT_MANIFEST_SCHEMA:
        manifest_status = "invalid"

    entries: dict[str, dict[str, Any]] = {}
    if isinstance(manifest, dict):
        for entry in manifest.get("artifacts", []):
            if isinstance(entry, dict) and entry.get("model_id"):
                entries[str(entry["model_id"])] = entry

    present: list[str] = []
    missing: list[str] = []
    hash_mismatch: list[str] = []
    unverified: list[str] = []
    for model_id, relative_path in DEPLOYMENT_REQUIRED_ARTIFACTS.items():
        resolved = _resolve_artifact(base, relative_path)
        if resolved is None:
            missing.append(model_id)
            continue
        present.append(model_id)
        entry = entries.get(model_id)
        expected = str(entry.get("sha256", "")).strip().lower() if entry else ""
        if not expected:
            unverified.append(model_id)
            continue
        actual = compute_sha256(resolved)
        if actual != expected:
            hash_mismatch.append(model_id)

    return {
        "present": present,
        "missing": missing,
        "hash_mismatch": hash_mismatch,
        "unverified": unverified,
        "manifest_status": manifest_status,
    }


# 统一模型 ID 命名规范：使用 lower_snake_case，并按业务域分组。
MODEL_PATHS: dict[str, str] = {
    "structured_logistic_regression_quick": "models/artifacts/structured_v1.20/structured_model_v1.20.pkl",
    "structured_logistic_regression_v1.20": "models/artifacts/structured_v1.20/structured_model_v1.20.pkl",
    "structured_scaler_v1.20": "models/artifacts/structured_v1.20/structured_scaler_v1.20.pkl",
    "structured_manifest_v1.20": "models/artifacts/structured_v1.20/structured_manifest_v1.20.json",
    "structured_random_forest_quick": "models/artifacts/depression_tabular/best_model.pkl",
    "structured_best_ensemble_quick": "models/artifacts/depression_tabular/best_model.pkl",
    "structured_best_threshold": "models/artifacts/depression_tabular/metrics.json",
    "text_improved_bilingual_model": "models/text/improved_bilingual_model.pkl",
    "text_improved_bilingual_tfidf": "models/text/improved_bilingual_tfidf.pkl",
    "text_depression_model": "models/artifacts/text_depression_classifier/text_model.pkl",
    "text_depression_tfidf": "models/artifacts/text_depression_classifier/text_tfidf.pkl",
    # 2026-10-09 实测真相：这三个条目指向的 models/keras/ 是**仓库根的训练期影子目录**
    # （权重文件 2026-02，未纳入版本控制，backend/Dockerfile 只 COPY backend/models/）。
    # 部署侧 backend/models/ 下不存在 keras 子目录，因此这三条在生产/CI 恒为 MISSING，
    # preload 走 FileNotFoundError → 回退启发式/加权融合。
    # 历史坑：修复前 _abs_path 会把相对 model_dir 的父目录解析成 CWD，导致从仓库根启动时
    # 静默加载这批 2026-02 陈旧权重（同一份代码、两种行为）。现已锚定 backend_root
    # 并移除 CWD 兜底，见 tests/test_model_path_resolution.py 防复发闸门。
    # 保留条目的原因：model_compatibility 登记与实验性对比仍引用这些 ID，移除会破坏
    # test_model_compatibility_registry 的断言；若要真正启用 TF 融合，需先把权重
    # 落到 backend/models/keras/ 并纳入交付流程。
    "fusion_dnn_best": "models/keras/dnn_fusion_model_best.keras",
    "fusion_cross_modal_best": "models/keras/cross_modal_fusion_model_best.keras",
    "fusion_transformer_best": "models/keras/transformer_fusion_model_best.keras",
    "physiological_risk_model": "models/physiological/physiological_model.pkl",
    "physiological_risk_scaler": "models/physiological/physiological_scaler.pkl",
    "physiological_model_v2_dl": "models/artifacts/physiological_optimized/model.json",
    "physiological_scaler_v2_dl": "models/artifacts/physiological_optimized/scaler.json",
    "physiological_features_v2_dl": "models/artifacts/physiological_optimized/feature_names.json",
    # S-03 (V4 ML 优化): v1.21 模型已清理并归档到 models/_archive/structured_v1.21/
    # 4 个 v1.21 注册条目 (binary_lr/binary_rf/multiclass_lr/multiclass_rf) 及相关 scaler/manifest 已移除
    # 2026-10-04 (P0-1 遗留①): text_bert_classifier 注册条目与 models/text/bert_text_classifier/
    # 权重一并移除。该目录从未被 git 跟踪(本地仅 6.8KB 占位产物, 非真实 BERT 权重),
    # 生产文本主路径为双语 TF-IDF+LR(见 tests/test_model_engine.py: _predict_text_ml
    # 永不请求 text_bert_classifier)。产物归档至 models/_archive/bert_text_classifier_20261004/
    # (不入库, 沿用 v1.21 归档先例)。替代升级路线见 P2-1 句向量升级立项。
    "structured_v1.23_external_lr": "models/v1.23_external_lr/model.pkl",
    "structured_v1.23_external_scaler": "models/v1.23_external_lr/scaler.pkl",
    "structured_v1.24_adapter": "models/v1.24_adapter/score_adapter.pkl",
    "mmpsy_lite_model": "models/v1.25_mmpsy_lite/mmpsy_lite_model.pkl",
    "mmpsy_lite_scaler": "models/v1.25_mmpsy_lite/mmpsy_lite_scaler.pkl",
    "mmpsy_lite_gbdt": "models/v1.25_mmpsy_lite/mmpsy_lite_model_gbdt.pkl",
    # v1.27 lite LR 概率校准器 (Platt, 冻结 v1.25 模型):
    # predict_lite 在产物存在时应用; 缺失时静默回退 raw 概率 (行为不变)
    "mmpsy_lite_calibrator": "models/v1.27_lite_calibration/calibrator.pkl",
    "mmpsy_lite_calibrator_meta": "models/v1.27_lite_calibration/calibrator_meta.json",
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
    # 2026-11 (D5): 制品路径是否可解析。False 表示注册表条目对应的权重文件
    # 不在交付物中（死条目），调用方必须先判空再加载。
    resolvable: bool = True


MODEL_REGISTRY: dict[str, ModelMetadata] = {
    model_id: ModelMetadata(
        name=model_id,
        path=path,
        supports_fusion=model_id.startswith("fusion_") or model_id.startswith("physiological_"),
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
# S-03 (V4 ML 优化): v1.21 deprecated 模型已清理
# 原 4 个注册条目 (structured_v1.21_binary_lr / _binary_rf / _multiclass_lr / _multiclass_rf)
# 及其 scaler/manifest 路径已从 MODEL_PATHS 和 MODEL_REGISTRY 中移除。
# 模型文件已归档到 models/_archive/structured_v1.21/。
# _run_experimental_v121() 方法保留以维持 PERF-P0-002 并行机制，
# 内部通过 get_model_info() 返回 None 走 deprecated 分支，记录 debug 日志并返回 None 字段。
# Register v2 physiological model with detailed metadata
# S-01 (V4 ML 优化): v2 已为生产默认，实际推理通过 app/ml/model_loader.py 加载
MODEL_REGISTRY["physiological_model_v2_dl"] = ModelMetadata(
    name="physiological_model_v2_dl",
    path="models/artifacts/physiological_optimized/model.json",
    version="v1.2-depresjon-optimized",
    enabled=True,
    supports_fusion=True,
    lifecycle="default",
    feature_schema={
        "input_features": 13,
        "hidden_dims": [128, 64, 32, 16],
        "dropout_rate": 0.2,
        "use_batch_norm": True,
        "architecture": "MLP",
        "framework": "numpy",
    },
    artifact_metadata={
        "training_date": "2026-10-22",
        "dataset": "Depresjon (clinical, n=1029)",
        "dataset_size": 1029,
        "evaluation_set_size": 157,
        "evaluation_scheme": "single stratified 70/15/15 split, random_state=42",
        "test_f1": 0.8205128205128205,
        "test_accuracy": 0.8662420382165605,
        "test_roc_auc": 0.9450980392156862,
        "test_auprc": 0.8919268523615607,
        "best_epoch": 27,
        "model_parameters": 13153,
        "loss_function": "BCE",
    },
)
# S-01 (V4 ML 优化): v1 模型标记为 deprecated，保留作为回退路径
# 实际推理已通过 model_loader.py 加载 v2 (physiological_optimized/model.json)
MODEL_REGISTRY["physiological_risk_model"] = ModelMetadata(
    name="physiological_risk_model",
    path="models/physiological/physiological_model.pkl",
    version="v1.0",
    enabled=False,
    supports_fusion=False,
    lifecycle="deprecated",
    feature_schema={
        "input_features": 13,
        "architecture": "MLP",
        "framework": "numpy",
        "status": "deprecated — superseded by physiological_model_v2_dl (S-01)",
    },
    artifact_metadata={
        "training_date": "2026-04",
        "test_f1": 0.6936,
        "test_accuracy": 0.6890,
        "superseded_by": "physiological_model_v2_dl",
        "superseded_date": "2026-07-19",
    },
)
# Register v1.23 external clinical-label LR model
# S-02 (V4 ML 优化): lifecycle 从 "experimental" 升级为 "default"
# 通过 settings.structured_default_model 配置开关选择 v1.20 或 v1.23 作为默认
# 金丝雀发布时通过环境变量 STRUCTURED_DEFAULT_MODEL=v1.23 切换
MODEL_REGISTRY["structured_v1.23_external_lr"] = ModelMetadata(
    name="structured_v1.23_external_lr",
    path="models/v1.23_external_lr/model.pkl",
    version="v1.23",
    enabled=True,
    supports_fusion=False,
    lifecycle="default",
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
        "model_type": "Pipeline(ColumnTransformer + LogisticRegression)",
        "framework": "sklearn",
        "training_data": "external (Kaggle+Mendeley aligned, Mendeley sample_weight=5.0x)",
        "status": "default — candidate model, enable via STRUCTURED_DEFAULT_MODEL=v1.23",
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


# 2026-11 (D5): 显式标注死条目，避免下游把「注册表里有」误当「文件存在」。
# 放在所有注册语句之后执行，防止后续显式 register 把标记重置回 True。
for _dead_model_id in UNRESOLVABLE_MODEL_IDS:
    _dead_metadata = MODEL_REGISTRY.get(_dead_model_id)
    if _dead_metadata is not None:
        _dead_metadata.resolvable = False
        _dead_metadata.enabled = False
        _dead_metadata.lifecycle = ModelLifecycle.RETIRED
        _dead_metadata.artifact_metadata = {
            **_dead_metadata.artifact_metadata,
            "archive_reason": "artifact_missing_or_not_delivered",
            "archive_date": "2026-11",
        }

# 非文件承载条目：没有独立制品，但语义上仍可用（如 Pipeline 内置 scaler）。
for _non_file_model_id in NON_FILE_BACKED_MODEL_IDS:
    _non_file_metadata = MODEL_REGISTRY.get(_non_file_model_id)
    if _non_file_metadata is not None:
        _non_file_metadata.resolvable = False
        _non_file_metadata.artifact_metadata = {
            **_non_file_metadata.artifact_metadata,
            "embedded_in": "models/v1.23_external_lr/model.pkl",
            "note": "v1.23 的 scaler 在 Pipeline 内，无独立文件",
        }


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
    normalized = normalize_model_id(model_id)

    # 训练产物注册表 (V2) 优先: PRODUCTION 记录且产物存在时覆盖静态路径,
    # 使推理链可切换到经过验证的训练产物.
    try:
        from app.core.model_registry_v2 import ModelStatus, get_registry

        record = get_registry().get_model(normalized)
        if record is not None and record.status == ModelStatus.PRODUCTION and record.artifact_path:
            artifact = Path(record.artifact_path)
            # artifact_path 支持绝对路径或相对项目根路径 (backend/)
            candidates = [artifact]
            if not artifact.is_absolute():
                candidates.append(Path(__file__).resolve().parents[2] / artifact)
            for candidate in candidates:
                if candidate.exists():
                    return str(candidate)
    except Exception as exc:  # pragma: no cover - 注册表异常不应阻断推理
        logger.warning("resolve_model_path: V2 registry lookup failed for %s: %s", model_id, exc)

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
    return [(mid, meta) for mid, meta in MODEL_REGISTRY.items() if meta.lifecycle in allowed and meta.enabled]


def list_models_by_lifecycle() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for mid, meta in MODEL_REGISTRY.items():
        result.setdefault(meta.lifecycle, []).append(mid)
    return result
