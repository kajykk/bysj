"""中英双语文本 tokenizer.

供双语 TF-IDF 模型训练与推理共用。模块级函数可被 pickle by reference，
backend 推理进程 import 时惰性加载 jieba，避免加载开销与 pickle 依赖问题。
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
        except Exception:
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
