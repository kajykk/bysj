"""ROUND_35 接线闸门的真实变异见证（红 → 字节还原 → 末臂绿）。

判据：翻转实现必须翻转断言真值空间。每条接线只翻一处实现，跑对应闸门，
期望 RED；随后 try/finally 用**字节快照**还原（工作树有未提交改动，
禁用 git checkout --），并断言还原后 sha256 与变异前一致；最后末臂把
后端 8 条闸门与前端 3 组测试一起复跑，必须全 GREEN。

变异与测试严格串行，禁止并发。
用法（在仓库根/任意目录均可）：
    backend/.venv/Scripts/python.exe backend/tests/tools/mutate_round35.py
产物：backend/tests/tools/mutate_round35_result.log
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
LOG = Path(__file__).with_name("mutate_round35_result.log")

ADDONS = (
    "addopts=--strict-markers --import-mode=importlib "
    "--ignore=functional_test.py --ignore-glob=test_result*.txt --ignore=test_final.txt"
)
PYTEST_BASE = [str(PY), "-m", "pytest", "-o", ADDONS, "-p", "no:cacheprovider", "-q", "--tb=line"]
GATES_FILE = "tests/test_round35_wiring_gates.py"


def pytest_gate(name: str) -> list[str]:
    return PYTEST_BASE + ["-k", name, GATES_FILE]


def vitest(*paths: str) -> list[str]:
    """多个文件必须作为独立 argv 传入；拼成一个带空格的字符串会被当成不存在的路径。"""
    return ["node", "node_modules/vitest/vitest.mjs", "run", *paths]


MUTATIONS = [
    {
        "id": "G1 / M-01 CSP 模型不再实例化（校验成死代码）",
        "file": BACKEND / "app" / "api" / "csp_report.py",
        "old": b"body = CSPReportBody.model_validate(normalized)",
        "new": b"body = CSPReportBody.model_construct(**normalized)",
        "cmd": pytest_gate("test_csp_endpoint_instantiates_validation_model"),
        "cwd": BACKEND,
    },
    {
        "id": "G2 / M-05 审计 detail 写回明文绑定码",
        "file": BACKEND / "app" / "services" / "counselor_service_binding.py",
        "old": b'"bind_code_fingerprint": _fingerprint(code),',
        "new": b'"bind_code": code,',
        "cmd": pytest_gate("test_bind_audit_detail_never_writes_plaintext_code"),
        "cwd": BACKEND,
    },
    {
        "id": "G3 / M-07 影子 Task 丢失强引用",
        "file": BACKEND / "app" / "services" / "shadow_mode_service.py",
        "old": b"self._tasks.add(task)",
        "new": b"pass  # MUTATION: strong reference dropped",
        "cmd": pytest_gate("test_shadow_tasks_are_strongly_referenced"),
        "cwd": BACKEND,
    },
    {
        "id": "G4 / M-10 告警扫描退回固定 limit(500)",
        "file": BACKEND / "app" / "monitoring" / "escalation.py",
        "old": b".limit(_ESCALATION_BATCH_SIZE)",
        "new": b".limit(500)",
        "cmd": pytest_gate("test_escalation_scan_is_cursor_paged"),
        "cwd": BACKEND,
    },
    {
        "id": "G5 / M-02 去掉 PromQL 正则白名单",
        "file": BACKEND / "app" / "api" / "v1" / "metrics_helpers.py",
        "old": br'if re.fullmatch(r"[A-Za-z0-9_.*?+\-]{1,128}", pattern):',
        "new": b"if pattern:  # MUTATION: whitelist dropped",
        "cmd": pytest_gate("test_metrics_regex_is_whitelisted_and_fail_closed"),
        "cwd": BACKEND,
    },
    {
        "id": "G6 / S-01 响应契约重新加回 client_ip",
        "file": BACKEND / "app" / "schemas" / "analytics.py",
        "old": b"    metadata: dict[str, Any] = Field(default_factory=dict)\n",
        "new": b"    metadata: dict[str, Any] = Field(default_factory=dict)\n    client_ip: str | None = None  # MUTATION\n",
        "cmd": pytest_gate("test_analytics_event_record_has_no_client_ip"),
        "cwd": BACKEND,
    },
    {
        "id": "G7 / M-03 导出跨度上限放宽到 10 年",
        "file": BACKEND / "app" / "api" / "v1" / "admin.py",
        "old": b"if (end_time - start_time) > timedelta(days=90):",
        "new": b"if (end_time - start_time) > timedelta(days=3650):",
        "cmd": pytest_gate("test_operation_log_export_caps_time_span"),
        "cwd": BACKEND,
    },
    {
        "id": "G8 / M-12 跳过项不再阻断门禁（0 项检查报通过）",
        "file": BACKEND / "scripts" / "check_compatibility.py",
        "old": b'    skipped = [r for r in results if r.get("skipped")]',
        "new": b"    skipped = []  # MUTATION: skipped ignored",
        "cmd": pytest_gate("test_missing_model_gate_fails_closed"),
        "cwd": BACKEND,
    },
    {
        "id": "F1 / M-20 guard fail-closed 缩回只管 /admin",
        "file": FRONTEND / "src" / "router" / "guard.ts",
        "old": b"const privilegedArea = isAdminArea(toPath, meta) || toPath.startsWith('/counselor')",
        "new": b"const privilegedArea = isAdminArea(toPath, meta)",
        "cmd": vitest("src/router/guard.realstore.test.ts"),
        "cwd": FRONTEND,
    },
    {
        "id": "F2a / M-18 persistAuth 不再广播",
        "file": FRONTEND / "src" / "stores" / "auth.ts",
        "old": b"    broadcastAuthSync(next)\n",
        "new": b"    // MUTATION: broadcast removed\n",
        "cmd": vitest("src/utils/authBroadcast.wiring.test.ts"),
        "cwd": FRONTEND,
    },
    {
        "id": "F2b / M-18 401 刷新成功不再广播",
        "file": FRONTEND / "src" / "api" / "request.ts",
        "old": b"    broadcastAuthSync({ token: newToken, user: newUser })",
        "new": b"    void newToken  // MUTATION",
        "cmd": vitest("src/utils/authBroadcast.wiring.test.ts"),
        "cwd": FRONTEND,
    },
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def adapt(original: bytes, anchor: bytes) -> bytes:
    """按目标文件实际换行风格调整锚点（前端 CRLF / 后端 LF）。"""
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
        if any(token in line for token in ("passed", "failed", "Test Files", "Tests  ", "error"))
    ]
    return " | ".join(hits[-4:])[:400]


def main() -> int:
    assert PY.exists(), f"缺少后端解释器: {PY}"
    lines: list[str] = ["ROUND_35 wiring-gate mutation witness", "=" * 60]

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
            lines.append(f"  cmd             : {' '.join(mutation['cmd'][:5])} ...")
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

    # 末臂：全部还原后一起复跑，必须全绿
    green_cmds = [
        (PYTEST_BASE + [GATES_FILE], BACKEND, "backend 8 wiring gates"),
        (
            vitest(
                "src/router/guard.realstore.test.ts",
                "src/utils/authBroadcast.wiring.test.ts",
            ),
            FRONTEND,
            "frontend 2 wiring gates",
        ),
        (
            PYTEST_BASE + ["tests/api/test_round35_rbac_real_object_e2e.py"],
            BACKEND,
            "backend real-object RBAC e2e",
        ),
    ]
    all_green = True
    for cmd, cwd, label in green_cmds:
        proc = run(cmd, cwd)
        green = proc.returncode == 0
        all_green &= green
        lines.append(f"[FINAL ARM / {label}] rc={proc.returncode} {'GREEN' if green else 'RED (!!)'}")
        lines.append(f"  summary: {summary(proc)}")

    total = len(MUTATIONS)
    lines.append("=" * 60)
    lines.append(
        f"RESULT: {'PASS (' + str(total) + '/' + str(total) + ' RED, restored byte-identical, final GREEN)' if all_green else 'FAIL'}"
    )
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-8:]))
    return 0 if all_green else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # 异常也必须留痕，已进入变异的文件均由 finally 还原
        LOG.write_text(
            "ROUND_35 wiring-gate mutation witness\n" + "=" * 60 + "\n"
            f"ABORT: {type(exc).__name__}: {exc}\n"
            "所有已进入变异的文件均经 finally 字节快照还原；本次不构成变异见证。\n",
            encoding="utf-8",
        )
        raise
