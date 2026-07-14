"""PERF-P2-001 专项测试: start_training_job / start_evaluate_job / start_compare_job
移除 daemon Thread 回退, Celery 不可用时返回 HTTP 503.

测试覆盖:
1. 源码静态扫描: 验证 model_predict_service.py 中不再包含 Thread fallback 模式
2. 服务层: Celery 提交失败时抛出 HTTPException(503)
3. 服务层: 验证未创建 threading.Thread (SpyThread 监控)
4. API 端点: 503 异常透传到 FastAPI 返回 503 响应
5. 边界: save_job_to_redis 失败 (ImportError) 也返回 503
"""

from __future__ import annotations

import inspect
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services import model_predict_service as _mps
from app.services.model_predict_service import ModelPredictService

SERVICE_FILE = Path(_mps.__file__)


# =============================================================================
# 1. 源码静态扫描: 验证 Thread fallback 模式已被移除
# =============================================================================


class TestSourceCodeNoThreadFallback:
    """PERF-P2-001: 源码静态扫描, 确保 Thread fallback 模式完全移除."""

    def test_no_falling_back_log_in_source(self):
        """源码中不应包含 'falling back to daemon Thread' 日志."""
        source = SERVICE_FILE.read_text(encoding="utf-8")
        assert "falling back to daemon Thread" not in source, (
            "PERF-P2-001 违规: 源码仍包含 daemon Thread 回退日志"
        )

    def test_no_run_job_inner_function_in_source(self):
        """源码中不应包含 _run_job / _run_eval_job / _run_compare_job 内部函数."""
        source = SERVICE_FILE.read_text(encoding="utf-8")
        for name in ("_run_job", "_run_eval_job", "_run_compare_job"):
            assert f"def {name}" not in source, (
                f"PERF-P2-001 违规: 源码仍包含内部函数 {name}"
            )

    def test_no_from_threading_import_thread_in_method_bodies(self):
        """start_training_job / evaluate / compare 方法体内不应再 import Thread.

        注意: 模块顶层 `from threading import Lock` 仍然合法 (Lock 用于 TRAINING_JOBS_LOCK).
        """
        src_training = inspect.getsource(ModelPredictService.start_training_job)
        src_evaluate = inspect.getsource(ModelPredictService.start_evaluate_job)
        src_compare = inspect.getsource(ModelPredictService.start_compare_job)
        for label, src in [
            ("start_training_job", src_training),
            ("start_evaluate_job", src_evaluate),
            ("start_compare_job", src_compare),
        ]:
            assert "from threading import Thread" not in src, (
                f"PERF-P2-001 违规: {label} 仍 import threading.Thread"
            )
            assert "Thread(target=" not in src, (
                f"PERF-P2-001 违规: {label} 仍创建 Thread 实例"
            )
            assert "daemon=True" not in src, (
                f"PERF-P2-001 违规: {label} 仍使用 daemon=True"
            )

    def test_methods_raise_http_exception_503(self):
        """三个方法体应包含 raise HTTPException(status_code=503)."""
        src_training = inspect.getsource(ModelPredictService.start_training_job)
        src_evaluate = inspect.getsource(ModelPredictService.start_evaluate_job)
        src_compare = inspect.getsource(ModelPredictService.start_compare_job)
        for label, src in [
            ("start_training_job", src_training),
            ("start_evaluate_job", src_evaluate),
            ("start_compare_job", src_compare),
        ]:
            assert "HTTPException" in src, (
                f"PERF-P2-001 违规: {label} 未使用 HTTPException"
            )
            assert "503" in src, (
                f"PERF-P2-001 违规: {label} 未返回 503 状态码"
            )


# =============================================================================
# 2. 服务层: Celery 失败时抛出 HTTPException(503)
# =============================================================================


@pytest.fixture
def isolated_jobs(monkeypatch, tmp_path):
    """隔离 TRAINING_JOBS 全局状态与持久化文件路径."""
    fake_file = tmp_path / "training_jobs.json"
    monkeypatch.setattr(_mps, "_TRAINING_JOBS_FILE", fake_file)
    with _mps.TRAINING_JOBS_LOCK:
        saved = dict(_mps.TRAINING_JOBS)
        _mps.TRAINING_JOBS.clear()
    yield
    with _mps.TRAINING_JOBS_LOCK:
        _mps.TRAINING_JOBS.clear()
        _mps.TRAINING_JOBS.update(saved)


def _patch_celery_failure(monkeypatch, task_attr_name: str):
    """通用: patch app.tasks.model_training 使 Celery task.delay 抛异常."""
    import app.tasks.model_training as mt

    monkeypatch.setattr(mt, "save_job_to_redis", MagicMock())
    mock_task = MagicMock()
    mock_task.delay = MagicMock(side_effect=RuntimeError("celery broker down"))
    monkeypatch.setattr(mt, task_attr_name, mock_task)
    # 避免 get_training_job 触发真实 Redis 连接
    monkeypatch.setattr(mt, "get_job_from_redis", MagicMock(return_value=None))
    monkeypatch.setattr(mt, "update_job_in_redis", MagicMock())
    return mock_task


