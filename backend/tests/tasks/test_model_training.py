"""H-2 修复: BERT 模型训练 Celery 任务测试.

覆盖:
- _get_sync_redis: 单例懒加载
- _job_key: key 前缀构造
- save_job_to_redis: 成功 + Redis 异常 (L-18 warning)
- get_job_from_redis: 成功 / 无数据 / Redis 异常 (L-18)
- list_jobs_from_redis: 成功 / Redis 异常 (L-18)
- update_job_in_redis: 任务存在 / 任务不存在
- train_bert_model_task: 成功全流程 / 训练失败 (M-ML-5) / 任务注册
"""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from app.core.celery_app import celery_app

# ---------- 任务注册 ----------


def _ensure_tasks_loaded() -> None:
    """显式加载 model_training tasks 模块, 确保任务已注册."""
    import app.tasks.model_training  # noqa: F401


def test_train_bert_model_task_registered() -> None:
    """TC-COV-MT-001: train_bert_model_task 应在 Celery 中注册."""
    _ensure_tasks_loaded()
    task_names = list(celery_app.tasks.keys())
    assert "app.tasks.model_training.train_bert_model_task" in task_names


# ---------- _job_key ----------


def test_job_key_prefix() -> None:
    """TC-COV-MT-002: _job_key 应添加 training:job: 前缀."""
    from app.tasks.model_training import _job_key

    assert _job_key("abc-123") == "training:job:abc-123"
    assert _job_key("") == "training:job:"


# ---------- _get_sync_redis 单例 ----------


def test_get_sync_redis_caches_singleton() -> None:
    """TC-COV-MT-003: _get_sync_redis 多次调用应返回同一客户端 (懒加载单例)."""
    import app.tasks.model_training as mt_mod
    from app.tasks.model_training import _get_sync_redis

    # 重置单例
    original = mt_mod._sync_redis_client
    mt_mod._sync_redis_client = None
    try:
        with patch("redis.from_url") as mock_from_url:
            mock_client = MagicMock()
            mock_from_url.return_value = mock_client

            client1 = _get_sync_redis()
            client2 = _get_sync_redis()

        assert client1 is client2
        assert client1 is mock_client
        # from_url 只调用一次 (单例)
        mock_from_url.assert_called_once()
    finally:
        mt_mod._sync_redis_client = original


def test_get_sync_redis_returns_existing_client() -> None:
    """TC-COV-MT-004: 已存在的 _sync_redis_client 应直接返回, 不重新创建."""
    import app.tasks.model_training as mt_mod
    from app.tasks.model_training import _get_sync_redis

    mock_existing = MagicMock()
    original = mt_mod._sync_redis_client
    mt_mod._sync_redis_client = mock_existing
    try:
        with patch("redis.from_url") as mock_from_url:
            result = _get_sync_redis()
        assert result is mock_existing
        mock_from_url.assert_not_called()
    finally:
        mt_mod._sync_redis_client = original


# ---------- save_job_to_redis ----------


def test_save_job_to_redis_success() -> None:
    """TC-COV-MT-005: 成功保存时应调用 hset + sadd."""
    from app.tasks.model_training import save_job_to_redis

    mock_redis = MagicMock()
    job_data = {"job_id": "j1", "status": "running"}
    with patch("app.tasks.model_training._get_sync_redis", return_value=mock_redis):
        save_job_to_redis("j1", job_data)

    mock_redis.hset.assert_called_once()
    # hset(key, mapping=mapping): key 是位置参数, mapping 是关键字参数
    args = mock_redis.hset.call_args
    assert args[0][0] == "training:job:j1"
    # mapping 字段值为 JSON 编码, 保持与实现一致
    expected_mapping = {
        k: json.dumps(v, ensure_ascii=False) for k, v in job_data.items()
    }
    assert args.kwargs["mapping"] == expected_mapping
    mock_redis.sadd.assert_called_once_with("training:jobs", "j1")


