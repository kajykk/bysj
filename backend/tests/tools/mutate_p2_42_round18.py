"""ROUND_18 变异验证：M1 / M2 / M6 / M7 / M8 / M9 六条修复都必须被真实变异打红。

用法（backend 目录下）:
    .venv/Scripts/python.exe tests/tools/mutate_p2_42_round18.py

纪律（继承）：
- 只翻转实现、不翻转断言真值空间；
- 每个变异后按**字节快照**还原（删除型变异不能用文本 replace 还原）；
- 先跑基线（未变异全绿）再变异；收尾做快照比对，任何残留即退出码 1。

关于 T1 的变异点：``/auth/refresh`` 的强制点在内**响应模型**，不在处理函数的
返回值 —— FastAPI 会按 response_model 过滤多余键。因此变异改模型（把字段加回），
这样才能同时打红"键集合完全相等"与"OpenAPI 不再声明该字段"两条判据。
处理函数回退到 ``ok(tokens)`` 时闸门仍绿，属于"模型兜底生效"，不是假绿。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]

GATE_REFRESH = "tests/test_p2_42_round18_refresh_body.py"
GATE_VALIDATION = "tests/test_p2_43_round18_validation_created_by.py"
GATE_REVIEW = "tests/test_p2_44_round18_review_state.py"
GATE_WARNING = "tests/test_p2_45_round18_warning_escalate.py"
GATE_WS = "tests/unit/test_websocket_auth.py"
ALL_GATES = (GATE_REFRESH, GATE_VALIDATION, GATE_REVIEW, GATE_WARNING, GATE_WS)

LOG = Path(__file__).resolve().parent / "mutate_p2_42_round18_result.log"

AUTH_SCHEMA = BACKEND_ROOT / "app" / "schemas" / "auth.py"
WS = BACKEND_ROOT / "app" / "core" / "ws.py"
VALIDATION = BACKEND_ROOT / "app" / "api" / "v1" / "validation.py"
REVIEW_SVC = BACKEND_ROOT / "app" / "services" / "review_service.py"
WARNING_SVC = BACKEND_ROOT / "app" / "services" / "counselor_service_warning.py"

LINES: list[str] = []
SNAPSHOTS: dict[Path, bytes] = {}


def log(msg: str) -> None:
    print(msg)
    LINES.append(msg)


def run_gate(*targets: str) -> tuple[int, str]:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *targets,
            "-o",
            "addopts=--strict-markers --import-mode=importlib",
            "-p",
            "no:cacheprovider",
            "-q",
        ],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=1200,
    )
    return proc.returncode, proc.stdout


def mutate(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"锚点未命中: {path}: {old[:90]!r}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def drop(path: Path, block: str) -> None:
    """删除型变异：锚点必须是完整语句块。"""
    text = path.read_text(encoding="utf-8")
    assert block in text, f"删除锚点未命中: {path}: {block[:90]!r}"
    path.write_text(text.replace(block, "", 1), encoding="utf-8")


def red_for(targets: tuple[str, ...], expected: list[str]) -> bool:
    code, out = run_gate(*targets)
    failed = [ln for ln in out.splitlines() if "FAILED" in ln or "ERROR" in ln]
    hit = all(any(sub in ln for ln in failed) for sub in expected)
    ok = code != 0 and hit
    log(
        f"    returncode={code} | 失败 {len(failed)} 项 | 目标 {expected}: "
        f"{'RED-OK' if ok else 'UNEXPECTED'}"
    )
    for ln in failed[:4]:
        log(f"      {ln.strip()}")
    if code == 0:
        log("    !!! 假绿：变异后闸门仍全绿")
    return ok


def main() -> None:
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=BACKEND_ROOT.parent,
        capture_output=True,
        text=True,
    ).stdout.strip()
    log(f"[head] {head}")

    for path in (AUTH_SCHEMA, WS, VALIDATION, REVIEW_SVC, WARNING_SVC):
        SNAPSHOTS[path] = path.read_bytes()

    code, out = run_gate(*ALL_GATES)
    log(f"[baseline] 未变异 returncode={code}（0=全绿）")
    log(f"[baseline] {out.strip().splitlines()[-1] if out.strip() else ''}")
    assert code == 0, "基线不为绿，先修复再变异"

    results: dict[str, bool] = {}

    # ── T1（M1）：把 refresh_token 加回响应模型 ────────────────────────
    log("\n[T1] TokenResponse 重新声明 refresh_token")
    try:
        mutate(
            AUTH_SCHEMA,
            '''    access_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):''',
            '''    access_token: str
    token_type: str = "bearer"
    refresh_token: str | None = None


class LoginResponse(BaseModel):''',
        )
        results["T1"] = red_for(
            (GATE_REFRESH,),
            [
                "test_refresh_response_exposes_only_access_token",
                "test_refresh_response_schema_does_not_declare_refresh_token",
            ],
        )
    finally:
        AUTH_SCHEMA.write_bytes(SNAPSHOTS[AUTH_SCHEMA])

    # ── T2（M2）：撤销分支恒不生效 ────────────────────────────────────
    log("\n[T2] WS 握手把 `if revoked:` 改成 `if False:`")
    try:
        mutate(WS, "        if revoked:\n", "        if False:  # MUTATION-PROBE\n")
        results["T2"] = red_for(
            (GATE_WS,), ["test_websocket_rejects_jti_revoked_after_logout"]
        )
    finally:
        WS.write_bytes(SNAPSHOTS[WS])

    # ── T3（M6）：created_by 回到 int 口径 ────────────────────────────
    log("\n[T3] _deserialize_dict 把 created_by 转回 int")
    try:
        mutate(
            VALIDATION,
            "                result[key] = value.decode() if isinstance(value, bytes) else str(value)",
            '''                try:
                    result[key] = int(value)
                except (ValueError, TypeError):
                    result[key] = value''',
        )
        results["T3"] = red_for(
            (GATE_VALIDATION,),
            [
                "test_deserialize_keeps_created_by_as_str",
                "test_redis_mode_job_stays_visible_to_its_creator",
            ],
        )
    finally:
        VALIDATION.write_bytes(SNAPSHOTS[VALIDATION])

    # ── T4a（M7）：取行不再加锁 ───────────────────────────────────────
    log("\n[T4a] _locked_review_stmt 去掉 with_for_update()")
    try:
        mutate(REVIEW_SVC, "        .with_for_update()\n", "")
        results["T4a"] = red_for(
            (GATE_REVIEW,), ["test_locked_statement_compiles_with_for_update"]
        )
    finally:
        REVIEW_SVC.write_bytes(SNAPSHOTS[REVIEW_SVC])

    # ── T4b（M7）：删除处置审计 ───────────────────────────────────────
    log("\n[T4b] resolve_review 整段删除 record_audit(...)")
    audit_block = '''        await record_audit(
            self.db,
            actor_id=counselor_id,
            actor_role=USER_ROLE_ADMIN if is_admin else USER_ROLE_COUNSELOR,
            action="review.resolved",
            target_type="review_task",
            target_id=review_id,
            detail={
                "resolved_by": counselor_id,
                "previous_status": previous_status,
                # 只记长度，不落处置备注原文（临床内容不进审计表）
                "resolution_note_chars": len(resolution_note or ""),
            },
            request=request,
            tenant_id=tenant_id,
        )
'''
    try:
        drop(REVIEW_SVC, audit_block)
        results["T4b"] = red_for(
            (GATE_REVIEW,),
            ["test_resolve_writes_audit_without_clinical_note_text"],
        )
    finally:
        REVIEW_SVC.write_bytes(SNAPSHOTS[REVIEW_SVC])

    # ── T5（M8）：去掉受派人校验 ──────────────────────────────────────
    log("\n[T5] assign_review 删除 _ensure_assignee 调用")
    try:
        drop(REVIEW_SVC, "        await self._ensure_assignee(counselor_id, tenant_id)\n")
        results["T5"] = red_for(
            (GATE_REVIEW,),
            [
                "test_assign_rejects_missing_assignee",
                "test_assign_rejects_plain_user",
                "test_assign_rejects_cross_tenant_counselor",
                "test_assign_rejects_disabled_counselor",
            ],
        )
    finally:
        REVIEW_SVC.write_bytes(SNAPSHOTS[REVIEW_SVC])

    # ── T6（M9）：删除幂等/状态前置分支 ──────────────────────────────
    log("\n[T6] escalate_warning 删除 is_handled 幂等/状态前置分支")
    idempotent_block = '''        if warning.is_handled:
            if warning.handle_action == WARNING_ACTION_ESCALATE:
                # 重复升级幂等：状态与审计在首次调用已落地，这里仅回 True。
                # 不追加第二条审计，也不覆盖首次升级原因（事故复盘以首次为准）。
                logger.info(
                    "escalate_warning idempotent replay: warning_id=%s counselor_id=%s",
                    warning_id,
                    counselor_id,
                )
                return True
            # ignored / handled 之后不允许再升级（防"已判定无需干预"被悄悄改写）
            logger.warning(
                "escalate_warning rejected: warning_id=%s already handled with action=%s",
                warning_id,
                warning.handle_action,
            )
            return False

'''
    try:
        drop(WARNING_SVC, idempotent_block)
        results["T6"] = red_for(
            (GATE_WARNING,),
            [
                "test_escalate_twice_is_idempotent",
                "test_escalate_after_ignore_is_rejected",
            ],
        )
    finally:
        WARNING_SVC.write_bytes(SNAPSHOTS[WARNING_SVC])

    # ── 收尾：还原校验 + 最终复绿 ────────────────────────────────────
    residual = [str(p) for p, snap in SNAPSHOTS.items() if p.read_bytes() != snap]
    log(f"\n[residual] 残留文件: {residual or '无'}")

    code, out = run_gate(*ALL_GATES)
    log(f"[final] 还原后 returncode={code}（0=全绿）")
    log(f"[final] {out.strip().splitlines()[-1] if out.strip() else ''}")

    ok = all(results.values()) and not residual and code == 0
    log("\n[summary] " + " | ".join(f"{k}={'RED-OK' if v else 'FAILED'}" for k, v in results.items()))
    log(f"[summary] residual_clean={not residual} final_green={code == 0}")
    LOG.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
