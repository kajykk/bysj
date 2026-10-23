#!/usr/bin/env python
"""ROUND_32 前端闸门变异验证（一次性工具，结果见 mutate_round32_result.log）。

纪律：
- 每个变异项在 try/finally 里用字节快照还原，禁止 git checkout --（工作树有未提交改动）。
- 变异与测试不并发；同一时刻只跑一个 vitest。
- 每个新闸门必须有一次真实的「红 → 恢复绿」，否则不算闸门。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1]
NODE = Path(r"C:\Users\k\.workbuddy\binaries\node\versions\22.22.2-6\node.exe")
VITEST = FRONTEND / "node_modules" / "vitest" / "vitest.mjs"

TOUR = FRONTEND / "src" / "components" / "common" / "OnboardingTour.vue"
GUARD = FRONTEND / "src" / "router" / "guard.ts"
TOUR_TEST = "src/components/common/OnboardingTour.test.ts"
GUARD_TEST = "src/router/guard.test.ts"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_vitest(test_file: str) -> tuple[int, str]:
    proc = subprocess.run(
        [str(NODE), str(VITEST), "run", test_file],
        cwd=str(FRONTEND),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


def summarize(out: str) -> str:
    keep = []
    for line in out.splitlines():
        s = line.strip()
        if any(k in s for k in ("Tests ", "Test Files", "×", "FAIL", "AssertionError")):
            keep.append(s[:160])
    return "\n".join(keep[:12]) or "(无关键行)"


MUTATIONS = [
    (
        "M1 引导步骤绑定退回单向 :current（缺陷原始形态）",
        TOUR,
        'v-model:current="currentStep"',
        ':current="currentStep"',
        TOUR_TEST,
    ),
    (
        "M2 删除根路径重定向（登录后空白壳）",
        GUARD,
        "  if (toPath === '/') return roleVerified ? resolveRoleHome(auth.role) : '/login'",
        "  // [MUTATED] 根路径重定向已移除",
        GUARD_TEST,
    ),
    (
        "M3 根路径重定向去掉 roleVerified 约束（fail-closed 失效）",
        GUARD,
        "if (toPath === '/') return roleVerified ? resolveRoleHome(auth.role) : '/login'",
        "if (toPath === '/') return resolveRoleHome(auth.role)",
        GUARD_TEST,
    ),
]


def main() -> int:
    log: list[str] = []
    failures = 0

    for name, path, old, new, test_file in MUTATIONS:
        original = path.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        text = original.decode("utf-8")
        hits = text.count(old)
        log.append(f"\n=== {name} ===")
        log.append(f"target = {path.relative_to(FRONTEND)} | 命中次数 = {hits}")
        if hits != 1:
            log.append("SKIP：替换点不唯一，变异无效")
            failures += 1
            continue
        try:
            path.write_bytes(text.replace(old, new, 1).encode("utf-8"))
            rc, out = run_vitest(test_file)
            log.append(f"exit = {rc}（期望非 0 = RED）")
            log.append(summarize(out))
            if rc == 0:
                log.append("!!! 变异未被杀死：闸门失效")
                failures += 1
            else:
                log.append("OK：变异被杀死（RED）")
        finally:
            path.write_bytes(original)
            restored = sha(path)
            ok = restored == digest
            log.append(f"还原 sha 一致 = {ok}")
            if not ok:
                failures += 1

    # 恢复后必须回到 GREEN（否则 RED 可能来自环境而非变异）
    for test_file in (TOUR_TEST, GUARD_TEST):
        rc, out = run_vitest(test_file)
        log.append(f"\n=== 恢复后 GREEN 对照：{test_file} ===")
        log.append(f"exit = {rc}（期望 0）")
        log.append(summarize(out))
        if rc != 0:
            failures += 1

    log.append(f"\n===== 结论：{'全部通过' if failures == 0 else f'{failures} 项异常'} =====")
    report = "\n".join(log)
    print(report)

    out_path = Path(__file__).with_name("mutate_round32_result.log")
    out_path.write_text(report + "\n", encoding="utf-8")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