def test_save_job_to_redis_logs_warning_on_exception(caplog) -> None:
    """TC-COV-MT-006: L-18 - Redis 异常时应记录 warning 而非静默吞掉."""
    from app.tasks.model_training import save_job_to_redis

    with patch(
        "app.tasks.model_training._get_sync_redis",
        side_effect=RuntimeError("redis down"),
    ):
        with caplog.at_level(logging.WARNING, logger="app.tasks.model_training"):
            # 不应抛异常
            save_job_to_redis("j1", {"status": "running"})

    assert any("failed to save job j1 to Redis" in r.message for r in caplog.records)
    assert any("redis down" in r.message for r in caplog.records)


# ---------- get_job_from_redis ----------


def test_get_job_from_redis_success() -> None:
    """TC-COV-MT-007: 成功读取时应返回解析后的 dict."""
    from app.tasks.model_training import get_job_from_redis

    mock_redis = MagicMock()
    job_data = {"job_id": "j1", "status": "completed", "progress": 100}
    # ISS-009: Hash 结构, hgetall 返回 {field: json_string}
    mock_redis.hgetall.return_value = {
        k: json.dumps(v, ensure_ascii=False) for k, v in job_data.items()
    }

    with patch("app.tasks.model_training._get_sync_redis", return_value=mock_redis):
        result = get_job_from_redis("j1")

    assert result == job_data
    mock_redis.hgetall.assert_called_once_with("training:job:j1")


def test_get_job_from_redis_no_data_returns_none() -> None:
    """TC-COV-MT-008: 无数据时应返回 None."""
    from app.tasks.model_training import get_job_from_redis

    mock_redis = MagicMock()
    # ISS-009: Hash 结构, hgetall 返回空 dict 表示无数据
    mock_redis.hgetall.return_value = {}

    with patch("app.tasks.model_training._get_sync_redis", return_value=mock_redis):
        result = get_job_from_redis("missing")

    assert result is None


def test_get_job_from_redis_logs_warning_on_exception(caplog) -> None:
    """TC-COV-MT-009: L-18 - Redis 异常时应记录 warning 并返回 None."""
    from app.tasks.model_training import get_job_from_redis

    with patch(
        "app.tasks.model_training._get_sync_redis",
        side_effect=RuntimeError("conn refused"),
    ):
        with caplog.at_level(logging.WARNING, logger="app.tasks.model_training"):
            result = get_job_from_redis("j1")

    assert result is None
    assert any("failed to get job j1 from Redis" in r.message for r in caplog.records)
    assert any("conn refused" in r.message for r in caplog.records)


# ---------- list_jobs_from_redis ----------


def test_list_jobs_from_redis_success() -> None:
    """TC-COV-MT-010: 成功列出时应返回所有任务的 dict 列表."""
    from app.tasks.model_training import list_jobs_from_redis

    mock_redis = MagicMock()
    mock_redis.smembers.return_value = {"j1", "j2"}
    job1 = {"job_id": "j1", "status": "running"}
    job2 = {"job_id": "j2", "status": "completed"}

    # ISS-009: hgetall 调用顺序不确定 (set 无序), 用 side_effect 根据参数返回
    def mock_hgetall(key):
        if key == "training:job:j1":
            return {k: json.dumps(v, ensure_ascii=False) for k, v in job1.items()}
        if key == "training:job:j2":
            return {k: json.dumps(v, ensure_ascii=False) for k, v in job2.items()}
        return {}

    mock_redis.hgetall.side_effect = mock_hgetall

    with patch("app.tasks.model_training._get_sync_redis", return_value=mock_redis):
        result = list_jobs_from_redis()

    assert len(result) == 2
    job_ids = {j["job_id"] for j in result}
    assert job_ids == {"j1", "j2"}


def test_list_jobs_from_redis_empty() -> None:
    """TC-COV-MT-011: 无任务时应返回空列表."""
    from app.tasks.model_training import list_jobs_from_redis

    mock_redis = MagicMock()
    mock_redis.smembers.return_value = set()

    with patch("app.tasks.model_training._get_sync_redis", return_value=mock_redis):
        result = list_jobs_from_redis()

    assert result == []


