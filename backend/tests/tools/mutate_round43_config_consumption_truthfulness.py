#!/usr/bin/env python
"""ROUND_43 配置消费真实性闸门变异验证（结果见同名 _result.log）。

纪律：字节快照 + try/finally 还原（禁 git checkout --）；变异与测试不并发；
每个变异都必须被 p2_66 真实杀死，恢复后闸门必须回绿、sha 必须一致。

臂清单（9）：
M1 predict_lite 长度阈值重新硬编码 20
M2 覆盖率路由重新硬编码 0.80
M3 路由层 lite 长度重新硬编码 20
M4 覆盖率比较反转（>= 改 <）
M5 predict_lite 长度比较反转（< 改 >）
M6 预留项开始被消费（豁免清单变成过期）
M7 docstring 退回「窗口内推理样本」
M8 配置注释删掉「预留项」
M9 新增一个零消费 Settings 字段（棘轮必须发现）
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
T = "tests/test_p2_66_round43_config_consumption_truthfulness.py"

PREDICT = BACKEND / "app" / "core" / "model_engine" / "predict.py"
INFERENCE = BACKEND / "app" / "core" / "model_engine" / "inference.py"
SHADOW = BACKEND / "app" / "services" / "shadow_comparison_service.py"
CONFIG = BACKEND / "app" / "core" / "config.py"

MUTATIONS: list[tuple[str, Path, str, str, list[str]]] = [
    (
        "M1 predict_lite 长度阈值重新硬编码 20",
        PREDICT,
        "            if length < settings.route_lite_min_text_length:\n",
        "            if length < 20:  # MUTATION\n",
        [T],
    ),
    (
        "M2 覆盖率路由重新硬编码 0.80",
        INFERENCE,
        "        if f_coverage >= settings.route_feature_coverage_threshold:\n",
        "        if f_coverage >= 0.80:  # MUTATION\n",
        [T],
    ),
    (
        "M3 路由层 lite 长度重新硬编码 20",
        INFERENCE,
        """        if (
            gad7 is not None
            and transcript
            and len(str(transcript)) >= settings.route_lite_min_text_length
        ):
""",
        "        if gad7 is not None and transcript and len(str(transcript)) >= 20:  # MUTATION\n",
        [T],
    ),
    (
        "M4 覆盖率比较反转（>= 改 <）",
        INFERENCE,
        "        if f_coverage >= settings.route_feature_coverage_threshold:\n",
        "        if f_coverage < settings.route_feature_coverage_threshold:\n",
        [T],
    ),
    (
        "M5 predict_lite 长度比较反转（< 改 >）",
        PREDICT,
        "            if length < settings.route_lite_min_text_length:\n",
        "            if length > settings.route_lite_min_text_length:\n",
        [T],
    ),
    (
        "M6 预留项开始被消费（豁免清单过期）",
        SHADOW,
        """        from app.core.config import settings

        health = self.get_health(model_id)
""",
        """        from app.core.config import settings

        _window = settings.registry_auto_rollback_window_seconds
        health = self.get_health(model_id)
""",
        [T],
    ),
    (
        "M7 docstring 退回「窗口内推理样本」",
        SHADOW,
        "        条件: 进程内累计推理样本 >= min_samples 且回退率 > max_fallback_rate.\n",
        "        条件: 窗口内推理样本 >= min_samples 且回退率 > max_fallback_rate.\n",
        [T],
    ),
    (
        "M8 配置注释删掉「预留项」",
        CONFIG,
        "    # 预留项：评估时间窗口 (秒)。当前实现为进程内累计计数\n",
        "    # 评估时间窗口 (秒)。当前实现为进程内累计计数\n",
        [T],
    ),
    (
        "M9 新增零消费 Settings 字段",
        CONFIG,
        "    route_lite_min_text_length: int = 20\n",
        "    route_lite_min_text_length: int = 20\n    round43_mutation_dead_field: int = 0  # MUTATION\n",
        [T],
    ),
]


def run_pytest(node_ids: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        [str(PY), "-m", "pytest", *node_ids,
         "-o", "addopts=--strict-markers --import-mode=importlib",
         "-p", "no:cacheprovider", "-q", "--no-header", "--tb=no",
         "--basetemp=.pytest_tmp_r43mut"],
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
            "mutate_round43_config_consumption_truthfulness_result.log"
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
        "mutate_round43_config_consumption_truthfulness_result.log"
    ).write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
