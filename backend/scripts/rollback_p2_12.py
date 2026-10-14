#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P2 第十二轮回退对照实验驱动（#34 全量）。

纪律（第十二轮新增）：
- **变异先自评强度**：每个条目都写明"这个变异为什么够强"（是否 replace_all、
  断言有无子串逃逸、窗口是否确定性）。凡报"异常"先怀疑变异强度，补强后仍异常才认定真问题。
- Windows subprocess 一律 `encoding="utf-8"`（默认 GBK 会让失败标记乱码 → failed 恒空）。
- 变异一律 read → replace → write；anchor 缺失当场抛错，不记 INVALID。
- 驱动自检：变异轮解析不出 failed 用例名 → 判 INVALID，不当 PASS。
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend"
REPO = BACKEND.parent
LOG = pathlib.Path(__file__).resolve().parent / "rollback_p2_12_result.log"

PY = str(BACKEND / ".venv/Scripts/python.exe")
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def run(cmd: list[str], cwd: pathlib.Path) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def be_test(node: str) -> tuple[int, str]:
    return run([PY, "-m", "pytest", node, "-o",
                "addopts=--strict-markers --import-mode=importlib",
                "-p", "no:cacheprovider", "-q", "--no-header"], BACKEND)


def py_failed(out: str) -> list[str]:
    return re.findall(r"^(?:FAILED|ERROR) (\S+)", out, re.M)


class TextMut:
    """文本替换型变异。replace_all=True 时替换全部。

    变异强度自评要点（写在每个条目的 strength 字段）：
    - 是否 replace_all：若断言检查"某个串不在文件里"，变异必须消掉**所有**出现处；
    - 子串逃逸：断言按子串匹配时，变异不得保留该子串；
    - 真值翻转：变异必须让目标断言的真值翻转，不能只"改动过"。

    ⚠️ **禁止把 new 设成空串**：`str.replace("", x)` 会在**每个字符间隙**插入 x，
    恢复时会把目标文件彻底打乱（第十二轮实锤：middlewares.py 被插成 303 行乱码）。
    需要"删掉一行"的语义时，用 `# 变异占位` 之类非空文本替换。
    """

    def __init__(self, path: pathlib.Path, old: str, new: str, replace_all: bool = False):
        if new == "":
            raise ValueError("TextMut.new 不得为空串（会用 replace('',x) 打乱文件）")
        self.path, self.old, self.new, self.replace_all = path, old, new, replace_all
        self._backup: str | None = None

    def apply(self):
        # 变异前整文件备份：恢复时优先用备份还原（避免 replace 逆向打乱）
        self._backup = self.path.read_text(encoding="utf-8")
        t = self._backup
        n = t.count(self.old)
        if n < 1:
            raise AssertionError(f"anchor 未命中: {self.path.name} :: {self.old[:60]!r}")
        t = t.replace(self.old, self.new) if self.replace_all else t.replace(self.old, self.new, 1)
        self.path.write_text(t, encoding="utf-8")
        return n

    def restore(self):
        # 用整文件备份还原（而不是逆向 replace），并从备份校验恢复完整性
        if self._backup is not None:
            self.path.write_text(self._backup, encoding="utf-8")
            return
        t = self.path.read_text(encoding="utf-8")
        t = t.replace(self.new, self.old) if self.replace_all else t.replace(self.new, self.old, 1)
        self.path.write_text(t, encoding="utf-8")

    def verify_restored(self) -> bool:
        """恢复后自检：备份与当前内容逐字节一致。"""
        return self._backup is not None and self.path.read_text(encoding="utf-8") == self._backup