def test_list_jobs_from_redis_logs_warning_on_exception(caplog) -> None:
    """TC-COV-MT-012: L-18 - Redis 异常时应记录 warning 并返回空列表."""
    from app.tasks.model_training import list_jobs_from_redis

    with patch(
        "app.tasks.model_training._get_sync_redis",
        side_effect=RuntimeError("redis offline"),
    ):
        with caplog.at_level(logging.WARNING, logger="app.tasks.model_training"):
            result = list_jobs_from_redis()

    assert result == []
    assert any("failed to list jobs from Redis" in r.message for r in caplog.records)
    assert any("redis offline" in r.message for r in caplog.records)


def test_list_jobs_from_redis_skips_missing_job_data() -> None:
    """TC-COV-MT-013: 索引中存在但 job key 已被删除时应跳过 (hgetall 返回空)."""
    from app.tasks.model_training import list_jobs_from_redis

    mock_redis = MagicMock()
    mock_redis.smembers.return_value = {"j1", "j2"}

    # j1 有数据, j2 的 hgetall 返回空 dict (已被清理)
    def mock_hgetall(key):
        if key == "training:job:j1":
            j1 = {"job_id": "j1", "status": "completed"}
            return {k: json.dumps(v, ensure_ascii=False) for k, v in j1.items()}
        return {}

    mock_redis.hgetall.side_effect = mock_hgetall

    with patch("app.tasks.model_training._get_sync_redis", return_value=mock_redis):
        result = list_jobs_from_redis()

    assert len(result) == 1
    assert result[0]["job_id"] == "j1"


# ---------- update_job_in_redis ----------


def test_update_job_in_redis_existing_job() -> None:
    """TC-COV-MT-014: 任务存在时应通过 HSET 原子写入 updates + updated_at."""
    from app.tasks.model_training import update_job_in_redis

    mock_redis = MagicMock()
    mock_redis.exists.return_value = 1  # 任务存在

    with patch("app.tasks.model_training._get_sync_redis", return_value=mock_redis):
        update_job_in_redis("j1", status="completed", progress=100)

    mock_redis.exists.assert_called_once_with("training:job:j1")
    mock_redis.hset.assert_called_once()
    # hset(key, mapping=mapping): key 是位置参数, mapping 是关键字参数
    args = mock_redis.hset.call_args
    assert args[0][0] == "training:job:j1"
    mapping = args.kwargs["mapping"]
    # ISS-009: mapping 字段值为 JSON 编码, 仅包含 updates + updated_at (不合并原字段)
    assert json.loads(mapping["status"]) == "completed"
    assert json.loads(mapping["progress"]) == 100
    assert "updated_at" in mapping  # 自动追加 updated_at 时间戳


def test_update_job_in_redis_job_not_found_logs_warning(caplog) -> None:
    """TC-COV-MT-015: 任务不存在时应记录 warning 并直接返回."""
    from app.tasks.model_training import update_job_in_redis

    mock_redis = MagicMock()
    mock_redis.exists.return_value = 0  # 任务不存在

    with patch("app.tasks.model_training._get_sync_redis", return_value=mock_redis):
        with caplog.at_level(logging.WARNING, logger="app.tasks.model_training"):
            update_job_in_redis("missing", status="running")

    mock_redis.exists.assert_called_once_with("training:job:missing")
    mock_redis.hset.assert_not_called()
    assert any(
        "job missing not found in Redis, cannot update" in r.message
        for r in caplog.records
    )


# ---------- train_bert_model_task ----------


