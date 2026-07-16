"""ISS-02 第七轮: app.tasks.model_training 纯逻辑聚焦测试.

覆盖点:
- _validate_path_param (ISS-008 路径遍历白名单校验, 安全关键)
- _job_key (Redis key 前缀拼接)
无需 DB / celery / redis 实时连接, 仅测模块级纯函数.
"""
from __future__ import annotations

import pytest

from app.tasks.model_training import _job_key, _validate_path_param


# ===== _validate_path_param (ISS-008 安全校验) =====
def test_validate_path_param_valid_simple():
    # 合法: 字母/数字/下划线/连字符 应通过
    _validate_path_param("dataset_name", "my_dataset-1_2")


def test_validate_path_param_valid_single():
    _validate_path_param("model_name", "abc")


def test_validate_path_param_rejects_slash():
    with pytest.raises(ValueError):
        _validate_path_param("dataset_name", "foo/bar")


def test_validate_path_param_rejects_dotdot():
    with pytest.raises(ValueError):
        _validate_path_param("dataset_name", "../etc/passwd")


def test_validate_path_param_rejects_dot():
    with pytest.raises(ValueError):
        _validate_path_param("model_name", "a.b")


def test_validate_path_param_rejects_space():
    with pytest.raises(ValueError):
        _validate_path_param("dataset_name", "a b")


def test_validate_path_param_rejects_non_str_int():
    with pytest.raises(ValueError):
        _validate_path_param("dataset_name", 123)


def test_validate_path_param_rejects_none():
    with pytest.raises(ValueError):
        _validate_path_param("dataset_name", None)


# ===== _job_key =====
def test_job_key_prefix():
    assert _job_key("job-42") == "training:job:job-42"
