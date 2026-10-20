"""ROUND_22 / T4 变异见证：改坏文档里的一个数字，数字闸门必须指名报错。

判据不是"变红就算过"——而是**红在正确的地方**：失败信息里必须出现对应的
检查编号（如 `[readme.buckets]`），否则说明闸门是靠别的检查顺带红的。

三处变异分别覆盖两类探针：
- T1/T3 走 ``probe``（现场复算：桶计数、扫描入口数）；
- T2 走 ``report``（跨文档对齐：泄漏红利在你的概览层写错一个末位）。

每处变异都先存字节快照，``finally`` 还原；收尾比对字节一致、再跑一次全绿。
日志同时写 stdout 与 ``mutate_p2_46_round22_result.log``。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
README = REPO / "README.md"
SUMMARY = REPO / "docs" / "EVALUATION_TRUST_SUMMARY.md"
LOG = Path(__file__).resolve().parent / "mutate_p2_46_round22_result.log"
TARGET = "tests/test_p2_46_round22_portfolio_docs.py::test_portfolio_numbers_match_repo_artifacts"

CASES = (
    (
        "T1",
        README,
        "**341 处 except 候选**全部裁定：已接线 109",
        "**342 处 except 候选**全部裁定：已接线 109",
        "readme.buckets",
        "probe 类：桶计数由 classify 产物钉住（锚点含 ** 强调符，见 §七.3 的踩坑）",
    ),
    (
        "T2",
        SUMMARY,
        "ΔF1 +0.3111 / ΔAUC +0.1573",
        "ΔF1 +0.3111 / ΔAUC +0.1574",
        "summary.delta_f1",
        "report 类：跨文档对齐，末位改一位也必须红",
    ),
    (
        "T3",
        README,
        "88 处划分与挑优调用点",
        "188 处划分与挑优调用点",
        "readme.scan",
        "probe 类：扫描入口数现场复算",
    ),
)

_lines: list[str] = []


def log(msg: str = "") -> None:
    print(msg, flush=True)
    _lines.append(msg)


def run_gate() -> tuple[int, str]:
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
            TARGET,
        ],
        cwd=str(BACKEND),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    log("=" * 72)
    log("ROUND_22 T4 数字自检闸门 —— 真实变异验证")
    log("闸门：tests/test_p2_46_round22_portfolio_docs.py（5 条）")
    log("=" * 72)

    snapshots = {path: path.read_bytes() for path in {case[1] for case in CASES}}
    results: dict[str, str] = {}

    try:
        for cid, path, old, new, expect_cid, why in CASES:
            log()
            log(f"[{cid}] {path.name}：{old!r} → {new!r}")
            log(f"     强度：强（{why}）")

            text = snapshots[path].decode("utf-8")
            if text.count(old) != 1:
                log(f"[{cid}] ✗ 锚点不唯一（出现 {text.count(old)} 次），变异无效")
                results[cid] = "ANCHOR-BAD"
                continue

            try:
                path.write_text(text.replace(old, new), encoding="utf-8")
                code, out = run_gate()
                targeted = f"[{expect_cid}]" in out
                if code == 0:
                    log(f"[{cid}] ✗ 假绿：改坏了数字闸门仍然通过")
                    results[cid] = "FALSE-GREEN"
                elif not targeted:
                    log(f"[{cid}] ✗ 红了但不是这一条（没出现 {expect_cid}），判据过弱")
                    results[cid] = "WRONG-TARGET"
                else:
                    log(f"[{cid}] ✓ 变异后变红，且指名 {expect_cid}")
                    results[cid] = "RED-OK"
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

    final_code, final_out = run_gate()
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