class TestStartTrainingJobReturns503:
    """PERF-P2-001: start_training_job Celery 失败时返回 503."""

    def test_raises_http_503_on_celery_failure(self, isolated_jobs, monkeypatch):
        _patch_celery_failure(monkeypatch, "train_bert_model_task")
        service = ModelPredictService()
        with pytest.raises(HTTPException) as exc_info:
            service.start_training_job("ds", "model", 1, 8, 0.001)
        assert exc_info.value.status_code == 503

    def test_503_detail_contains_celery_keyword(self, isolated_jobs, monkeypatch):
        _patch_celery_failure(monkeypatch, "train_bert_model_task")
        service = ModelPredictService()
        with pytest.raises(HTTPException) as exc_info:
            service.start_training_job("ds", "model", 1, 8, 0.001)
        detail = str(exc_info.value.detail)
        assert "Celery" in detail or "Redis" in detail or "不可用" in detail

    def test_503_leaves_job_in_queued_state(self, isolated_jobs, monkeypatch):
        """Celery 失败时任务保留在 TRAINING_JOBS 中 (status=queued), 但 503 返回.

        注意: try 块在 delay() 前已将 job 写入 TRAINING_JOBS + Redis,
        delay() 失败后 except 块抛出 503. job 记录保留供审计,
        由 cleanup_old_training_jobs() LRU 淘汰.
        """
        _patch_celery_failure(monkeypatch, "train_bert_model_task")
        service = ModelPredictService()
        with pytest.raises(HTTPException):
            service.start_training_job("ds", "model", 1, 8, 0.001)
        with _mps.TRAINING_JOBS_LOCK:
            assert len(_mps.TRAINING_JOBS) == 1
            job = list(_mps.TRAINING_JOBS.values())[0]
            assert job["status"] == "queued"

    def test_import_error_also_returns_503(self, isolated_jobs, monkeypatch):
        """ImportError (app.tasks.model_training 不可导入) 也应返回 503."""
        # 模拟 import 失败: 让 save_job_to_redis 抛 ImportError
        import app.tasks.model_training as mt

        monkeypatch.setattr(
            mt,
            "save_job_to_redis",
            MagicMock(side_effect=ImportError("module not found")),
        )
        monkeypatch.setattr(mt, "get_job_from_redis", MagicMock(return_value=None))
        service = ModelPredictService()
        with pytest.raises(HTTPException) as exc_info:
            service.start_training_job("ds", "model", 1, 8, 0.001)
        assert exc_info.value.status_code == 503


class TestStartEvaluateJobReturns503:
    """PERF-P2-001: start_evaluate_job Celery 失败时返回 503."""

    def test_raises_http_503_on_celery_failure(self, isolated_jobs, monkeypatch):
        _patch_celery_failure(monkeypatch, "evaluate_model_task")
        service = ModelPredictService()
        with pytest.raises(HTTPException) as exc_info:
            service.start_evaluate_job("ds", "model", "validation")
        assert exc_info.value.status_code == 503

    def test_503_detail_contains_keyword(self, isolated_jobs, monkeypatch):
        _patch_celery_failure(monkeypatch, "evaluate_model_task")
        service = ModelPredictService()
        with pytest.raises(HTTPException) as exc_info:
            service.start_evaluate_job("ds", "model", "test")
        detail = str(exc_info.value.detail)
        assert "Celery" in detail or "Redis" in detail or "不可用" in detail


class TestStartCompareJobReturns503:
    """PERF-P2-001: start_compare_job Celery 失败时返回 503."""

    def test_raises_http_503_on_celery_failure(self, isolated_jobs, monkeypatch):
        _patch_celery_failure(monkeypatch, "compare_models_task")
        service = ModelPredictService()
        with pytest.raises(HTTPException) as exc_info:
            service.start_compare_job("ds", ["model-a", "model-b"])
        assert exc_info.value.status_code == 503

    def test_503_detail_contains_keyword(self, isolated_jobs, monkeypatch):
        _patch_celery_failure(monkeypatch, "compare_models_task")
        service = ModelPredictService()
        with pytest.raises(HTTPException) as exc_info:
            service.start_compare_job("ds", ["model-a"])
        detail = str(exc_info.value.detail)
        assert "Celery" in detail or "Redis" in detail or "不可用" in detail


# =============================================================================
# 3. SpyThread 监控: 验证未创建 threading.Thread
# =============================================================================


