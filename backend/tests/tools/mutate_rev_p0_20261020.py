"""P0 源码审查修复（2026-10-20）变异验证：每条修复必须被真实变异打红（RED-OK），还原后复绿（GREEN-OK）.

输入：
    outputs/CODE_REVIEW_2026-10-20.md   （审查报告，S1–S7）
    outputs/CODE_REVIEW_FIX_2026-10-20.md（执行记录，S1–S7）

用途：执行记录 §二 声称 7 条修复各配了一次"改回缺陷实现 → 红"的真实变异，但
**未入库任何变异日志**（对比 B/B.5 轮次留有 mutate_p2_38_round14_result.log、
mutate_p2_39_round15_result.log、mutate_p2_40_round16_result.log）。本脚本补上
这一缺口：把"变异见证"从文档表格里的自述变成**可复跑的第三方可核验产物**。

用法（backend 目录下）:
    .venv/Scripts/python.exe tests/tools/mutate_rev_p0_20261020.py

铁律（继承 mutate_p2_40_round16.py）：
- 变异只改实现、必须能翻转某条断言的真值空间（不接受"无效变异"）；
- 每个变异 try/finally 还原（无论红绿）；
- 先跑基线（未变异全绿）再做变异；
- 收尾用标志串计数判定**无残留**；
- 前端用例走 vitest，故执行器按后端 pytest / 前端 vitest 两路分别实现。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
FRONTEND_ROOT = REPO_ROOT / "frontend"
LOG = Path(__file__).resolve().parent / "mutate_rev_p0_20261020_result.log"

LINES: list[str] = []


def log(msg: str) -> None:
    print(msg)
    LINES.append(msg)


def _run(
    cmd: list[str] | str,
    cwd: Path,
    timeout: int = 900,
    shell: bool = False,
) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=shell,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def run_pytest(targets: list[str]) -> tuple[int, str]:
    return _run(
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
        BACKEND_ROOT,
    )


def run_vitest(rel_path: str) -> tuple[int, str]:
    # Windows 下 npx 是 .cmd shim，subprocess 直接给 "npx" 会 FileNotFoundError
    # （WinError 2）⇒ 显式解析 npx.cmd，找不到再退回 shell=True。
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if npx:
        return _run(
            [npx, "vitest", "run", rel_path, "--reporter=verbose"],
            FRONTEND_ROOT,
            timeout=900,
        )
    return _run(
        f'npx vitest run {rel_path} --reporter=verbose',
        FRONTEND_ROOT,
        timeout=900,
        shell=True,
    )


def mutate(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"锚点未命中: {path}: {old[:70]!r}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def restore(path: Path, original: str, mutated: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert mutated in text, f"还原锚点未命中: {path}: {mutated[:70]!r}"
    path.write_text(text.replace(mutated, original, 1), encoding="utf-8")


def red_for(
    label: str,
    runner,
    expected: list[str],
    extra_note: str = "",
) -> bool:
    """变异后必须 returncode!=0 且失败行命中全部目标用例名（查全量输出，非尾部几行）."""
    code, out = runner()
    failed = [ln for ln in out.splitlines() if "FAILED" in ln or "FAIL " in ln]
    missing = [e for e in expected if not any(e in ln for ln in failed)]
    ok = code != 0 and not missing
    log(
        f"    returncode={code} | 失败行 {len(failed)} 条 | "
        f"命中目标 {'全部' if not missing else f'缺 {missing}'} => "
        f"{'RED-OK' if ok else 'UNEXPECTED'}"
    )
    for ln in failed[:6]:
        log(f"      {ln.strip()[:170]}")
    if code == 0:
        log("    !!! 假绿：变异后用例仍全绿")
    if extra_note:
        log(f"    note: {extra_note}")
    return ok


def main() -> None:
    # ── 文件定位 ────────────────────────────────────────────────────────
    request_ts = FRONTEND_ROOT / "src" / "api" / "request.ts"
    anonymize = BACKEND_ROOT / "app" / "services" / "gdpr_service_anonymize.py"
    review_service = BACKEND_ROOT / "app" / "services" / "review_service.py"
    binding = BACKEND_ROOT / "app" / "services" / "counselor_service_binding.py"
    counselor_user = BACKEND_ROOT / "app" / "services" / "counselor_service_user.py"
    uploads = BACKEND_ROOT / "app" / "api" / "v1" / "uploads.py"
    db_breaker = BACKEND_ROOT / "app" / "core" / "db_breaker.py"
    pdf_service = BACKEND_ROOT / "app" / "services" / "pdf_report_service.py"
    risk_service = BACKEND_ROOT / "app" / "services" / "risk_service.py"
    tenant_status = BACKEND_ROOT / "app" / "core" / "tenant_status.py"
    deps = BACKEND_ROOT / "app" / "core" / "deps.py"
    ws_module = BACKEND_ROOT / "app" / "core" / "ws.py"

    results: dict[str, bool] = {}

    # 变异目标文件的**字节级快照**：收尾时逐一比对，确认"变异→还原"是
    # 精确往返。比"标志串计数"强得多 —— 标志串只能覆盖我们想到的残留形态，
    # 而字节快照能覆盖**任何**残留（含还原参数写反导致的累积）。
    # 注意不能用 git hash-object 比 HEAD：本仓工作区是 CRLF（core.autocrlf），
    # 与 git blob（LF）天然不同，比 HEAD 会得到一堆假报。
    MUTATED_FILES = [
        request_ts,
        anonymize,
        review_service,
        binding,
        counselor_user,
        uploads,
        db_breaker,
        pdf_service,
        risk_service,
        tenant_status,
        deps,
        ws_module,
    ]
    snapshots = {p: p.read_bytes() for p in MUTATED_FILES}

    # ── 基线：未变异必须全绿 ────────────────────────────────────────────
    log("[baseline] 后端 P0 回归集（未变异）")
    code, out = run_pytest(
        [
            "tests/test_rev_s2_anonymize_json.py",
            "tests/test_rev_s3_binding_tenant.py",
            "tests/test_rev_s5_pdf_cjk.py",
            "tests/test_rev_s6_warning_isolation.py",
            "tests/test_rev_s7_tenant_suspend.py",
            "tests/test_db_breaker.py",
            "tests/test_isolation_wiring_gate.py",
            "tests/unit/test_websocket_auth.py",
        ]
    )
    log(f"[baseline] returncode={code} | {out.strip().splitlines()[-1] if out.strip() else ''}")
    if code != 0:
        log("[baseline] !!! 基线不绿，先修复再变异")
        sys.exit(1)

    log("[baseline] 前端 S1 回归（未变异）")
    code, out = run_vitest("src/api/request.interceptors.test.ts")
    log(f"[baseline] returncode={code}")
    if code != 0:
        log("[baseline] !!! 前端基线不绿")
        sys.exit(1)

    # ── S1：前端 refresh URL 双拼 ──────────────────────────────────────
    log("\n[S1] 前端 refresh 改回 buildApiUrl('/auth/refresh')（URL 二次拼接）")
    s1_old_import = "import { normalizePageResult, type UnifiedPageResult } from '@/types/contracts'"
    s1_new_import = (
        s1_old_import + "\nimport { buildApiUrl } from './base'"
    )
    s1_old_call = "const { data } = await request.post('/auth/refresh', {}, {"
    s1_new_call = "const { data } = await request.post(buildApiUrl('/auth/refresh'), {}, {"
    try:
        mutate(request_ts, s1_old_import, s1_new_import)
        mutate(request_ts, s1_old_call, s1_new_call)
        results["S1"] = red_for(
            "S1",
            lambda: run_vitest("src/api/request.interceptors.test.ts"),
            ["路径合并"],
            "该用例用 request.getUri(captured) 走真实 buildFullPath，"
            "断言最终 URL 只有一层 /api/v1 前缀",
        )
    finally:
        restore(request_ts, s1_old_call, s1_new_call)
        restore(request_ts, s1_old_import, s1_new_import)

    # ── S2a：匿名化写回裸串（写侧）─────────────────────────────────────
    log("\n[S2a] 匿名化 crisis_keywords 写回裸串 ANON_TEXT（非法 JSON）")
    s2a_old = "ev.crisis_keywords = json.dumps([])"
    s2a_new = "ev.crisis_keywords = ANON_TEXT"
    try:
        mutate(anonymize, s2a_old, s2a_new)
        results["S2a"] = red_for(
            "S2a",
            lambda: run_pytest(["tests/test_rev_s2_anonymize_json.py"]),
            ["test_anonymize_writes_valid_json_and_clear_action"],
        )
    finally:
        restore(anonymize, s2a_old, s2a_new)

    # ── S2b：读取侧容错被去掉 ──────────────────────────────────────────
    log("\n[S2b] _parse_crisis_keywords 不再捕获 ValueError（JSONDecodeError 冒泡）")
    s2b_old = "    except (TypeError, ValueError):"
    s2b_new = "    except (TypeError,):"
    try:
        mutate(review_service, s2b_old, s2b_new)
        results["S2b"] = red_for(
            "S2b",
            lambda: run_pytest(["tests/test_rev_s2_anonymize_json.py"]),
            ["test_legacy_dirty_row_is_tolerated"],
            "JSONDecodeError 是 ValueError 子类，放开 ValueError 即恢复原 500 缺陷",
        )
    finally:
        restore(review_service, s2b_old, s2b_new)

    # ── S3a：绑定流程去掉租户比对 ──────────────────────────────────────
    log("\n[S3a] bind_by_code 去掉咨询师/用户租户比对")
    s3a_old = "        if (bound_user.tenant_id or DEFAULT_TENANT_ID) != ("
    s3a_new = "        if False and (bound_user.tenant_id or DEFAULT_TENANT_ID) != ("
    try:
        mutate(binding, s3a_old, s3a_new)
        results["S3a"] = red_for(
            "S3a",
            lambda: run_pytest(["tests/test_rev_s3_binding_tenant.py"]),
            ["test_bind_by_code_rejects_cross_tenant_counselor"],
        )
    finally:
        restore(binding, s3a_old, s3a_new)

    # ── S3b：get_user_detail 去掉 User 查询的租户过滤 ──────────────────
    log("\n[S3b] get_user_detail 去掉 tenant_scoped_filter(User, tenant_id)")
    s3b_old = "            tenant_scoped_filter(User, tenant_id),"
    s3b_new = "            True,  # MUTATION-PROBE: 租户过滤被移除"
    try:
        mutate(counselor_user, s3b_old, s3b_new)
        results["S3b"] = red_for(
            "S3b",
            lambda: run_pytest(
                [
                    "tests/test_rev_s3_binding_tenant.py",
                    "tests/test_isolation_wiring_gate.py",
                ]
            ),
            [
                "test_get_user_detail_rejects_dangling_cross_tenant_binding",
                "test_no_new_unfiltered_tenant_queries",
            ],
            "同一次变异应同时打红「跨租户详情」用例与「租户查询棘轮」"
            "（后者证明我修的字面量判据确实在承重）",
        )
    finally:
        restore(counselor_user, s3b_old, s3b_new)

    # ── S3c：uploads admin 分支去掉租户比对 ────────────────────────────
    log("\n[S3c] uploads admin 分支去掉目标用户租户比对")
    s3c_old = "        if (target_tenant or DEFAULT_TENANT_ID) != ("
    s3c_new = "        if False and (target_tenant or DEFAULT_TENANT_ID) != ("
    try:
        mutate(uploads, s3c_old, s3c_new)
        results["S3c"] = red_for(
            "S3c",
            lambda: run_pytest(["tests/test_rev_s3_binding_tenant.py"]),
            ["test_uploads_admin_branch_is_tenant_scoped"],
        )
    finally:
        restore(uploads, s3c_old, s3c_new)

    # ── S4：熔断器不归还半开探针令牌 ────────────────────────────────────
    log("\n[S4] db_breaker.on_failure 不再归还 HALF_OPEN 探针令牌")
    s4_old = "                if self._state == CircuitState.HALF_OPEN:\n                    self._half_open_calls = 0"
    s4_new = "                if False and self._state == CircuitState.HALF_OPEN:\n                    self._half_open_calls = 0"
    try:
        mutate(db_breaker, s4_old, s4_new)
        results["S4"] = red_for(
            "S4",
            lambda: run_pytest(["tests/test_db_breaker.py"]),
            ["half_open"],
        )
    finally:
        restore(db_breaker, s4_old, s4_new)

    # ── S5：PDF 不注册 CJK 字体 ─────────────────────────────────────────
    log("\n[S5] pdf_report_service 不注册 STSong-Light（回落 Helvetica）")
    s5_old = "        pdfmetrics.registerFont(UnicodeCIDFont(_CJK_FONT_NAME))"
    s5_new = "        return None  # MUTATION-PROBE: 未注册 CJK 字体"
    try:
        mutate(pdf_service, s5_old, s5_new)
        results["S5"] = red_for(
            "S5",
            lambda: run_pytest(["tests/test_rev_s5_pdf_cjk.py"]),
            ["test_generate_pdf_renders_chinese"],
        )
    finally:
        restore(pdf_service, s5_old, s5_new)

    # ── S6：预警不再独立提交 ────────────────────────────────────────────
    log("\n[S6] risk_service 预警不再先独立 commit（与干预同事务）")
    s6_old = "        try:\n            await db.commit()\n        except Exception:"
    s6_new = "        try:\n            pass  # MUTATION-PROBE: 预警未独立提交\n        except Exception:"
    try:
        mutate(risk_service, s6_old, s6_new)
        results["S6"] = red_for(
            "S6",
            lambda: run_pytest(["tests/test_rev_s6_warning_isolation.py"]),
            ["test_fire_and_forget_keeps_warning_when_intervention_fails"],
        )
    finally:
        restore(risk_service, s6_old, s6_new)

    # ── S7a：is_tenant_suspended 恒返回 False ──────────────────────────
    log("\n[S7a] is_tenant_suspended 恒返回 False（封禁永不生效）")
    s7a_old = "    return tenant.status == TENANT_STATUS_SUSPENDED"
    s7a_new = "    return False  # MUTATION-PROBE: 封禁永不生效"
    try:
        mutate(tenant_status, s7a_old, s7a_new)
        results["S7a"] = red_for(
            "S7a",
            lambda: run_pytest(["tests/test_rev_s7_tenant_suspend.py"]),
            ["test_suspended_tenant_blocks_authenticated_request"],
        )
    finally:
        restore(tenant_status, s7a_old, s7a_new)

    # ── S7b：deps.get_current_user 不校验租户封禁 ───────────────────────
    log("\n[S7b] deps.get_current_user 跳过租户封禁校验")
    s7b_old = "    if await is_tenant_suspended(db, effective_tenant_id):"
    s7b_new = "    if False and await is_tenant_suspended(db, effective_tenant_id):"
    try:
        mutate(deps, s7b_old, s7b_new)
        results["S7b"] = red_for(
            "S7b",
            lambda: run_pytest(["tests/test_rev_s7_tenant_suspend.py"]),
            ["test_suspended_tenant_blocks_authenticated_request"],
        )
    finally:
        restore(deps, s7b_old, s7b_new)

    # ── W1（我补的）：WS 握手不校验租户封禁 ─────────────────────────────
    log("\n[W1] ws.py 握手不拒绝 suspended 租户（我补的用例应打红）")
    w1_old = "    if tenant_suspended:"
    w1_new = "    if False and tenant_suspended:  # MUTATION-PROBE"
    try:
        mutate(ws_module, w1_old, w1_new)
        results["W1"] = red_for(
            "W1",
            lambda: run_pytest(["tests/unit/test_websocket_auth.py"]),
            ["test_websocket_rejects_suspended_tenant"],
        )
    finally:
        restore(ws_module, w1_old, w1_new)

    # ── 收尾：还原后复绿 + 残留判定 ────────────────────────────────────
    log("\n[final] 全部还原后复跑后端回归集")
    code, out = run_pytest(
        [
            "tests/test_rev_s2_anonymize_json.py",
            "tests/test_rev_s3_binding_tenant.py",
            "tests/test_rev_s5_pdf_cjk.py",
            "tests/test_rev_s6_warning_isolation.py",
            "tests/test_rev_s7_tenant_suspend.py",
            "tests/test_db_breaker.py",
            "tests/test_isolation_wiring_gate.py",
            "tests/unit/test_websocket_auth.py",
        ]
    )
    green_ok = code == 0
    log(f"[final] returncode={code} | {out.strip().splitlines()[-1] if out.strip() else ''}")

    log("\n[residual-check] 变异标志串计数（全部应为 0）:")
    markers = [
        # 注意：标志串必须钉**调用式**结构，不能用裸函数名 ——
        # request.ts 的解释性注释里就写着 "原写法 buildApiUrl('/auth/refresh')"，
        # 用裸串做残留判据会**误报**（本脚本第一版就踩了：残留检查报 S1 计数 1，
        # 实际代码是干净的）。这正是本仓反复出现的「断言钉结构不钉字面量」。
        (request_ts, "request.post(buildApiUrl('/auth/refresh')", "S1 URL 双拼"),
        # import 行也要单独盯：S1 变异要加一行 import，若还原参数写反（把
        # original/mututed 传反），调用会还原而 import 会**累积**残留 ——
        # 本脚本第一版就踩了这个（残留检查只盯调用，漏掉了 import 残留）。
        (request_ts, "import { buildApiUrl } from './base'", "S1 临时 import 残留"),
        (anonymize, "ev.crisis_keywords = ANON_TEXT", "S2a 裸串写入"),
        (review_service, "except (TypeError,):", "S2b 去掉 ValueError 容错"),
        (binding, "if False and (bound_user.tenant_id", "S3a 去掉绑定租户比对"),
        (counselor_user, "MUTATION-PROBE: 租户过滤被移除", "S3b 去掉详情租户过滤"),
        (uploads, "if False and (target_tenant or DEFAULT_TENANT_ID)", "S3c 去掉 uploads 租户比对"),
        (db_breaker, "if False and self._state == CircuitState.HALF_OPEN", "S4 不归还半开令牌"),
        (pdf_service, "MUTATION-PROBE: 未注册 CJK 字体", "S5 不注册 CJK 字体"),
        (risk_service, "MUTATION-PROBE: 预警未独立提交", "S6 预警未独立提交"),
        (tenant_status, "MUTATION-PROBE: 封禁永不生效", "S7a 封禁恒 False"),
        (deps, "if False and await is_tenant_suspended", "S7b 跳过封禁校验"),
        (ws_module, "if False and tenant_suspended", "W1 WS 不校验封禁"),
    ]
    residual_ok = True
    for path, marker, label in markers:
        cnt = path.read_text(encoding="utf-8").count(marker)
        if cnt:
            residual_ok = False
        log(f"    {'OK ' if cnt == 0 else '!!!'} {label}: {cnt}")

    log("\n[integrity-check] 变异目标文件字节级快照比对（须与变异前完全一致）:")
    integrity_ok = True
    for path in MUTATED_FILES:
        same = path.read_bytes() == snapshots[path]
        if not same:
            integrity_ok = False
        log(f"    {'OK ' if same else '!!!'} {path.name}: {'一致' if same else '不一致（有残留）'}")

    red_count = sum(1 for v in results.values() if v)
    log(
        f"\n[summary] RED-OK {red_count}/{len(results)} | "
        f"final GREEN-OK={green_ok} | residual-clean={residual_ok} | "
        f"integrity-clean={integrity_ok}"
    )
    for k, v in results.items():
        log(f"    {k}: {'RED-OK' if v else '!!! 未红'}")

    LOG.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    print(f"\n[written] {LOG}")
    if red_count != len(results) or not green_ok or not residual_ok or not integrity_ok:
        sys.exit(1)


if __name__ == "__main__":
    # 铁律补充：日志必须**异常路径也落盘**。否则脚本中途抛异常（例如锚点未命中）
    # 会把此前所有变异读数一起丢掉，等于什么都没证明。
    try:
        main()
    except BaseException as exc:  # noqa: BLE001
        log(f"\n[ABORT] 脚本异常终止: {type(exc).__name__}: {exc}")
        import traceback

        log(traceback.format_exc())
        LOG.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        print(f"\n[written] {LOG} (ABORT)")
        raise
    else:
        print(f"\n[written] {LOG}")
