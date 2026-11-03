from __future__ import annotations

from app.core.text_context import analyze_match_context


def _context(text: str, keyword: str):
    start = text.index(keyword)
    return analyze_match_context(text, start, start + len(keyword))


class TestTextContext:
    def test_negation_prefix(self) -> None:
        ctx = _context("不是想死，是不想再继续", "想死")
        assert ctx.negated is True
        assert ctx.negation_marker == "不是"

    def test_bare_bu_directly_before_keyword(self) -> None:
        ctx = _context("我不想死，我想好好活着", "想死")
        assert ctx.negated is True

    def test_renbuzhu_is_not_negation(self) -> None:
        ctx = _context("我忍不住想死", "想死")
        assert ctx.negated is False

    def test_kongzhi_buzhu_is_not_negation(self) -> None:
        ctx = _context("我控制不住自己想死", "想死")
        assert ctx.negated is False

    def test_double_negation_is_affirmative(self) -> None:
        ctx = _context("我不是没有想过自杀", "自杀")
        assert ctx.negated is False

    def test_negation_window_stops_at_clause_delimiter(self) -> None:
        ctx = _context("不是没有希望，我想死", "想死")
        assert ctx.negated is False

    def test_quoted_meta_mention(self) -> None:
        ctx = _context("「想死」太吓人，像在演别人", "想死")
        assert ctx.in_quote is True
        assert ctx.meta_mention is True
        assert ctx.suppressed is True
        assert ctx.suppress_reason == "meta_mention"

    def test_quoted_meta_word_noun(self) -> None:
        ctx = _context("「绝望」这个词太重了", "绝望")
        assert ctx.meta_mention is True

    def test_quoted_reported_speech_is_kept(self) -> None:
        ctx = _context("他说「我想死」，我有点担心", "想死")
        assert ctx.in_quote is True
        assert ctx.meta_mention is False
        assert ctx.reported_speech is True
        assert ctx.suppressed is False

    def test_unquoted_meta_noun(self) -> None:
        ctx = _context("绝望这个词太重了", "绝望")
        assert ctx.meta_mention is True

    def test_unquoted_judgement_without_quote_is_not_meta(self) -> None:
        ctx = _context("我很绝望，绝望太重了", "绝望")
        assert ctx.meta_mention is False

    def test_meta_before_quote(self) -> None:
        ctx = _context("所谓的「绝望」其实很笼统", "绝望")
        assert ctx.meta_mention is True
