#!/usr/bin/env python
"""ROUND_42 OTel 配置面真实性闸门变异验证（结果见同名 _result.log）。

纪律：字节快照 + try/finally 还原（禁 git checkout --）；变异与测试不并发；
每个变异都必须被 p2_65 真实杀死，恢复后闸门必须回绿、sha 必须一致。

臂清单（≥6）：
M1 开关分支恒假化（关闭配置仍继续装配）
M2 开关分支恒真化（开启配置也被跳过）
M3 关闭路径仍置 _otel_initialized=True（跳过伪装成已初始化）
M4 资源属性解析结果被丢弃（配置值不进 Resource.create）
M5 畸形资源属性改抛异常（配置问题升级成 FAILED）
M6 main 不再透传 settings.otel_enabled
M7 .env.example 的 OTEL_ENABLED 登记行被删
M8 关闭路径返回 OK（未启用伪装成成功）
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
T = "tests/test_p2_65_round42_otel_config_truthfulness.py"

OTEL = BACKEND / "app" / "core" / "otel.py"
MAIN = BACKEND / "app" / "main.py"
ENV_EXAMPLE = BACKEND / ".env.example"

MUTATIONS: list[tuple[str, Path, str, str, list[str]]] = [
    (
        "M1 开关分支恒假化（enabled=False 仍继续装配）",
        OTEL,
        "    if not enabled:\n",
        "    if False:  # MUTATION\n",
        [T],
    ),
    (
        "M2 开关分支恒真化（enabled=True 也被跳过）",
        OTEL,
        "    if not enabled:\n",
        "    if True:  # MUTATION\n",
        [T],
    ),
    (
        "M3 关闭路径仍置 _otel_initialized=True",
        OTEL,
        '''            "(otel_enabled=False)"
        )
        return OtelInit.SKIPPED
''',
        '''            "(otel_enabled=False)"
        )
        _otel_initialized = True
        return OtelInit.SKIPPED
''',
        [T],
    ),
    (
        "M4 资源属性解析结果被丢弃",
        OTEL,
        "        resource_attrs.update(_parse_resource_attributes(resource_attributes))\n",
        "",
        [T],
    ),
    (
        "M5 畸形资源属性改抛异常",
        OTEL,
        """            continue
        attrs[key] = value.strip()
""",
        """            raise ValueError("bad resource attribute")
        attrs[key] = value.strip()
""",
        [T],
    ),
    (
        "M6 main 不再透传 settings.otel_enabled",
        MAIN,
        "        enabled=settings.otel_enabled,\n",
        "        enabled=True,\n",
        [T],
    ),
    (
        "M7 .env.example 的 OTEL_ENABLED 登记行被删",
        ENV_EXAMPLE,
        "# OTEL_ENABLED=false\n",
        "",
        [T],
    ),
    (
        "M8 关闭路径返回 OK（未启用伪装成成功）",
        OTEL,
        '''            "(otel_enabled=False)"
        )
        return OtelInit.SKIPPED
''',
        '''            "(otel_enabled=False)"
        )
        return OtelInit.OK
''',
        [T],
    ),
]


def run_pytest(node_ids: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        [str(PY), "-m", "pytest", *node_ids,
         "-o", "addopts=--strict-markers --import-mode=importlib",
         "-p", "no:cacheprovider", "-q", "--no-header", "--tb=no",
         "--basetemp=.pytest_tmp_r42mut"],
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
            "mutate_round42_otel_config_truthfulness_result.log"
        ).write_text(report + "\n", encoding="utf-8")
        print(report)
        return 1

    for name, path, old, new, targets in MUTATIONS:
        original = path.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        text = original.decode("utf-8")
        # 工作区是 CRLF：多行模式两种换行都要试
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
        "mutate_round42_otel_config_truthfulness_result.log"
    ).write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
