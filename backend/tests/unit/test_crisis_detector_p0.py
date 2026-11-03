"""P0 危机识别修复回归（阶段 1：D1 分级 / D2 双阈值 / D4 第三人称归属）。

修复前这些用例会失败：

- 「活着没有意义，不想再坚持了」：旧实现只做精确子串匹配，词库缺
  「活着没有意义」与「不想再坚持」，返回 ``crisis_detected=False``。
- 「活着没有的意义」：旧实现不忽略插入虚词「的」，无法召回。
- 「活著沒有意義」：旧实现不做繁简归一，无法召回。
- 「他自杀了」：旧实现只看关键词，第三人称同样升级为危机。
- ``risk_level``：旧 schema 默认 0，未判定被伪装成「无风险」。
- 文本 0.30–0.55：旧实现只有单阈值，直接判高风险。
"""

from __future__ import annotations

import pytest

from app.core.crisis_detector import CrisisDetector
from app.core.ml_decision_thresholds import (
    TEXT_BILINGUAL_DECISION_THRESHOLD,
    TEXT_BILINGUAL_REVIEW_THRESHOLD,
    TEXT_DECISION_STATE_HIGH_RISK,
    TEXT_DECISION_STATE_NORMAL,
    TEXT_DECISION_STATE_SUSPECT,
    classify_text_probability,
)
from app.core.model_engine import ModelEngine
from app.core.model_engine.text_fusion import fuse_text_signals


@pytest.fixture
def detector() -> CrisisDetector:
    return CrisisDetector()


def _fuse_from_scan(scan: dict) -> dict:
    return fuse_text_signals(
        ml_probability=0.10,
        heuristic_score=0.10,
        crisis_score=float(scan["crisis_score"]),
        crisis_detected=bool(scan["crisis_detected"]),
        requires_corroboration=bool(scan.get("requires_corroboration", False)),
        matched_categories=scan.get("matched_categories", []),
        critical_intent=bool(scan.get("critical_intent", False)),
    )


class TestD1PassiveIdeationGrading:
    """D1：明确消极/被动意念必须 crisis_detected=True 且 risk_level>=3。"""

    @pytest.mark.parametrize(
        "text",
        [
            "活着没有意义，不想再坚持了",
            "活着没意义",
            "活着没有的意义",          # 插入虚词「的」
            "活著沒有意義",            # 繁体
            "我没有活下去的勇气",
            "我觉得自己是累赘",
            "我真的不想再坚持了",
        ],
    )
    def test_passive_ideation_detected_and_high_level(
        self, detector: CrisisDetector, text: str
    ) -> None:
        scan = detector.scan(text)
        assert scan["crisis_detected"] is True
        assert "passive_ideation" in scan["matched_categories"]
        fusion = _fuse_from_scan(scan)
        assert fusion["risk_level"] >= 3
        assert fusion["requires_human_review"] is True

    def test_passive_ideation_never_critical(self, detector: CrisisDetector) -> None:
        """无时间/计划/手段/明确意图的被动意念不得直接判 4 级。"""
        scan = detector.scan("活着没有意义，不想再坚持了")
        assert scan["critical_intent"] is False
        fusion = _fuse_from_scan(scan)
        assert fusion["risk_level"] == 3
        assert fusion["crisis_override"] is False
        assert "crisis_low_confidence" in fusion["review_reasons"]

    @pytest.mark.parametrize(
        "text",
        ["我想自杀", "我今晚就结束", "我准备好了结"],
    )
    def test_explicit_intent_can_reach_critical(
        self, detector: CrisisDetector, text: str
    ) -> None:
        scan = detector.scan(text)
        assert scan["crisis_detected"] is True
        assert scan["critical_intent"] is True
        fusion = _fuse_from_scan(scan)
        assert fusion["risk_level"] == 4
        assert fusion["crisis_override"] is True

    def test_broad_planning_stays_below_critical(
        self, detector: CrisisDetector
    ) -> None:
        scan = detector.scan("已经准备好了")
        assert scan["crisis_detected"] is True
        assert scan["critical_intent"] is False
        assert _fuse_from_scan(scan)["risk_level"] == 3


class TestD4ThirdPersonAndNegation:
    """D4：第三人称/引用/元讨论只记录不升级；否定仍生效。"""

    def test_third_person_suicide_only_recorded(
        self, detector: CrisisDetector
    ) -> None:
        scan = detector.scan("他自杀了")
        assert scan["crisis_detected"] is False
        assert scan["matched_keywords"] == []
        assert {item["keyword"] for item in scan["third_person_matches"]} == {"自杀"}
        assert _fuse_from_scan(scan)["risk_level"] is None

    def test_first_person_coexistence_treated_as_self(
        self, detector: CrisisDetector
    ) -> None:
        """文本同时含第一人称表述时按本人处理。"""
        scan = detector.scan("他自杀了，我也很难受")
        assert scan["crisis_detected"] is True
        assert "自杀" in scan["matched_keywords"]

    def test_negation_still_suppresses(self, detector: CrisisDetector) -> None:
        scan = detector.scan("我不会自杀")
        assert scan["crisis_detected"] is False
        assert any(
            item["reason"] == "negated" for item in scan["suppressed_matches"]
        )

    def test_reported_speech_with_first_person_kept(
        self, detector: CrisisDetector
    ) -> None:
        """既有行为保持：转述 + 第一人称在场时仍进入人工复核。"""
        scan = detector.scan("他说「我想死」，我有点担心。")
        assert scan["crisis_detected"] is True
        assert scan["matched_keywords"] == ["想死"]

    def test_quoted_meta_discussion_not_crisis(
        self, detector: CrisisDetector
    ) -> None:
        scan = detector.scan("「绝望」太重了，不像。")
        assert scan["crisis_detected"] is False
        assert scan["suppressed_matches"][0]["reason"] == "meta_mention"


