"""ROUND_34 P0 三闸门的真实变异见证（红 → 字节还原 → 末臂绿）。

判据：翻转实现必须翻转断言真值空间。每个闸门只翻一处实现，跑对应测试，
期望 RED；随后 try/finally 用**字节快照**还原（工作树有未提交改动，
禁用 git checkout --），并断言 sha256 与还原前一致；最后三条闸门一起
再跑一次，期望全 GREEN。

用法（在仓库根/任意目录均可）：
    backend/.venv/Scripts/python.exe backend/tests/tools/mutate_round34.py
产物：backend/tests/tools/mutate_round34_result.log
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
FRONTEND = REPO / "frontend"
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
LOG = Path(__file__).with_name("mutate_round34_result.log")

ADDONS = (
    "addopts=--strict-markers --import-mode=importlib "
    "--ignore=functional_test.py --ignore-glob=test_result*.txt --ignore=test_final.txt"
)

PYTEST_BASE = [str(PY), "-m", "pytest", "-o", ADDONS, "-p", "no:cacheprovider", "-q"]
TEST_TENANT = "tests/api/test_round34_analytics_tenant_isolation.py"
TEST_BASELINE = "tests/test_round34_baseline_no_fabrication.py"
VITEST = [
    "node",
    "node_modules/vitest/vitest.mjs",
    "run",
    "src/views/counselor/CounselorDashboard.failure.test.ts",
]

MUTATIONS = [
    {
        "id": "S-01 / analytics tenant filter -> return all",
        "file": BACKEND / "app" / "api" / "v1" / "analytics_events.py",
        "old": b'        if isinstance(record.get("tenant_id"), int) and record["tenant_id"] == tenant_id\n',
        "new": b"        if True  # MUTATION: tenant filter disabled\n",
        "cmd": PYTEST_BASE + [TEST_TENANT],
        "cwd": BACKEND,
    },
    {
        "id": "S-03 / missing baseline -> fabricate metrics again",
        "file": REPO / "scripts" / "compare_text_models.py",
        "old": (
            b"                model_path_file,\n"
            b"            )\n"
            b"            return None\n"
        ),
        "new": (
            b"                model_path_file,\n"
            b"            )\n"
            b'            return {"f1": 0.9681, "roc_auc": 0.98}  # MUTATION\n'
        ),
        "cmd": PYTEST_BASE + [TEST_BASELINE],
        "cwd": BACKEND,
    },
    {
        "id": "S-02 / drop failure-state assignment",
        "file": FRONTEND / "src" / "views" / "counselor" / "CounselorDashboard.vue",
        "old": b"    unhandledCount.value = null\n",
        "new": b"    // MUTATION: failure-state assignment removed\n",
        "cmd": VITEST,
        "cwd": FRONTEND,
    },
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def adapt(original: bytes, anchor: bytes) -> bytes:
    """按目标文件的实际换行风格调整锚点（前端 .vue 为 CRLF，后端 .py 为 LF）。

    Windows 工作树混用 CRLF/LF；锚点一律以 LF 书写，命中前就地适配，
    否则会出现「变异锚点未命中」的假失败。
    """
    if b"\r\n" in original and b"\r\n" not in anchor:
        return anchor.replace(b"\n", b"\r\n")
    return anchor


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )


def summary(proc: subprocess.CompletedProcess[str]) -> str:
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    hits = [
        line.strip()
        for line in text.splitlines()
        if any(
            token in line
            for token in ("passed", "failed", "Test Files", "Tests  ", "error")
        )
    ]
    return " | ".join(hits[-4:])[:400]


def main() -> int:
    assert PY.exists(), f"缺少后端解释器: {PY}"
    lines: list[str] = ["ROUND_34 P0 mutation witness", "=" * 60]

    for mutation in MUTATIONS:
        path: Path = mutation["file"]
        original = path.read_bytes()
        original_sha = digest(original)
        old: bytes = adapt(original, mutation["old"])
        new: bytes = adapt(original, mutation["new"])
        assert old in original, f"{mutation['id']}: 变异锚点未命中，拒绝执行"
        assert old != new

        red = False
        try:
            path.write_bytes(original.replace(old, new, 1))
            mutated_sha = digest(path.read_bytes())
            proc = run(mutation["cmd"], mutation["cwd"])
            red = proc.returncode != 0
            lines.append(f"[{mutation['id']}]")
            lines.append(f"  file            : {path.relative_to(REPO).as_posix()}")
            lines.append(f"  original_sha256 : {original_sha}")
            lines.append(f"  mutated_sha256  : {mutated_sha}")
            lines.append(f"  cmd             : {' '.join(mutation['cmd'][:4])} ...")
            lines.append(f"  rc              : {proc.returncode}")
            lines.append(f"  expected        : RED (rc != 0)")
            lines.append(f"  observed        : {'RED' if red else 'GREEN (!! 闸门无验证力)'}")
            lines.append(f"  summary         : {summary(proc)}")
        finally:
            # 字节快照还原，不依赖 git；任何异常都必须先还原
            path.write_bytes(original)

        restored = path.read_bytes()
        restored_sha = digest(restored)
        assert restored == original, f"{mutation['id']}: 还原后字节不一致"
        lines.append(f"  restore         : byte-identical, sha256={restored_sha}")
        lines.append(f"  verdict         : {'OK (RED -> restored)' if red else 'FAIL'}")
        lines.append("-" * 60)
        if not red:
            lines.append("ABORT: 至少一个闸门未变红，禁止声称变异见证通过")
            LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return 1

    # 末臂：全部还原后三条闸门一起复跑，必须全绿
    green_cmds = [
        (PYTEST_BASE + [TEST_TENANT, TEST_BASELINE], BACKEND, "backend-2-gates"),
        (VITEST, FRONTEND, "frontend-1-gate"),
    ]
    all_green = True
    for cmd, cwd, label in green_cmds:
        proc = run(cmd, cwd)
        green = proc.returncode == 0
        all_green &= green
        lines.append(f"[FINAL ARM / {label}] rc={proc.returncode} "
                     f"{'GREEN' if green else 'RED (!!)'}")
        lines.append(f"  summary: {summary(proc)}")

    lines.append("=" * 60)
    lines.append(f"RESULT: {'PASS (3/3 RED, restored byte-identical, final GREEN)' if all_green else 'FAIL'}")
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-6:]))
    return 0 if all_green else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # 异常也必须留痕，且所有已变异文件均由 finally 还原
        LOG.write_text(
            "ROUND_34 P0 mutation witness\n" + "=" * 60 + "\n"
            f"ABORT: {type(exc).__name__}: {exc}\n"
            "所有已进入变异的文件均经 finally 字节快照还原；本次不构成变异见证。\n",
            encoding="utf-8",
        )
        raise
