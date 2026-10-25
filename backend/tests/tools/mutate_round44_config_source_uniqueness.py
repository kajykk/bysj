#!/usr/bin/env python
"""ROUND_44 配置来源唯一性闸门变异验证（结果见同名 _result.log）。

纪律：字节快照 + try/finally 还原（禁 git checkout --）；变异与测试不并发；
每个变异都必须被 p2_67 真实杀死，恢复后闸门必须回绿、sha 必须一致。

臂清单（9）：
M1 predict_structured 恢复 v1.20 兜底（兜底值漂移）
M2 _model_roots 恢复 None 兜底（兜底值漂移）
M3 cache 新增同名字段直读 MODEL_DIR（未登记第二来源）
M4 cache 的 REDIS_URL 改读 REDIS_URL_LEGACY（允许项变过期）
M5 sentry 新增同名直读 SENTRY_ENVIRONMENT（未登记第二来源）
M6 model_cache_maxsize 兜底 20 改 21（兜底值漂移）
M7 main 不再透传 settings.sentry_dsn（库级 env 兜底接管）
M8 cache 不再优先读取 settings.redis_url（兜底前置）
M9 声明默认值 model_dir 改 models2（默认值被挪走）
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
T = "tests/test_p2_67_round44_config_source_uniqueness.py"

PREDICT = BACKEND / "app" / "core" / "model_engine" / "predict.py"
METRICS = BACKEND / "app" / "api" / "v1" / "metrics_helpers.py"
CACHE = BACKEND / "app" / "core" / "cache.py"
SENTRY = BACKEND / "app" / "core" / "sentry.py"
ENGINE = BACKEND / "app" / "core" / "model_engine" / "__init__.py"
MAIN = BACKEND / "app" / "main.py"
CONFIG = BACKEND / "app" / "core" / "config.py"

MUTATIONS: list[tuple[str, Path, str, str, list[str]]] = [
    (
        "M1 predict_structured 恢复 v1.20 兜底",
        PREDICT,
        "            default_model_version = settings.structured_default_model\n",
        '            default_model_version = getattr(settings, "structured_default_model", "v1.20")  # MUTATION\n',
        [T],
    ),
    (
        "M2 _model_roots 恢复 None 兜底",
        METRICS,
        "    raw = settings.model_dir\n",
        '    raw = getattr(settings, "model_dir", None)  # MUTATION\n',
        [T],
    ),
    (
        "M3 cache 新增同名直读 MODEL_DIR",
        CACHE,
        '    """从 settings 或环境变量获取 Redis URL. 无可用 URL 返回 None."""\n    try:\n',
        '    """从 settings 或环境变量获取 Redis URL. 无可用 URL 返回 None."""\n'
        '    _mutation_probe = os.getenv("MODEL_DIR")  # MUTATION\n    try:\n',
        [T],
    ),
    (
        "M4 cache 的 REDIS_URL 改读 REDIS_URL_LEGACY",
        CACHE,
        '    env_url = os.getenv("REDIS_URL")\n',
        '    env_url = os.getenv("REDIS_URL_LEGACY")  # MUTATION\n',
        [T],
    ),
    (
        "M5 sentry 新增同名直读 SENTRY_ENVIRONMENT",
        SENTRY,
        '    dsn = dsn or os.getenv("SENTRY_DSN")\n',
        '    dsn = dsn or os.getenv("SENTRY_DSN")\n'
        '    _mutation_probe = os.getenv("SENTRY_ENVIRONMENT")  # MUTATION\n',
        [T],
    ),
    (
        "M6 model_cache_maxsize 兜底 20 改 21",
        ENGINE,
        'getattr(settings, "model_cache_maxsize", 20)',
        'getattr(settings, "model_cache_maxsize", 21)',
        [T],
    ),
    (
        "M7 main 不再透传 settings.sentry_dsn",
        MAIN,
        "        dsn=settings.sentry_dsn,\n",
        "        dsn=None,  # MUTATION\n",
        [T],
    ),
    (
        "M8 cache 不再优先读取 settings.redis_url",
        CACHE,
        "        url = settings.redis_url\n",
        "        url = None  # MUTATION\n",
        [T],
    ),
    (
        "M9 声明默认值 model_dir 改 models2",
        CONFIG,
        '    model_dir: str = "models"\n',
        '    model_dir: str = "models2"  # MUTATION\n',
        [T],
    ),
]


def run_pytest(node_ids: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        [str(PY), "-m", "pytest", *node_ids,
         "-o", "addopts=--strict-markers --import-mode=importlib",
         "-p", "no:cacheprovider", "-q", "--no-header", "--tb=no",
         "--basetemp=.pytest_tmp_r44mut"],
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
            "mutate_round44_config_source_uniqueness_result.log"
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
        "mutate_round44_config_source_uniqueness_result.log"
    ).write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
