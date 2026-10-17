"""第三十六批挑簇：location 登记表结构信号的延续（第三十五批同款口径）。

挑簇口径演进（第三十五批第三次换信号后本批为第四次使用同一信号）：
- 第三十三批「basename 零记载」：第三十四批初耗尽，且**反向失效**
  （短名被文档别处同名串命中 ⇒ 假负）。
- 第三十四批「函数名级零记载」：**彻底退化**（25 个候选函数名在三份审计
  文档全文命中数全为 0 —— 文档只按 location 登记、不按函数名登记）。
- 第三十五批起「**location 登记表零收录**」：候选文件从未出现在任何
  `| \`a.b.c\` | \`path/x.py\` |` 登记表行里，再减去历批已处理簇 +
  逐簇人工核对 ⇒ 命中 8 文件 8 条（第三十五批全部裁定不接）。

本批（第三十六批）排除集：
  E1 location 登记表文件（三份审计文档的 `| a.b.c | path/x.py |` 行，
     即 W 桶已接线点所在文件）；
  E2 三份审计文档（P2_11 / P2_12 / P2_13）全部「一之XX」批章节与附录中
     登记过的候选文件（路径规范化：剥掉 `app/` 前缀；裸 basename 按
     basename 匹配——宁可多排，不可重复挑已裁簇）；
  E3 scan 结果中已接线的候选（except 体内有 record_silent_degradation）。

产物：`tests/tools/pick_p2_35_batch36_result.json`（粗排候选，仍须逐簇人工核对）。
"""

from __future__ import annotations

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

# location 登记表行：| `a.b.c` | `path/x.py` |
LOCATION_ROW = re.compile(r"^\|\s*`[a-zA-Z0-9_.]+`\s*\|\s*`([a-zA-Z0-9_/]+\.py)`\s*\|")
# 文档中出现的 py 路径（反引号包裹，允许 `path/x.py:228` 带行号形式——
# 第三十五批起的裁定表用「路径:行号」登记，不剥行号会漏排已处理文件）
PY_PATH = re.compile(r"`([a-zA-Z0-9_/]+\.py)(?::\d+)?`")


def load(modname: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(modname, TOOLS / f"{modname}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def norm(path: str) -> str:
    """规范化到相对 app/ 的 key；裸 basename 原样返回（调用方按 basename 再匹配）。"""
    p = path.replace("\\", "/")
    if p.startswith("app/"):
        return p[len("app/") :]
    if p.startswith("backend/app/"):
        return p[len("backend/app/") :]
    return p


def collect_excluded() -> tuple[set[str], set[str], dict[str, int]]:
    """返回 (全路径排除集, basename 排除集, 每个来源的命中计数)。"""
    full: set[str] = set()
    base: set[str] = set()
    hits: dict[str, int] = {}

    for doc in AUDIT_DOCS:
        if not doc.exists():
            continue
        text = doc.read_text(encoding="utf-8")
        n_loc = 0
        n_path = 0
        for ln in text.splitlines():
            m = LOCATION_ROW.match(ln)
            if m:
                full.add(norm(m.group(1)))
                n_loc += 1
                continue
            # 只在「一之XX」批章节与附录区域里收 py 路径，避免把测试文件/
            # 工具脚本路径误当业务文件（它们本来也排不进 app/ 候选池，无实害，
            # 但收进来会让排除集膨胀难核对）
            for pm in PY_PATH.finditer(ln):
                raw = pm.group(1)
                if raw.startswith(("tests/", "backend/", "unit/", "contract/")):
                    continue
                k = norm(raw)
                if "/" in k:
                    full.add(k)
                else:
                    base.add(k)
                n_path += 1
        hits[doc.name] = n_loc + n_path

    return full, base, hits


def main() -> int:
    scan = load("scan_p2_35_batch6")
    scan.main()  # 重跑 scan 落盘，保证不是陈旧快照
    result = json.loads(
        (TOOLS / "scan_p2_35_batch6_result.json").read_text(encoding="utf-8")
    )

    full, base, hits = collect_excluded()
    print("=" * 78)
    print("第三十六批挑簇（location 登记表零收录 + 文档已登记排除）")
    print("=" * 78)
    for name, n in hits.items():
        print(f"  {name}: 登记行/路径命中 {n}")
    print(f"  排除集：全路径 {len(full)} 个，裸 basename {len(base)} 个")

    candidates: dict[str, list[dict]] = {}
    excluded_files: dict[str, str] = {}
    for rec in result["real_list"] + result["probe_list"]:
        if rec["wired"]:
            continue
        rel = rec["file"]  # app/ 相对路径
        app_rel = rel[len("app/") :] if rel.startswith("app/") else rel
        bn = pathlib.PurePosixPath(app_rel).name
        if app_rel in full:
            excluded_files[rel] = "location/文档全路径登记"
            continue
        if bn in base:
            excluded_files[rel] = f"文档 basename 登记({bn})"
            continue
        candidates.setdefault(rel, []).append(
            {
                "line": rec["line"],
                "handled": rec["handled"],
                "fire_and_forget": rec["fire_and_forget"],
                "returns": rec["returns"],
            }
        )

    print("-" * 78)
    print(f"排除文件 {len(excluded_files)} 个；剩余候选文件 {len(candidates)} 个：")
    for f in sorted(candidates):
        print(f"  {len(candidates[f]):3d}  {f}")

    out = TOOLS / "pick_p2_35_batch36_result.json"
    out.write_text(
        json.dumps(
            {
                "excluded_full": sorted(full),
                "excluded_base": sorted(base),
                "excluded_files": excluded_files,
                "candidates": candidates,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"落盘: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
