"""RES-P1-005/006/007 测试: 资源清理 (TRAINING_JOBS / uploads / experiment artifacts).

测试覆盖:
1. cleanup_old_training_jobs() - LRU 上限清理逻辑
2. _cleanup_uploads_dir_impl() - uploads/ 目录清理逻辑
3. _cleanup_experiment_artifacts_impl() - experiment artifact 清理逻辑
4. Celery 任务入口 - cleanup_training_jobs_task / cleanup_uploads_dir_task / cleanup_experiment_artifacts_task
5. Celery beat schedule 配置 - 3 个清理任务已注册
6. 源码静态扫描 - 关键设计点已实现
"""

from __future__ import annotations

import inspect
import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from app.services.model_predict_service import (
    _ACTIVE_JOB_STATUSES,
    TRAINING_JOBS,
    TRAINING_JOBS_LOCK,
    TRAINING_JOBS_MAX_SIZE,
    cleanup_old_training_jobs,
)
from app.tasks.scheduler import (
    _cleanup_experiment_artifacts_impl,
    _cleanup_uploads_dir_impl,
    cleanup_experiment_artifacts_task,
    cleanup_training_jobs_task,
    cleanup_uploads_dir_task,
)

# ============================================================================
# RES-P1-005: TRAINING_JOBS LRU 清理测试
# ============================================================================


class TestCleanupOldTrainingJobsConstants:
    """测试常量定义."""

    def test_max_size_is_100(self):
        """TC-RES-001: TRAINING_JOBS_MAX_SIZE 为 100."""
        assert TRAINING_JOBS_MAX_SIZE == 100

    def test_active_statuses_includes_running_queued(self):
        """TC-RES-002: _ACTIVE_JOB_STATUSES 包含 running 和 queued."""
        assert "running" in _ACTIVE_JOB_STATUSES
        assert "queued" in _ACTIVE_JOB_STATUSES