class TestDiagnosisMatrixMissedRecall:
    """诊断矩阵：规则层剩余漏检必须全部召回（均走被动意念，封顶 3 级）。"""

    @pytest.mark.parametrize(
        "text",
        [
            "我不想再活下去了",
            "想从这个世界上消失",
            "活着真的一点意义都没有",
            "我活够了",
            "唔想活",
            "唔想做人",
        ],
    )
    def test_missed_expressions_detected(
        self, detector: CrisisDetector, text: str
    ) -> None:
        scan = detector.scan(text)
        assert scan["crisis_detected"] is True
        assert "passive_ideation" in scan["matched_categories"]
        fusion = _fuse_from_scan(scan)
        assert fusion["risk_level"] == 3
        assert fusion["requires_human_review"] is True

    @pytest.mark.parametrize(
        "text",
        ["他自杀了", "我朋友说他不想活了", "新闻里说有人自杀", "有人自杀了"],
    )
    def test_third_party_subjects_not_escalated(
        self, detector: CrisisDetector, text: str
    ) -> None:
        scan = detector.scan(text)
        assert scan["crisis_detected"] is False
        assert scan["third_person_matches"], text
        assert _fuse_from_scan(scan)["risk_level"] is None

    def test_third_party_plus_self_kept(
        self, detector: CrisisDetector
    ) -> None:
        """「我朋友说他…」中的「我」属第三方领属，但后文本人共存时不能压掉。"""
        scan = detector.scan("我朋友说他不想活，我也有点撑不住")
        assert scan["crisis_detected"] is True
        assert "不想活" in scan["matched_keywords"]

    @pytest.mark.parametrize(
        "text", ["我忍不住想死", "我控制不住自己想自杀"]
    )
    def test_known_negation_lookalikes_not_suppressed(
        self, detector: CrisisDetector, text: str
    ) -> None:
        scan = detector.scan(text)
        assert scan["crisis_detected"] is True
        assert not scan["suppressed_matches"]

    def test_unquoted_meta_discussion_suppressed(
        self, detector: CrisisDetector
    ) -> None:
        scan = detector.scan("想死这个词太重了")
        assert scan["crisis_detected"] is False
        assert scan["suppressed_matches"][0]["reason"] == "meta_mention"

    def test_clinical_reported_ideation_is_level_3(
        self, detector: CrisisDetector
    ) -> None:
        scan = detector.scan("医生说我有自杀意念")
        assert scan["crisis_detected"] is True
        assert scan["critical_intent"] is False
        fusion = _fuse_from_scan(scan)
        assert fusion["risk_level"] == 3
        assert fusion["requires_human_review"] is True


class TestD2DualThresholdGate:
    """D2：<0.30 正常；0.30–0.55 疑似需复核；>0.55 高风险。"""

    @pytest.mark.parametrize(
        ("probability", "expected"),
        [
            (0.29, TEXT_DECISION_STATE_NORMAL),
            (0.30, TEXT_DECISION_STATE_SUSPECT),
            (0.55, TEXT_DECISION_STATE_SUSPECT),
            (0.56, TEXT_DECISION_STATE_HIGH_RISK),
        ],
    )
    def test_three_state_classification(self, probability: float, expected: str) -> None:
        assert classify_text_probability(probability) == expected

    def test_thresholds_are_configured_constants(self) -> None:
        assert TEXT_BILINGUAL_DECISION_THRESHOLD == 0.30
        assert TEXT_BILINGUAL_REVIEW_THRESHOLD == 0.55


class TestRiskLevelUnknownContract:
    """未判定必须是显式 None，不能默认 0。"""

    @pytest.mark.asyncio
    async def test_suspect_probability_requires_review_without_level(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = ModelEngine()

        async def fake_predict_text_ml(_text: str) -> dict:
            return {
                "prediction": 0,
                "probability": 0.40,
                "sentiment_label": "negative",
                "sentiment_score": 0.40,
                "model_used": "text_improved_bilingual_model",
                "text_decision_state": TEXT_DECISION_STATE_SUSPECT,
            }

        monkeypatch.setattr(engine, "_predict_text_ml", fake_predict_text_ml)
        result = await engine.predict_text("最近压力很大但还好")
        assert result["risk_level"] is None
        assert result["requires_human_review"] is True
        assert "text_suspect_probability" in result["review_reasons"]
        assert result["prediction"] == 0

    @pytest.mark.asyncio
    async def test_high_probability_sets_high_risk_level(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = ModelEngine()

        async def fake_predict_text_ml(_text: str) -> dict:
            return {
                "prediction": 1,
                "probability": 0.70,
                "sentiment_label": "negative",
                "sentiment_score": 0.70,
                "model_used": "text_improved_bilingual_model",
                "text_decision_state": TEXT_DECISION_STATE_HIGH_RISK,
            }

        monkeypatch.setattr(engine, "_predict_text_ml", fake_predict_text_ml)
        result = await engine.predict_text("最近压力很大但还好")
        assert result["risk_level"] == 3
        assert result["requires_human_review"] is True
        assert "text_high_risk_probability" in result["review_reasons"]

    @pytest.mark.asyncio
    async def test_passive_ideation_end_to_end_grading(self) -> None:
        engine = ModelEngine()
        result = await engine.predict_text("活着没有意义，不想再坚持了")
        assert result["crisis_detected"] is True
        assert result["risk_level"] == 3
        assert result["requires_human_review"] is True

    @pytest.mark.asyncio
    async def test_third_person_end_to_end_not_escalated(self) -> None:
        engine = ModelEngine()
        result = await engine.predict_text("他自杀了")
        assert result["crisis_detected"] is False
        assert result["risk_level"] is None