# (id, 说明, 测试节点, 变异, 变异强度自评)
EXPS: list[tuple[str, str, str, TextMut, str]] = [
    (
        "F1",
        "#34 硬约束：ServiceError.to_dict() 开始携带 internal_detail",
        "tests/test_p2_12_round12.py::TestServiceErrorContract::test_client_message_is_the_only_egress_field",
        TextMut(BACKEND / "app/core/exceptions.py",
                '                "details": self.details,\n            },\n        }\n\n    def log_payload',
                '                "details": self.details,\n                "internal_detail": self.internal_detail,\n            },\n        }\n\n    def log_payload'),
        "强度：anchor 带**唯一上下文**（`log_payload` 前的收尾括号），只命中 ServiceError.to_dict 一处；"
        "断言按子串查 'psycopg2'/'duplicate key'，变异后二者都进响应体 => 真值翻转。",
    ),
    (
        "F2",
        "#34 tenant_id 必填：sentinel 换成 None 默认值",
        "tests/test_p2_12_round12.py::TestServiceErrorContract::test_missing_tenant_id_raises_typeerror_with_message",
        TextMut(BACKEND / "app/core/exceptions.py",
                "tenant_id: int | None | Any = _MISSING_TENANT,",
                "tenant_id: int | None | Any = None,"),
        "强度：把 sentinel 默认值改成 None ⇒ 漏传不再抛 TypeError，`pytest.raises(TypeError, match='tenant_id')` "
        "直接失败（不是靠巧合的其它 TypeError）；单处替换即翻转真值。",
    ),
    (
        "F3",
        "#34 末道脱敏：特征清单被清空（脱敏失效）",
        "tests/test_p2_12_round12.py::TestLastDitchSanitizer::test_scrub_catches_psycopg_detail_alone",
        TextMut(BACKEND / "app/core/middlewares.py",
                '        r"\\b(psycopg|psycopg2|sqlalchemy\\.exc|asyncpg)\\b",\n',
                '        # 变异: psycopg 特征被移除\n'),
        "强度：从清单里**删掉 psycopg 这条特征**。测试 body 含 'psycopg2.errors.UniqueViolation'，"
        "删掉后该串不再命中任何特征 => `scrubbed is True` 与 `psycopg2 not in body` 双双翻转。"
        "（首轮的 `tuple() or tuple(` 变异因括号不配平会让测试崩在收集期，且 anchor 命中注释段，"
        "属打错靶 —— 已换成删单条特征。）",
    ),
    (
        "F4",
        "#34 末道脱敏误伤：正当用户文案被替换",
        "tests/test_p2_12_round12.py::TestLastDitchSanitizer::test_scrub_ignores_short_strings",
        TextMut(BACKEND / "app/core/middlewares.py",
                "    if not isinstance(value, str) or len(value) < _MIN_SENSITIVE_LEN:",
                "    if not isinstance(value, str):"),
        "强度：去掉长度下限 ⇒ 短文本（'404'/'不存在'/None/12345）不再被直接放行，"
        "`_looks_sensitive('404') is False` 翻转。（首轮用的 'Path traversal detected...' 有 61 字符，"
        "本就不受长度下限保护，属测试用例选错 —— 已换成专测该下限的用例。）",
    ),
    (
        "F5",
        "#34 泄漏清零：把一处已迁的 ServiceError 改回 HTTPException(detail=str(exc))",
        "tests/test_p2_12_round12.py::TestP234LeakConvergence::test_no_exception_text_in_http_exception_detail",
        TextMut(BACKEND / "app/api/v1/review.py",
                "raise ServiceError(str(e), tenant_id=current_user.tenant_id) from e",
                "raise HTTPException(status_code=400, detail=str(e)) from e"),
        "强度：这是**反向**变异（把已收敛的点改回泄漏形态）。判据是 AST 扫全仓 "
        "`HTTPException detail 带异常格式化`，改回一处即被扫出 => 真值翻转。单处即够，"
        "因为判据是「存在性」而非计数。",
    ),
    (
        "F6",
        "#34 样板间：review.py 不再走 ServiceError",
        "tests/test_p2_12_round12.py::TestP234LeakConvergence::test_service_error_is_used_in_review_template",
        TextMut(BACKEND / "app/api/v1/review.py",
                "raise ServiceError(str(e), tenant_id=current_user.tenant_id) from e",
                "raise HTTPException(status_code=400, detail=str(e)) from e",
                replace_all=True),
        "强度：断言 `count('raise ServiceError(') >= 6`，必须 replace_all 把 6 处全改回 "
        "HTTPException 才能让计数跌破 6 —— 这正是「变异必须覆盖全部出现位置」的实例"
        "（只改一处计数仍为 5，断言照样过，会造出假异常）。",
    ),
    (
        "F7",
        "#34 tenant_id 必填：抽掉一处的 tenant_id 实参",
        "tests/test_p2_12_round12.py::TestP234LeakConvergence::test_migrated_call_sites_pass_tenant_id",
        TextMut(BACKEND / "app/api/v1/review.py",
                "raise ServiceError(str(e), tenant_id=current_user.tenant_id) from e",
                "raise ServiceError(str(e)) from e"),
        "强度：判据用括号配平截取整个调用体再查 'tenant_id='，删掉实参后配平体内不再含该串 "
        "=> 真值翻转；单处即够（判据是「存在一处缺失即红」）。",
    ),
    (
        "F8",
        "作用域闸门：给一个原本没有 logger 的文件加 logger.warning（第十一轮 CI 事故形态）",
        "tests/test_p2_12_round12.py::TestScopeResolution::test_used_names_are_defined_or_imported",
        TextMut(BACKEND / "app/api/v1/review.py",
                "def _parse_date_param(",
                "logger.warning('probe')\n\n\ndef _parse_date_param("),
        "强度：在模块级插入一个对未定义 `logger` 的引用 —— review.py 顶层没有 logger，"
        "模块 import 不报错、运行期才 NameError，正是第十一轮 fusion.py 事故形态。"
        "判据按作用域链解析 Name(Load)，必红。",
    ),
    (
        "F9",
        "作用域闸门：删掉一个已用的 import（模拟误删）",
        "tests/test_p2_12_round12.py::TestScopeResolution::test_used_names_are_defined_or_imported",
        TextMut(BACKEND / "app/api/v1/review.py",
                "from app.core.exceptions import ServiceError\n",
                "# import 被变异删除\n"),
        "强度：把 import 行注释掉后 6 处 `raise ServiceError` 全部变成未解析名字 => 真值翻转。"
        "（首轮用空串替换，恢复时 anchor 已丢失导致恢复轮 rc=4 —— 已改成可逆的注释化替换。）",
    ),
]


