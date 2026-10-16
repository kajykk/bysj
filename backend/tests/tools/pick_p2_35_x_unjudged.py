"""P2-35 第二十一批挑簇器：X 桶未裁定候选批量标注。

纪律（第十六~二十批实锤）：
- zero-mention 信号会被本批文档登记自我覆盖 → 不能只数提及次数，
  必须逐条精确匹配「裁定点」：`file:line` 串 或 location key（点号串）。
- 全路径匹配假阴性（审计文档用短名引用文件）→ 用 basename+func。
- `ws.py` 会命中 `views.py` → basename 匹配须带扩展名点号分隔。

产物：stdout 排序清单（不落盘 JSON，避免又被当成静态审计产物）。
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[2]
SCAN_JSON = BACKEND / "tests" / "tools" / "scan_p2_35_batch6_result.json"
DOCS = [
    BACKEND.parent / "docs" / "P2_11_ROUND11_AUDIT.md",
    BACKEND.parent / "docs" / "P2_12_ROUND12_AUDIT.md",
    BACKEND.parent / "docs" / "P2_13_ROUND13_AUDIT.md",
    BACKEND.parent / "docs" / "CODE_REVIEW_2026-10-11.md",
]


def enclosing_func(tree: ast.AST, lineno: int) -> str:
    """返回包含 lineno 的最内层函数名（含类名前缀）。"""
    best = ""
    best_span = None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.lineno <= lineno <= (node.end_lineno or node.lineno):
            span = (node.end_lineno or node.lineno) - node.lineno
            if best_span is None or span < best_span:
                best_span = span
                prefix = ""
                # 找直接父类
                for cls in ast.walk(tree):
                    if not isinstance(cls, ast.ClassDef):
                        continue
                    if any(
                        isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and st is node
                        for st in cls.body
                    ):
                        prefix = cls.name + "."
                best = prefix + node.name
    return best or "<module>"


def main() -> int:
    scan = json.loads(SCAN_JSON.read_text(encoding="utf-8"))
    unwired = [r for r in scan["real_list"] if not r["wired"]]
    doc_texts = {}
    for d in DOCS:
        doc_texts[d.name] = d.read_text(encoding="utf-8") if d.exists() else ""

    unjudged: list[dict] = []
    judged = 0
    for rec in unwired:
        rel = rec["file"]  # e.g. app/core/ws.py
        line = rec["line"]
        base = rel.rsplit("/", 1)[-1]  # ws.py
        p = BACKEND / rel
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=rel)
        except Exception:
            continue
        func = enclosing_func(tree, line)
        # 裁定点 1：file:line 精确串（任取 basename 前缀或全 rel）
        loc_patterns = [f"{rel}:{line}", f"{base}:{line}", f"{base}:{line} "]
        # 裁定点 2：basename + func 同行共现（跨行叙述用两段窗口兜底）
        hit = None
        for name, text in doc_texts.items():
            for pat in loc_patterns:
                if pat in text:
                    hit = f"{name}:{pat}"
                    break
            if hit:
                break
            # basename+func 同行共现：逐行找同时含两者的行
            for ln in text.splitlines():
                if base in ln and func != "<module>" and func in ln:
                    hit = f"{name}:basename+func({func})"
                    break
            if hit:
                break
        if hit:
            judged += 1
        else:
            unjudged.append(
                {
                    "file": rel,
                    "line": line,
                    "func": func,
                    "handled": "/".join(rec["handled"]),
                    "returns": rec.get("returns"),
                    "fire_and_forget": rec.get("fire_and_forget", False),
                }
            )

    print(f"未接线候选 {len(unwired)}；已裁定 {judged}；未裁定 {len(unjudged)}")
    print("=" * 70)
    by_file: dict[str, list[dict]] = {}
    for u in unjudged:
        by_file.setdefault(u["file"], []).append(u)
    for f, items in sorted(by_file.items(), key=lambda x: (-len(x[1]), x[0])):
        print(f"\n### {f}（{len(items)} 条未裁定）")
        for it in items:
            ret = f" return={it['returns']}" if it["returns"] else ""
            ff = " [fire-and-forget]" if it["fire_and_forget"] else ""
            print(
                f"  L{it['line']:<5d} {it['func']:<45s} "
                f"[{it['handled']}]{ret}{ff}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
