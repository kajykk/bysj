from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.crisis_detector import CrisisDetector
from app.core.model_registry import MODEL_REGISTRY, ModelMetadata, is_model_enabled
from app.core.security import get_password_hash, verify_password


class TestCrisisDetectorSeverity:
    def test_suicide_keyword_returns_max_severity_100(self):
        detector = CrisisDetector()
        result = detector.scan("我想自杀不想活了")
        assert result["crisis_detected"] is True
        assert result["crisis_score"] == 100

    def test_self_harm_keyword_returns_severity_100(self):
        detector = CrisisDetector()
        result = detector.scan("我经常割腕自残")
        assert result["crisis_detected"] is True
        assert result["crisis_score"] == 100

    def test_despair_keyword_returns_severity_80(self):
        detector = CrisisDetector()
        result = detector.scan("我彻底绝望了撑不下去了")
        assert result["crisis_detected"] is True
        assert result["crisis_score"] == 80

    def test_help_seeking_keyword_returns_severity_40_not_80(self):
        detector = CrisisDetector()
        result = detector.scan("救救我我需要帮助")
        assert result["crisis_detected"] is True
        assert result["crisis_score"] == 40
        assert result["crisis_score"] != 80

    def test_help_seeking_is_distinct_from_suicide(self):
        detector = CrisisDetector()
        suicide_result = detector.scan("我想结束生命")
        help_result = detector.scan("谁能帮帮我我快撑不住了")
        assert suicide_result["crisis_score"] == 100
        assert help_result["crisis_score"] < suicide_result["crisis_score"]

    def test_casual_expression_not_detected_as_crisis(self):
        detector = CrisisDetector()
        result = detector.scan("累死了烦死了")
        assert result["crisis_detected"] is False
        assert result["crisis_score"] == 0.0
        assert result["is_casual"] is True

    def test_empty_text_returns_no_crisis(self):
        detector = CrisisDetector()
        result = detector.scan("")
        assert result["crisis_detected"] is False
        assert result["crisis_score"] == 0.0

    def test_short_text_returns_no_crisis(self):
        detector = CrisisDetector()
        result = detector.scan("a")
        assert result["crisis_detected"] is False


