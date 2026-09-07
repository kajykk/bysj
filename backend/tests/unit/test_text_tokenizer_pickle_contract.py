"""N1 修订：text_tokenizer pickle 契约回归测试。

背景：静态引用扫描显示 ``app.core.text_tokenizer`` 在 app/tests/scripts 中零引用，
看似死代码。但训练产物 ``models/text/improved_bilingual_tfidf.pkl`` 中的
``TfidfVectorizer.tokenizer`` 以 pickle by-reference 方式引用
``app.core.text_tokenizer.zh_bilingual_tokenize`` —— 删除该模块会破坏
双语文本预测路径（Level 2 回退）的运行时反序列化。

本测试将这一隐式依赖固化为显式契约：
1. 纯函数行为测试（不依赖模型产物，始终可跑）
2. pickle 契约断言（产物存在时校验 tokenizer 解析到本模块函数）
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.text_tokenizer import (
    make_bilingual_tokenizer,
    zh_bilingual_tokenize,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
TFIDF_ARTIFACT = (
    BACKEND_DIR / "models" / "text" / "improved_bilingual_tfidf.pkl"
)

skip_no_artifact = pytest.mark.skipif(
    not TFIDF_ARTIFACT.exists(),
    reason="双语 TF-IDF 产物不存在 (gitignored, 仅本地/CI 构建上下文可用)",
)


class TestBilingualTokenizerBehavior:
    """zh_bilingual_tokenize 纯函数行为契约（不依赖模型产物）。"""

    def test_empty_text_returns_empty_list(self) -> None:
        assert zh_bilingual_tokenize("") == []
        assert zh_bilingual_tokenize(None) == []  # type: ignore[arg-type]

    def test_chinese_segmentation_with_jieba(self) -> None:
        tokens = zh_bilingual_tokenize("我很焦虑")
        # jieba 切词应产出语义化词元（至少包含"焦虑"），而非按字切分
        assert "焦虑" in tokens

    def test_english_words_kept_as_tokens(self) -> None:
        tokens = zh_bilingual_tokenize("I feel anxious today")
        assert "I" in tokens
        assert "feel" in tokens
        assert "anxious" in tokens
        assert "today" in tokens

    def test_mixed_bilingual_text(self) -> None:
        tokens = zh_bilingual_tokenize("我最近 feeling down")
        assert "我" in tokens or "最近" in tokens
        assert "feeling" in tokens
        assert "down" in tokens

    def test_custom_terms_registered(self) -> None:
        """jieba 自定义词（抑郁症/emo 等）应被完整保留。"""
        tokens = zh_bilingual_tokenize("我有抑郁症")
        assert "抑郁症" in tokens

    def test_make_bilingual_tokenizer_returns_module_function(self) -> None:
        assert make_bilingual_tokenizer() is zh_bilingual_tokenize


class TestBilingualPickleContract:
    """模型产物 → 本模块函数的 pickle 契约（防止静态分析误删）。"""

    def test_module_function_qualname(self) -> None:
        """契约锚点：函数必须位于 app.core.text_tokenizer 模块。"""
        assert zh_bilingual_tokenize.__module__ == "app.core.text_tokenizer"
        assert zh_bilingual_tokenize.__qualname__ == "zh_bilingual_tokenize"

    @skip_no_artifact
    def test_pickled_tfidf_tokenizer_references_this_module(self) -> None:
        """产物存在时，校验其 tokenizer 反序列化后仍解析到本模块函数。"""
        import joblib

        vectorizer = joblib.load(TFIDF_ARTIFACT)
        tokenizer = getattr(vectorizer, "tokenizer", None)

        assert tokenizer is not None, "TF-IDF 产物缺少 tokenizer 属性"
        assert tokenizer.__module__ == "app.core.text_tokenizer"
        assert tokenizer.__qualname__ == "zh_bilingual_tokenize"

    @skip_no_artifact
    def test_pickled_tfidf_transform_still_works(self) -> None:
        """完整链路：加载产物并执行一次 transform，确保反序列化不破损。"""
        import joblib

        vectorizer = joblib.load(TFIDF_ARTIFACT)
        matrix = vectorizer.transform(["最近压力很大，睡不着"])
        # 稀疏矩阵应至少包含 1 个非零特征
        assert matrix.nnz >= 1