class TestNoThreadCreated:
    """PERF-P2-001: Celery 失败时不应创建任何 threading.Thread."""

    @pytest.fixture
    def spy_thread(self, monkeypatch):
        """替换 threading.Thread 为 Spy, 记录所有构造调用."""
        original_thread = threading.Thread
        created: list[threading.Thread] = []

        class _SpyThread(original_thread):
            def __init__(self, *args, **kwargs):
                created.append(self)
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(threading, "Thread", _SpyThread)
        yield created

    def test_training_no_thread(self, isolated_jobs, monkeypatch, spy_thread):
        _patch_celery_failure(monkeypatch, "train_bert_model_task")
        service = ModelPredictService()
        with pytest.raises(HTTPException):
            service.start_training_job("ds", "model", 1, 8, 0.001)
        assert spy_thread == [], "start_training_job 不应创建 Thread"

    def test_evaluate_no_thread(self, isolated_jobs, monkeypatch, spy_thread):
        _patch_celery_failure(monkeypatch, "evaluate_model_task")
        service = ModelPredictService()
        with pytest.raises(HTTPException):
            service.start_evaluate_job("ds", "model", "validation")
        assert spy_thread == [], "start_evaluate_job 不应创建 Thread"

    def test_compare_no_thread(self, isolated_jobs, monkeypatch, spy_thread):
        _patch_celery_failure(monkeypatch, "compare_models_task")
        service = ModelPredictService()
        with pytest.raises(HTTPException):
            service.start_compare_job("ds", ["model-a"])
        assert spy_thread == [], "start_compare_job 不应创建 Thread"


# =============================================================================
# 4. 成功路径回归: Celery 成功时仍正常返回 queued 状态
# =============================================================================


class TestSuccessPathUnchanged:
    """PERF-P2-001: 成功路径 (Celery 可用) 行为不变."""

    def test_training_success_returns_queued(self, isolated_jobs, monkeypatch):
        import app.tasks.model_training as mt

        monkeypatch.setattr(mt, "save_job_to_redis", MagicMock())
        monkeypatch.setattr(mt, "get_job_from_redis", MagicMock(return_value=None))
        mock_task = MagicMock()
        monkeypatch.setattr(mt, "train_bert_model_task", mock_task)

        service = ModelPredictService()
        result = service.start_training_job("ds", "model", 1, 8, 0.001)
        assert result["status"] == "queued"
        mock_task.delay.assert_called_once()

    def test_evaluate_success_returns_queued(self, isolated_jobs, monkeypatch):
        import app.tasks.model_training as mt

        monkeypatch.setattr(mt, "save_job_to_redis", MagicMock())
        monkeypatch.setattr(mt, "get_job_from_redis", MagicMock(return_value=None))
        mock_task = MagicMock()
        monkeypatch.setattr(mt, "evaluate_model_task", mock_task)

        service = ModelPredictService()
        result = service.start_evaluate_job("ds", "model", "validation")
        assert result["status"] == "queued"
        mock_task.delay.assert_called_once()

    def test_compare_success_returns_queued(self, isolated_jobs, monkeypatch):
        import app.tasks.model_training as mt

        monkeypatch.setattr(mt, "save_job_to_redis", MagicMock())
        monkeypatch.setattr(mt, "get_job_from_redis", MagicMock(return_value=None))
        mock_task = MagicMock()
        monkeypatch.setattr(mt, "compare_models_task", mock_task)

        service = ModelPredictService()
        result = service.start_compare_job("ds", ["model-a", "model-b"])
        assert result["status"] == "queued"
        mock_task.delay.assert_called_once()


# =============================================================================
# 5. API 端点: 503 异常透传到 FastAPI 返回 503 响应
# =============================================================================


class TestApiEndpointReturns503:
    """PERF-P2-001: API 端点 /model/experiment/train|evaluate|compare 在 Celery 失败时返回 503.

    使用 conftest 的 session-scoped TestClient + autouse 鉴权 override.
    设置 CURRENT_USER["role"]="admin" 通过 require_permission 校验.
    """

    def test_train_endpoint_returns_503(self, client, isolated_jobs, monkeypatch, as_role):
        as_role("admin")
        _patch_celery_failure(monkeypatch, "train_bert_model_task")
        resp = client.post(
            "/api/v1/model/experiment/train",
            json={
                "dataset_name": "ds",
                "model_name": "model",
                "epochs": 1,
                "batch_size": 8,
                "learning_rate": 0.001,
            },
        )
        assert resp.status_code == 503

    def test_evaluate_endpoint_returns_503(self, client, isolated_jobs, monkeypatch, as_role):
        as_role("admin")
        _patch_celery_failure(monkeypatch, "evaluate_model_task")
        resp = client.post(
            "/api/v1/model/experiment/evaluate",
            json={
                "dataset_name": "ds",
                "model_name": "model",
                "split": "validation",
            },
        )
        assert resp.status_code == 503

    def test_compare_endpoint_returns_503(self, client, isolated_jobs, monkeypatch, as_role):
        as_role("admin")
        _patch_celery_failure(monkeypatch, "compare_models_task")
        resp = client.post(
            "/api/v1/model/experiment/compare",
            json={
                "dataset_name": "ds",
                "model_names": ["model-a", "model-b"],
            },
        )
        assert resp.status_code == 503