class TestSecurityExceptions:
    def test_verify_password_with_valid_hash(self):
        hashed = get_password_hash("testpassword")
        assert verify_password("testpassword", hashed) is True

    def test_verify_password_with_wrong_password(self):
        hashed = get_password_hash("testpassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_verify_password_with_broken_hash_does_not_raise(self):
        assert verify_password("anything", "not-a-valid-bcrypt-hash") is False

    def test_verify_password_with_empty_hash_does_not_raise(self):
        assert verify_password("anything", "") is False

    def test_verify_password_long_password_truncated(self):
        # Phase 1 安全加固：超长密码不再被静默截断，而是直接拒绝
        # 防止两个共享前 72 字节的密码被视为相同
        long_password = "a" * 80
        with pytest.raises(ValueError, match="密码不能超过"):
            get_password_hash(long_password)

    def test_password_hash_is_deterministic_for_same_input(self):
        password = "uniquepassword123"
        hashed = get_password_hash(password)
        assert verify_password(password, hashed) is True


class TestModelRegistry:
    def test_is_model_enabled_unknown_model_returns_false(self):
        assert is_model_enabled("nonexistent_model_id_xyz") is False

    def test_is_model_enabled_known_default_model(self):
        if "structured_logistic_regression_v1.20" in MODEL_REGISTRY:
            assert is_model_enabled("structured_logistic_regression_v1.20") is True

    def test_is_model_enabled_disabled_model_returns_false(self):
        MODEL_REGISTRY["test_disabled_model"] = ModelMetadata(
            name="test_disabled_model",
            path="/fake/path",
            enabled=False,
            lifecycle="disabled",
        )
        try:
            assert is_model_enabled("test_disabled_model") is False
        finally:
            MODEL_REGISTRY.pop("test_disabled_model", None)


class TestGpaScaling:
    @pytest.mark.asyncio
    async def test_gpa_scale_parameter_is_used(self):
        from app.core.model_engine import ModelEngine

        model = ModelEngine()
        mock_model = MagicMock()
        mock_model.feature_names_in_ = None

        raw = {"cgpa": 3.8, "gpa_scale": 4.0}
        model._build_structured_input(raw, ["cgpa", "CGPA"], mock_model)

        raw2 = {"cgpa": 3.8, "gpa_scale": 10.0}
        model._build_structured_input(raw2, ["cgpa", "CGPA"], mock_model)


class TestSuicidalThoughtsSeparate:
    def test_suicidal_thoughts_not_conflated_with_panic_attack(self):
        from app.core.model_engine import ModelEngine

        model = ModelEngine()
        mock_model = MagicMock()
        mock_model.feature_names_in_ = None

        raw_only_panic = {
            "panic_attack": 1,
            "suicidal_thoughts": 0,
            "cgpa": 3.0,
            "gpa_scale": 4.0,
        }
        result = model._build_structured_input(
            raw_only_panic,
            ["panic_attack", "Have you ever had suicidal thoughts ?"],
            mock_model,
        )
        suicidal_field = result.get("Have you ever had suicidal thoughts ?")
        assert suicidal_field == 0

    def test_suicidal_thoughts_yes_when_field_is_1(self):
        from app.core.model_engine import ModelEngine

        model = ModelEngine()
        mock_model = MagicMock()
        mock_model.feature_names_in_ = None

        raw_with_suicidal = {
            "panic_attack": 0,
            "suicidal_thoughts": 1,
            "cgpa": 3.0,
            "gpa_scale": 4.0,
        }
        result = model._build_structured_input(
            raw_with_suicidal,
            ["panic_attack", "Have you ever had suicidal thoughts ?"],
            mock_model,
        )
        suicidal_field = result.get("Have you ever had suicidal thoughts ?")
        assert suicidal_field == 1


class TestLiteCrisisOverride:
    def test_crisis_override_level_is_4_not_3(self):
        from app.core.model_engine import model_engine

        safety = model_engine._check_crisis_safety("我想自杀活不下去了")
        assert safety["crisis_override"] is True
        assert len(safety["crisis_keywords_matched"]) > 0


class TestWebSocketFirstMessageAuth:
    def test_normalize_token_strips_bearer_prefix(self):
        from app.core.ws import _normalize_websocket_token

        assert _normalize_websocket_token("Bearer mytoken123") == "mytoken123"
        assert _normalize_websocket_token("bearer mytoken456") == "mytoken456"
        assert _normalize_websocket_token("mytoken789") == "mytoken789"
        assert _normalize_websocket_token(None) == ""
        assert _normalize_websocket_token("") == ""

    @pytest.mark.asyncio
    async def test_receive_auth_token_valid_message(self):
        from app.core.ws import _receive_auth_token

        mock_ws = AsyncMock()
        mock_ws.receive_text.return_value = json.dumps(
            {"type": "auth", "token": "Bearer test_token_123"}
        )

        token = await _receive_auth_token(mock_ws)
        assert token == "test_token_123"

    @pytest.mark.asyncio
    async def test_receive_auth_token_wrong_type_returns_empty(self):
        from app.core.ws import _receive_auth_token

        mock_ws = AsyncMock()
        mock_ws.receive_text.return_value = json.dumps(
            {"type": "ping", "token": "some_token"}
        )

        token = await _receive_auth_token(mock_ws)
        assert token == ""

    @pytest.mark.asyncio
    async def test_receive_auth_token_invalid_json_returns_empty(self):
        from app.core.ws import _receive_auth_token

        mock_ws = AsyncMock()
        mock_ws.receive_text.return_value = "not valid json{{{"

        token = await _receive_auth_token(mock_ws)
        assert token == ""


class TestCrisisDetectorEdgeCases:
    def test_multiple_categories_use_max_severity(self):
        detector = CrisisDetector()
        result = detector.scan("我想自杀了我需要帮助救救我")
        assert result["crisis_detected"] is True
        assert result["crisis_score"] == 100
        assert len(result["matched_keywords"]) >= 2

    def test_crisis_with_text_containing_both_suicide_and_help(self):
        detector = CrisisDetector()
        result = detector.scan("我想自杀谁能帮帮我")
        assert result["crisis_detected"] is True
        assert result["crisis_score"] == 100


class TestPasswordByteValidation:
    def test_ascii_password_under_72_bytes_is_valid(self):
        from app.core.security import validate_password_bytes

        validate_password_bytes("a" * 72)

    def test_ascii_password_73_bytes_raises(self):
        from app.core.security import validate_password_bytes

        with pytest.raises(ValueError, match="密码不能超过72字节"):
            validate_password_bytes("a" * 73)

    def test_cjk_password_24_chars_exceeds_72_bytes(self):
        from app.core.security import validate_password_bytes

        with pytest.raises(ValueError, match="密码不能超过72字节"):
            validate_password_bytes("密" * 25)

    def test_cjk_password_20_chars_is_valid(self):
        from app.core.security import validate_password_bytes

        validate_password_bytes("密" * 20)

    def test_mixed_password_correctly_computed(self):
        from app.core.security import MAX_PASSWORD_BYTES, validate_password_bytes

        pwd = "abc中文123"
        byte_len = len(pwd.encode("utf-8"))
        assert byte_len < MAX_PASSWORD_BYTES
        validate_password_bytes(pwd)


class TestRateLimiter:
    def test_limiter_exists_and_is_callable(self):
        from app.core.rate_limit import limiter

        assert limiter is not None

    def test_limiter_has_key_func(self):
        from app.core.rate_limit import limiter

        assert callable(limiter._key_func)

    def test_limiter_disabled_in_dev(self):
        import os

        from app.core.rate_limit import limiter

        if os.environ.get("APP_ENV", "").lower() not in ("production", "prod"):
            assert limiter.enabled is False


class TestFileSha256:
    def test_compute_sha256_on_small_file(self, tmp_path):
        from app.core.model_engine import _compute_file_sha256

        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        h = _compute_file_sha256(f)
        import hashlib

        expected = hashlib.sha256(b"hello world").hexdigest()
        assert h == expected

    def test_compute_sha256_on_large_file(self, tmp_path):
        from app.core.model_engine import CHUNK_SIZE, _compute_file_sha256

        f = tmp_path / "large.bin"
        data = b"X" * (CHUNK_SIZE * 3 + 123)
        f.write_bytes(data)
        h = _compute_file_sha256(f)
        import hashlib

        expected = hashlib.sha256(data).hexdigest()
        assert h == expected
        assert len(h) == 64


class TestPreloadExceptionClassification:
    def test_preload_handles_filenotfound_as_warning(self, caplog):
        import logging

        from app.core.model_engine import model_engine

        original_ids = model_engine.PRELOAD_IDS
        model_engine.PRELOAD_IDS = ["nonexistent_model_for_test"]
        caplog.set_level(logging.WARNING)
        try:
            model_engine.preload()
        finally:
            model_engine.PRELOAD_IDS = original_ids

        assert any(
            "recoverable" in r.message.lower() or "not found" in r.message.lower()
            for r in caplog.records
        )

    def test_preload_does_not_crash_on_all_errors(self):
        from app.core.model_engine import model_engine

        original_ids = model_engine.PRELOAD_IDS
        model_engine.PRELOAD_IDS = ["nonexistent_1", "nonexistent_2"]
        try:
            model_engine.preload()
        finally:
            model_engine.PRELOAD_IDS = original_ids
