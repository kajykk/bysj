#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P2-33 余量迁移器：手写 `OperationLog(...)` → `record_audit(...)`。

设计（为什么半自动而不是全自动）：
- `OperationLog(...)` 的关键字参数名与 `record_audit` **不同**
  （`operator_id` → `actor_id`、`action_type` → `action`、`detail=str` → `detail=dict`），
  且各处 `detail` 形态不一（f-string / json.dumps / 裸串）。全自动映射必然出错。
- 故本脚本只做**机械可判定的部分**：定位调用点、抽取各实参、生成目标代码，
  再由人工确认 `tenant_id` / `request` 两个必须逐点决策的参数。
- `record_audit` 硬约束（`app/core/audit.py`）：`tenant_id` 必填关键字、`ip_address`
  一律从 request 经 `get_real_client_ip` 取、无 request 则 `request=None` +
  detail 注 `no_request`。

用法：
    python scripts/migrate_operation_log.py --dry-run     # 只打印不写
    python scripts/migrate_operation_log.py --file app/services/xxx.py
"""
from __future__ import annotations

import argparse
import ast
import re
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]

# 参数名映射：OperationLog → record_audit
KW_MAP = {
    "operator_id": "actor_id",
    "operator_role": "actor_role",
    "action_type": "action",
    "target_type": "target_type",
    "target_id": "target_id",
}


def unparse(node: ast.AST) -> str:
    return ast.unparse(node)


def extract_detail(node: ast.Call) -> tuple[str, bool]:
    """抽 detail 实参，返回 (源码, 是否为 dict 字面量)。"""
    for kw in node.keywords:
        if kw.arg == "detail":
            return unparse(kw.value), isinstance(kw.value, (ast.Dict, ast.DictComp))
    return "None", True


def gen_record_audit(call: ast.Call, indent: str, *, tenant_src: str, has_request: bool,
                     tenant_note: str = "") -> str:
    args: list[str] = []
    for kw in call.keywords:
        if kw.arg in KW_MAP:
            args.append(f"{KW_MAP[kw.arg]}={unparse(kw.value)}")
        elif kw.arg == "detail":
            src, is_dict = extract_detail(call)
            if is_dict:
                args.append(f"detail={src}")
            else:
                # 非 dict：包一层，保证 record_audit 的 json.dumps 契约
                args.append(f'detail={{"raw": {src}}}')
        elif kw.arg == "ip_address":
            continue  # record_audit 禁止手填 ip
        # 其余未知参数原样透传（宁可显式失败也不静默丢弃）
        else:
            args.append(f"{kw.arg}={unparse(kw.value)}")
    args.append(f"tenant_id={tenant_src}")
    args.append("request=request" if has_request else "request=None")
    inner = "".join(f"{indent}    {a},\n" for a in args)
    return (
        f"{indent}await record_audit(\n{indent}    self.db,\n"
        f"{tenant_note}{inner}{indent})"
    )


def process(path: pathlib.Path, *, dry: bool) -> int:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and (getattr(n.func, "id", None) or getattr(n.func, "attr", None)) == "OperationLog"
    ]
    if not calls:
        return 0

    lines = src.splitlines(keepends=True)
    # 自后向前替换，避免行号漂移
    edits: list[tuple[int, int, str]] = []
    for c in calls:
        # 找所在函数，判断有无 request 参数 / self.db
        fn = None
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if n.lineno <= c.lineno <= (n.end_lineno or n.lineno):
                    fn = n
        if fn is None:
            print(f"  ! {path.name}:{c.lineno} 不在任何函数内，跳过", file=sys.stderr)
            continue
        params = [a.arg for a in fn.args.args + fn.args.kwonlyargs]
        has_request = "request" in params
        is_method = bool(fn.args.args and fn.args.args[0].arg in ("self", "cls"))
        indent = " " * (c.col_offset)

        # tenant_src：有 current_user 用 current_user.tenant_id；
        # 无登录态的调用点一律 None（平台级），并把"租户来源缺失"作为**独立事实**返回，
        # 由人工决定是否需要从业务对象推导 —— 不在生成代码里塞注释（注释会吞掉行尾逗号）。
        tenant_note = ""
        if "current_user" in params:
            tenant_src = "current_user.tenant_id"
        else:
            tenant_src = "None"
            tenant_note = (
                f"{indent}# TODO(人工): 本调用点无登录态，tenant_id 记 None（平台级）；"
                f"若业务上应归属某租户，需从业务对象推导后再改。\n"
            )

        # record_audit 第一个位置参数是 db；方法内用 self.db，函数内用 db
        db_src = "self.db" if is_method and "self" in params else "db"
        gen = gen_record_audit(c, indent, tenant_src=tenant_src, has_request=has_request,
                               tenant_note=tenant_note)
        gen = gen.replace("await record_audit(\n", f"await record_audit(\n", 1)
        gen = gen.replace(f"{indent})", f"{indent})", 1)
        # 把 db 实参插到第一位
        gen = gen.replace(
            f"{indent}await record_audit(\n{indent}    ",
            f"{indent}await record_audit(\n{indent}    {db_src},\n{indent}    ",
            1,
        )
        # 赋值形式 `x = OperationLog(...)`：record_audit 返回同一个模型对象，
        # 故改写成 `x = await record_audit(...)`，保持后续 `db.add(x)` 不变。
        stmt = lines[c.lineno - 1]
        assign = None
        prefix = stmt[: c.col_offset]
        m_assign = re.match(r"^(\s*)([A-Za-z_]\w*)\s*=\s*$", prefix)
        if m_assign and not prefix.strip().startswith(("return", "await", "raise")):
            assign = m_assign.group(2)
            gen = gen.replace(
                f"{indent}await record_audit(",
                f"{indent}{assign} = await record_audit(",
                1,
            )

        start = c.lineno - 1
        end = (c.end_lineno or c.lineno) - 1
        edits.append((start, end + 1, gen))

    for start, end, gen in sorted(edits, reverse=True):
        lines[start:end] = [gen]

    out = "".join(lines)
    # 补 import（必须对**替换后**的文本重新 parse 定位；用原文行号会插错位置）
    if "from app.core.audit import record_audit" not in out:
        tree2 = ast.parse(out)  # 顺带自检：生成代码必须可解析
        last = 0
        for node in tree2.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                last = max(last, node.end_lineno or node.lineno)
        ls = out.splitlines(keepends=True)
        ls.insert(last, "from app.core.audit import record_audit\n")
        out = "".join(ls)
        ast.parse(out)  # 再次自检

    if dry:
        print(f"[dry-run] {path.name}: {len(edits)} 处待迁移")
        for s, e, _ in sorted(edits):
            print(f"    L{s+1}-{e}")
        return len(edits)
    path.write_text(out, encoding="utf-8")
    print(f"{path.name}: 迁移 {len(edits)} 处")
    return len(edits)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", action="append", default=[])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all-remaining", action="store_true")
    a = ap.parse_args()

    files = [BACKEND / f for f in a.file]
    if a.all_remaining:
        files = sorted((BACKEND / "app").rglob("*.py"))
        files = [f for f in files if "__pycache__" not in f.parts]

    total = 0
    for f in files:
        try:
            total += process(f, dry=a.dry_run)
        except SyntaxError as exc:
            print(f"  ! {f.name} 语法错误，跳过: {exc}", file=sys.stderr)
    print(f"合计 {total} 处")
    return 0


if __name__ == "__main__":
    sys.exit(main())
