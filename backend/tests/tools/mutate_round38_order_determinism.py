#!/usr/bin/env python
"""ROUND_38 排序确定性闸门变异验证（结果见 mutate_round38_order_determinism_result.log）。

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
T = "tests/test_p2_62_round38_order_determinism.py"


def node(test: str) -> str:
    return f"{T}::{test}"


TARGETS_FAST = [
    T,
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
        if any(k in s for k in ("passed", "failed", "AssertionError", "ValueError")):
            keep.append(s[:140])
    return "\n".join(keep[:5]) or "(无关键行)"


MUTATIONS: list[tuple[str, Path, str, str, list[str], bool]] = [
    (
        "M1 去掉咨询师用户详情风险时间线的 id 次级键",
        BACKEND / "app" / "services" / "counselor_service_user.py",
        ".order_by(RiskAssessment.created_at.desc(), RiskAssessment.id.desc())",
        ".order_by(RiskAssessment.created_at.desc())",
        [
            node("TestBehavioralOrderDeterminism::"
                 "test_counselor_user_detail_timelines_have_tie_break"),
            node("TestStructuralOrderDeterminism"),
        ],
        False,
    ),
    (
        "M2 去掉危机导出 CSV 的 id 次级键",
        BACKEND / "app" / "services" / "crisis_export_service.py",
        ".order_by(CrisisEvent.created_at.desc(), CrisisEvent.id.desc())",
        ".order_by(CrisisEvent.created_at.desc())",
        [
            node("TestBehavioralOrderDeterminism::test_crisis_export_has_tie_break"),
            node("TestStructuralOrderDeterminism"),
        ],
        False,
    ),
    (
        "M3 去掉活跃干预计划选取的 id 次级键",
        BACKEND / "app" / "services" / "intervention_service.py",
        ".where(\n                InterventionPlan.user_id == user_id, "
        "InterventionPlan.status == \"active\"\n            )\n"
        "            .order_by(InterventionPlan.created_at.desc(), "
        "InterventionPlan.id.desc())\n            .limit(1)",
        ".where(\n                InterventionPlan.user_id == user_id, "
        "InterventionPlan.status == \"active\"\n            )\n"
        "            .order_by(InterventionPlan.created_at.desc())\n            .limit(1)",
        [
            node("TestBehavioralOrderDeterminism::"
                 "test_intervention_active_plan_has_tie_break"),
            node("TestStructuralOrderDeterminism"),
        ],
        False,
    ),
    (
        "M4 去掉预警判定「上一条评估」的 id 次级键",
        BACKEND / "app" / "services" / "risk_service_warning.py",
        ".order_by(RiskAssessment.created_at.desc(), RiskAssessment.id.desc())"
        "\n            .limit(1)\n        )\n        previous =",
        ".order_by(RiskAssessment.created_at.desc())"
        "\n            .limit(1)\n        )\n        previous =",
        [
            node("TestBehavioralOrderDeterminism::"
                 "test_warning_trigger_previous_has_tie_break"),
            node("TestStructuralOrderDeterminism"),
        ],
        False,
    ),
    (
        "M5 去掉异常检测窗口「每用户取最新」的 id 次级键",
        BACKEND / "app" / "services" / "anomaly_detection_service.py",
        "partition_by=[OperationLog.operator_id, OperationLog.operator_role],\n"
        "            order_by=(OperationLog.created_at.desc(), OperationLog.id.desc()),",
        "partition_by=[OperationLog.operator_id, OperationLog.operator_role],\n"
        "            order_by=OperationLog.created_at.desc(),",
        [node("TestStructuralOrderDeterminism")],
        False,
    ),
    (
        "M6 去掉内容审核历史的 id 次级键",
        BACKEND / "app" / "api" / "v1" / "content_governance.py",
        ".order_by(OperationLog.created_at.desc(), OperationLog.id.desc())",
        ".order_by(OperationLog.created_at.desc())",
        [node("TestStructuralOrderDeterminism")],
        False,
    ),
    (
        "M7 去掉偏好品类 top3 的并列裁决键",
        BACKEND / "app" / "services" / "content_service.py",
        ".order_by(\n                func.count(ContentViewHistory.id).desc(), "
        "EducationContent.category.asc()\n            )",
        ".order_by(\n                func.count(ContentViewHistory.id).desc()\n            )",
        [node("TestStructuralOrderDeterminism")],
        False,
    ),
    (
        "M8 去掉运维看板近期审计的 id 次级键",
        BACKEND / "app" / "api" / "v1" / "ops_dashboard.py",
        ".order_by(OperationLog.created_at.desc(), OperationLog.id.desc())",
        ".order_by(OperationLog.created_at.desc())",
        [
            node("TestBehavioralOrderDeterminism::"
                 "test_recent_audit_events_have_tie_break"),
        ],
        False,
    ),
    (
        "M9 删掉 config_key 的唯一约束（豁免前提失效）",
        BACKEND / "app" / "models" / "admin.py",
        "config_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)",
        "config_key: Mapped[str] = mapped_column(String(100), nullable=False)",
        [node("TestExemptions::test_config_key_is_unique")],
        False,
    ),
]


def main() -> int:
    log: list[str] = []
    failures = 0

    rc, out = run_pytest(TARGETS_FAST)
    log.append("=== 基线（未变异，必须绿） ===")
    log.append(f"exit = {rc}")
    log.append(summarize(out))
    if rc != 0:
        log.append("!!! 基线就红，后续变异结论无效")
        Path(__file__).with_name("mutate_round38_order_determinism_result.log").write_text(
            "\n".join(log) + "\n", encoding="utf-8")
        print("\n".join(log))
        return 1

    for name, path, old, new, targets, needs_rerun in MUTATIONS:
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

    rc, out = run_pytest(TARGETS_FAST)
    log.append("\n=== 恢复后 GREEN 对照 ===")
    log.append(f"exit = {rc}（期望 0）")
    log.append(summarize(out))
    if rc != 0:
        failures += 1

    log.append(f"\n===== 结论：{'全部通过' if failures == 0 else f'{failures} 项异常'} =====")
    report = "\n".join(log)
    print(report)
    Path(__file__).with_name("mutate_round38_order_determinism_result.log").write_text(
        report + "\n", encoding="utf-8")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