class TestCleanupOldTrainingJobsLogic:
    """测试 cleanup_old_training_jobs 清理逻辑."""

    def setup_method(self):
        """每个测试前清空 TRAINING_JOBS."""
        with TRAINING_JOBS_LOCK:
            saved = dict(TRAINING_JOBS)
            TRAINING_JOBS.clear()
            self._saved = saved

    def teardown_method(self):
        """测试后恢复 TRAINING_JOBS."""
        with TRAINING_JOBS_LOCK:
            TRAINING_JOBS.clear()
            TRAINING_JOBS.update(self._saved)

    def test_cleanup_no_op_when_below_max(self):
        """TC-RES-003: 任务数 <= max_size 时返回 0 不清理."""
        # 添加 5 个任务 (远小于 100)
        now = time.time()
        for i in range(5):
            TRAINING_JOBS[f"job-{i}"] = {
                "job_id": f"job-{i}",
                "status": "completed",
                "created_at": now - i * 100,
            }
        removed = cleanup_old_training_jobs(max_size=100)
        assert removed == 0
        assert len(TRAINING_JOBS) == 5

    def test_cleanup_removes_oldest_completed(self):
        """TC-RES-004: 超过上限时淘汰最老的 completed 任务."""
        now = time.time()
        # 添加 5 个 completed 任务 (created_at 升序)
        for i in range(5):
            TRAINING_JOBS[f"job-{i}"] = {
                "job_id": f"job-{i}",
                "status": "completed",
                "created_at": now - (5 - i) * 100,  # job-0 最老
            }
        # max_size=3, 应淘汰 2 个最老的 (job-0, job-1)
        removed = cleanup_old_training_jobs(max_size=3)
        assert removed == 2
        assert "job-0" not in TRAINING_JOBS
        assert "job-1" not in TRAINING_JOBS
        assert "job-2" in TRAINING_JOBS
        assert "job-3" in TRAINING_JOBS
        assert "job-4" in TRAINING_JOBS

    def test_cleanup_skips_running_jobs(self):
        """TC-RES-005: running/queued 任务不淘汰."""
        now = time.time()
        # job-old 是 completed 且最老
        TRAINING_JOBS["job-old"] = {
            "job_id": "job-old",
            "status": "completed",
            "created_at": now - 1000,
        }
        # job-running 是 running 但更老
        TRAINING_JOBS["job-running"] = {
            "job_id": "job-running",
            "status": "running",
            "created_at": now - 2000,
        }
        # job-queued 是 queued 但更老
        TRAINING_JOBS["job-queued"] = {
            "job_id": "job-queued",
            "status": "queued",
            "created_at": now - 3000,
        }
        # max_size=1, 应淘汰 job-old (running/queued 不淘汰)
        removed = cleanup_old_training_jobs(max_size=1)
        assert removed == 1
        assert "job-old" not in TRAINING_JOBS
        assert "job-running" in TRAINING_JOBS
        assert "job-queued" in TRAINING_JOBS

    def test_cleanup_returns_zero_when_all_active(self):
        """TC-RES-006: 全是活跃任务时不淘汰 (即使超过上限)."""
        now = time.time()
        # 添加 5 个 running 任务
        for i in range(5):
            TRAINING_JOBS[f"job-{i}"] = {
                "job_id": f"job-{i}",
                "status": "running",
                "created_at": now - i * 100,
            }
        # max_size=2, 但全是 running, 无法淘汰
        removed = cleanup_old_training_jobs(max_size=2)
        assert removed == 0
        assert len(TRAINING_JOBS) == 5

    def test_cleanup_handles_missing_created_at(self):
        """TC-RES-007: 缺失 created_at 视为 0 (最老) 优先淘汰."""
        TRAINING_JOBS["job-no-time"] = {
            "job_id": "job-no-time",
            "status": "completed",
            # 没有 created_at
        }
        TRAINING_JOBS["job-with-time"] = {
            "job_id": "job-with-time",
            "status": "completed",
            "created_at": time.time(),
        }
        # max_size=1, 应淘汰 job-no-time (created_at 缺失视为 0, 最老)
        removed = cleanup_old_training_jobs(max_size=1)
        assert removed == 1
        assert "job-no-time" not in TRAINING_JOBS
        assert "job-with-time" in TRAINING_JOBS

    def test_cleanup_handles_invalid_created_at(self):
        """TC-RES-008: created_at 为非数字时视为 0 优先淘汰."""
        TRAINING_JOBS["job-invalid"] = {
            "job_id": "job-invalid",
            "status": "completed",
            "created_at": "not-a-number",
        }
        TRAINING_JOBS["job-valid"] = {
            "job_id": "job-valid",
            "status": "completed",
            "created_at": time.time(),
        }
        removed = cleanup_old_training_jobs(max_size=1)
        assert removed == 1
        assert "job-invalid" not in TRAINING_JOBS
        assert "job-valid" in TRAINING_JOBS


# ============================================================================
# RES-P1-006: uploads/ 目录清理测试
# ============================================================================