def test_train_bert_model_task_success() -> None:
    """TC-COV-MT-016: 成功训练流程应推进 progress 并写入 completed 状态."""
    from app.tasks.model_training import train_bert_model_task

    final_state = {"job_id": "j1", "status": "completed", "progress": 100}

    with patch("app.tasks.model_training.update_job_in_redis") as mock_update, patch(
        "app.tasks.model_training.get_job_from_redis", return_value=final_state
    ), patch("app.services.experiment_service.ExperimentService") as mock_svc_cls:
        mock_svc = mock_svc_cls.return_value
        mock_svc.import_dataset.return_value = {"imported": True}
        mock_svc.train_model.return_value = {"train_loss": [0.1], "val_accuracy": [0.9]}
        mock_svc.evaluate_model.return_value = {"accuracy": 0.92}

        result = train_bert_model_task(
            job_id="j1",
            dataset_name="ds",
            model_name="bert-base",
            epochs=3,
            batch_size=32,
            learning_rate=0.001,
        )

    # 应多次更新进度: import(10) -> train(35) -> evaluate(75) -> completed(100)
    assert mock_update.call_count == 4
    # 验证最后一次更新为 completed
    last_call = mock_update.call_args_list[-1]
    assert last_call.kwargs["status"] == "completed"
    assert last_call.kwargs["progress"] == 100
    assert last_call.kwargs["stage"] == "completed"
    # 返回最终状态
    assert result == final_state
    mock_svc.import_dataset.assert_called_once()
    mock_svc.train_model.assert_called_once()
    mock_svc.evaluate_model.assert_called_once()


def test_train_bert_model_task_failure_marks_failed_and_reraises(caplog) -> None:
    """TC-COV-MT-017: M-ML-5 - 训练失败应写入 failed 状态并重新抛出异常."""
    from app.tasks.model_training import train_bert_model_task

    with patch("app.tasks.model_training.update_job_in_redis") as mock_update, patch(
        "app.services.experiment_service.ExperimentService"
    ) as mock_svc_cls:
        mock_svc = mock_svc_cls.return_value
        mock_svc.import_dataset.side_effect = RuntimeError("dataset missing")

        with caplog.at_level(logging.ERROR, logger="app.tasks.model_training"):
            with pytest.raises(RuntimeError, match="dataset missing"):
                train_bert_model_task(
                    job_id="j2",
                    dataset_name="missing",
                    model_name="bert",
                    epochs=1,
                    batch_size=8,
                    learning_rate=0.01,
                )

    # 应调用 update_job_in_redis 标记 failed
    failed_call = mock_update.call_args
    assert failed_call.kwargs["status"] == "failed"
    assert failed_call.kwargs["progress"] == 100
    assert failed_call.kwargs["stage"] == "failed"
    assert "dataset missing" in failed_call.kwargs["error"]
    assert any("[training_task] failed job_id=j2" in r.message for r in caplog.records)


def test_train_bert_model_task_failure_during_train_stage() -> None:
    """TC-COV-MT-018: train 阶段失败时应标记 failed (覆盖 stage=train 之后失败)."""
    from app.tasks.model_training import train_bert_model_task

    with patch("app.tasks.model_training.update_job_in_redis") as mock_update, patch(
        "app.services.experiment_service.ExperimentService"
    ) as mock_svc_cls:
        mock_svc = mock_svc_cls.return_value
        mock_svc.import_dataset.return_value = {"ok": True}
        mock_svc.train_model.side_effect = RuntimeError("OOM")

        with pytest.raises(RuntimeError, match="OOM"):
            train_bert_model_task(
                job_id="j3",
                dataset_name="ds",
                model_name="big",
                epochs=5,
                batch_size=64,
                learning_rate=0.001,
            )

    # 验证至少有 import(10) + train(35) + failed 三个更新
    assert mock_update.call_count >= 3
    failed_call = mock_update.call_args
    assert failed_call.kwargs["status"] == "failed"
    assert failed_call.kwargs["error"] == "OOM"


def test_train_bert_model_task_failure_during_evaluate_stage() -> None:
    """TC-COV-MT-019: evaluate 阶段失败时应标记 failed (覆盖 stage=evaluate 之后失败)."""
    from app.tasks.model_training import train_bert_model_task

    with patch("app.tasks.model_training.update_job_in_redis") as mock_update, patch(
        "app.services.experiment_service.ExperimentService"
    ) as mock_svc_cls:
        mock_svc = mock_svc_cls.return_value
        mock_svc.import_dataset.return_value = {"ok": True}
        mock_svc.train_model.return_value = {"train_loss": [0.1]}
        mock_svc.evaluate_model.side_effect = RuntimeError("eval crashed")

        with pytest.raises(RuntimeError, match="eval crashed"):
            train_bert_model_task(
                job_id="j4",
                dataset_name="ds",
                model_name="m",
                epochs=1,
                batch_size=16,
                learning_rate=0.001,
            )

    failed_call = mock_update.call_args
    assert failed_call.kwargs["status"] == "failed"
    assert failed_call.kwargs["error"] == "eval crashed"


