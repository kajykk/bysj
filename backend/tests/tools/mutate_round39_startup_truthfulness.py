#!/usr/bin/env python
"""ROUND_39 启动自检真实性闸门变异验证（结果见同名 _result.log）。

纪律：字节快照 + try/finally 还原（禁 git checkout --）；变异与测试不并发；
每个新闸门必须有一次真实的「红 → 恢复绿」。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
T = "tests/test_p2_63_round39_startup_truthfulness.py"


def run_pytest(node_ids: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        [str(PY), "-m", "pytest", *node_ids,
         "-o", "addopts=--strict-markers --import-mode=importlib",
         "-p", "no:cacheprovider", "-q", "--no-header", "--tb=no"],
        cwd=str(BACKEND), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def summarize(out: str) -> str:
    keep = []
    for line in out.splitlines():
        s = line.strip()
        if any(k in s for k in ("passed", "failed", "AssertionError")):
            keep.append(s[:140])
    return "\n".join(keep[:5]) or "(无关键行)"


SS = BACKEND / "app" / "core" / "startup_status.py"
SENTRY = BACKEND / "app" / "core" / "sentry.py"
MAIN = BACKEND / "app" / "main.py"

MUTATIONS: list[tuple[str, Path, str, str, list[str]]] = [
    (
        "M1 同步包装器忽略 SKIPPED 哨兵（回到一律 ok）",
        SS,
        '        result = func()\n'
        '        duration_ms = (time.monotonic() - start) * 1000\n'
        '        status = "skipped" if isinstance(result, SkippedStep) else "ok"',
        '        result = func()\n'
        '        duration_ms = (time.monotonic() - start) * 1000\n'
        '        status = "ok"',
        [T],
    ),
    (
        "M2 异步包装器忽略 SKIPPED 哨兵",
        SS,
        '        result = await coro\n'
        '        duration_ms = (time.monotonic() - start) * 1000\n'
        '        status = "skipped" if isinstance(result, SkippedStep) else "ok"',
        '        result = await coro\n'
        '        duration_ms = (time.monotonic() - start) * 1000\n'
        '        status = "ok"',
        [T],
    ),
    (
        "M3 未配置 DSN 时谎报已初始化（return True）",
        SENTRY,
        '        logger.warning("SENTRY_DSN not set, skipping Sentry initialization")\n'
        '        return False',
        '        logger.warning("SENTRY_DSN not set, skipping Sentry initialization")\n'
        '        return True',
        [T],
    ),
    (
        "M4 SDK 不可用时谎报已初始化（return True）",
        SENTRY,
        '        logger.warning("sentry_sdk not available, skipping Sentry initialization")\n'
        '        return False',
        '        logger.warning("sentry_sdk not available, skipping Sentry initialization")\n'
        '        return True',
        [T],
    ),
    (
        "M5 成功初始化谎报未初始化（return False）",
        SENTRY,
        '        traces_sample_rate,\n    )\n    return True',
        '        traces_sample_rate,\n    )\n    return False',
        [T],
    ),
    (
        "M6 main 丢弃未初始化信号（回到 None 常态）",
        MAIN,
        '    return None if initialized else SKIPPED',
        '    return None',
        [T],
    ),
    (
        "M7 main 一律记为 skipped（成功也被吞）",
        MAIN,
        '    return None if initialized else SKIPPED',
        '    return SKIPPED',
        [T],
    ),
    (
        "M8 lifespan 把 init_sentry 改成 fatal=True（truthful 化变成阻断启动）",
        MAIN,
        'record_step_sync("init_sentry", _init_sentry, fatal=False)',
        'record_step_sync("init_sentry", _init_sentry, fatal=True)',
        [T],
    ),
]


def main() -> int:
    log: list[str] = []
    failures = 0

    rc, out = run_pytest([T])
    log.append("=== 基线（未变异，必须绿） ===")
    log.append(f"exit = {rc}")
    log.append(summarize(out))
    if rc != 0:
        log.append("!!! 基线就红，后续变异结论无效")
        Path(__file__).with_name("mutate_round39_startup_truthfulness_result.log").write_text(
            "\n".join(log) + "\n", encoding="utf-8")
        print("\n".join(log))
        return 1

    for name, path, old, new, targets in MUTATIONS:
        original = path.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        text = original.decode("utf-8")
        # 工作区可能因 core.autocrlf 是 CRLF：多行模式两种换行都要试
        variants = [(old, new)]
        if "\n" in old:
            variants.append((old.replace("\n", "\r\n"), new.replace("\n", "\r\n")))
        picked = next(((o, n) for o, n in variants if text.count(o) == 1), None)
        log.append(f"\n=== {name} ===")
        log.append(
            f"target = {path.relative_to(BACKEND).as_posix()} | 命中 = "
            f"{1 if picked else 0}"
        )
        if picked is None:
            log.append("SKIP：替换点不唯一或未命中，变异无效")
            failures += 1
            continue
        matched_old, matched_new = picked
        try:
            path.write_bytes(text.replace(matched_old, matched_new, 1).encode("utf-8"))
            rc, out = run_pytest(targets)
            log.append(f"exit = {rc}（期望非 0 = RED）")
            log.append(summarize(out))
            if rc == 0:
                log.append("!!! 变异未被杀死：闸门失效")
                failures += 1
            else:
                log.append("OK：变异被杀死（RED）")
        finally:
            path.write_bytes(original)
            ok = hashlib.sha256(path.read_bytes()).hexdigest() == digest
            log.append(f"还原 sha 一致 = {ok}")
            if not ok:
                failures += 1

    rc, out = run_pytest([T])
    log.append("\n=== 恢复后 GREEN 对照 ===")
    log.append(f"exit = {rc}（期望 0）")
    log.append(summarize(out))
    if rc != 0:
        failures += 1

    log.append(f"\n===== 结论：{'全部通过' if failures == 0 else f'{failures} 项异常'} =====")
    report = "\n".join(log)
    print(report)
    Path(__file__).with_name("mutate_round39_startup_truthfulness_result.log").write_text(
        report + "\n", encoding="utf-8")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
