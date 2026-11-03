from __future__ import annotations

import pytest

from app.ml.text_analyzer import TextAnalyzer


class TestTextAnalyzer:
    """文本分析器单元测试。"""

    @pytest.fixture
    def analyzer(self) -> TextAnalyzer:
        return TextAnalyzer()

    # --- Happy Path ---

    def test_normal_text(self, analyzer: TextAnalyzer) -> None:
        """正常文本应返回空列表。"""
        result = analyzer.analyze("今天天气很好，心情不错。")
        assert result["risk_factors"] == []
        assert result["protective_factors"] == []

    def test_sleep_problem(self, analyzer: TextAnalyzer) -> None:
        """检测睡眠问题。"""
        result = analyzer.analyze("最近压力很大，睡不着，失眠严重。")
        assert "睡眠问题" in result["risk_factors"]
        assert "sleep_problem" in result["risk_factor_scores"]

    def test_help_seeking(self, analyzer: TextAnalyzer) -> None:
        """检测求助意愿。"""
        result = analyzer.analyze("我想求助，想聊聊我的问题。")
        assert "求助意愿" in result["protective_factors"]
        assert "help_seeking" in result["protective_factor_scores"]

    # --- Edge Cases ---

    def test_mixed_risk_and_protective(self, analyzer: TextAnalyzer) -> None:
        """混合风险和保护因素。"""
        result = analyzer.analyze("最近睡不着很焦虑，但想求助，朋友也在支持我。")
        assert "睡眠问题" in result["risk_factors"]
        assert "焦虑情绪" in result["risk_factors"]
        assert "求助意愿" in result["protective_factors"]
        assert "社会支持" in result["protective_factors"]

    def test_repeated_keywords(self, analyzer: TextAnalyzer) -> None:
        """同一关键词重复出现不应把分数堆到饱和。"""
        result = analyzer.analyze("睡不着睡不着睡不着睡不着睡不着")
        assert result["risk_factor_scores"]["sleep_problem"] == 32.5
        assert result["risk_factor_scores"]["sleep_problem"] < 100.0
        assert result["risk_evidence"]["sleep_problem"] == ["睡不着"]

    def test_empty_text(self, analyzer: TextAnalyzer) -> None:
        """空文本。"""
        result = analyzer.analyze("")
        assert result["risk_factors"] == []
        assert result["protective_factors"] == []

    def test_translate_category(self, analyzer: TextAnalyzer) -> None:
        """类别翻译。"""
        assert analyzer._translate_category("sleep_problem") == "睡眠问题"
        assert analyzer._translate_category("unknown") == "unknown"

    # --- P1 症状本体与上下文 ---

    def test_appetite_and_psychomotor_categories(self, analyzer: TextAnalyzer) -> None:
        """新增食欲与精神运动性迟滞类别。"""
        result = analyzer.analyze("不想吃饭，没胃口，连站起来都费劲，不想起床。")
        assert "食欲改变" in result["risk_factors"]
        assert "精神运动性迟滞" in result["risk_factors"]
        assert "appetite_change" in result["risk_factor_scores"]
        assert "psychomotor" in result["risk_factor_scores"]

    def test_worthlessness_and_hopelessness(self, analyzer: TextAnalyzer) -> None:
        """新增自我否定与无望感类别。"""
        result = analyzer.analyze("我觉得自己一无是处，看不到希望。")
        assert "自我否定" in result["risk_factors"]
        assert "无望感" in result["risk_factors"]

    def test_quoted_meta_not_counted(self, analyzer: TextAnalyzer) -> None:
        """引号内讨论「绝望」这个词，不算症状。"""
        result = analyzer.analyze("「绝望」太重了，「想死」太吓人。")
        assert result["risk_factors"] == []
        reasons = {item["reason"] for item in result["suppressed_matches"]}
        assert "meta_mention" in reasons

    def test_negated_protective_not_counted(self, analyzer: TextAnalyzer) -> None:
        """「不想求助」不能算求助意愿。"""
        result = analyzer.analyze("我不想求助，也不想聊聊。")
        assert "求助意愿" not in result["protective_factors"]

    def test_bare_nuli_is_not_protective(self, analyzer: TextAnalyzer) -> None:
        """裸「努力」不再算未来导向（努力表演不是保护因素）。"""
        result = analyzer.analyze("我每天都在努力表演一个正常人。")
        assert "未来导向" not in result["protective_factors"]
        assert result["protective_factor_scores"] == {}

    def test_bare_jianchi_is_not_protective(self, analyzer: TextAnalyzer) -> None:
        """「坚持不下去了」不能算未来导向。"""
        result = analyzer.analyze("我真的坚持不下去了。")
        assert "未来导向" not in result["protective_factors"]

    def test_third_person_symptom_not_counted(self, analyzer: TextAnalyzer) -> None:
        """第三人称的症状不记为用户症状。"""
        result = analyzer.analyze("我朋友最近很难受，也很焦虑。")
        assert result["risk_factors"] == []

    def test_reported_user_symptom_is_counted(self, analyzer: TextAnalyzer) -> None:
        """「朋友说我很难受」的主语仍是用户本人。"""
        result = analyzer.analyze("朋友说我最近很难受。")
        assert "持续低落" in result["risk_factors"]

    def test_bare_friend_is_not_social_support(self, analyzer: TextAnalyzer) -> None:
        """「朋友都不理我」不能算社会支持。"""
        result = analyzer.analyze("朋友都不理我。")
        assert "社会支持" not in result["protective_factors"]

    def test_protective_discount_is_capped(self, analyzer: TextAnalyzer) -> None:
        """再多保护因素也不能把重度症状压到低分（最多抵扣 25%）。"""
        severe = "我不想再继续了，看不到出路，一无是处。"
        base = analyzer.analyze(severe)["heuristic_sentiment_score"]
        with_protective = analyzer.analyze(
            severe + "但朋友支持我，家人支持我，我也想求助，想聊聊，天天运动。"
        )["heuristic_sentiment_score"]
        assert with_protective < base
        assert with_protective >= base * 0.75 - 1e-9

    def test_repeated_same_word_does_not_saturate(self, analyzer: TextAnalyzer) -> None:
        """同一句里重复 10 次「难过」的分数应低于 0.2。"""
        result = analyzer.analyze("难过，难过，难过，难过，难过，难过，难过，难过，难过，难过。")
        assert "持续低落" in result["risk_factors"]
        assert result["heuristic_sentiment_score"] < 0.2