class TestCleanupUploadsDir:
    """测试 _cleanup_uploads_dir_impl 清理逻辑."""

    def setup_method(self):
        """创建临时 uploads 目录."""
        self.tmp_dir = tempfile.mkdtemp(prefix="test_uploads_")
        self.uploads_dir = Path(self.tmp_dir) / "uploads"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        """清理临时目录."""
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _make_user_file(self, user_id: str, filename: str, mtime_days_ago: float = 0):
        """在 uploads/{user_id}/ 下创建文件并设置 mtime."""
        user_dir = self.uploads_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        file_path = user_dir / filename
        file_path.write_text(f"test content for {filename}")
        if mtime_days_ago > 0:
            old_time = time.time() - mtime_days_ago * 86400
            os.utime(file_path, (old_time, old_time))
        return file_path

    def _make_public_file(self, dirname: str, filename: str):
        """在 uploads/{dirname}/ 下创建公共文件."""
        pub_dir = self.uploads_dir / dirname
        pub_dir.mkdir(parents=True, exist_ok=True)
        file_path = pub_dir / filename
        file_path.write_text(f"public content for {filename}")
        return file_path

    def test_cleanup_removes_old_files(self):
        """TC-RES-009: 删除超过 max_age_days 的旧文件."""
        # 用户 1 的文件 31 天前 (应删除)
        self._make_user_file("1", "old.txt", mtime_days_ago=31)
        # 用户 1 的文件 10 天前 (应保留)
        self._make_user_file("1", "recent.txt", mtime_days_ago=10)

        with patch(
            "app.api.v1.uploads._resolve_upload_dir", return_value=self.uploads_dir
        ):
            removed = _cleanup_uploads_dir_impl(max_age_days=30)

        assert removed == 1
        assert not (self.uploads_dir / "1" / "old.txt").exists()
        assert (self.uploads_dir / "1" / "recent.txt").exists()

    def test_cleanup_skips_public_dirs(self):
        """TC-RES-010: 公共目录 (audio/content) 不清理."""
        # 公共 audio 目录的文件 100 天前 (应保留)
        self._make_public_file("audio", "old.mp3")
        old_time = time.time() - 100 * 86400
        os.utime(self.uploads_dir / "audio" / "old.mp3", (old_time, old_time))
        # 用户 1 的文件 31 天前 (应删除)
        self._make_user_file("1", "old.txt", mtime_days_ago=31)

        with patch(
            "app.api.v1.uploads._resolve_upload_dir", return_value=self.uploads_dir
        ):
            removed = _cleanup_uploads_dir_impl(max_age_days=30)

        assert removed == 1
        assert (self.uploads_dir / "audio" / "old.mp3").exists()

    def test_cleanup_skips_non_digit_dirs(self):
        """TC-RES-011: 非数字命名的目录不清理."""
        # 非数字目录文件 100 天前 (应保留)
        non_digit_dir = self.uploads_dir / "temp_dir"
        non_digit_dir.mkdir(parents=True, exist_ok=True)
        old_file = non_digit_dir / "old.txt"
        old_file.write_text("test")
        old_time = time.time() - 100 * 86400
        os.utime(old_file, (old_time, old_time))

        with patch(
            "app.api.v1.uploads._resolve_upload_dir", return_value=self.uploads_dir
        ):
            removed = _cleanup_uploads_dir_impl(max_age_days=30)

        assert removed == 0
        assert old_file.exists()

    def test_cleanup_removes_empty_user_dirs(self):
        """TC-RES-012: 清理后空的用户目录应被删除."""
        # 用户 1 的文件 31 天前 (应删除, 然后目录为空)
        self._make_user_file("1", "old.txt", mtime_days_ago=31)

        with patch(
            "app.api.v1.uploads._resolve_upload_dir", return_value=self.uploads_dir
        ):
            _cleanup_uploads_dir_impl(max_age_days=30)

        # 用户目录应为空后被删除
        assert not (self.uploads_dir / "1").exists()

    def test_cleanup_returns_zero_when_dir_not_exists(self):
        """TC-RES-013: uploads 目录不存在时返回 0."""
        with patch(
            "app.api.v1.uploads._resolve_upload_dir",
            return_value=Path("/nonexistent/path"),
        ):
            removed = _cleanup_uploads_dir_impl(max_age_days=30)
        assert removed == 0

    def test_cleanup_keeps_files_within_threshold(self):
        """TC-RES-014: 未超过 max_age_days 的文件保留."""
        # 30 天前 (恰好等于阈值, 不删除, 因为 cutoff = now - 30*86400)
        # 修改时间是 30 天前 + 1 秒 (即 cutoff 之后, 应保留)
        self._make_user_file("1", "boundary.txt", mtime_days_ago=29.9)

        with patch(
            "app.api.v1.uploads._resolve_upload_dir", return_value=self.uploads_dir
        ):
            removed = _cleanup_uploads_dir_impl(max_age_days=30)

        assert removed == 0
        assert (self.uploads_dir / "1" / "boundary.txt").exists()


# ============================================================================
# RES-P1-007: experiment artifact 清理测试
# ============================================================================


