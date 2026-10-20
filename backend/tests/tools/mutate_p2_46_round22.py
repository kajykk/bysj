"""ROUND_22 / T4 变异见证：改坏一处实现，数字闸门必须红在正确的地方。

判据不是"变红就算过"——而是**红在正确的地方**：
- 文档类变异，失败信息里必须出现对应的检查编号（如 `[readme.buckets]`），
  否则说明闸门是靠别的检查顺带红的；
- 实现类变异（T4/T5），必须由**指名的那条用例**失败（隔离用例 / 展开用例），
  而不是别的用例连带报错。

五处变异覆盖四类判据：
- T1/T3 走 ``probe``（现场复算：桶计数、扫描入口数）；
- T2 走 ``report``（跨文档对齐：泄漏红利在概览层写错一个末位）；
- T4 走**测量位置**（把 `probe_routes` 从"子进程数"翻回"进程内数"，
  钉住 2026-10-20 CI 红项不再复发）；
- T5 走**展开契约**（删掉 `_IncludedRouter.original_router` 展开分支，
  钉住 2026-10-21 CI 红项不再复发：fastapi ≥0.151 的 include_router 不再
  扁平化 `app.routes`，不展开就只会数到 main.py 自注册的 5 条）。

每处变异都先存字节快照，``finally`` 还原；收尾比对字节一致、再跑一次全绿。
日志同时写 stdout 与 ``mutate_p2_46_round22_result.log``。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
README = REPO / "README.md"
SUMMARY = REPO / "docs" / "EVALUATION_TRUST_SUMMARY.md"
CHECKER = Path(__file__).resolve().parent / "check_portfolio_numbers.py"
ROUTE_COUNTING = Path(__file__).resolve().parent / "route_counting.py"
LOG = Path(__file__).resolve().parent / "mutate_p2_46_round22_result.log"

GATE = "tests/test_p2_46_round22_portfolio_docs.py"
GATE_FILE = BACKEND / GATE
NUMBERS_TEST = f"{GATE}::test_portfolio_numbers_match_repo_artifacts"
ISOLATION_TEST = f"{GATE}::test_route_probe_isolated_from_in_process_app_state"
EXPANSION_TEST = f"{GATE}::test_route_counting_expands_include_markers"
GATE_TEST_COUNT = len(
    re.findall(r"^def test_", GATE_FILE.read_text(encoding="utf-8"), re.MULTILINE)
)
# 参数化自证会展开成多条用例，故条数以 [final] 行的 passed 数为准，
# 这里只报用例函数数，避免"9 个函数 vs 11 passed"的读数混淆。

CASES = (
    {
        "cid": "T1",
        "path": README,
        "old": "**341 处 except 候选**全部裁定：已接线 109",
        "new": "**342 处 except 候选**全部裁定：已接线 109",
        "target": NUMBERS_TEST,
        "expect": "[readme.buckets]",
        "why": "probe 类：桶计数由 classify 产物钉住（锚点含 ** 强调符，见 §七.3 的踩坑）",
    },
    {
        "cid": "T2",
        "path": SUMMARY,
        "old": "ΔF1 +0.3111 / ΔAUC +0.1573",
        "new": "ΔF1 +0.3111 / ΔAUC +0.1574",
        "target": NUMBERS_TEST,
        "expect": "[summary.delta_f1]",
        "why": "report 类：跨文档对齐，末位改一位也必须红",
    },
    {
        "cid": "T3",
        "path": README,
        "old": "88 处划分与挑优调用点",
        "new": "188 处划分与挑优调用点",
        "target": NUMBERS_TEST,
        "expect": "[readme.scan]",
        "why": "probe 类：扫描入口数现场复算",
    },
    {
        "cid": "T4",
        "path": CHECKER,
        "old": "    measured = _measure_routes_in_child()\n",
        "new": (
            "    from fastapi.routing import APIRoute\n"
            "    from starlette.routing import WebSocketRoute\n"
            "\n"
            "    from app.main import app\n"
            "\n"
            "    measured = {\n"
            '        "rest": sum(1 for r in app.routes if isinstance(r, APIRoute)),\n'
            '        "ws": sum(1 for r in app.routes if isinstance(r, WebSocketRoute)),\n'
            "    }\n"
        ),
        "target": ISOLATION_TEST,
        "expect": "test_route_probe_isolated_from_in_process_app_state",
        "why": (
            "测量位置类：把子进程计数翻回进程内计数，隔离用例必须红"
            "（2026-10-20 CI 实测 5 个 REST 的复发闸门）"
        ),
    },
    {
        "cid": "T5",
        "path": ROUTE_COUNTING,
        "old": '        marker_router = getattr(route, "original_router", None)\n',
        "new": '        marker_router = getattr(route, "_original_router_removed", None)\n',
        "target": EXPANSION_TEST,
        "expect": "test_route_counting_expands_include_markers",
        "why": (
            "展开契约类：删掉 _IncludedRouter.original_router 展开分支，标记形状"
            "用例必须红（2026-10-21 CI 红项复发闸门：fastapi ≥0.151 不展开就只数"
            "得到 main.py 自注册的 5 条）。嵌套/自引用两条合成用例是同源旁证，"
            "本处只跑指名目标，避免与已知的 readme.scale.core 漂移混线"
        ),
    },
)

_lines: list[str] = []


def log(msg: str = "") -> None:
    print(msg, flush=True)
    _lines.append(msg)


def run_gate(target: str) -> tuple[int, str]:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=--strict-markers --import-mode=importlib --ignore=functional_test.py",
            "-p",
            "no:cacheprovider",
            "-q",
            "--tb=short",
            target,
        ],
        cwd=str(BACKEND),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    log("=" * 72)
    log("ROUND_22 T4 数字自检闸门 —— 真实变异验证")
    log(f"闸门：{GATE}（{GATE_TEST_COUNT} 个用例函数；含参数化展开后以 [final] 行为准）")
    log("=" * 72)

    snapshots = {case["path"]: case["path"].read_bytes() for case in CASES}
    results: dict[str, str] = {}

    try:
        for case in CASES:
            cid = case["cid"]
            path = case["path"]
            old = case["old"]
            new = case["new"]
            log()
            log(f"[{cid}] {path.name}：{old.strip()!r} → {new.strip()!r}")
            log(f"     强度：强（{case['why']}）")

            # 用 read_text 而不是 snapshot.decode：前者做换行归一化（CRLF→\n），
            # 否则带换行的锚点（T4）在本机 autocrlf 检出下永远匹配不到。
            text = path.read_text(encoding="utf-8")
            if text.count(old) != 1:
                log(f"[{cid}] ✗ 锚点不唯一（出现 {text.count(old)} 次），变异无效")
                results[cid] = "ANCHOR-BAD"
                continue

            try:
                path.write_text(text.replace(old, new), encoding="utf-8")
                code, out = run_gate(case["target"])
                failed = [
                    line.split(" - ")[0].strip()
                    for line in out.splitlines()
                    if line.startswith("FAILED ")
                ]
                targeted = case["expect"] in out
                if code == 0:
                    log(f"[{cid}] ✗ 假绿：改坏了实现/数字，闸门仍然通过")
                    results[cid] = "FALSE-GREEN"
                elif not targeted:
                    log(f"[{cid}] ✗ 红了但不是这一条（没出现 {case['expect']}），判据过弱")
                    results[cid] = "WRONG-TARGET"
                else:
                    log(f"[{cid}] ✓ 变异后变红，且指名 {case['expect']}")
                    results[cid] = "RED-OK"
                if failed:
                    log(f"     实际失败用例：{failed}")
            finally:
                path.write_bytes(snapshots[path])
                log(f"[{cid}] ✓ 还原（字节一致={path.read_bytes() == snapshots[path]}）")
    finally:
        for path, blob in snapshots.items():
            if path.read_bytes() != blob:  # pragma: no cover - 兜底
                path.write_bytes(blob)

    residual = [str(p.relative_to(REPO)) for p, blob in snapshots.items() if p.read_bytes() != blob]
    log()
    log(f"[residual] 残留文件: {'无' if not residual else residual}")

    final_code, final_out = run_gate(GATE)
    tail = [line for line in final_out.splitlines() if " passed" in line or " failed" in line]
    log(f"[final] 还原后 returncode={final_code}（0=全绿）")
    log(f"[final] {tail[-1].strip() if tail else '<无结论行>'}")

    log()
    log("[summary] " + " | ".join(f"{cid}={res}" for cid, res in results.items()))
    all_red_ok = all(res == "RED-OK" for res in results.values())
    log(f"[summary] residual_clean={not residual} final_green={final_code == 0} all_red_ok={all_red_ok}")

    LOG.write_text("\n".join(_lines) + "\n", encoding="utf-8")
    print(f"\n日志已写入 {LOG.relative_to(REPO)}")
    return 0 if (all_red_ok and not residual and final_code == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
