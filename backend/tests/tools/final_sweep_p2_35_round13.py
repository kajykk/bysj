"""第十三轮 #35 终局扫描：scan 全量未接线候选里，还有哪些**从未被逐条登记**。

口径演进到第五代（条目级零记载）：
- 文件级 location 登记表零收录（第三十五/三十六批）：第37批跑出 0 候选
  ⇒ 文件级信号耗尽。但「文件被登记过」不等于「该文件的每条 except 都
  裁定过」——本工具按 (文件, 行号) 条目级核对：
  对 scan 的每个未接线候选，在三份审计文档全文找以下任一登记形态：
    a) `path/x.py:行号`（第三十五批起裁定表的带行号登记）；
    b) 文档裁定格式「文件 L号(函数名)」中的 `文件` + `L号` 同段共现；
    c) 该 handler 所属函数的函数名与文件 basename 同段共现。
  三条都查不到 ⇒ 从未登记 ⇒ 真·剩余未决。

产物：`tests/tools/final_sweep_p2_35_round13_result.json`。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import pathlib
import re
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
TOOLS = BACKEND / "tests" / "tools"
DOCS = REPO / "docs"

AUDIT_DOCS = [
    DOCS / "P2_11_ROUND11_AUDIT.md",
    DOCS / "P2_12_ROUND12_AUDIT.md",
    DOCS / "P2_13_ROUND13_AUDIT.md",
]


def load(modname: str):
    spec = importlib.util.spec_from_file_location(modname, TOOLS / f"{modname}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def enclosing_func(tree: ast.AST, line: int) -> str | None:
    best: tuple[int, str] | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= line <= (node.end_lineno or node.lineno):
                if best is None or node.lineno > best[0]:
                    best = (node.lineno, node.name)
    return best[1] if best else None


def main() -> int:
    scan = load("scan_p2_35_batch6")
    scan.main()
    result = json.loads(
        (TOOLS / "scan_p2_35_batch6_result.json").read_text(encoding="utf-8")
    )

    # 三份文档全文（按行保留，用于「同段共现」判定：行内或相邻 3 行内）
    doc_lines: dict[str, list[str]] = {}
    for doc in AUDIT_DOCS:
        doc_lines[doc.name] = doc.read_text(encoding="utf-8").splitlines()

    def registered(rel: str, line: int, fn_name: str | None) -> str | None:
        """返回登记形态描述；None = 从未登记。

        已知登记格式（历批演进，逐批都不同，故多形态全查）：
          a) `path/x.py:行号`（第三十五批起裁定表带行号登记）；
          b) 「文件 L号(函数名)」同行（P2_11 早期裁定格式）；
          c) 「| L号 | `函数名` |」表格行（第二十四批 ws 簇格式：行号独立成列）；
          d) 「| location | `文件` `函数名` |」表格行（第十六批起格式）；
          e) `L号` 所在行 ±5 行内出现 basename 或函数名（跨行宽容）。
        """
        base = pathlib.PurePosixPath(rel).name
        pat_line = re.compile(
            rf"(?:^|[\s`(]){re.escape(base)}:{line}(?:[\s`),.]|$)"
        )
        pat_ll = re.compile(rf"{re.escape(base)}\s+L{line}\b")
        pat_lonly = re.compile(rf"(?:^|[\s`|(])L{line}(?:[\s`|),.、（(]|$)")
        pat_fn = re.compile(rf"\b{re.escape(fn_name)}\b") if fn_name else None
        for name, lines in doc_lines.items():
            for i, ln in enumerate(lines):
                if pat_line.search(ln) or pat_ll.search(ln):
                    return f"{name}:L{i + 1}(路径:行号)"
                # c/d：表格行内 L号 或 basename，与函数名同行共现
                if pat_fn and pat_fn.search(ln) and (
                    base in ln or pat_lonly.search(ln)
                ):
                    return f"{name}:L{i + 1}(表格行共现)"
                # d：location 表格行（basename + 函数名同行，无行号）
                if pat_fn and pat_fn.search(ln) and base in ln:
                    return f"{name}:L{i + 1}(函数名+basename共现)"
                # e：±5 行宽容（L号 独立成列、basename 在节标题的格式）
                window = lines[max(0, i - 5) : i + 6]
                wtext = "\n".join(window)
                if pat_lonly.search(ln) and (
                    base in wtext or (pat_fn and pat_fn.search(wtext))
                ):
                    return f"{name}:L{i + 1}(相邻共现)"
        return None

    never: list[dict] = []
    wired = 0
    for rec in result["real_list"] + result["probe_list"]:
        if rec["wired"]:
            wired += 1
            continue
        rel = rec["file"]
        line = rec["line"]
        try:
            src = (BACKEND / rel).read_text(encoding="utf-8")
            tree = ast.parse(src)
        except Exception:
            continue
        fn_name = enclosing_func(tree, line)
        if registered(rel, line, fn_name) is None:
            never.append(
                {
                    "file": rel,
                    "line": line,
                    "func": fn_name,
                    "handled": rec["handled"],
                    "returns": rec["returns"],
                }
            )

    print("=" * 78)
    print("第十三轮 #35 终局扫描（条目级零记载）")
    print("=" * 78)
    print(f"scan 候选总数（真降级+探针）：{len(result['real_list']) + len(result['probe_list'])}")
    print(f"  已接线：{wired}")
    print(f"  未接线且**从未被逐条登记**：{len(never)}")
    print("-" * 78)
    by_file: dict[str, int] = {}
    for n in never:
        by_file[n["file"]] = by_file.get(n["file"], 0) + 1
    for f, c in sorted(by_file.items(), key=lambda x: -x[1]):
        print(f"  {c:3d}  {f}")
    out = TOOLS / "final_sweep_p2_35_round13_result.json"
    out.write_text(
        json.dumps({"never_registered": never}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    print(f"落盘: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
