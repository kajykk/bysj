"""P2-32 SSOT 闸门（后端侧）：危机词表只能有一份来源。

实测背景（scripts/audit_ssot_duplication.py）：
`app/core/model_engine/inference.py` 曾持有第二份 CRISIS_KEYWORDS，与
`app/core/config.py` 的 `Settings.crisis_keywords` **字面完全相同**（10 词），
但无任何生产消费点 —— 唯一读词表的地方是 `model_engine/risk.py:119`
读 `settings.crisis_keywords`。两份都"看起来是词表"，Settings 默认值调整时
inference 那份会静默漂移。本轮删除死副本，SSOT 唯一保留在 Settings。

有一处**有意不合并**的：
- `crisis_detector.CRISIS_KEYWORDS`：6 分类危机分类器（dict[str, list[str]]，
  含 category 分层），职责与「布尔命中词表」不同，合并会丢失分类语义。
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND / "app"

# 唯一允许持有「危机命中词表」的位置（Settings 字段，环境可覆盖）
CRISIS_WORDLIST_SSOT = "core/config.py"

# 有意保留的分类器（非词表，职责不同）
CLASSIFIER_ALLOWLIST = {"core/crisis_detector.py"}


def _crisis_wordlist_definitions() -> list[tuple[str, int, str]]:
    """扫描 app/ 下形如 crisis_keywords/CRISIS_KEYWORDS 的定义，返回**词表**（list 形态）。

    关键：按**值的真实形态**判定，而不是按节点类型跳过 Dict ——
    crisis_detector 的定义形如
        CRISIS_KEYWORDS: dict[str, list[str]] = {"suicide": [...], ...}
    它的 AST 值节点是 Dict，但 `ast.walk(node)` 会走到 dict 的**值列表**里，
    把分类下的 58 个词全收集成"词表" → 把分类器误判成重复。
    故这里只认"值的顶层就是字符串列表"的定义：即 AnnAssign/Assign 的
    value 若是 List（或 Dict 的值里每个元素都是 List 的分类器，单独判别）。
    """
    found: list[tuple[str, int, str]] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue
        rel = path.relative_to(APP_DIR).as_posix()
        for node in ast.walk(tree):
            value: ast.expr | None = None
            if isinstance(node, ast.AnnAssign):
                value = node.value
            elif (
                isinstance(node, ast.Assign)
                and isinstance(node.value, (ast.List, ast.Dict))
            ):
                value = node.value
            if value is None:
                continue
            names: list[str] = []
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
            elif isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if not any(n in ("crisis_keywords", "CRISIS_KEYWORDS") for n in names):
                continue
            # 只认**顶层字符串列表** = 词表；Dict（分类器）与其它形态一律不算
            if not isinstance(value, ast.List):
                continue
            if not all(
                isinstance(e, ast.Constant) and isinstance(e.value, str) for e in value.elts
            ):
                continue
            if len(value.elts) < 2:
                continue
            found.append((rel, node.lineno, names[0]))
    return found


class TestCrisisKeywordWordlistSSTO:
    def test_wordlist_defined_only_in_ssot(self) -> None:
        """危机命中词表只能在 Settings（SSOT）里定义一次。"""
        offenders = [
            f"{rel}:{line} ({name})"
            for rel, line, name in _crisis_wordlist_definitions()
            if rel != CRISIS_WORDLIST_SSOT
        ]
        assert not offenders, (
            "以下位置重复定义了危机命中词表（SSOT = "
            f"app/{CRISIS_WORDLIST_SSOT} 的 Settings.crisis_keywords）：\n  "
            + "\n  ".join(offenders)
            + "\n重复定义的词表没有生产消费点，却会在 SSOT 调整时静默漂移。"
            "请删除副本；若确需独立语义，登记进 CLASSIFIER_ALLOWLIST 并写明依据。"
        )

    def test_ssot_actually_still_defines_the_wordlist(self) -> None:
        """分流的前提是 SSOT 本身还在 —— 否则上面那条断言是「零定义即绿」的假闸门。"""
        definitions = _crisis_wordlist_definitions()
        ssot_hits = [d for d in definitions if d[0] == CRISIS_WORDLIST_SSOT]
        assert ssot_hits, (
            f"SSOT（app/{CRISIS_WORDLIST_SSOT}）不再定义危机词表 —— "
            "要么被误删，要么被改成 dict 形态（那是分类器，需另找 SSOT）。"
        )

    def test_classifier_is_still_allowed_and_present(self) -> None:
        """分类器（crisis_detector）必须还在：它是危机检测主路径，不是重复。

        也守住 CLASSIFIER_ALLOWLIST 本身的价值：若分类器被改成 list 词表，
        豁免就失去依据（它会与 Settings 重复），本断言必须能发现。
        """
        for rel in CLASSIFIER_ALLOWLIST:
            path = APP_DIR / rel
            assert path.is_file(), f"{rel} 消失，需重新评估危机检测主路径"
            tree = ast.parse(path.read_text(encoding="utf-8"))
            # 分类器的形态 = `CRISIS_KEYWORDS: dict[...] = {...}`（AnnAssign + Dict）。
            # 不能写 `isinstance(node, ast.Dict) and node.targets` —— Dict 节点
            # 本身没有 targets 属性（那是 Assign 节点的），会在运行时 AttributeError。
            has_dict_form = any(
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "CRISIS_KEYWORDS"
                and isinstance(node.value, ast.Dict)
                for node in ast.walk(tree)
            )
            assert has_dict_form, (
                f"{rel} 的 CRISIS_KEYWORDS 不再是 dict 分类形态 —— "
                "若被改成 list 词表，它就与 Settings 重复，"
                "CLASSIFIER_ALLOWLIST 的豁免失去依据，必须重新评估。"
            )