def test_train_bert_model_task_returns_unknown_when_redis_empty() -> None:
    """TC-COV-MT-020: 训练成功但 Redis 无最终状态时应返回 unknown 占位 dict."""
    from app.tasks.model_training import train_bert_model_task

    with patch("app.tasks.model_training.update_job_in_redis"), patch(
        "app.tasks.model_training.get_job_from_redis", return_value=None
    ), patch("app.services.experiment_service.ExperimentService") as mock_svc_cls:
        mock_svc = mock_svc_cls.return_value
        mock_svc.import_dataset.return_value = {}
        mock_svc.train_model.return_value = {"train_loss": []}
        mock_svc.evaluate_model.return_value = {}

        result = train_bert_model_task(
            job_id="j5",
            dataset_name="ds",
            model_name="m",
            epochs=1,
            batch_size=8,
            learning_rate=0.001,
        )

    assert result == {"job_id": "j5", "status": "unknown"}


def test_train_bert_model_task_max_retries_is_zero() -> None:
    """TC-COV-MT-021: 验证 train_bert_model_task 配置 max_retries=0 (失败不重试)."""
    from app.tasks.model_training import train_bert_model_task

    assert train_bert_model_task.max_retries == 0


# ---------- PERF-P1-006: evaluate_model_task ----------


def test_evaluate_model_task_registered() -> None:
    """PERF-P1-006: evaluate_model_task 应在 Celery 中注册."""
    _ensure_tasks_loaded()
    task_names = list(celery_app.tasks.keys())
    assert "app.tasks.model_training.evaluate_model_task" in task_names


def test_evaluate_model_task_success() -> None:
    """PERF-P1-006: 成功评估流程应推进 progress 并写入 completed 状态."""
    from app.tasks.model_training import evaluate_model_task

    final_state = {"job_id": "je1", "status": "completed", "progress": 100}

    with patch("app.tasks.model_training.update_job_in_redis") as mock_update, patch(
        "app.tasks.model_training.get_job_from_redis", return_value=final_state
    ), patch("app.services.experiment_service.ExperimentService") as mock_svc_cls:
        mock_svc = mock_svc_cls.return_value
        mock_svc.evaluate_model.return_value = {"accuracy": 0.92, "f1": 0.88}

        result = evaluate_model_task(
            job_id="je1",
            dataset_name="ds",
            model_name="bert-base",
            split="validation",
        )

    # 应 2 次更新进度: running(20) -> completed(100)
    assert mock_update.call_count == 2
    last_call = mock_update.call_args_list[-1]
    assert last_call.kwargs["status"] == "completed"
    assert last_call.kwargs["progress"] == 100
    assert last_call.kwargs["stage"] == "completed"
    assert last_call.kwargs["result"] == {"accuracy": 0.92, "f1": 0.88}
    assert result == final_state
    mock_svc.evaluate_model.assert_called_once_with("ds", "bert-base", "validation")


def test_evaluate_model_task_failure_marks_failed_and_reraises(caplog) -> None:
    """PERF-P1-006: 评估失败应写入 failed 状态并重新抛出异常 (M-ML-5 一致性)."""
    from app.tasks.model_training import evaluate_model_task

    with patch("app.tasks.model_training.update_job_in_redis") as mock_update, patch(
        "app.services.experiment_service.ExperimentService"
    ) as mock_svc_cls:
        mock_svc = mock_svc_cls.return_value
        mock_svc.evaluate_model.side_effect = RuntimeError("model not found")

        with caplog.at_level(logging.ERROR, logger="app.tasks.model_training"):
            with pytest.raises(RuntimeError, match="model not found"):
                evaluate_model_task(
                    job_id="je2",
                    dataset_name="ds",
                    model_name="missing",
                    split="test",
                )

    failed_call = mock_update.call_args
    assert failed_call.kwargs["status"] == "failed"
    assert failed_call.kwargs["progress"] == 100
    assert failed_call.kwargs["stage"] == "failed"
    assert "model not found" in failed_call.kwargs["error"]
    assert any("[evaluate_task] failed job_id=je2" in r.message for r in caplog.records)