class TestCleanupExperimentArtifacts:
    """测试 _cleanup_experiment_artifacts_impl 清理逻辑."""

    def setup_method(self):
        """创建临时 trained 目录."""
        self.tmp_dir = tempfile.mkdtemp(prefix="test_trained_")
        self.trained_root = Path(self.tmp_dir) / "trained"
        self.trained_root.mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        """清理临时目录."""
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _make_artifact_dir(
        self, name: str, mtime_days_ago: float = 0, files: list[str] | None = None
    ):
        """创建训练产物目录."""
        dir_path = self.trained_root / name
        dir_path.mkdir(parents=True, exist_ok=True)
        for f in files or ["model.bin"]:
            (dir_path / f).write_text(f"content for {f}")
        if mtime_days_ago > 0:
            old_time = time.time() - mtime_days_ago * 86400
            os.utime(dir_path, (old_time, old_time))
        return dir_path

    def test_cleanup_removes_oldest_beyond_keep(self):
        """TC-RES-015: 超过 keep_recent 时淘汰最老的目录."""
        # 创建 5 个目录, mtime 递减 (oldest 在前)
        for i in range(5):
            self._make_artifact_dir(f"model_v{i}", mtime_days_ago=10 - i)

        with patch("app.core.config.settings.model_dir", self.tmp_dir):
            with patch("app.core.model_registry.MODEL_PATHS", {}):
                removed = _cleanup_experiment_artifacts_impl(keep_recent=3)

        assert removed == 2
        # 最老的 2 个应被删除 (model_v0, model_v1)
        assert not (self.trained_root / "model_v0").exists()
        assert not (self.trained_root / "model_v1").exists()
        # 最近的 3 个保留 (model_v2, model_v3, model_v4)
        assert (self.trained_root / "model_v2").exists()
        assert (self.trained_root / "model_v3").exists()
        assert (self.trained_root / "model_v4").exists()

    def test_cleanup_no_op_when_below_keep(self):
        """TC-RES-016: 目录数 <= keep_recent 时不清理."""
        for i in range(3):
            self._make_artifact_dir(f"model_v{i}", mtime_days_ago=i)

        with patch("app.core.config.settings.model_dir", self.tmp_dir):
            with patch("app.core.model_registry.MODEL_PATHS", {}):
                removed = _cleanup_experiment_artifacts_impl(keep_recent=10)

        assert removed == 0
        assert len(list(self.trained_root.iterdir())) == 3

    def test_cleanup_skips_active_model_dirs(self):
        """TC-RES-017: 包含 active 模型文件的目录不删除."""
        # 创建 5 个目录
        dirs = []
        for i in range(5):
            d = self._make_artifact_dir(f"model_v{i}", mtime_days_ago=10 - i)
            dirs.append(d)

        # 将最老目录中的文件注册为 active 模型路径
        active_path = str(dirs[0] / "model.bin")
        with patch("app.core.config.settings.model_dir", self.tmp_dir):
            with patch(
                "app.core.model_registry.MODEL_PATHS", {"active_model": active_path}
            ):
                removed = _cleanup_experiment_artifacts_impl(keep_recent=3)

        # 应删除 1 个 (跳过 active 的最老目录, 删除次老的)
        assert removed == 1
        # active 目录保留
        assert dirs[0].exists()
        # 次老目录删除
        assert not dirs[1].exists()

    def test_cleanup_returns_zero_when_dir_not_exists(self):
        """TC-RES-018: trained 目录不存在时返回 0."""
        with patch("app.core.config.settings.model_dir", "/nonexistent"):
            with patch("app.core.model_registry.MODEL_PATHS", {}):
                removed = _cleanup_experiment_artifacts_impl(keep_recent=10)
        assert removed == 0


# ============================================================================
# Celery 任务入口测试
# ============================================================================


class TestCeleryTaskEntries:
    """测试 Celery 任务入口函数."""

    def test_cleanup_training_jobs_task_callable(self):
        """TC-RES-019: cleanup_training_jobs_task 可调用 (Celery task 装饰)."""
        # 验证是 Celery task 对象
        assert hasattr(cleanup_training_jobs_task, "delay")
        assert hasattr(cleanup_training_jobs_task, "apply_async")

    def test_cleanup_uploads_dir_task_callable(self):
        """TC-RES-020: cleanup_uploads_dir_task 可调用 (Celery task 装饰)."""
        assert hasattr(cleanup_uploads_dir_task, "delay")
        assert hasattr(cleanup_uploads_dir_task, "apply_async")

    def test_cleanup_experiment_artifacts_task_callable(self):
        """TC-RES-021: cleanup_experiment_artifacts_task 可调用 (Celery task 装饰)."""
        assert hasattr(cleanup_experiment_artifacts_task, "delay")
        assert hasattr(cleanup_experiment_artifacts_task, "apply_async")


# ============================================================================
# Celery beat schedule 配置测试
# ============================================================================


