"""P2-31 回退对照实验驱动：每项机制改动做「变异→确认红→恢复→确认绿」。

纪律（来自 MEMORY.md「验证工具自身的失效会伪装成修复有效」）：
- subprocess 显式 encoding="utf-8"（Windows 默认 GBK 会把 UTF-8 输出的失败
  标记译成乱码 → failed 集合恒空 → 变异轮假通过）；
- 驱动自检：变异轮若检不出任何 failed，实验判 INVALID 并显式报出，不算通过；
- 每个变异恢复后做字节级还原校验，再跑恢复轮。

用法：cd backend && .venv/Scripts/python.exe scripts/rollback_experiments_p2_31.py
产物：scripts/rollback_p2_31_result.log（完整读数，提交信息引用）
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PYTEST = BACKEND / ".venv" / "Scripts" / "python.exe"
LOG_PATH = Path(__file__).resolve().parent / "rollback_p2_31_result.log"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class Mutation:
    name: str
    file: str  # 相对 backend 的路径
    old: str
    new: str
    targets: list[str]  # pytest 目标（文件或 ::用例）
    expect_red: list[str]  # 期望变红的用例名片段（空列表 = 期望目标文件整体红）
    note: str = ""


@dataclass
class ExperimentResult:
    name: str
    mutation_round: dict = field(default_factory=dict)
    restore_round: dict = field(default_factory=dict)
    verdict: str = "PENDING"


MUTATIONS: list[Mutation] = [
    Mutation(
        name="E1a 卸载测试引擎闸门",
        file="tests/conftest.py",
        old="install_tenant_guard(engine)",
        new="# 变异：临时卸载闸门\n# install_tenant_guard(engine)",
        targets=["tests/test_p2_31_tenant_guard.py::TestGuardMechanism::test_guard_installed_on_test_engine"],
        expect_red=["test_guard_installed_on_test_engine"],
        note="闸门未安装 → 元断言红；同时所有反向闸门失去对象",
    ),
    Mutation(
        name="E1b 服务层 JOIN 手写回归（闸门在位）",
        file="app/services/review_service.py",
        old="""        stmt = user_tenant_scoped_query(ReviewTask, tenant_id).where(
            ReviewTask.id == review_id
        )""",
        new="""        stmt = select(ReviewTask).where(ReviewTask.id == review_id)""",
        targets=[
            "tests/test_p2_31_tenant_guard.py::TestServiceBehaviorUnderGuard::test_get_review_by_id_cross_tenant_returns_none",
            "tests/test_p2_31_tenant_guard.py::TestServiceBehaviorUnderGuard::test_get_review_by_id_same_tenant_returns_task",
        ],
        expect_red=["test_get_review_by_id_cross_tenant_returns_none", "test_get_review_by_id_same_tenant_returns_task"],
        note="模拟根因段失效模式：手写裸查询忘 JOIN → 执行层现红",
    ),
    Mutation(
        name="E2 tenant_id 必填退化为默认值",
        file="app/services/review_service.py",
        old="""    async def get_review_by_id(
        self, review_id: int, *, tenant_id: int
    ) -> ReviewTask | None:""",
        new="""    async def get_review_by_id(
        self, review_id: int, *, tenant_id: int = 1
    ) -> ReviewTask | None:""",
        targets=[
            "tests/test_p2_31_tenant_guard.py::TestReverseGates::test_tenant_id_is_required_keyword",
            "tests/test_p2_31_tenant_guard.py::TestReverseGates::test_missing_tenant_id_call_raises_typeerror",
        ],
        expect_red=["test_tenant_id_is_required_keyword", "test_missing_tenant_id_call_raises_typeerror"],
        note="漏传从 TypeError 变静默租户 1 —— 范式②的闸门必须红",
    ),
    Mutation(
        name="E3 create_review_task 幂等检查豁免移除",
        file="app/services/review_service.py",
        old="""            .limit(1)
            .execution_options(tenant_exempt="system_internal_idempotency_check")
        )""",
        new="""            .limit(1)
        )""",
        targets=[
            "tests/test_p2_31_tenant_guard.py::TestServiceBehaviorUnderGuard::test_get_review_by_id_same_tenant_returns_task",
        ],
        expect_red=["test_get_review_by_id_same_tenant_returns_task"],
        note="豁免标记删除 → 系统内部写路径被闸门拦下 → 红",
    ),
    Mutation(
        name="E4 ops_dashboard 一条豁免移除",
        file="app/api/v1/ops_dashboard.py",
        old="""            .where(
                ReviewTask.priority == "crisis_review",
                ReviewTask.status.in_(["pending", "in_review"]),
            )
            .execution_options(tenant_exempt="platform_admin_ops_dashboard")
        )
    ).scalar_one()""",
        new="""            .where(
                ReviewTask.priority == "crisis_review",
                ReviewTask.status.in_(["pending", "in_review"]),
            )
        )
    ).scalar_one()""",
        targets=["tests/api/test_ops_dashboard_api.py"],
        expect_red=[],
        note="平台看板 overview 聚合打到该语句 → 文件内至少一红",
    ),
    Mutation(
        name="E5 crisis_export 豁免移除",
        file="app/services/crisis_export_service.py",
        old="""            .execution_options(
                yield_per=1000,
                tenant_exempt="platform_admin_crisis_export",
            )""",
        new="""            .execution_options(yield_per=1000)""",
        targets=["tests/services/test_crisis_export_service.py"],
        expect_red=[],
        note="tenant_id=None 默认路径（平台管理员全量导出）被拦 → 红",
    ),
    Mutation(
        name="E6 gdpr 导出豁免移除",
        file="app/services/gdpr_service_export.py",
        old="""                    select(CrisisEvent)
                    .where(CrisisEvent.user_id == user_id)
                    .execution_options(tenant_exempt="data_subject_gdpr")""",
        new="""                    select(CrisisEvent)
                    .where(CrisisEvent.user_id == user_id)""",
        targets=["tests/services/test_gdpr_service.py", "tests/test_gdpr_pii.py"],
        expect_red=[],
        note="数据主体导出被拦 → 红",
    ),
    Mutation(
        name="E7 测试夹具豁免移除",
        file="tests/api/test_review_assign_auth.py",
        old="""            select(ReviewTask)
            .where(ReviewTask.id == task_id)
            .execution_options(tenant_exempt="test_row_verification")""",
        new="""            select(ReviewTask)
            .where(ReviewTask.id == task_id)""",
        targets=["tests/api/test_review_assign_auth.py"],
        expect_red=[],
        note="_reload 回读被拦 → 红",
    ),
    Mutation(
        name="E9 受保护表被塞进白名单棘轮集合（退化解法）",
        file="tests/test_isolation_wiring_gate.py",
        old='TENANT_SENSITIVE_MODELS = {"User", "OperationLog"}',
        new='TENANT_SENSITIVE_MODELS = {"User", "OperationLog", "ReviewTask"}',
        targets=["tests/test_isolation_wiring_gate.py"],
        expect_red=[
            "test_no_new_unfiltered_tenant_queries",
            "test_protected_models_absent_from_ratchet_set",
            "test_ratchet_anchor_assumption_still_holds",
        ],
        note="把无 tenant_id 列的受保护表加进棘轮 → 既有棘轮误报正确隔离的服务文件，"
        "新增的两条分流断言同时红（闸门 4 反向验证）",
    ),
]


def run_pytest(targets: list[str]) -> tuple[str, int, int, list[str]]:
    """跑 pytest，返回 (原始输出, passed 数, failed 数, 失败用例名列表)。"""
    cmd = [
        str(PYTEST), "-m", "pytest", *targets,
        "-o", "addopts=--import-mode=importlib",
        "-p", "no:cacheprovider", "-q", "--no-header",
    ]
    proc = subprocess.run(cmd, cwd=BACKEND, capture_output=True, encoding="utf-8", errors="replace")
    out = _ANSI_RE.sub("", proc.stdout + proc.stderr)
    failed_names = re.findall(r"^FAILED (\S+)", out, re.M)
    m = re.search(r"(\d+) failed", out)
    n_failed = int(m.group(1)) if m else 0
    m2 = re.search(r"(\d+) passed", out)
    n_passed = int(m2.group(1)) if m2 else 0
    return out, n_passed, n_failed, failed_names


def apply_mutation(mut: Mutation) -> None:
    path = BACKEND / mut.file
    src = path.read_text(encoding="utf-8")
    assert src.count(mut.old) == 1, f"{mut.file}: 变异锚点不唯一（{src.count(mut.old)} 处）"
    path.write_text(src.replace(mut.old, mut.new), encoding="utf-8")


def restore_mutation(mut: Mutation, original: str) -> None:
    path = BACKEND / mut.file
    current = path.read_text(encoding="utf-8")
    assert current == mut.new.replace("\n", "\n") or True  # 宽松：下面按原文还原
    path.write_text(original, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == original, f"{mut.file}: 还原校验失败"


def main() -> int:
    log_lines: list[str] = []
    results: list[ExperimentResult] = []

    for mut in MUTATIONS:
        res = ExperimentResult(name=mut.name)
        path = BACKEND / mut.file
        original = path.read_text(encoding="utf-8")
        log_lines.append(f"\n{'=' * 78}\n{mut.name}\n  说明: {mut.note}\n  文件: {mut.file}\n  目标: {mut.targets}")

        try:
            apply_mutation(mut)
            out, n_passed, n_failed, failed_names = run_pytest(mut.targets)
            res.mutation_round = {"passed": n_passed, "failed": n_failed, "failed_names": failed_names}
            log_lines.append(f"  [变异轮] passed={n_passed} failed={n_failed}")
            for name in failed_names:
                log_lines.append(f"    RED: {name}")
            if n_failed == 0:
                log_lines.append("  !! 变异轮零失败 → 实验无效（验证工具失效或变异未生效）")
                res.verdict = "INVALID"
                results.append(res)
                continue
            if mut.expect_red:
                missing = [e for e in mut.expect_red if not any(e in n for n in failed_names)]
                if missing:
                    log_lines.append(f"  !! 期望变红未出现: {missing} → 实验无效")
                    res.verdict = "INVALID"
                    results.append(res)
                    continue
        finally:
            restore_mutation(mut, original)

        # 恢复轮
        out, n_passed, n_failed, failed_names = run_pytest(mut.targets)
        res.restore_round = {"passed": n_passed, "failed": n_failed, "failed_names": failed_names}
        log_lines.append(f"  [恢复轮] passed={n_passed} failed={n_failed}")
        if n_failed != 0:
            log_lines.append("  !! 恢复轮仍有失败 → 还原不完整")
            res.verdict = "RESTORE_FAILED"
        else:
            res.verdict = "PASS"
        results.append(res)

    # E1c 复合变异：无闸门 + JOIN 回归（证明没有机制时泄露真实存在）
    log_lines.append(f"\n{'=' * 78}\nE1c 复合变异：卸载闸门 + 服务层 JOIN 回归")
    conf = BACKEND / "tests/conftest.py"
    svc = BACKEND / "app/services/review_service.py"
    conf_orig = conf.read_text(encoding="utf-8")
    svc_orig = svc.read_text(encoding="utf-8")
    target = [
        "tests/test_p2_31_tenant_guard.py::TestServiceBehaviorUnderGuard::test_get_review_by_id_cross_tenant_returns_none",
    ]
    try:
        conf.write_text(conf_orig.replace(
            "install_tenant_guard(engine)",
            "# 变异：临时卸载闸门\n# install_tenant_guard(engine)",
        ), encoding="utf-8")
        svc.write_text(svc_orig.replace(
            """        stmt = user_tenant_scoped_query(ReviewTask, tenant_id).where(
            ReviewTask.id == review_id
        )""",
            """        stmt = select(ReviewTask).where(ReviewTask.id == review_id)""",
        ), encoding="utf-8")
        out, n_passed, n_failed, failed_names = run_pytest(target)
        log_lines.append(f"  [复合变异轮] passed={n_passed} failed={n_failed}")
        for name in failed_names:
            log_lines.append(f"    RED: {name}")
        assert "test_get_review_by_id_cross_tenant_returns_none" in " ".join(failed_names), (
            "复合变异未使跨租户用例变红 —— 要么泄露不存在（不可能），要么驱动失效"
        )
        verdict = "PASS" if n_failed else "INVALID"
    finally:
        conf.write_text(conf_orig, encoding="utf-8")
        svc.write_text(svc_orig, encoding="utf-8")
    out, n_passed, n_failed, _ = run_pytest(target)
    log_lines.append(f"  [恢复轮] passed={n_passed} failed={n_failed}")
    if n_failed:
        verdict = "RESTORE_FAILED"
    results.append(ExperimentResult(
        name="E1c 复合变异（无闸门+JOIN回归）",
        verdict=verdict,
    ))

    # 汇总
    log_lines.append(f"\n{'=' * 78}\n汇总")
    invalid = [r for r in results if r.verdict != "PASS"]
    for r in results:
        log_lines.append(f"  [{r.verdict}] {r.name}")
    log_lines.append(f"\n结论: {len(results) - len(invalid)}/{len(results)} 项通过"
                     + (f"；未通过: {[r.name for r in invalid]}" if invalid else "（无）"))

    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print("\n".join(log_lines[-12:]))
    print(f"\n完整日志: {LOG_PATH}")
    return 0 if not invalid else 1


if __name__ == "__main__":
    sys.exit(main())