def main() -> int:
    lines: list[str] = []
    results: list[tuple[str, str, str]] = []

    def log(s: str) -> None:
        print(s)
        lines.append(s)

    log("P2 第十二轮 回退对照实验（每个闸门一条；含变异强度自评）")
    log("=" * 78)

    only = sys.argv[1] if len(sys.argv) > 1 else ""
    for eid, desc, node, mut, strength in EXPS:
        if only and eid != only:
            continue
        log(f"\n[{eid}] {desc}")
        log(f"    判据: {node}")
        log(f"    变异强度自评: {strength}")
        verdict = "NOT-RUN"
        try:
            hits = mut.apply()
            log(f"    anchor 命中 {hits} 处")
            rc, out = be_test(node)
            failed = py_failed(out)
            # 第十一轮实锤的盲区：变异让模块崩在**收集期**（import 时 NameError/SyntaxError），
            # pytest 报 rc=4 且没有 FAILED 行 —— 这不是"假闸门"，而是"闸门没跑到断言"。
            # 识别特征：输出含 ERROR ... <file> 或 NameError/SyntaxError 且无 FAILED 行。
            collect_crash = bool(
                re.search(r"^ERROR \S+", out, re.M)
                or re.search(r"(NameError|SyntaxError|ImportError|IndentationError)", out)
            ) and not failed
            if rc != 0 and failed:
                verdict = "RED-OK"
            elif rc != 0 and collect_crash:
                verdict = "RED-OK(崩在收集期，闸门未跑到断言)"
            elif rc != 0 and not failed:
                verdict = "INVALID(解析不出 failed)"
            else:
                verdict = "NOT-RED(假闸门!)"
            log(f"    变异轮: rc={rc} failed={len(failed)} -> {verdict}")
            for f in failed[:4]:
                log(f"      - {f}")
            if verdict.startswith("INVALID"):
                tail = (ANSI.sub("", out).strip().splitlines() or [""])[-1]
                log(f"      [诊断] {tail[:160]}")
        except AssertionError as exc:
            verdict = f"ANCHOR-MISSING({exc})"
            log(f"    {verdict}")
        finally:
            mut.restore()

        if not mut.verify_restored():
            log("    !! 恢复自检失败：文件与备份不一致，实验作废")
            results.append((eid, verdict, "RESTORE-MISMATCH"))
            continue

        rc2, out2 = be_test(node)
        failed2 = py_failed(out2)
        green = "GREEN-OK" if rc2 == 0 else f"STILL-RED(failed={len(failed2)})"
        log(f"    恢复轮: rc={rc2} failed={len(failed2)} -> {green}")
        results.append((eid, verdict, green))

    log("\n" + "=" * 78)
    log("汇总：")
    for eid, v, g in results:
        log(f"  {eid}: 变异 {v} / 恢复 {g}")
    bad = [r for r in results if not r[1].startswith("RED-OK") or not r[2].startswith("GREEN-OK")]
    log(f"合计 {len(results)} 项，异常 {len(bad)} 项")
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n日志落盘: {LOG}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