class TestCeleryBeatSchedule:
    """测试 Celery beat schedule 中已注册 3 个清理任务."""

    def test_cleanup_training_jobs_in_beat_schedule(self):
        """TC-RES-022: cleanup-training-jobs 已注册到 beat_schedule."""
        from app.core.celery_app import celery_app

        assert "cleanup-training-jobs" in celery_app.conf.beat_schedule
        schedule = celery_app.conf.beat_schedule["cleanup-training-jobs"]
        assert schedule["task"] == "app.tasks.scheduler.cleanup_training_jobs_task"

    def test_cleanup_uploads_dir_in_beat_schedule(self):
        """TC-RES-023: cleanup-uploads-dir 已注册到 beat_schedule."""
        from app.core.celery_app import celery_app

        assert "cleanup-uploads-dir" in celery_app.conf.beat_schedule
        schedule = celery_app.conf.beat_schedule["cleanup-uploads-dir"]
        assert schedule["task"] == "app.tasks.scheduler.cleanup_uploads_dir_task"

    def test_cleanup_experiment_artifacts_in_beat_schedule(self):
        """TC-RES-024: cleanup-experiment-artifacts 已注册到 beat_schedule."""
        from app.core.celery_app import celery_app

        assert "cleanup-experiment-artifacts" in celery_app.conf.beat_schedule
        schedule = celery_app.conf.beat_schedule["cleanup-experiment-artifacts"]
        assert (
            schedule["task"] == "app.tasks.scheduler.cleanup_experiment_artifacts_task"
        )


# ============================================================================
# 源码静态扫描测试
# ============================================================================


class TestSourceStructure:
    """源码静态扫描 - 确认关键设计点已实现."""

    def test_cleanup_old_training_jobs_defined(self):
        """TC-RES-025: cleanup_old_training_jobs 函数已定义."""
        from app.services.model_predict_service import cleanup_old_training_jobs

        assert callable(cleanup_old_training_jobs)

    def test_cleanup_function_uses_lock(self):
        """TC-RES-026: cleanup_old_training_jobs 必须使用 TRAINING_JOBS_LOCK."""
        source = inspect.getsource(cleanup_old_training_jobs)
        assert "TRAINING_JOBS_LOCK" in source

    def test_cleanup_function_skips_active_statuses(self):
        """TC-RES-027: cleanup_old_training_jobs 必须检查活跃状态."""
        source = inspect.getsource(cleanup_old_training_jobs)
        assert "_ACTIVE_JOB_STATUSES" in source

    def test_cleanup_function_persists_after_cleanup(self):
        """TC-RES-028: cleanup_old_training_jobs 清理后必须持久化."""
        source = inspect.getsource(cleanup_old_training_jobs)
        assert "_save_training_jobs" in source

    def test_start_training_job_calls_cleanup(self):
        """TC-RES-029: start_training_job 必须调用 cleanup_old_training_jobs."""
        from app.services.model_predict_service import ModelPredictService

        source = inspect.getsource(ModelPredictService.start_training_job)
        assert "cleanup_old_training_jobs" in source

    def test_module_load_calls_cleanup(self):
        """TC-RES-030: 模块加载时必须调用 cleanup_old_training_jobs."""
        from app.services import model_predict_service

        source = inspect.getsource(model_predict_service)
        # 模块级调用应在 _load_training_jobs 之后
        assert "cleanup_old_training_jobs()" in source

    def test_cleanup_uploads_impl_skips_public_dirs(self):
        """TC-RES-031: _cleanup_uploads_dir_impl 必须跳过 PUBLIC_DIRS."""
        source = inspect.getsource(_cleanup_uploads_dir_impl)
        assert "PUBLIC_DIRS" in source

    def test_cleanup_uploads_impl_only_digit_dirs(self):
        """TC-RES-032: _cleanup_uploads_dir_impl 仅清理数字命名目录."""
        source = inspect.getsource(_cleanup_uploads_dir_impl)
        assert "isdigit" in source

    def test_cleanup_artifacts_impl_checks_active_paths(self):
        """TC-RES-033: _cleanup_experiment_artifacts_impl 必须检查 active 模型路径."""
        source = inspect.getsource(_cleanup_experiment_artifacts_impl)
        assert "MODEL_PATHS" in source
        assert "active_paths" in source

    def test_cleanup_artifacts_impl_keep_recent_default_10(self):
        """TC-RES-034: _cleanup_experiment_artifacts_impl 默认 keep_recent=10."""
        import inspect as ins

        sig = ins.signature(_cleanup_experiment_artifacts_impl)
        assert sig.parameters["keep_recent"].default == 10
