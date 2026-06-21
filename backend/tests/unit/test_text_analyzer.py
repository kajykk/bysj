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
        """重复关键词，分数累加但不超过 100。"""
        result = analyzer.analyze("睡不着睡不着睡不着睡不着睡不着")
        assert result["risk_factor_scores"]["sleep_problem"] == 100.0

    def test_empty_text(self, analyzer: TextAnalyzer) -> None:
        """空文本。"""
        result = analyzer.analyze("")
        assert result["risk_factors"] == []
        assert result["protective_factors"] == []

    def test_translate_category(self, analyzer: TextAnalyzer) -> None:
        """类别翻译。"""
        assert analyzer._translate_category("sleep_problem") == "睡眠问题"
        assert analyzer._translate_category("unknown") == "unknown"
