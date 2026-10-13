"""实测 #32 SSOT 重复现状（机制扫描，不靠目测）。

对报告 #32 列出的 7 类逐一定义判据，输出带文件+行号+片段的清单。
判定为「真重复」的条件是**内容集合相同**（可 re-export），
而非「有重叠词」（crisis_detector 与 config 有交集但职责不同，不能合并）。
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend" / "src"
OUT = BACKEND.parent / "docs" / "P2_32_SSOT_DEDUP_AUDIT.md"


@dataclass
class Finding:
    category: str
    file: str
    line: int
    detail: str
    segment: str


@dataclass
class Category:
    name: str
    title: str
    verdict: str = ""
    notes: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


def _py_sources(root: Path) -> list[Path]:
    return [p for p in sorted(root.rglob("*.py")) if "__pycache__" not in p.parts]


def _ts_vue_sources(root: Path) -> list[Path]:
    exts = {".ts", ".vue"}
    return [
        p
        for p in sorted(root.rglob("*"))
        if p.suffix in exts and "node_modules" not in p.parts and p.is_file()
    ]


def _segment(lines: list[str], lineno: int, width: int = 110) -> str:
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1].strip()[:width]
    return ""


# ── 类别 1：危机词表（字面同一性才判真重复）───────────────────────────────
def scan_crisis_keywords() -> Category:
    cat = Category("crisis_keywords", "危机词表")
    tables: dict[str, list[str]] = {}
    for path in _py_sources(BACKEND / "app"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            # 两种赋值形态都要认：模块级 Assign（crisis_detector 的
            # CRISIS_KEYWORDS = {...}）与 Pydantic 字段的 AnnAssign
            # （config.Settings 里 crisis_keywords: list[str] = [...]）。
            # 只认 Assign 会把 Settings 里的那份漏掉 → 假否定。
            names: list[str] = []
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
            if not names:
                continue
            if not any("crisis_keywords" in n or "CRISIS_KEYWORDS" in n for n in names):
                continue
            values = []
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    values.append(sub.value)
            if not values:
                continue
            rel = path.relative_to(BACKEND).as_posix()
            key = f"{rel}:{node.lineno}"
            tables[key] = values
            cat.findings.append(
                Finding(
                    "crisis_keywords",
                    rel,
                    node.lineno,
                    f"{len(values)} 词：{', '.join(values[:6])}…",
                    _segment(lines, node.lineno),
                )
            )
    # 内容集合相同 → 可 re-export
    groups: dict[frozenset[str], list[str]] = {}
    for key, values in tables.items():
        groups.setdefault(frozenset(values), []).append(key)
    for members in groups.values():
        if len(members) > 1:
            cat.notes.append(
                "**字面完全相同**（可 re-export）：" + " ≡ ".join(f"`{m}`" for m in members)
            )
    distinct = {frozenset(v) for v in tables.values()}
    cat.verdict = (
        f"{len(tables)} 处定义 / {len(distinct)} 种内容；"
        f"{sum(1 for m in groups.values() if len(m) > 1)} 组完全相同"
    )
    return cat


# ── 类别 2：风险等级标签 ────────────────────────────────────────────────
# 判据不能只认「≥2 个字符串字面量」：RISK_LEVEL_MAP 是 dict[int, str]
# （键为 int），risk_thresholds 的等级则是 dict[str, int]（键为字符串等级名）。
# 两种形态都要认，否则会把唯一的 SSOT（contracts.RISK_LEVEL_MAP）漏掉。
RISK_LEVEL_RE = re.compile(
    r"""^(none|low|medium|high|critical|mild|moderate|severe|unknown)$"""
)


def scan_risk_levels() -> Category:
    cat = Category("risk_levels", "风险等级标签")
    for path in _py_sources(BACKEND / "app"):
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
            lines = text.splitlines()
        except (OSError, SyntaxError):
            continue
        rel = path.relative_to(BACKEND).as_posix()
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
            if not names:
                continue
            name = names[0]
            if not re.search(r"risk_level|severity|level_map", name, re.I):
                continue
            # 两种形态：值是等级名（str），或键是等级名（dict 的 key）
            values = {
                s.value
                for s in ast.walk(node)
                if isinstance(s, ast.Constant) and isinstance(s.value, str)
            }
            levels = sorted(v for v in values if RISK_LEVEL_RE.match(v))
            if len(levels) < 2:
                continue
            cat.findings.append(
                Finding(
                    "risk_levels",
                    rel,
                    node.lineno,
                    f"{name}：{levels}",
                    _segment(lines, node.lineno),
                )
            )
    vocab: dict[str, list[Finding]] = {}
    for f in cat.findings:
        m = re.search(r"\[([^\]]*)\]", f.detail)
        key = m.group(1) if m else f.detail
        vocab.setdefault(key, []).append(f)
    for key, items in vocab.items():
        if len(items) > 1:
            cat.notes.append(
                f"**同一套等级词表 {len(items)} 份定义**："
                + ", ".join(f"`{i.file}:{i.line}`" for i in items)
            )
    cat.verdict = f"{len(cat.findings)} 处等级集合定义 / {len(vocab)} 种词表"
    return cat


# ── 类别 3：文件名清洗 ──────────────────────────────────────────────────
FILENAME_SANITIZE_RE = re.compile(
    r"def\s+(_?\w*(sanitize|clean|safe)\w*filename\w*)\s*\(|"
    r"^[A-Z_]*FILENAME[A-Z_]*\s*[:=]",
    re.M,
)


def scan_filename_sanitize() -> Category:
    cat = Category("filename_sanitize", "文件名清洗")
    for path in _py_sources(BACKEND / "app"):
        try:
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
        except OSError:
            continue
        rel = path.relative_to(BACKEND).as_posix()
        for i, line in enumerate(lines, 1):
            if FILENAME_SANITIZE_RE.search(line):
                cat.findings.append(
                    Finding("filename_sanitize", rel, i, "清洗实现定义处", line.strip()[:110])
                )
    # 用户自述：也统计 Content-Disposition 使用点（可能未清洗）
    for path in _py_sources(BACKEND / "app"):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        rel = path.relative_to(BACKEND).as_posix()
        for i, line in enumerate(lines, 1):
            if "Content-Disposition" in line and "attachment" in line:
                cleaned = "sanitize" in line or "safe" in line or "quoted" in line
                cat.findings.append(
                    Finding(
                        "filename_sanitize",
                        rel,
                        i,
                        "Content-Disposition 使用点："
                        + ("行内见清洗痕迹" if cleaned else "**行内无清洗痕迹**"),
                        line.strip()[:110],
                    )
                )
    cat.verdict = f"{len(cat.findings)} 处（清洗定义 + Content-Disposition 使用点）"
    return cat


# ── 类别 4：CSV 转义（前端）─────────────────────────────────────────────
# 判据分两级：
#   定义级 = `function sanitizeCellForExcel` / `dangerousPrefixes = [...]`
#             （自己实现了转义规则 → 重复）
#   使用级 = 调用 sanitizeCellForExcel 或重复实现引号转义链
# 先前把 `.map((cell) => \`"${sanitizeCellForExcel(...)}\"\`)` 与测试断言
# 都标成「自行实现」，是噪声：前者正确复用了 SSOT，后者是测试期望值。
CSV_ESCAPE_DEFINE_RE = re.compile(r"function\s+sanitizeCellForExcel|dangerousPrefixes\s*=")
CSV_ESCAPE_USE_RE = re.compile(r"""sanitizeCellForExcel\s*\(|replace\(/"/g, '""'\)""")


def scan_csv_escape() -> Category:
    cat = Category("csv_escape", "CSV 转义")
    for path in _ts_vue_sources(FRONTEND):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(FRONTEND.parent).as_posix()
        is_test = ".test." in path.name or ".spec." in path.name
        for i, line in enumerate(lines, 1):
            defines = bool(CSV_ESCAPE_DEFINE_RE.search(line))
            uses = bool(CSV_ESCAPE_USE_RE.search(line))
            if not (defines or uses):
                continue
            if is_test:
                detail = "测试断言/期望值（非重复点）"
            elif defines:
                detail = "**转义规则定义**（SSOT 本体）" if "exportUtils" in rel else (
                    "**自行实现转义规则**（绕过 SSOT）"
                )
            elif "exportUtils" in line and "import" in line:
                detail = "调用 SSOT（import）"
            elif "exportUtils" in rel:
                detail = "SSOT 内部调用"
            else:
                detail = "**内联重复转义链**（绕过 SSOT）"
            cat.findings.append(
                Finding("csv_escape", rel, i, detail, line.strip()[:110])
            )
    dup = [f for f in cat.findings if "绕过" in f.detail]
    cat.notes.append(
        f"绕过 SSOT 的重复点：{len(dup)} 处（测试文件不计入）"
    )
    cat.verdict = f"{len(cat.findings)} 处引用 / {len(dup)} 处绕过 SSOT"
    return cat


# ── 类别 5：Blob 下载 ───────────────────────────────────────────────────
DOWNLOAD_ANCHOR_RE = re.compile(r"document\.createElement\(['\"]a['\"]\)")


def _is_test_file(path: Path) -> bool:
    """测试文件不是生产重复点。

    闸门测试自身必然含`document.createElement('a')` 这类字面量（判据字符串
    与反例样例），把它计入「绕过 SSOT」是噪声 —— 实测会把 3 处残留全部
    报成生产问题，而生产代码其实只剩 SSOT 一处。
    """
    return ".test." in path.name or ".spec." in path.name


def scan_blob_download() -> Category:
    cat = Category("blob_download", "Blob 下载")
    variants: dict[str, list[Finding]] = {}
    for path in _ts_vue_sources(FRONTEND):
        if _is_test_file(path):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(FRONTEND.parent).as_posix()
        text = "\n".join(lines)
        if not DOWNLOAD_ANCHOR_RE.search(text):
            continue
        is_ssot = path.name == "exportUtils.ts"
        for i, line in enumerate(lines, 1):
            if not DOWNLOAD_ANCHOR_RE.search(line):
                continue
            # 判定范围 = **所在函数/方法体**。
            # 向上：找最近一个缩进更小的非空行（函数头或外层块）；
            # 向下：从函数头的缩进起，直到出现缩进更小且非续行的行。
            # 不能用固定行窗口（会跨到邻近函数，把别人的 revoke 算进来），
            # 也不能只按本行缩进截断（`a.href = url` 与锚点同缩进，会立刻截断成 1 行）。
            indent = len(line) - len(line.lstrip())
            start = i - 1
            while start > 0:
                prev = lines[start - 1]
                if not prev.strip():
                    start -= 1
                    continue
                if len(prev) - len(prev.lstrip()) < indent:
                    break
                start -= 1
            head_indent = len(lines[start]) - len(lines[start].lstrip())
            end = i
            for nxt in lines[i:]:
                if not nxt.strip():
                    end += 1
                    continue
                nxt_indent = len(nxt) - len(nxt.lstrip())
                if nxt_indent < head_indent:
                    break
                if nxt_indent == head_indent and nxt.strip().startswith(
                    ("}", ")", "]", "},", ");", "},")
                ):
                    break
                end += 1
            block_text = "\n".join(lines[start:end])
            if "setTimeout" in block_text and "revokeObjectURL" in block_text:
                variant = "延迟 revoke（setTimeout）"
            elif "revokeObjectURL" in block_text:
                variant = "同步 revoke（M-29 缺陷复现）"
            else:
                variant = "无 revoke"
            f = Finding(
                "blob_download",
                rel,
                i,
                variant + ("（SSOT 本体）" if is_ssot else "（绕过 SSOT）"),
                line.strip()[:110],
            )
            cat.findings.append(f)
            variants.setdefault(variant, []).append(f)
    for variant, items in sorted(variants.items()):
        cat.notes.append(f"{variant}：{len(items)} 处")
    sync = variants.get("同步 revoke（M-29 缺陷复现）", [])
    if sync:
        cat.notes.append(
            "**M-29 修复漏网的同步 revoke 位置**："
            + ", ".join(f"`{f.file}:{f.line}`" for f in sync)
        )
    cat.verdict = f"{len(cat.findings)} 处下载链路 / {len(variants)} 种变体"
    return cat


# ── 类别 6：角色定义 ────────────────────────────────────────────────────
ROLE_RE = re.compile(r"""["'](super_admin|platform_admin|admin|counselor|user|teacher|parent)["']""")


def scan_roles() -> Category:
    cat = Category("roles", "角色定义")
    for path in _ts_vue_sources(FRONTEND):
        try:
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(FRONTEND.parent).as_posix()
        for i, line in enumerate(lines, 1):
            if re.search(r"\b(isAdmin\w*|isStaff\w*)\s*[=(]|(isAdmin|isStaff)\s*=>", line):
                cat.findings.append(
                    Finding("roles", rel, i, "前端角色判定函数", line.strip()[:110])
                )
    # 后端角色：判据不能只认 RoleStr/RoleEnum/class Role —— 实际的 SSOT 是
    # contracts.py 里的 USER_ROLE_* 模块常量 + USER_ROLES 集合，
    # 只认类/别名形态会把唯一 SSOT 漏掉 → 假否定。
    for path in _py_sources(BACKEND / "app"):
        try:
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
        except OSError:
            continue
        rel = path.relative_to(BACKEND).as_posix()
        for i, line in enumerate(lines, 1):
            if re.search(r"^\s*(USER_ROLE_|ROLE_)[A-Z_]+\s*(:|=)", line):
                cat.findings.append(
                    Finding("roles", rel, i, "后端角色常量定义", line.strip()[:110])
                )
    # 裸字面量角色（inline 未走常量）—— 真正的重复点
    for path in _py_sources(BACKEND / "app"):
        try:
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
        except OSError:
            continue
        rel = path.relative_to(BACKEND).as_posix()
        for i, line in enumerate(lines, 1):
            if re.search(r"""["'](super_admin|counselor)["']""", line) and not re.search(
                r"USER_ROLE_|#", line
            ):
                cat.findings.append(
                    Finding("roles", rel, i, "**裸字面量角色**（未走常量）", line.strip()[:110])
                )
    cat.verdict = f"{len(cat.findings)} 处"
    return cat


# ── 类别 7：模型元数据 ──────────────────────────────────────────────────
MODEL_META_RE = re.compile(r"model_version|MODEL_VERSION|default_model|DEFAULT_MODEL")


def scan_model_meta() -> Category:
    cat = Category("model_meta", "模型元数据")
    for root, kind in ((BACKEND / "app", "backend"), (FRONTEND, "frontend")):
        paths = (
            _py_sources(root)
            if kind == "backend"
            else _ts_vue_sources(root)
        )
        for path in paths:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            rel = path.relative_to(BACKEND.parent).as_posix()
            for i, line in enumerate(lines, 1):
                if MODEL_META_RE.search(line):
                    cat.findings.append(
                        Finding("model_meta", rel, i, "模型元数据引用", line.strip()[:110])
                    )
    cat.verdict = f"{len(cat.findings)} 处引用"
    return cat


def render(cats: list[Category]) -> str:
    lines = [
        "# P2-32 SSOT 重复现状全仓审计清单",
        "",
        f"- 生成时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
        "- 方法：机制扫描（AST / 正则判据），不靠目测。判定「真重复」的标准是",
        "  **内容集合完全相同**（可 re-export），仅「有重叠词」不算重复 ——",
        "  `crisis_detector` 与 `config.crisis_keywords` 有交集但职责不同",
        "  （前者是 6 分类危机分类器，后者是布尔命中词表），不能合并。",
        "",
        "## 本轮改动前后对照",
        "",
        "| 类目 | 改前 | 改后 | 处置 |",
        "|---|---|---|---|",
        "| Blob 下载 | 14 处链路 / 2 种变体（**4 处同步 revoke**） | **1 处 / 1 种变体** | "
        "建 `exportUtils.downloadBlob()` SSOT，11 处改调|",
        "| 危机词表 | 5 处 / **1 组字面完全相同** | 4 处 / 0 组 | "
        "删除 `inference.CRISIS_KEYWORDS`（实测无生产消费点的死副本）|",
        "",
        "剩余类目（风险等级 / 文件名清洗 / CSV 转义 / 角色 / 模型元数据）本轮**只审计不改**，",
        "理由见各类目结论与文末局限说明。",
        "",
        "## 汇总",
        "",
        "| 类目 | 结论 |",
        "|---|---|",
    ]
    for c in cats:
        lines.append(f"| {c.title} | {c.verdict} |")
    for c in cats:
        lines += [
            "",
            f"## {c.title}（`{c.name}`）",
            "",
            f"**结论**：{c.verdict}",
            "",
        ]
        for n in c.notes:
            lines.append(f"- {n}")
        if c.notes:
            lines.append("")
        if not c.findings:
            lines.append("（扫描未发现相关实现）")
            continue
        lines += [
            "| 位置 | 说明 | 证据（源码行） |",
            "|---|---|---|",
        ]
        for f in sorted(c.findings, key=lambda x: (x.file, x.line)):
            seg = f.segment.replace("|", "\\|")
            lines.append(f"| `{f.file}:{f.line}` | {f.detail} | `{seg}` |")
    lines += [
        "",
        "## 已知局限（如实记账）",
        "",
        "1. 风险等级 / 角色 / 模型元数据三类只扫描**定义处**与字面量出现，",
        "   不做语义等价判定（如 `mild/moderate` 与 `low/medium` 是否同义需",
        "   业务确认，不属机械可判范围）。",
        "2. 类别 2/6/7 的 verdict 是「发现数量」而非「重复数量」—— 真正需要",
        "   re-export 的子集需人工判定后写进本文件第X 节，闸门按该子集把守。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    cats = [
        scan_crisis_keywords(),
        scan_risk_levels(),
        scan_filename_sanitize(),
        scan_csv_escape(),
        scan_blob_download(),
        scan_roles(),
        scan_model_meta(),
    ]
    OUT.write_text(render(cats), encoding="utf-8")
    print("类目:", len(cats))
    for c in cats:
        print(f"  {c.name}: {c.verdict}")
    print("清单已落盘:", OUT)


if __name__ == "__main__":
    main()