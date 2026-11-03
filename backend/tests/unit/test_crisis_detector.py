from __future__ import annotations

import pytest

from app.core.crisis_detector import CrisisDetector


class TestCrisisDetector:
    """危机检测器单元测试。"""

    @pytest.fixture
    def detector(self) -> CrisisDetector:
        return CrisisDetector()

    # --- Happy Path ---

    def test_normal_text_no_crisis(self, detector: CrisisDetector) -> None:
        """正常文本应返回 crisis_detected=False。"""
        result = detector.scan("最近有点累，但总体还好。")
        assert result["crisis_detected"] is False
        assert result["crisis_score"] == 0.0
        assert result["matched_keywords"] == []
        assert result["category"] is None

    def test_risk_factors_no_crisis(self, detector: CrisisDetector) -> None:
        """包含风险因素但无危机表达。"""
        result = detector.scan("最近压力很大，睡不好，学习效率很低。")
        assert result["crisis_detected"] is False
        assert result["crisis_score"] == 0.0

    # --- Sad Path: Crisis Detection ---

    def test_suicide_keyword(self, detector: CrisisDetector) -> None:
        """自杀关键词检测。"""
        result = detector.scan("我不想活了，想结束这一切。")
        assert result["crisis_detected"] is True
        assert result["crisis_score"] == 100.0
        assert "不想活" in result["matched_keywords"]
        assert result["category"] == "suicide"

    def test_self_harm_keyword(self, detector: CrisisDetector) -> None:
        """自伤关键词检测。"""
        result = detector.scan("我想割腕，想伤害自己。")
        assert result["crisis_detected"] is True
        assert result["crisis_score"] == 100.0
        assert "割腕" in result["matched_keywords"]
        assert result["category"] == "self_harm"

    def test_despair_keyword(self, detector: CrisisDetector) -> None:
        """绝望关键词检测。"""
        result = detector.scan("我觉得没救了，一切都完了。")
        assert result["crisis_detected"] is True
        assert result["crisis_score"] == 80.0
        assert "没救了" in result["matched_keywords"]
        assert result["category"] == "despair"

    def test_multiple_keywords(self, detector: CrisisDetector) -> None:
        """多个危机关键词。"""
        result = detector.scan("我不想活了，想跳楼自杀。")
        assert result["crisis_detected"] is True
        assert result["crisis_score"] == 100.0
        assert len(result["matched_keywords"]) >= 2

    # --- Edge Cases ---

    def test_empty_text(self, detector: CrisisDetector) -> None:
        """空文本。"""
        result = detector.scan("")
        assert result["crisis_detected"] is False
        assert result["crisis_score"] == 0.0

    def test_short_text(self, detector: CrisisDetector) -> None:
        """极短文本。"""
        result = detector.scan("a")
        assert result["crisis_detected"] is False

    def test_casual_expression_filtered(self, detector: CrisisDetector) -> None:
        """口语化表达应被过滤。"""
        result = detector.scan("累死了")
        assert result["is_casual"] is True
        assert result["crisis_detected"] is False

    def test_mixed_casual_and_crisis(self, detector: CrisisDetector) -> None:
        """混合口语和危机表达，应检测为危机。"""
        result = detector.scan("累死了，真想自杀")
        assert result["crisis_detected"] is True
        assert "自杀" in result["matched_keywords"]

    def test_get_crisis_score(self, detector: CrisisDetector) -> None:
        """get_crisis_score 方法。"""
        assert detector.get_crisis_score("正常文本") == 0.0
        assert detector.get_crisis_score("我不想活了") == 100.0

    # --- v1.17 新增测试 ---

    def test_internet_slang_crisis(self, detector: CrisisDetector) -> None:
        """TC-TEXT-V17-HP-001: 网络用语危机检测。"""
        result = detector.scan("emo到不想活，真的撑不下去了")
        assert result["crisis_detected"] is True
        assert "emo到不想活" in result["matched_keywords"]

    def test_internet_slang_pofang(self, detector: CrisisDetector) -> None:
        """TC-TEXT-V17-HP-002: 破防到想死检测。"""
        result = detector.scan("破防到想死，一切都完了")
        assert result["crisis_detected"] is True
        assert "破防到想死" in result["matched_keywords"]

    def test_planning_expression(self, detector: CrisisDetector) -> None:
        """TC-TEXT-V17-HP-003: 计划性表达检测。"""
        result = detector.scan("已经准备好了，今晚就结束")
        assert result["crisis_detected"] is True
        assert "已经准备好了" in result["matched_keywords"]

    def test_help_seeking_expression(self, detector: CrisisDetector) -> None:
        """TC-TEXT-V17-HP-004: 求助表达检测。"""
        result = detector.scan("救救我，我控制不住自己")
        assert result["crisis_detected"] is True
        assert "救救我" in result["matched_keywords"]

    def test_casual_expression_xiaosi(self, detector: CrisisDetector) -> None:
        """TC-TEXT-V17-EC-001: 笑死了应被过滤。"""
        result = detector.scan("笑死了")
        assert result["is_casual"] is True
        assert result["crisis_detected"] is False

    def test_casual_expression_qisi(self, detector: CrisisDetector) -> None:
        """TC-TEXT-V17-EC-002: 气死了应被过滤。"""
        result = detector.scan("气死了")
        assert result["is_casual"] is True
        assert result["crisis_detected"] is False

    def test_casual_expression_shesi(self, detector: CrisisDetector) -> None:
        """TC-TEXT-V17-EC-003: 社死了应被过滤。"""
        result = detector.scan("社死了")
        assert result["is_casual"] is True
        assert result["crisis_detected"] is False

    def test_casual_expression_ganga(self, detector: CrisisDetector) -> None:
        """社死了/尴尬死了应被过滤。"""
        result = detector.scan("尴尬死了")
        assert result["is_casual"] is True
        assert result["crisis_detected"] is False

    # --- 上下文裁定回归（P0：引号/否定/被动意念） ---

    def test_quoted_meta_discussion_not_crisis(
        self, detector: CrisisDetector
    ) -> None:
        """引号内讨论词语本身，不应触发危机。"""
        result = detector.scan("「绝望」太重了，不像。「想死」太吓人。")
        assert result["crisis_detected"] is False
        assert result["crisis_score"] == 0.0
        assert result["matched_keywords"] == []
        reasons = {item["reason"] for item in result["suppressed_matches"]}
        assert reasons == {"meta_mention"}
        keywords = {item["keyword"] for item in result["suppressed_matches"]}
        assert {"绝望", "想死"} <= keywords

    def test_unquoted_meta_noun_not_crisis(self, detector: CrisisDetector) -> None:
        """「绝望这个词」是在讨论词，不是表达绝望。"""
        result = detector.scan("绝望这个词太重了")
        assert result["crisis_detected"] is False
        assert result["suppressed_matches"][0]["reason"] == "meta_mention"

    def test_negated_suicidal_thought_not_counted(
        self, detector: CrisisDetector
    ) -> None:
        """「不是想死」被否定，同句的被动意念仍然命中。"""
        result = detector.scan("不是想死，是不想再继续。")
        assert result["crisis_detected"] is True
        assert "想死" not in result["matched_keywords"]
        assert "不想再继续" in result["matched_keywords"]
        assert result["category"] == "passive_ideation"
        assert result["crisis_score"] == 85.0
        assert {item["keyword"] for item in result["suppressed_matches"]} == {"想死"}

    def test_passive_ideation_requires_corroboration(
        self, detector: CrisisDetector
    ) -> None:
        """单条被动意念不足以直接 level 4。"""
        result = detector.scan("我真的不想再继续了。")
        assert result["crisis_detected"] is True
        assert result["matched_categories"] == ["passive_ideation"]
        assert result["requires_corroboration"] is True

    def test_single_despair_requires_corroboration(
        self, detector: CrisisDetector
    ) -> None:
        """单条绝望需第二类信号佐证。"""
        result = detector.scan("我很绝望。")
        assert result["crisis_detected"] is True
        assert result["category"] == "despair"
        assert result["requires_corroboration"] is True

    def test_two_categories_corroborate_each_other(
        self, detector: CrisisDetector
    ) -> None:
        """绝望 + 求助构成双类别佐证。"""
        result = detector.scan("我很绝望，救救我。")
        assert result["crisis_detected"] is True
        assert set(result["matched_categories"]) == {"despair", "help_seeking"}
        assert result["requires_corroboration"] is False

    def test_direct_suicide_is_high_confidence(self, detector: CrisisDetector) -> None:
        """自杀表达本身语义明确，无需额外佐证。"""
        result = detector.scan("他说：我想死，我控制不住自己。")
        assert result["crisis_detected"] is True
        assert result["category"] == "suicide"
        assert result["requires_corroboration"] is False

    def test_reported_suicide_in_quotes_is_kept(
        self, detector: CrisisDetector
    ) -> None:
        """转述的危机表达仍要保留，交给人工复核归属。"""
        result = detector.scan("他说「我想死」，我有点担心。")
        assert result["crisis_detected"] is True
        assert result["matched_keywords"] == ["想死"]

    def test_broad_planning_keyword_requires_corroboration(
        self, detector: CrisisDetector
    ) -> None:
        """「已经准备好了」过于宽泛，单条不直接 critical。"""
        result = detector.scan("已经准备好了")
        assert result["crisis_detected"] is True
        assert result["category"] == "planning"
        assert result["requires_corroboration"] is True

    def test_explicit_planning_keyword_is_high_confidence(
        self, detector: CrisisDetector
    ) -> None:
        """「今晚就结束」语义明确，可直接 critical。"""
        result = detector.scan("今晚就结束")
        assert result["crisis_detected"] is True
        assert result["requires_corroboration"] is False
