"""中英双语文本 tokenizer.

供双语 TF-IDF 模型训练与推理共用。模块级函数可被 pickle by reference，
backend 推理进程 import 时惰性加载 jieba，避免加载开销与 pickle 依赖问题。

.. warning::
    **PICKLE 契约 — 禁止删除本模块**

    训练产物 ``models/text/improved_bilingual_tfidf.pkl`` 中的
    ``TfidfVectorizer.tokenizer`` 以 pickle by-reference 方式引用本模块的
    ``zh_bilingual_tokenize``（序列化字节含 ``app.core.text_tokenizer`` 全限定路径）。

    因此本模块是**运行时硬依赖**，不是死代码：静态引用扫描（grep/import-linter 等）
    无法发现该依赖，若按"零引用"误删，双语文本预测路径（Level 2 回退）会在
    ``tfidf.transform()`` 反序列化时抛 ``ModuleNotFoundError``，静默降级为英文主模型。

    契约测试见 ``backend/tests/unit/test_text_tokenizer_pickle_contract.py``。
    如需移除，必须同步重新训练/重新序列化 ``improved_bilingual_tfidf.pkl``。
"""

from __future__ import annotations

import re
from typing import Callable

_EN_ATTERN = re.compile(r"[a-zA-Z0-9]+(?:\'[a-z]+)?")
_JIEBA = None


def _get_jieba():
    global _JIEBA
    if _JIEBA is None:
        import jieba

        try:
            jieba.setLogLevel(20)  # 静默 INFO 日志
        except AttributeError:
            # 旧版 jieba 无 setLogLevel 时降级为默认日志级别
            pass
        for word in ("抑郁症", "焦虑症", "失眠", "emo", "躺平", "内卷", "摆烂"):
            jieba.add_word(word)
        _JIEBA = jieba
    return _JIEBA


def zh_bilingual_tokenize(text: str) -> list[str]:
    """中文按词切分（jieba），英文/数字按词元切分，混合返回 token 列表。

    中文无空格分词借助 jieba；英文 (含 URL/数字) 用正则保词。过滤空白。
    """
    if not text:
        return []
    tokens: list[str] = []
    jieba = _get_jieba()

    for segment in re.split(r"([\u4e00-\u9fff\u3400-\u4dbf]+)", text):
        if not segment:
            continue
        if "\u4e00" <= segment[0] <= "\u9fff" or "\u3400" <= segment[0] <= "\u4dbf":
            tokens.extend([t for t in jieba.cut(segment) if t.strip()])
        else:
            tokens.extend(seg for seg in _EN_ATTERN.findall(segment) if seg)
    return tokens


def make_bilingual_tokenizer() -> Callable[[str], list[str]]:
    return zh_bilingual_tokenize