def test_evaluate_model_task_max_retries_is_zero() -> None:
    """PERF-P1-006: evaluate_model_task 配置 max_retries=0."""
    from app.tasks.model_training import evaluate_model_task

    assert evaluate_model_task.max_retries == 0


def test_evaluate_model_task_time_limit_is_600() -> None:
    """PERF-P1-006: evaluate_model_task 配置 time_limit=600 (评估比训练快)."""
    from app.tasks.model_training import evaluate_model_task

    assert evaluate_model_task.time_limit == 600


# ---------- PERF-P1-006: compare_models_task ----------


def test_compare_models_task_registered() -> None:
    """PERF-P1-006: compare_models_task 应在 Celery 中注册."""
    _ensure_tasks_loaded()
    task_names = list(celery_app.tasks.keys())
    assert "app.tasks.model_training.compare_models_task" in task_names


def test_compare_models_task_success() -> None:
    """PERF-P1-006: 成功对比流程应推进 progress 并写入 completed 状态."""
    from app.tasks.model_training import compare_models_task

    final_state = {"job_id": "jc1", "status": "completed", "progress": 100}

    with patch("app.tasks.model_training.update_job_in_redis") as mock_update, patch(
        "app.tasks.model_training.get_job_from_redis", return_value=final_state
    ), patch("app.services.experiment_service.ExperimentService") as mock_svc_cls:
        mock_svc = mock_svc_cls.return_value
        mock_svc.compare_models.return_value = {"best": "model-a", "results": []}

        result = compare_models_task(
            job_id="jc1",
            dataset_name="ds",
            model_names=["model-a", "model-b"],
        )

    # 应 2 次更新进度: running(10) -> completed(100)
    assert mock_update.call_count == 2
    last_call = mock_update.call_args_list[-1]
    assert last_call.kwargs["status"] == "completed"
    assert last_call.kwargs["progress"] == 100
    assert last_call.kwargs["stage"] == "completed"
    assert last_call.kwargs["result"] == {"best": "model-a", "results": []}
    assert result == final_state
    mock_svc.compare_models.assert_called_once_with("ds", ["model-a", "model-b"])


def test_compare_models_task_failure_marks_failed_and_reraises(caplog) -> None:
    """PERF-P1-006: 对比失败应写入 failed 状态并重新抛出异常 (M-ML-5 一致性)."""
    from app.tasks.model_training import compare_models_task

    with patch("app.tasks.model_training.update_job_in_redis") as mock_update, patch(
        "app.services.experiment_service.ExperimentService"
    ) as mock_svc_cls:
        mock_svc = mock_svc_cls.return_value
        mock_svc.compare_models.side_effect = RuntimeError("dataset missing")

        with caplog.at_level(logging.ERROR, logger="app.tasks.model_training"):
            with pytest.raises(RuntimeError, match="dataset missing"):
                compare_models_task(
                    job_id="jc2",
                    dataset_name="missing",
                    model_names=["model-a"],
                )

    failed_call = mock_update.call_args
    assert failed_call.kwargs["status"] == "failed"
    assert failed_call.kwargs["progress"] == 100
    assert failed_call.kwargs["stage"] == "failed"
    assert "dataset missing" in failed_call.kwargs["error"]
    assert any("[compare_task] failed job_id=jc2" in r.message for r in caplog.records)


def test_compare_models_task_max_retries_is_zero() -> None:
    """PERF-P1-006: compare_models_task 配置 max_retries=0."""
    from app.tasks.model_training import compare_models_task

    assert compare_models_task.max_retries == 0


def test_compare_models_task_time_limit_is_1800() -> None:
    """PERF-P1-006: compare_models_task 配置 time_limit=1800 (多模型串行, 与 train 同档位)."""
    from app.tasks.model_training import compare_models_task

    assert compare_models_task.time_limit == 1800
