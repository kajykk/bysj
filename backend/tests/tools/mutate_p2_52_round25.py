#!/usr/bin/env python
"""ROUND_25（L13 脚本处置 + 未入库含凭证脚本记账闸门）变异见证：四组。

M1  把口令字面量塞回**已入库**的 scripts/login_admin.py
    → 结构扫描 test_scripts_have_no_hardcoded_passwords_or_tokens 红
      （证明入库后 CI 真能看见这类回归——23b 时该文件不入库、CI 看不见）
M2  在 KNOWN_UNTRACKED_CREDENTIAL_SCRIPTS 里伪造一条指向不存在文件的条目
    → 方向 2（防腐烂）test_registry_has_no_stale_entries 红（本机形态）
M3  **反向臂**：git add -f 把已登记的未入库脚本 check_tabular_v2.py 强推进库
    （模拟 A2 完成但忘同步清单）
    → 本机形态：方向 2 红（清单 ⊋ 实测）；CI 形态（CI=true）：方向 2 的
      「登记项不得指向已入库文件」分支红。两种形态都指名同一用例
M4  新建一个未入库却消费凭证的脚本 scripts/_mutant_new_cred.py
    → 方向 1 test_no_unregistered_credential_script 红
      （本轮闸门存在的核心理由：CI 看不见的含凭证脚本必须在 push 前现形）

纪律（继承 ROUND_23a / ROUND_24）：
- 只翻转实现/数据、没翻转断言真值空间的变异不上场（四组均翻转真值）；
- 字节快照 + try/finally 还原；M3 另用 git rm --cached 还原索引；
- 末尾 residual-clean（逐文件回比快照）+ 还原后全绿（final-green）；
- 变异与测试**禁并发**（SQLite 争用会造假失败）——单独跑本脚本。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
GATE = "tests/test_p2_49_round23b_secret_scan.py"
PYTHON = sys.executable

LOGIN_ADMIN = REPO / "scripts" / "login_admin.py"
GATE_FILE = BACKEND / GATE
CHECK_TABULAR_V2 = REPO / "scripts" / "check_tabular_v2.py"
MUTANT_NEW = REPO / "scripts" / "_mutant_new_cred.py"

LOG_PATH = Path(__file__).with_name("mutate_p2_52_round25_result.log")
_log_lines: list[str] = []


def log(msg: str = "") -> None:
    print(msg)
    _log_lines.append(msg)


def run_tests(env_ci: bool = False) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ)
    if env_ci:
        env["CI"] = "true"
    else:
        env.pop("CI", None)
    return subprocess.run(
        [
            PYTHON,
            "-m",
            "pytest",
            GATE,
            "-o",
            "addopts=--strict-markers --import-mode=importlib",
            "-p",
            "no:cacheprovider",
            "-q",
        ],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=900,
        env=env,
    )


def test_count(path: Path) -> int:
    src = path.read_text(encoding="utf-8")
    return len(re.findall(r"^\s+(?:async )?def (test_[A-Za-z0-9_]+)", src, re.M))


MUTATIONS = [
    {
        "id": "M1",
        "desc": "口令字面量塞回已入库脚本 login_admin.py",
        "kind": "text",
        "file": LOGIN_ADMIN,
        "old": 'USERNAME = os.environ.get("BYSJ_ADMIN_USERNAME")\n',
        "new": (
            'USERNAME = os.environ.get("BYSJ_ADMIN_USERNAME")\n'
            'PASSWORD = "MutantPassw0rd!"  # MUTATION M1\n'
        ),
        "expect": "red",
        "target": "test_scripts_have_no_hardcoded_passwords_or_tokens",
        "expect_msg": "MutantPassw0rd!",
    },
    {
        "id": "M2",
        "desc": "登记簿伪造一条指向不存在文件的条目",
        "kind": "text",
        "file": GATE_FILE,
        "old": "KNOWN_UNTRACKED_CREDENTIAL_SCRIPTS: dict[str, str] = {\n",
        "new": (
            "KNOWN_UNTRACKED_CREDENTIAL_SCRIPTS: dict[str, str] = {\n"
            '    "scripts/__mutant_ghost__.py": "MUTATION M2 伪造条目",\n'
        ),
        "expect": "red",
        "target": "test_registry_has_no_stale_entries",
        "expect_msg": "__mutant_ghost__",
    },
    {
        "id": "M3",
        "desc": "反向臂：已登记未入库脚本被强推进库（模拟 A2 完成忘同步清单）",
        "kind": "git-add",
        "file": CHECK_TABULAR_V2,
        "expect": "red",
        "target": "test_registry_has_no_stale_entries",
        "expect_msg": "check_tabular_v2.py",
        "both_forms": True,
    },
    {
        "id": "M4",
        "desc": "新建未入库却消费凭证的脚本",
        "kind": "create",
        "file": MUTANT_NEW,
        "new": (
            '"""MUTATION M4: 未登记的含凭证脚本。"""\n'
            "import os\n"
            'TOKEN = os.environ.get("BYSJ_MUTANT_TOKEN")\n'
        ),
        "expect": "red",
        "target": "test_no_unregistered_credential_script",
        "expect_msg": "_mutant_new_cred.py",
    },
]


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def _apply(m: dict) -> None:
    if m["kind"] == "text":
        text = m["file"].read_text(encoding="utf-8")
        assert text.count(m["old"]) == 1, f"{m['id']} 锚点命中 {text.count(m['old'])} 次"
        m["file"].write_text(text.replace(m["old"], m["new"]), encoding="utf-8")
    elif m["kind"] == "create":
        m["file"].write_text(m["new"], encoding="utf-8")
    elif m["kind"] == "git-add":
        proc = _git("add", "-f", m["file"].relative_to(REPO).as_posix())
        assert proc.returncode == 0, f"{m['id']} git add -f 失败: {proc.stderr}"
    else:  # pragma: no cover
        raise AssertionError(m["kind"])


def _restore(m: dict, original: bytes | None) -> None:
    if m["kind"] == "text":
        assert original is not None
        m["file"].write_bytes(original)
    elif m["kind"] == "create":
        m["file"].unlink(missing_ok=True)
    elif m["kind"] == "git-add":
        _git("rm", "--cached", "--quiet", m["file"].relative_to(REPO).as_posix())


def _check_one(m: dict, env_ci: bool) -> tuple[bool, str]:
    """执行一组变异并判定；返回 (ok, 末行读数)。"""
    original = m["file"].read_bytes() if m["file"].exists() else None
    try:
        _apply(m)
        proc = run_tests(env_ci=env_ci)
        out = proc.stdout + proc.stderr
        last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        if m["expect"] == "red":
            target_hit = m["target"] in out
            msg_hit = m.get("expect_msg", "") in out
            ok = proc.returncode != 0 and target_hit and msg_hit
            form = "CI形态" if env_ci else "本机形态"
            log(
                f"[{m['id']}{'·' + form if m.get('both_forms') else ''}] "
                f"{'RED-OK' if ok else '❌ WRONG-TARGET'}  {m['desc']}"
            )
            log(
                f"       returncode={proc.returncode} target_hit={target_hit} "
                f"msg_hit={msg_hit}；{last}"
            )
            if not ok:
                for line in out.splitlines()[-20:]:
                    log(f"  | {line}")
            return ok, last
        ok = proc.returncode == 0
        log(f"[{m['id']}] {'GREEN-OK' if ok else '❌ 放行臂失效'}  {m['desc']}；{last}")
        return ok, last
    finally:
        _restore(m, original)


def main() -> int:
    log(f"# ROUND_25 变异见证 — {GATE}")
    log(f"# 闸门 collected 用例数 14（ROUND_24 时 10：6+2×2 parametrize；本轮 +4 记账闸门）")
    log("")

    baseline = run_tests()
    log(f"[baseline] returncode={baseline.returncode}")
    if baseline.stdout.strip():
        log(baseline.stdout.strip().splitlines()[-1])
    if baseline.returncode != 0:
        log("[baseline] ❌ 基线非绿，终止（先修实现再变异）")
        LOG_PATH.write_text("\n".join(_log_lines) + "\n", encoding="utf-8")
        return 1

    red_ok = 0
    red_total = 0
    all_ok = True

    for m in MUTATIONS:
        if m["expect"] != "red":
            continue
        red_total += 1
        ok, _ = _check_one(m, env_ci=False)
        all_ok = all_ok and ok
        if ok:
            red_ok += 1
        if m.get("both_forms"):
            ok_ci, _ = _check_one(m, env_ci=True)
            all_ok = all_ok and ok_ci
            if ok_ci:
                red_ok += 1
            red_total += 1

    # ---- 还原核验：逐文件回比字节快照 + 索引/磁盘状态 ----
    residual: list[str] = []
    for m in MUTATIONS:
        p = m["file"]
        if not p.exists():
            if m["kind"] != "create":
                residual.append(f"{p} 丢失")
            continue
        if "MUTATION" in p.read_text(encoding="utf-8"):
            residual.append(str(p))
    tracked = _git("ls-files", "scripts/check_tabular_v2.py").stdout.strip()
    if tracked:
        residual.append("check_tabular_v2.py 仍被 git 跟踪（索引未还原）")
    staged = _git("diff", "--cached", "--numstat", "--", "scripts/check_tabular_v2.py").stdout.strip()
    if staged:
        residual.append(f"check_tabular_v2.py 索引残留: {staged}")

    final = run_tests()
    log("")
    log(f"[final] returncode={final.returncode}")
    if final.stdout.strip():
        log(final.stdout.strip().splitlines()[-1])

    log(f"[residual] {'CLEAN' if not residual else residual}")

    ok = (
        red_ok == red_total
        and not residual
        and final.returncode == 0
    )
    log(
        f"[summary] {red_ok}/{red_total} RED-OK；"
        f"residual_clean={not residual}; final_green={final.returncode == 0}"
    )
    log(f"[exit] {'PASS' if ok else 'FAIL'}")
    LOG_PATH.write_text("\n".join(_log_lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
