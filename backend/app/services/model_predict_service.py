from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock, Thread
from time import time
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.core.model_engine import model_engine
from app.core.model_registry import MODEL_PATHS, get_model_info, resolve_model_path

logger = logging.getLogger(__name__)

TRAINING_JOBS: dict[str, dict[str, Any]] = {}
TRAINING_JOBS_LOCK = Lock()


class ModelPredictService:
    def get_model_status(self) -> dict[str, Any]:
        model_dir = Path(settings.model_dir)
        status: list[dict[str, Any]] = []
        for model_id, rel_path in MODEL_PATHS.items():
            path = Path(resolve_model_path(model_id))
            abs_path = path if path.is_absolute() else (model_dir.parent / path if path.parts and path.parts[0] == 'models' else model_dir / path)
            exists = abs_path.exists()
            model_info = get_model_info(model_id)
            lifecycle = model_info.lifecycle if model_info else None
            status.append(
                {
                    'model_id': model_id,
                    'path': str(abs_path),
                    'exists': exists,
                    'size_kb': round(abs_path.stat().st_size / 1024, 2) if exists else None,
                    'modified_at': abs_path.stat().st_mtime if exists else None,
                    'lifecycle': lifecycle,
                }
            )

        performance = model_engine.get_metrics_snapshot()
        performance_summary = {
            'cached_models': performance['cache_size'],
            'tracked_models': len(performance['model_load_stats']),
            'tracked_paths': len(performance['predict_stats']),
            'cache_hits_total': sum(int(item.get('cache_hits', 0)) for item in performance['model_load_stats'].values()),
            'loads_total': sum(int(item.get('loads', 0)) for item in performance['model_load_stats'].values()),
            'predict_calls_total': sum(int(item.get('count', 0)) for item in performance['predict_stats'].values()),
            'avg_predict_ms': round(
                sum(float(item.get('total_ms', 0.0)) for item in performance['predict_stats'].values())
                / max(1, sum(int(item.get('count', 0)) for item in performance['predict_stats'].values())),
                2,
            ),
        }

        return {
            'model_dir': str(model_dir),
            'items': status,
            'ready': all(item['exists'] for item in status if item['model_id'] in {'structured_logistic_regression_quick', 'text_depression_model', 'text_depression_tfidf'}),
            'performance': performance,
            'performance_summary': performance_summary,
        }

    def start_training_job(self, dataset_name: str, model_name: str, epochs: int, batch_size: int, learning_rate: float) -> dict[str, Any]:
        from app.services.experiment_service import ExperimentService as BertExperimentService

        job_id = uuid4().hex
        with TRAINING_JOBS_LOCK:
            TRAINING_JOBS[job_id] = {
                'job_id': job_id,
                'status': 'queued',
                'progress': 0,
                'stage': 'queued',
                'message': '任务已排队',
                'created_at': time(),
                'updated_at': time(),
                'result': None,
                'error': None,
            }

        def _run_job() -> None:
            service = BertExperimentService()
            try:
                self._update_job(job_id, status='running', progress=10, stage='import', message='开始导入数据集')
                service.import_dataset(dataset_name, 'local', 0.7, 0.15, 0.15)
                self._update_job(job_id, progress=35, stage='train', message='开始训练模型')
                result = service.train_model(dataset_name, model_name, epochs, batch_size, learning_rate)
                self._update_job(job_id, progress=75, stage='evaluate', message='开始评估模型')
                evaluation = service.evaluate_model(dataset_name, model_name, 'validation')
                self._update_job(job_id, progress=100, stage='completed', status='completed', message='训练完成', result={'train': result, 'evaluation': evaluation})
            except Exception as exc:
                self._update_job(job_id, status='failed', progress=100, stage='failed', message='训练失败', error=str(exc))

        Thread(target=_run_job, daemon=True).start()
        return self.get_training_job(job_id)

    def get_training_job(self, job_id: str) -> dict[str, Any]:
        with TRAINING_JOBS_LOCK:
            return dict(TRAINING_JOBS.get(job_id, {'job_id': job_id, 'status': 'not_found', 'progress': 0, 'stage': 'not_found', 'message': '任务不存在'}))

    def list_training_jobs(self) -> list[dict[str, Any]]:
        with TRAINING_JOBS_LOCK:
            return [dict(item) for item in TRAINING_JOBS.values()]

    def _update_job(self, job_id: str, **updates: Any) -> None:
        with TRAINING_JOBS_LOCK:
            job = TRAINING_JOBS.get(job_id)
            if not job:
                return
            job.update(updates)
            job['updated_at'] = time()

    async def predict_tabular(self, features: dict[str, float | int | str | bool]) -> dict:
        sanitized: dict[str, float | int | str | bool] = {}
        for key, value in features.items():
            sanitized[key] = value

        result = await model_engine.predict_structured(sanitized)

        routing_info = result.get("routing_info", {})
        if routing_info:
            logger.info(
                "Model routing: family=%s reason=%s coverage=%.2f band=%s",
                routing_info.get("selected_model_family"),
                routing_info.get("routing_reason"),
                routing_info.get("feature_coverage_ratio", 0),
                routing_info.get("prediction_confidence_band"),
            )

        return result

    async def predict_text(self, text: str) -> dict:
        cleaned = text.strip()
        return await model_engine.predict_text(cleaned)

    async def predict_physiological(self, physiological: dict[str, float | int]) -> dict:
        return await model_engine.predict_physiological(physiological)

    async def predict_fusion(
        self,
        features: dict[str, float | int] | None = None,
        text: str | None = None,
        physiological: dict[str, float | int] | None = None,
    ) -> dict:
        return await model_engine.predict_fusion(features=features, text=text, physiological=physiological)


class ModelExperimentService:
    def __init__(self) -> None:
        from app.services.experiment_service import ExperimentService as BertExperimentService
        self._service = BertExperimentService()

    def import_dataset(self, dataset_name: str, source_type: str, train_ratio: float, val_ratio: float, test_ratio: float) -> dict:
        return self._service.import_dataset(dataset_name, source_type, train_ratio, val_ratio, test_ratio)

    def train(self, dataset_name: str, model_name: str, epochs: int, batch_size: int, learning_rate: float) -> dict:
        return self._service.train_model(dataset_name, model_name, epochs, batch_size, learning_rate)

    def evaluate(self, dataset_name: str, model_name: str, split: str) -> dict:
        return self._service.evaluate_model(dataset_name, model_name, split)

    def compare(self, dataset_name: str, model_names: list[str]) -> dict:
        if not model_names:
            raise ValueError("model_names 不能为空")
        return self._service.compare_models(dataset_name, model_names)
