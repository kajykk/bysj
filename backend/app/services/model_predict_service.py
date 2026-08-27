"""Compatibility facade for the split model prediction service.

Implementations live in ``app.services.model_predict``. This module intentionally
keeps the historical import path and patch points stable for API consumers and
existing integrations.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.cache import cache_get, cache_set, make_cache_key
from app.core.config import settings
from app.core.ml_breaker import call_with_ml_breaker
from app.core.model_engine import model_engine

from .model_predict import fusion as _fusion
from .model_predict import inference as _inference
from .model_predict import training_jobs as _training

logger = logging.getLogger(__name__)

_ML_INFERENCE_CACHE_TTL: int = getattr(settings, "ml_inference_cache_ttl", 60)

TRAINING_JOBS = _training.TRAINING_JOBS
TRAINING_JOBS_LOCK = _training.TRAINING_JOBS_LOCK
TRAINING_JOBS_MAX_SIZE = _training.TRAINING_JOBS_MAX_SIZE
_ACTIVE_JOB_STATUSES = _training._ACTIVE_JOB_STATUSES
_TRAINING_JOBS_FILE = _training._TRAINING_JOBS_FILE


def _sync_modules() -> None:
    _inference.model_engine = model_engine
    _inference.cache_get = cache_get
    _inference.cache_set = cache_set
    _inference.make_cache_key = make_cache_key
    _inference.call_with_ml_breaker = call_with_ml_breaker
    _inference._ML_INFERENCE_CACHE_TTL = _ML_INFERENCE_CACHE_TTL
    _fusion.model_engine = model_engine
    _fusion.cache_get = cache_get
    _fusion.cache_set = cache_set
    _fusion.make_cache_key = make_cache_key
    _fusion.call_with_ml_breaker = call_with_ml_breaker
    _fusion._ML_INFERENCE_CACHE_TTL = _ML_INFERENCE_CACHE_TTL
    _training.TRAINING_JOBS = TRAINING_JOBS
    _training.TRAINING_JOBS_LOCK = TRAINING_JOBS_LOCK
    _training._TRAINING_JOBS_FILE = _TRAINING_JOBS_FILE


def _load_training_jobs() -> None:
    _sync_modules()
    _training._load_training_jobs(json.load)


def _save_training_jobs() -> None:
    _sync_modules()
    _training._save_training_jobs(json.dump)


def cleanup_old_training_jobs(max_size: int = TRAINING_JOBS_MAX_SIZE) -> int:
    _sync_modules()
    return _training.cleanup_old_training_jobs(max_size)


class ModelPredictService(_inference.InferenceService):
    """Historical service class backed by the split implementation."""

    def get_model_status(self) -> dict[str, Any]:
        _sync_modules()
        return super().get_model_status()

    def start_training_job(
        self,
        dataset_name: str,
        model_name: str,
        epochs: int,
        batch_size: int,
        learning_rate: float,
    ) -> dict[str, Any]:
        """Submit a training task; failures are surfaced as HTTPException(503)."""
        _sync_modules()
        return _training.start_training_job(dataset_name, model_name, epochs, batch_size, learning_rate)

    def start_evaluate_job(self, dataset_name: str, model_name: str, split: str) -> dict[str, Any]:
        """Submit an evaluation task; failures are surfaced as HTTPException(503)."""
        _sync_modules()
        return _training.start_evaluate_job(dataset_name, model_name, split)

    def start_compare_job(self, dataset_name: str, model_names: list[str]) -> dict[str, Any]:
        """Submit a comparison task; failures are surfaced as HTTPException(503)."""
        _sync_modules()
        return _training.start_compare_job(dataset_name, model_names)

    def get_training_job(self, job_id: str) -> dict[str, Any]:
        _sync_modules()
        return _training.get_training_job(job_id)

    def list_training_jobs(self) -> list[dict[str, Any]]:
        _sync_modules()
        return _training.list_training_jobs()

    def _update_job(self, job_id: str, **updates: Any) -> None:
        _sync_modules()
        _training.update_job(job_id, **updates)

    async def predict_tabular(self, features: dict[str, float | int | str | bool]) -> dict:
        """Run cached tabular inference (cache_get/cache_set, ml:tabular)."""
        _sync_modules()
        return await super().predict_tabular(features)

    async def predict_text(self, text: str) -> dict:
        """Run cached text inference (cache_get/cache_set, ml:text)."""
        _sync_modules()
        return await super().predict_text(text)

    async def predict_physiological(self, physiological: dict[str, float | int]) -> dict:
        """Run cached physiological inference (cache_get/cache_set, ml:physiological)."""
        _sync_modules()
        return await super().predict_physiological(physiological)

    async def predict_fusion(
        self,
        features: dict[str, float | int] | None = None,
        text: str | None = None,
        physiological: dict[str, float | int] | None = None,
        user_id: int | None = None,
    ) -> dict:
        """Run cached multimodal inference (cache_get/cache_set, ml:fusion)."""
        _sync_modules()
        return await super().predict_fusion(
            features=features,
            text=text,
            physiological=physiological,
            user_id=user_id,
        )


class ModelExperimentService:
    def __init__(self) -> None:
        from app.services.experiment_service import ExperimentService as BertExperimentService

        self._service = BertExperimentService()

    def import_dataset(
        self,
        dataset_name: str,
        source_type: str,
        train_ratio: float,
        val_ratio: float,
        test_ratio: float,
    ) -> dict:
        return self._service.import_dataset(dataset_name, source_type, train_ratio, val_ratio, test_ratio)

    def train(
        self,
        dataset_name: str,
        model_name: str,
        epochs: int,
        batch_size: int,
        learning_rate: float,
    ) -> dict:
        return self._service.train_model(dataset_name, model_name, epochs, batch_size, learning_rate)

    def evaluate(self, dataset_name: str, model_name: str, split: str) -> dict:
        return self._service.evaluate_model(dataset_name, model_name, split)

    def compare(self, dataset_name: str, model_names: list[str]) -> dict:
        if not model_names:
            raise ValueError("model_names 不能为空")
        return self._service.compare_models(dataset_name, model_names)
