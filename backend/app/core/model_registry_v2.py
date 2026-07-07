"""
Model Registry V2 - Production-grade model governance system.

Features:
- Model lifecycle management (candidate -> staging -> production -> retired)
- Fallback chain management
- Performance threshold monitoring
- Training configuration tracking
- Version control with semver

Usage:
    from app.core.model_registry_v2 import ModelRegistryV2, ModelStatus

    registry = ModelRegistryV2()
    registry.register_model(
        model_id="physiological_xgboost",
        name="Physiological XGBoost",
        version="v1.0.0",
        model_type="xgboost",
        status=ModelStatus.CANDIDATE,
        fallback_id="physiological_risk_model",
        artifact_path="models/artifacts/physiological/xgboost_model.pkl",
        metrics={"f1_score": 0.81, "precision": 0.79, "recall": 0.83},
        training_config={"random_state": 42, "n_estimators": 200},
    )
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ModelStatus(Enum):
    """Model lifecycle statuses."""

    CANDIDATE = "candidate"
    STAGING = "staging"
    PRODUCTION = "production"
    RETIRED = "retired"


class ModelType(Enum):
    """Supported model types."""

    XGBOOST = "xgboost"
    LIGHTGBM = "lightgbm"
    MLP = "mlp"
    CATBOOST = "catboost"
    LOGISTIC_REGRESSION = "logistic_regression"


@dataclass
class ModelRecord:
    """A single model record in the registry."""

    model_id: str
    name: str
    version: str
    model_type: ModelType
    status: ModelStatus
    fallback_id: str | None
    performance_threshold: dict[str, float]
    metrics: dict[str, float]
    artifact_path: str
    training_config: dict[str, Any]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "version": self.version,
            "model_type": self.model_type.value,
            "status": self.status.value,
            "fallback_id": self.fallback_id,
            "performance_threshold": self.performance_threshold,
            "metrics": self.metrics,
            "artifact_path": self.artifact_path,
            "training_config": self.training_config,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelRecord:
        return cls(
            model_id=data["model_id"],
            name=data["name"],
            version=data["version"],
            model_type=ModelType(data["model_type"]),
            status=ModelStatus(data["status"]),
            fallback_id=data.get("fallback_id"),
            performance_threshold=data.get("performance_threshold", {}),
            metrics=data.get("metrics", {}),
            artifact_path=data["artifact_path"],
            training_config=data.get("training_config", {}),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )


class ModelRegistryV2:
    """Production-grade model registry with lifecycle management."""

    def __init__(self, registry_path: str | None = None) -> None:
        self.registry: dict[str, ModelRecord] = {}
        self.registry_path = registry_path or "models/registry/model_registry_v2.json"
        self._load_registry()

    def _load_registry(self) -> None:
        """Load registry from disk."""
        path = Path(self.registry_path)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for model_id, record_data in data.get("models", {}).items():
                    self.registry[model_id] = ModelRecord.from_dict(record_data)
                logger.info("Loaded %d models from registry", len(self.registry))
            # M-Core-14 修复：扩大异常捕获范围，避免未知异常导致启动崩溃
            except (json.JSONDecodeError, KeyError, OSError, ValueError) as exc:
                logger.warning("Failed to load registry: %s", exc)

    def _save_registry(self) -> None:
        """Save registry to disk."""
        path = Path(self.registry_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": "2.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "models": {
                model_id: record.to_dict() for model_id, record in self.registry.items()
            },
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def register_model(
        self,
        model_id: str,
        name: str,
        version: str,
        model_type: ModelType,
        status: ModelStatus = ModelStatus.CANDIDATE,
        fallback_id: str | None = None,
        performance_threshold: dict[str, float] | None = None,
        metrics: dict[str, float] | None = None,
        artifact_path: str = "",
        training_config: dict[str, Any] | None = None,
    ) -> ModelRecord:
        """Register a new model or update an existing one."""
        now = datetime.now(timezone.utc).isoformat()

        if model_id in self.registry:
            # Update existing model
            # M-07 修复：保存旧状态，磁盘写入失败时回滚内存状态
            record = self.registry[model_id]
            old_snapshot = {
                "name": record.name,
                "version": record.version,
                "model_type": record.model_type,
                "status": record.status,
                "fallback_id": record.fallback_id,
                "performance_threshold": record.performance_threshold,
                "metrics": record.metrics,
                "artifact_path": record.artifact_path,
                "training_config": record.training_config,
                "updated_at": record.updated_at,
            }
            record.name = name
            record.version = version
            record.model_type = model_type
            record.status = status
            record.fallback_id = fallback_id
            record.performance_threshold = performance_threshold or {}
            record.metrics = metrics or {}
            record.artifact_path = artifact_path
            record.training_config = training_config or {}
            record.updated_at = now
            try:
                self._save_registry()
            except Exception as exc:
                # 磁盘写入失败，回滚内存状态
                record.name = old_snapshot["name"]
                record.version = old_snapshot["version"]
                record.model_type = old_snapshot["model_type"]
                record.status = old_snapshot["status"]
                record.fallback_id = old_snapshot["fallback_id"]
                record.performance_threshold = old_snapshot["performance_threshold"]
                record.metrics = old_snapshot["metrics"]
                record.artifact_path = old_snapshot["artifact_path"]
                record.training_config = old_snapshot["training_config"]
                record.updated_at = old_snapshot["updated_at"]
                logger.error("Failed to persist model update %s: %s", model_id, exc)
                raise
            logger.info("Updated model %s to version %s", model_id, version)
        else:
            # Create new model record
            record = ModelRecord(
                model_id=model_id,
                name=name,
                version=version,
                model_type=model_type,
                status=status,
                fallback_id=fallback_id,
                performance_threshold=performance_threshold or {},
                metrics=metrics or {},
                artifact_path=artifact_path,
                training_config=training_config or {},
                created_at=now,
                updated_at=now,
            )
            # 先加入内存 registry，再保存到磁盘；保存失败时回滚内存状态。
            # 原实现顺序相反，导致 _save_registry 遍历 self.registry 时新记录尚未入表，
            # 写入文件的 "models" 字段为空，重启后加载不出新建模型。
            self.registry[model_id] = record
            try:
                self._save_registry()
            except Exception as exc:
                # 磁盘写入失败，回滚内存 registry
                del self.registry[model_id]
                logger.error("Failed to persist new model %s: %s", model_id, exc)
                raise
            logger.info("Registered new model %s (version %s)", model_id, version)

        return record

    def get_model(self, model_id: str) -> ModelRecord | None:
        """Get a model record by ID."""
        return self.registry.get(model_id)

    def get_models_by_status(self, status: ModelStatus) -> list[ModelRecord]:
        """Get all models with a specific status."""
        return [record for record in self.registry.values() if record.status == status]

    def get_production_models(self) -> list[ModelRecord]:
        """Get all production models."""
        return self.get_models_by_status(ModelStatus.PRODUCTION)

    def promote_model(
        self, model_id: str, new_status: ModelStatus
    ) -> ModelRecord | None:
        """Promote or demote a model to a new status."""
        record = self.registry.get(model_id)
        if not record:
            logger.error("Model %s not found", model_id)
            return None

        # Validate status transitions
        valid_transitions = {
            ModelStatus.CANDIDATE: [ModelStatus.STAGING],
            ModelStatus.STAGING: [ModelStatus.PRODUCTION, ModelStatus.CANDIDATE],
            ModelStatus.PRODUCTION: [ModelStatus.RETIRED, ModelStatus.STAGING],
            ModelStatus.RETIRED: [],
        }

        if new_status not in valid_transitions.get(record.status, []):
            logger.error(
                "Invalid status transition: %s -> %s",
                record.status.value,
                new_status.value,
            )
            return None

        # M-07 修复：先保存旧状态，磁盘写入失败时回滚内存状态，保持一致性
        old_status = record.status
        old_updated_at = record.updated_at
        record.status = new_status
        record.updated_at = datetime.now(timezone.utc).isoformat()
        try:
            self._save_registry()
        except Exception as exc:
            # 磁盘写入失败，回滚内存状态
            record.status = old_status
            record.updated_at = old_updated_at
            logger.error(
                "Failed to persist model promotion %s -> %s: %s",
                model_id,
                new_status.value,
                exc,
            )
            return None

        logger.info("Model %s promoted to %s", model_id, new_status.value)
        return record

    def get_fallback_chain(self, model_id: str) -> list[str]:
        """Get the fallback chain for a model."""
        chain = []
        visited = set()
        current = model_id

        while current and current not in visited:
            visited.add(current)
            chain.append(current)
            record = self.registry.get(current)
            if not record:
                break
            current = record.fallback_id

        return chain

    def check_performance_regression(
        self, model_id: str, current_metrics: dict[str, float]
    ) -> dict[str, Any]:
        """Check if current metrics indicate performance regression."""
        record = self.registry.get(model_id)
        if not record:
            return {"error": f"Model {model_id} not found"}

        threshold = record.performance_threshold
        if not threshold:
            return {"regression_detected": False, "reason": "No threshold configured"}

        regressions = []
        for metric, threshold_value in threshold.items():
            current_value = current_metrics.get(metric)
            if current_value is None:
                continue

            # H-Core-6 修复：对所有 metric 执行回归检查（原实现仅检查 f1_score，
            # 导致 precision/recall/auc 等指标的性能回归被静默忽略）
            if current_value < threshold_value:
                regressions.append(
                    {
                        "metric": metric,
                        "current": current_value,
                        "threshold": threshold_value,
                        "drop": threshold_value - current_value,
                    }
                )

        return {
            "regression_detected": len(regressions) > 0,
            "regressions": regressions,
            "model_id": model_id,
        }

    def list_models(self) -> list[dict[str, Any]]:
        """List all models in the registry."""
        return [record.to_dict() for record in self.registry.values()]

    def validate_artifact_exists(self, model_id: str) -> bool:
        """Check if the model artifact file exists."""
        record = self.registry.get(model_id)
        if not record:
            return False

        path = Path(record.artifact_path)
        if not path.is_absolute():
            # Try relative to project root
            project_root = Path(__file__).resolve().parents[3]
            path = project_root / path

        return path.exists()


# Global registry instance
_registry_instance: ModelRegistryV2 | None = None


def get_registry() -> ModelRegistryV2:
    """Get the global registry instance."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ModelRegistryV2()
    return _registry_instance
