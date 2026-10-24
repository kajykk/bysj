#!/usr/bin/env python
"""ROUND_40 OTel 启动自检真实性闸门变异验证（结果见同名 _result.log）。

纪律：字节快照 + try/finally 还原（禁 git checkout --）；变异与测试不并发；
每个变异都必须被 p2_64 真实杀死，恢复后闸门必须回绿。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
T = "tests/test_p2_64_round40_otel_startup_truthfulness.py"

OTEL = BACKEND / "app" / "core" / "otel.py"
MAIN = BACKEND / "app" / "main.py"

MUTATIONS: list[tuple[str, Path, str, str, list[str]]] = [
    (
        "M1 main 丢弃 FAILED（最终 raise 改成 return None → 一律 ok）",
        MAIN,
        '''    raise OTelInitError(
        f"OpenTelemetry configured but initialization failed (state={state!r})"
    )
''',
        """    return None
""",
        [T],
    ),
    (
        "M2 main 把 SKIPPED 映射成 ok（哨兵被吞）",
        MAIN,
        """    if state is OtelInit.SKIPPED:
        return SKIPPED
""",
        """    if state is OtelInit.SKIPPED:
        return None
""",
        [T],
    ),
    (
        "M3 init_otel 装配异常路径返回 OK",
        OTEL,
        """            exc_info=True,
        )
        return OtelInit.FAILED
""",
        """            exc_info=True,
        )
        return OtelInit.OK
""",
        [T],
    ),
    (
        "M4 空 endpoint 返回 OK（未配置伪装成成功）",
        OTEL,
        '''            "distributed tracing disabled"
        )
        return OtelInit.SKIPPED
''',
        '''            "distributed tracing disabled"
        )
        return OtelInit.OK
''',
        [T],
    ),
    (
        "M5 依赖不可导入返回 OK",
        OTEL,
        '''            "pip install opentelemetry-distro opentelemetry-exporter-otlp"
        )
        return OtelInit.SKIPPED
''',
        '''            "pip install opentelemetry-distro opentelemetry-exporter-otlp"
        )
        return OtelInit.OK
''',
        [T],
    ),
    (
        "M6 失败路径返回 SKIPPED（失败伪装成未启用）",
        OTEL,
        """            exc_info=True,
        )
        return OtelInit.FAILED
""",
        """            exc_info=True,
        )
        return OtelInit.SKIPPED
""",
        [T],
    ),
    (
        "M7 成功路径返回 FAILED（反向谎报）",
        OTEL,
        """        _instrument_redis()

        return OtelInit.OK
""",
        """        _instrument_redis()

        return OtelInit.FAILED
""",
        [T],
    ),
    (
        "M8 lifespan 把 init_otel 改成 fatal=True（truthful 化变成阻断启动）",
        MAIN,
        'record_step_sync("init_otel", _init_otel, fatal=False)',
        'record_step_sync("init_otel", _init_otel, fatal=True)',
        [T],
    ),
]


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


def main() -> int:
    log: list[str] = []
    failures = 0

    rc, out = run_pytest([T])
    log.append("=== 基线（未变异，必须绿） ===")
    log.append(f"exit = {rc}")
    log.append(summarize(out))
    if rc != 0:
        log.append("!!! 基线就红，后续变异结论无效")
        report = "\n".join(log)
        Path(__file__).with_name(
            "mutate_round40_otel_startup_truthfulness_result.log"
        ).write_text(report + "\n", encoding="utf-8")
        print(report)
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
    Path(__file__).with_name(
        "mutate_round40_otel_startup_truthfulness_result.log"
    ).write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
