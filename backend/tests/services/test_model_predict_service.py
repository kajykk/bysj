"""Tests for ModelPredictService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.model_predict_service import (
    ModelExperimentService,
    ModelPredictService,
)


class TestModelPredictService:
    """Test model predict service."""

    def test_get_model_status(self):
        """TC-COV-MPD-001: Get model status."""
        service = ModelPredictService()
        result = service.get_model_status()
        assert "items" in result
        assert "ready" in result
        assert "performance" in result
        assert "performance_summary" in result
        assert isinstance(result["items"], list)

    def test_get_training_job_not_found(self):
        """TC-COV-MPD-002: Get non-existent training job."""
        service = ModelPredictService()
        result = service.get_training_job("nonexistent")
        assert result["status"] == "not_found"

    def test_list_training_jobs_empty(self):
        """TC-COV-MPD-003: List training jobs when empty."""
        service = ModelPredictService()
        result = service.list_training_jobs()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_predict_tabular(self):
        """TC-COV-MPD-004: Predict tabular data."""
        service = ModelPredictService()
        with patch("app.services.model_predict_service.model_engine") as mock_engine:
            mock_engine.predict_structured = AsyncMock(
                return_value={
                    "prediction": 1,
                    "probability": 0.85,
                    "risk_score": 85.0,
                }
            )
            result = await service.predict_tabular({"feature1": 1.0, "feature2": 2})
            assert "prediction" in result

    @pytest.mark.asyncio
    async def test_predict_text(self):
        """TC-COV-MPD-005: Predict text data."""
        service = ModelPredictService()
        with patch("app.services.model_predict_service.model_engine") as mock_engine:
            mock_engine.predict_text = AsyncMock(
                return_value={
                    "sentiment_score": 0.2,
                    "sentiment_label": "negative",
                }
            )
            result = await service.predict_text("I feel sad today")
            assert "sentiment_score" in result

    @pytest.mark.asyncio
    async def test_predict_physiological(self):
        """TC-COV-MPD-006: Predict physiological data."""
        service = ModelPredictService()
        with patch("app.services.model_predict_service.model_engine") as mock_engine:
            mock_engine.predict_physiological = AsyncMock(
                return_value={
                    "prediction": 1,
                    "probability": 0.75,
                }
            )
            result = await service.predict_physiological(
                {"heart_rate": 80, "sleep_hours": 6}
            )
            assert "prediction" in result

    @pytest.mark.asyncio
    async def test_predict_fusion(self):
        """TC-COV-MPD-007: Predict fusion data."""
        service = ModelPredictService()
        with patch("app.services.model_predict_service.model_engine") as mock_engine:
            mock_engine.predict_fusion = AsyncMock(
                return_value={
                    "prediction": 1,
                    "probability": 0.9,
                    "risk_score": 90.0,
                }
            )
            result = await service.predict_fusion(
                features={"feature1": 1.0},
                text="I feel sad",
                physiological={"heart_rate": 80},
            )
            assert "prediction" in result

    @pytest.mark.asyncio
    async def test_predict_fusion_partial(self):
        """TC-COV-MPD-008: Predict fusion with partial data."""
        service = ModelPredictService()
        with patch("app.services.model_predict_service.model_engine") as mock_engine:
            mock_engine.predict_fusion = AsyncMock(
                return_value={
                    "prediction": 1,
                    "probability": 0.8,
                }
            )
            result = await service.predict_fusion(text="I feel sad")
            assert "prediction" in result


class TestModelExperimentService:
    """Test model experiment service."""

    def test_compare_empty_models(self):
        """TC-COV-MPD-009: Compare with empty model names raises error."""
        service = ModelExperimentService()
        with pytest.raises(ValueError, match="model_names 不能为空"):
            service.compare("dataset", [])


# =============================================================================
# 以下为新增测试，覆盖：
#   - 模块级函数 _load_training_jobs / _save_training_jobs
#   - start_training_job（Celery 成功 + Thread 回退）
#   - _update_job（不存在 + Redis 同步失败 L-18 修复点）
#   - get_training_job / list_training_jobs 的 Redis 命中路径
#   - ModelExperimentService 委托方法
#   - predict_tabular routing_info 日志 / predict_text 空文本校验
# =============================================================================

import json
import logging
import threading

from app.services import model_predict_service as _mps


@pytest.fixture
def isolated_jobs(monkeypatch, tmp_path):
    """隔离 TRAINING_JOBS 全局状态与持久化文件路径，避免测试间污染."""
    fake_file = tmp_path / "training_jobs.json"
    monkeypatch.setattr(_mps, "_TRAINING_JOBS_FILE", fake_file)
    with _mps.TRAINING_JOBS_LOCK:
        saved = dict(_mps.TRAINING_JOBS)
        _mps.TRAINING_JOBS.clear()
    yield
    with _mps.TRAINING_JOBS_LOCK:
        _mps.TRAINING_JOBS.clear()
        _mps.TRAINING_JOBS.update(saved)


class TestModelPredictServicePersistence:
    """测试模块级持久化函数 _load_training_jobs 与 _save_training_jobs."""

    def test_load_training_jobs_no_file(self, isolated_jobs):
        """TC-COV-MPD-010: 持久化文件不存在时正常返回，不抛异常."""
        _mps._load_training_jobs()
        assert _mps.TRAINING_JOBS == {}

    def test_load_training_jobs_running_status_marked_interrupted(self, isolated_jobs):
        """TC-COV-MPD-011: 重启后 running/queued 状态任务被改写为 interrupted."""
        # isolated_jobs 已将 _TRAINING_JOBS_FILE 指向 tmp_path/"training_jobs.json"
        _mps._TRAINING_JOBS_FILE.write_text(
            json.dumps(
                {
                    "job-1": {"job_id": "job-1", "status": "running"},
                    "job-2": {"job_id": "job-2", "status": "queued"},
                    "job-3": {"job_id": "job-3", "status": "completed"},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        _mps._load_training_jobs()
        assert _mps.TRAINING_JOBS["job-1"]["status"] == "interrupted"
        assert _mps.TRAINING_JOBS["job-1"]["stage"] == "interrupted"
        assert _mps.TRAINING_JOBS["job-1"]["error"] == "service_restart"
        assert _mps.TRAINING_JOBS["job-2"]["status"] == "interrupted"
        assert _mps.TRAINING_JOBS["job-3"]["status"] == "completed"

    def test_load_training_jobs_invalid_json_logs_warning(self, isolated_jobs, caplog):
        """TC-COV-MPD-012: JSON 解析失败时记录 warning 日志不抛异常."""
        _mps._TRAINING_JOBS_FILE.write_text("not valid json {{{", encoding="utf-8")
        with caplog.at_level(
            logging.WARNING, logger="app.services.model_predict_service"
        ):
            _mps._load_training_jobs()
        assert "Failed to load training jobs" in caplog.text

    def test_save_training_jobs_writes_file(self, isolated_jobs):
        """TC-COV-MPD-013: 成功将训练任务持久化到磁盘."""
        with _mps.TRAINING_JOBS_LOCK:
            _mps.TRAINING_JOBS["job-x"] = {"job_id": "job-x", "status": "queued"}
        _mps._save_training_jobs()
        data = json.loads(_mps._TRAINING_JOBS_FILE.read_text(encoding="utf-8"))
        assert data["job-x"]["status"] == "queued"

    def test_save_training_jobs_write_failure_logs_warning(self, isolated_jobs, caplog):
        """TC-COV-MPD-014: 写入失败时记录 warning 日志不抛异常."""
        with _mps.TRAINING_JOBS_LOCK:
            _mps.TRAINING_JOBS["job-y"] = {"job_id": "job-y"}
        with patch(
            "app.services.model_predict_service.json.dump",
            side_effect=OSError("disk full"),
        ):
            with caplog.at_level(
                logging.WARNING, logger="app.services.model_predict_service"
            ):
                _mps._save_training_jobs()
        assert "Failed to save training jobs" in caplog.text


class TestStartTrainingJob:
    """测试 start_training_job 的 Celery 提交与 PERF-P2-001 503 返回路径."""

    def test_start_training_job_celery_success(self, isolated_jobs, monkeypatch):
        """TC-COV-MPD-015: Celery 任务提交成功时返回 queued 状态."""
        import app.tasks.model_training as mt

        monkeypatch.setattr(mt, "save_job_to_redis", MagicMock())
        # 避免 get_training_job 触发真实 Redis 连接（3s 超时）
        monkeypatch.setattr(mt, "get_job_from_redis", MagicMock(return_value=None))
        mock_task = MagicMock()
        monkeypatch.setattr(mt, "train_bert_model_task", mock_task)

        service = ModelPredictService()
        result = service.start_training_job("ds", "model", 1, 8, 0.001)

        assert result["status"] == "queued"
        assert result["progress"] == 0
        mt.save_job_to_redis.assert_called_once()
        mock_task.delay.assert_called_once()

    def test_start_training_job_celery_failure_returns_503(
        self, isolated_jobs, monkeypatch
    ):
        """PERF-P2-001: Celery 提交失败时返回 HTTPException(503), 不再回退到 daemon Thread."""
        import app.tasks.model_training as mt
        from fastapi import HTTPException

        # save_job_to_redis 成功但 delay 抛异常触发 503
        monkeypatch.setattr(mt, "save_job_to_redis", MagicMock())
        mock_task = MagicMock()
        mock_task.delay = MagicMock(side_effect=RuntimeError("celery down"))
        monkeypatch.setattr(mt, "train_bert_model_task", mock_task)
        # 避免 get_training_job / update_job_in_redis 触发真实 Redis 调用
        monkeypatch.setattr(mt, "get_job_from_redis", MagicMock(return_value=None))
        monkeypatch.setattr(mt, "update_job_in_redis", MagicMock())

        service = ModelPredictService()
        with pytest.raises(HTTPException) as exc_info:
            service.start_training_job("ds", "model", 1, 8, 0.001)
        assert exc_info.value.status_code == 503
        assert "Celery" in exc_info.value.detail or "Redis" in exc_info.value.detail
        # 验证未创建 daemon Thread (ExperimentService 不应被实例化)
        # mock_exp 未设置, 若代码尝试回退会因 ExperimentService 未 mock 而失败

    def test_start_training_job_503_no_thread_created(
        self, isolated_jobs, monkeypatch
    ):
        """PERF-P2-001: Celery 失败时不应创建任何 threading.Thread."""
        import app.tasks.model_training as mt
        from fastapi import HTTPException

        monkeypatch.setattr(mt, "save_job_to_redis", MagicMock())
        mock_task = MagicMock()
        mock_task.delay = MagicMock(side_effect=RuntimeError("celery down"))
        monkeypatch.setattr(mt, "train_bert_model_task", mock_task)
        monkeypatch.setattr(mt, "get_job_from_redis", MagicMock(return_value=None))
        monkeypatch.setattr(mt, "update_job_in_redis", MagicMock())

        # 监控 threading.Thread 构造, 若被调用则测试失败
        original_thread = threading.Thread
        thread_created = []

        class _SpyThread(original_thread):
            def __init__(self, *args, **kwargs):
                thread_created.append(self)
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(threading, "Thread", _SpyThread)

        service = ModelPredictService()
        with pytest.raises(HTTPException) as exc_info:
            service.start_training_job("ds", "model", 1, 8, 0.001)
        assert exc_info.value.status_code == 503
        assert thread_created == [], "不应创建 daemon Thread"


class TestUpdateJob:
    """测试 _update_job 的更新与 Redis 同步逻辑."""

    def test_update_job_silent_when_not_found(self, isolated_jobs):
        """TC-COV-MPD-017: job_id 不存在时静默返回，不抛异常."""
        service = ModelPredictService()
        service._update_job("nonexistent-job", status="running", progress=50)
        assert _mps.TRAINING_JOBS == {}

    def test_update_job_redis_sync_failure_logs_warning(
        self, isolated_jobs, monkeypatch, caplog
    ):
        """TC-COV-MPD-018: Redis 同步失败时记录 warning 日志（L-18 修复点）."""
        import app.tasks.model_training as mt

        with _mps.TRAINING_JOBS_LOCK:
            _mps.TRAINING_JOBS["job-l18"] = {"job_id": "job-l18", "status": "queued"}
        monkeypatch.setattr(
            mt, "update_job_in_redis", MagicMock(side_effect=RuntimeError("redis down"))
        )

        service = ModelPredictService()
        with caplog.at_level(
            logging.WARNING, logger="app.services.model_predict_service"
        ):
            service._update_job("job-l18", status="running", progress=50)

        # 内存中已更新
        assert _mps.TRAINING_JOBS["job-l18"]["status"] == "running"
        assert _mps.TRAINING_JOBS["job-l18"]["progress"] == 50
        # L-18 修复：记录 warning 日志而非静默吞掉
        assert "update_job_in_redis failed" in caplog.text


class TestRedisJobAccess:
    """测试 get_training_job 与 list_training_jobs 的 Redis 命中路径."""

    def test_get_training_job_redis_hit(self, isolated_jobs, monkeypatch):
        """TC-COV-MPD-019: Redis 命中时返回 Redis 数据而非内存字典."""
        import app.tasks.model_training as mt

        redis_data = {"job_id": "redis-job", "status": "running", "progress": 50}
        monkeypatch.setattr(
            mt, "get_job_from_redis", MagicMock(return_value=redis_data)
        )

        service = ModelPredictService()
        result = service.get_training_job("redis-job")

        assert result == redis_data
        assert result["status"] == "running"

    def test_list_training_jobs_redis_hit(self, isolated_jobs, monkeypatch):
        """TC-COV-MPD-020: Redis 命中时返回 Redis 数据列表而非内存字典."""
        import app.tasks.model_training as mt

        redis_jobs = [
            {"job_id": "job-1", "status": "completed"},
            {"job_id": "job-2", "status": "running"},
        ]
        monkeypatch.setattr(
            mt, "list_jobs_from_redis", MagicMock(return_value=redis_jobs)
        )

        service = ModelPredictService()
        result = service.list_training_jobs()

        assert result == redis_jobs
        assert len(result) == 2

    def test_get_training_job_redis_exception_falls_back_to_memory(
        self, isolated_jobs, monkeypatch
    ):
        """TC-COV-MPD-027: get_job_from_redis 抛异常时回退到内存字典."""
        import app.tasks.model_training as mt

        # 预置内存任务
        with _mps.TRAINING_JOBS_LOCK:
            _mps.TRAINING_JOBS["mem-job"] = {"job_id": "mem-job", "status": "queued"}
        # get_job_from_redis 抛异常触发 except 分支
        monkeypatch.setattr(
            mt, "get_job_from_redis", MagicMock(side_effect=RuntimeError("redis down"))
        )

        service = ModelPredictService()
        result = service.get_training_job("mem-job")

        assert result["job_id"] == "mem-job"
        assert result["status"] == "queued"

    def test_list_training_jobs_redis_exception_falls_back_to_memory(
        self, isolated_jobs, monkeypatch
    ):
        """TC-COV-MPD-028: list_jobs_from_redis 抛异常时回退到内存字典."""
        import app.tasks.model_training as mt

        with _mps.TRAINING_JOBS_LOCK:
            _mps.TRAINING_JOBS["mem-job"] = {"job_id": "mem-job", "status": "queued"}
        # list_jobs_from_redis 抛异常触发 except 分支
        monkeypatch.setattr(
            mt,
            "list_jobs_from_redis",
            MagicMock(side_effect=RuntimeError("redis down")),
        )

        service = ModelPredictService()
        result = service.list_training_jobs()

        assert any(j["job_id"] == "mem-job" for j in result)


class TestModelExperimentServiceDelegation:
    """测试 ModelExperimentService 委托 ExperimentService 的方法."""

    def test_import_dataset_delegates(self, monkeypatch):
        """TC-COV-MPD-021: import_dataset 委托给 ExperimentService.import_dataset."""
        mock_service = MagicMock()
        mock_service.import_dataset.return_value = {"status": "ok"}
        monkeypatch.setattr(
            "app.services.experiment_service.ExperimentService", lambda: mock_service
        )

        svc = ModelExperimentService()
        result = svc.import_dataset("ds", "local", 0.7, 0.15, 0.15)

        assert result == {"status": "ok"}
        mock_service.import_dataset.assert_called_once_with(
            "ds", "local", 0.7, 0.15, 0.15
        )

    def test_train_delegates(self, monkeypatch):
        """TC-COV-MPD-022: train 委托给 ExperimentService.train_model."""
        mock_service = MagicMock()
        mock_service.train_model.return_value = {"loss": 0.1}
        monkeypatch.setattr(
            "app.services.experiment_service.ExperimentService", lambda: mock_service
        )

        svc = ModelExperimentService()
        result = svc.train("ds", "model", 1, 8, 0.001)

        assert result == {"loss": 0.1}
        mock_service.train_model.assert_called_once_with("ds", "model", 1, 8, 0.001)

    def test_evaluate_delegates(self, monkeypatch):
        """TC-COV-MPD-023: evaluate 委托给 ExperimentService.evaluate_model."""
        mock_service = MagicMock()
        mock_service.evaluate_model.return_value = {"accuracy": 0.9}
        monkeypatch.setattr(
            "app.services.experiment_service.ExperimentService", lambda: mock_service
        )

        svc = ModelExperimentService()
        result = svc.evaluate("ds", "model", "validation")

        assert result == {"accuracy": 0.9}
        mock_service.evaluate_model.assert_called_once_with("ds", "model", "validation")

    def test_compare_delegates_to_underlying_service(self, monkeypatch):
        """TC-COV-MPD-024: compare 委托给 ExperimentService.compare_models."""
        mock_service = MagicMock()
        mock_service.compare_models.return_value = {"best": "model-a"}
        monkeypatch.setattr(
            "app.services.experiment_service.ExperimentService", lambda: mock_service
        )

        svc = ModelExperimentService()
        result = svc.compare("ds", ["model-a", "model-b"])

        assert result == {"best": "model-a"}
        mock_service.compare_models.assert_called_once_with(
            "ds", ["model-a", "model-b"]
        )


class TestModelPredictServiceEdgeCases:
    """补全覆盖 predict_tabular routing_info 日志与 predict_text 空文本校验."""

    async def test_predict_tabular_with_routing_info(self):
        """TC-COV-MPD-025: predict_tabular 含 routing_info 时记录路由日志."""
        service = ModelPredictService()
        with patch("app.services.model_predict_service.model_engine") as mock_engine:
            mock_engine.predict_structured = AsyncMock(
                return_value={
                    "prediction": 1,
                    "routing_info": {
                        "selected_model_family": "logistic",
                        "routing_reason": "coverage",
                        "feature_coverage_ratio": 0.8,
                        "prediction_confidence_band": "high",
                    },
                }
            )
            result = await service.predict_tabular({"feature1": 1.0})
        assert result["prediction"] == 1
        assert result["routing_info"]["selected_model_family"] == "logistic"

    async def test_predict_text_empty_raises(self):
        """TC-COV-MPD-026: predict_text 空文本与纯空白文本抛出 ValueError."""
        service = ModelPredictService()
        with pytest.raises(ValueError, match="text cannot be empty"):
            await service.predict_text("")
        with pytest.raises(ValueError, match="text cannot be empty"):
            await service.predict_text("   ")


# =============================================================================
# PERF-P1-006: start_evaluate_job / start_compare_job 测试
# PERF-P2-001: 移除 Thread 回退, Celery 失败时返回 503
# =============================================================================





class TestStartEvaluateJob:
    """PERF-P1-006 + PERF-P2-001: 测试 start_evaluate_job 的 Celery 提交与 503 返回路径."""

    def test_start_evaluate_job_celery_success(self, isolated_jobs, monkeypatch):
        """PERF-P1-006: Celery 任务提交成功时返回 queued 状态."""
        import app.tasks.model_training as mt

        monkeypatch.setattr(mt, "save_job_to_redis", MagicMock())
        monkeypatch.setattr(mt, "get_job_from_redis", MagicMock(return_value=None))
        mock_task = MagicMock()
        monkeypatch.setattr(mt, "evaluate_model_task", mock_task)

        service = ModelPredictService()
        result = service.start_evaluate_job("ds", "model", "validation")

        assert result["status"] == "queued"
        assert result["progress"] == 0
        assert result["stage"] == "queued"
        mt.save_job_to_redis.assert_called_once()
        mock_task.delay.assert_called_once()
        # 验证 delay 参数传递正确
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["dataset_name"] == "ds"
        assert call_kwargs["model_name"] == "model"
        assert call_kwargs["split"] == "validation"

    def test_start_evaluate_job_celery_failure_returns_503(
        self, isolated_jobs, monkeypatch
    ):
        """PERF-P2-001: Celery 提交失败时返回 HTTPException(503), 不再回退到 daemon Thread."""
        import app.tasks.model_training as mt
        from fastapi import HTTPException

        monkeypatch.setattr(mt, "save_job_to_redis", MagicMock())
        mock_task = MagicMock()
        mock_task.delay = MagicMock(side_effect=RuntimeError("celery down"))
        monkeypatch.setattr(mt, "evaluate_model_task", mock_task)
        monkeypatch.setattr(mt, "get_job_from_redis", MagicMock(return_value=None))
        monkeypatch.setattr(mt, "update_job_in_redis", MagicMock())

        service = ModelPredictService()
        with pytest.raises(HTTPException) as exc_info:
            service.start_evaluate_job("ds", "model", "validation")
        assert exc_info.value.status_code == 503
        assert "Celery" in exc_info.value.detail or "Redis" in exc_info.value.detail

    def test_start_evaluate_job_503_no_thread_created(
        self, isolated_jobs, monkeypatch
    ):
        """PERF-P2-001: Celery 失败时不应创建任何 threading.Thread."""
        import app.tasks.model_training as mt
        from fastapi import HTTPException

        monkeypatch.setattr(mt, "save_job_to_redis", MagicMock())
        mock_task = MagicMock()
        mock_task.delay = MagicMock(side_effect=RuntimeError("celery down"))
        monkeypatch.setattr(mt, "evaluate_model_task", mock_task)
        monkeypatch.setattr(mt, "get_job_from_redis", MagicMock(return_value=None))
        monkeypatch.setattr(mt, "update_job_in_redis", MagicMock())

        original_thread = threading.Thread
        thread_created = []

        class _SpyThread(original_thread):
            def __init__(self, *args, **kwargs):
                thread_created.append(self)
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(threading, "Thread", _SpyThread)

        service = ModelPredictService()
        with pytest.raises(HTTPException) as exc_info:
            service.start_evaluate_job("ds", "model", "test")
        assert exc_info.value.status_code == 503
        assert thread_created == [], "不应创建 daemon Thread"


class TestStartCompareJob:
    """PERF-P1-006 + PERF-P2-001: 测试 start_compare_job 的 Celery 提交与 503 返回路径."""

    def test_start_compare_job_celery_success(self, isolated_jobs, monkeypatch):
        """PERF-P1-006: Celery 任务提交成功时返回 queued 状态."""
        import app.tasks.model_training as mt

        monkeypatch.setattr(mt, "save_job_to_redis", MagicMock())
        monkeypatch.setattr(mt, "get_job_from_redis", MagicMock(return_value=None))
        mock_task = MagicMock()
        monkeypatch.setattr(mt, "compare_models_task", mock_task)

        service = ModelPredictService()
        result = service.start_compare_job("ds", ["model-a", "model-b"])

        assert result["status"] == "queued"
        assert result["progress"] == 0
        assert result["stage"] == "queued"
        mt.save_job_to_redis.assert_called_once()
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["dataset_name"] == "ds"
        assert call_kwargs["model_names"] == ["model-a", "model-b"]

    def test_start_compare_job_celery_failure_returns_503(
        self, isolated_jobs, monkeypatch
    ):
        """PERF-P2-001: Celery 提交失败时返回 HTTPException(503), 不再回退到 daemon Thread."""
        import app.tasks.model_training as mt
        from fastapi import HTTPException

        monkeypatch.setattr(mt, "save_job_to_redis", MagicMock())
        mock_task = MagicMock()
        mock_task.delay = MagicMock(side_effect=RuntimeError("celery down"))
        monkeypatch.setattr(mt, "compare_models_task", mock_task)
        monkeypatch.setattr(mt, "get_job_from_redis", MagicMock(return_value=None))
        monkeypatch.setattr(mt, "update_job_in_redis", MagicMock())

        service = ModelPredictService()
        with pytest.raises(HTTPException) as exc_info:
            service.start_compare_job("ds", ["model-a", "model-b"])
        assert exc_info.value.status_code == 503
        assert "Celery" in exc_info.value.detail or "Redis" in exc_info.value.detail

    def test_start_compare_job_503_no_thread_created(
        self, isolated_jobs, monkeypatch
    ):
        """PERF-P2-001: Celery 失败时不应创建任何 threading.Thread."""
        import app.tasks.model_training as mt
        from fastapi import HTTPException

        monkeypatch.setattr(mt, "save_job_to_redis", MagicMock())
        mock_task = MagicMock()
        mock_task.delay = MagicMock(side_effect=RuntimeError("celery down"))
        monkeypatch.setattr(mt, "compare_models_task", mock_task)
        monkeypatch.setattr(mt, "get_job_from_redis", MagicMock(return_value=None))
        monkeypatch.setattr(mt, "update_job_in_redis", MagicMock())

        original_thread = threading.Thread
        thread_created = []

        class _SpyThread(original_thread):
            def __init__(self, *args, **kwargs):
                thread_created.append(self)
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(threading, "Thread", _SpyThread)

        service = ModelPredictService()
        with pytest.raises(HTTPException) as exc_info:
            service.start_compare_job("ds", ["model-a"])
        assert exc_info.value.status_code == 503
        assert thread_created == [], "不应创建 daemon Thread"

    def test_start_compare_job_empty_models_raises(self, isolated_jobs):
        """PERF-P1-006: 空模型列表抛 ValueError."""
        service = ModelPredictService()
        with pytest.raises(ValueError, match="model_names 不能为空"):
            service.start_compare_job("ds", [])
