"""ROUND_17 变异验证：T1 计数与 T2 覆盖闸门都必须被真实变异打红。

用法（backend 目录下）:
    .venv/Scripts/python.exe tests/tools/mutate_p2_41_round17.py

纪律：
- 变异只改实现、不翻转断言真值空间；
- 每个变异 try/finally 还原，收尾做字节级快照比对；
- 先跑基线（未变异全绿）再变异；任何残留即退出码 1。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
T1_GATE = "tests/test_p2_41_round17_tenant_status.py"
T2_GATE = "tests/test_p2_41_round17_auth_gate.py"
LOG = Path(__file__).resolve().parent / "mutate_p2_41_round17_result.log"

TENANT_STATUS = BACKEND_ROOT / "app" / "core" / "tenant_status.py"
AUTH_SERVICE = BACKEND_ROOT / "app" / "services" / "auth_service.py"

LINES: list[str] = []
SNAPSHOTS: dict[Path, bytes] = {}


def log(msg: str) -> None:
    print(msg)
    LINES.append(msg)


def run_gate(*targets: str) -> tuple[int, str]:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *targets,
            "-o",
            "addopts=--strict-markers --import-mode=importlib",
            "-p",
            "no:cacheprovider",
            "-q",
        ],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=900,
    )
    return proc.returncode, proc.stdout


def mutate(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"锚点未命中: {path}: {old[:80]!r}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def restore(path: Path, original: str, mutated: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert mutated in text, f"还原锚点未命中: {path}: {mutated[:80]!r}"
    path.write_text(text.replace(mutated, original, 1), encoding="utf-8")


def red_for(targets: tuple[str, ...], expected: list[str]) -> bool:
    code, out = run_gate(*targets)
    failed = [ln for ln in out.splitlines() if "FAILED" in ln]
    hit = all(any(sub in ln for ln in failed) for sub in expected)
    ok = code != 0 and hit
    log(
        f"    returncode={code} | 失败 {len(failed)} 项 | 目标 {expected}: "
        f"{'RED-OK' if ok else 'UNEXPECTED'}"
    )
    for ln in failed[:4]:
        log(f"      {ln.strip()}")
    if code == 0:
        log("    !!! 假绿：变异后闸门仍全绿")
    return ok


def main() -> None:
    log(f"[head] {subprocess.run(['git','rev-parse','--short','HEAD'], cwd=BACKEND_ROOT.parent, capture_output=True, text=True).stdout.strip()}")
    for path in (TENANT_STATUS, AUTH_SERVICE):
        SNAPSHOTS[path] = path.read_bytes()

    code, out = run_gate(T1_GATE, T2_GATE)
    log(f"[baseline] 未变异 returncode={code}（0=全绿）")
    log(f"[baseline] {out.strip().splitlines()[-1] if out.strip() else ''}")
    assert code == 0, "基线不为绿，先修复再变异"

    results: dict[str, bool] = {}

    # ── T1：删掉缺行降级计数 ───────────────────────────────────────────
    log("\n[T1] tenant_status 缺租户行不再记 silent_degradation")
    t1_old = """        record_silent_degradation(
            "core.tenant_status.missing_tenant", tenant_id=tenant_id
        )
"""
    try:
        mutate(TENANT_STATUS, t1_old, "")
        results["T1"] = red_for(
            (T1_GATE,), ["test_missing_tenant_counts_with_tenant_label"]
        )
    finally:
        # 删除型变异不能用 restore()（mutated 为空串会在文件头插入原块），
        # 直接按字节快照还原 —— 本脚本第一版就踩了这个假残留。
        TENANT_STATUS.write_bytes(SNAPSHOTS[TENANT_STATUS])

    # ── T2a：移除 refresh 入口的封禁校验 ───────────────────────────────
    log("\n[T2a] AuthService.refresh 去掉 is_tenant_suspended 调用")
    t2a_old = '''        # 最长 7 天都"封不住"。
        from app.core.tenant_status import is_tenant_suspended

        if await is_tenant_suspended(
            self.db, user.tenant_id or DEFAULT_TENANT_ID
        ):'''
    t2a_new = '''        # 最长 7 天都"封不住"。
        from app.core.tenant_status import is_tenant_suspended

        if False:  # MUTATION-PROBE'''
    try:
        mutate(AUTH_SERVICE, t2a_old, t2a_new)
        results["T2a"] = red_for(
            (T2_GATE,),
            ["test_enforced_entries_have_ban_check"],
        )
    finally:
        restore(AUTH_SERVICE, t2a_old, t2a_new)

    # ── T2b：新增一个未登记的 token 操作入口 ───────────────────────────
    log("\n[T2b] 新增未登记的 decode_token 入口（发现集应报红）")
    probe = '''

async def _r17_unregistered_auth_probe(token: str):
    from app.core.security import decode_token

    return decode_token(token)
'''
    try:
        original = TENANT_STATUS.read_text(encoding="utf-8")
        TENANT_STATUS.write_text(original + probe, encoding="utf-8")
        results["T2b"] = red_for(
            (T2_GATE,),
            ["test_every_token_operation_function_is_registered"],
        )
    finally:
        text = TENANT_STATUS.read_text(encoding="utf-8")
        assert probe in text, "T2b 还原锚点未命中"
        TENANT_STATUS.write_text(text.replace(probe, "", 1), encoding="utf-8")

    # ── 收尾 ───────────────────────────────────────────────────────────
    log("\n[final] 全部还原后复跑两个门禁")
    code, out = run_gate(T1_GATE, T2_GATE)
    green_ok = code == 0
    log(f"[final] returncode={code} | {out.strip().splitlines()[-1] if out.strip() else ''}")

    log("\n[residual-check] 变异标志串计数（全部应为 0）:")
    markers = [
        (TENANT_STATUS, "MUTATION-PROBE", "T1/T2b 标志串"),
        # T1 是删除型变异：还原后计数调用**本就应该存在**，
        # 不能拿它当残留判据（第一版这样写会恒报 1）。删除型变异由
        # 下方字节级快照比对负责。
        (AUTH_SERVICE, "if False:  # MUTATION-PROBE", "T2a 跳过校验"),
        (TENANT_STATUS, "_r17_unregistered_auth_probe", "T2b 未登记探针"),
    ]
    residual_ok = True
    for path, marker, label in markers:
        cnt = path.read_text(encoding="utf-8").count(marker)
        if cnt:
            residual_ok = False
        log(f"    {'OK ' if cnt == 0 else '!!!'} {label}: {cnt}")

    log("\n[integrity-check] 字节级快照比对（须与变异前完全一致）:")
    integrity_ok = True
    for path, snap in SNAPSHOTS.items():
        same = path.read_bytes() == snap
        if not same:
            integrity_ok = False
        log(f"    {'OK ' if same else '!!!'} {path.name}: {'一致' if same else '不一致（有残留）'}")

    red_count = sum(1 for v in results.values() if v)
    log(
        f"\n[summary] RED-OK {red_count}/{len(results)} | "
        f"final GREEN-OK={green_ok} | residual-clean={residual_ok} | "
        f"integrity-clean={integrity_ok}"
    )
    for k, v in results.items():
        log(f"    {k}: {'RED-OK' if v else '!!! 未红'}")

    LOG.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    print(f"\n[written] {LOG}")
    if red_count != len(results) or not green_ok or not residual_ok or not integrity_ok:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:  # noqa: BLE001
        log(f"\n[ABORT] 脚本异常终止: {type(exc).__name__}: {exc}")
        import traceback

        log(traceback.format_exc())
        LOG.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        print(f"[written] {LOG} (ABORT)")
        raise
