#!/usr/bin/env python
"""ROUND_23a（M13）变异见证：四个变异锚点，各自指名一条必须变红的用例。

T1  删掉 model 的部分唯一 Index（uq_intervention_plans_active_per_user）
    → 测试库 create_all 无约束 ⇒ 并发用例 active 变 2 条
    → 指名 test_concurrent_assessments_yield_single_active_plan
T2  except SAIntegrityError 的「回查并返回」改回直接 raise
    → 确定性交错用例里 B 的冲突无人接 ⇒ 异常逃逸
    → 指名 test_second_writer_recovers_from_unique_conflict
T3  迁移的 find_duplicate_active_plans 改成恒返回 []（冲突检测失效）
    → upgrade 不再中止 ⇒ 迁移中止契约用例红
    → 指名 test_upgrade_aborts_on_conflicts_without_creating_index
T4  升级路径 savepoint 内「无模板时撤销让位」被删
    → 旧 active 计划停在 cancelled，用户失去所有干预（M17 语义被破坏）
    → 指名 test_level_elevation_without_template_keeps_old_plan

纪律：
- 只翻转实现、没翻转断言真值空间的变异不上场（四组均直接改变被测事实）；
- 字节快照 + try/finally 还原；工作树有未提交改动时本脚本不适用（断言前置）；
- 变异与测试**禁并发**（SQLite 文件库争用会造假失败）；
- 末尾残差清洁（residual-clean）+ 还原后全绿（final-green）。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
GATE = "tests/test_p2_48_round23a_m13_intervention_unique.py"
PYTHON = sys.executable

MODEL_FILE = BACKEND / "app" / "models" / "intervention.py"
SERVICE_FILE = BACKEND / "app" / "services" / "risk_service_warning.py"
MIGRATION_FILE = (
    BACKEND / "alembic" / "versions" / "r2a3b4c5d6e7_add_intervention_active_unique.py"
)

LOG_PATH = Path(__file__).with_name("mutate_p2_48_round23a_result.log")
_log_lines: list[str] = []


def log(msg: str = "") -> None:
    print(msg)
    _log_lines.append(msg)


def run_gate() -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [PYTHON, "-m", "pytest", GATE, "-o", "addopts=--strict-markers --import-mode=importlib", "-p", "no:cacheprovider", "-q"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=900,
    )
    return proc


def gate_count() -> int:
    src = (BACKEND / GATE).read_text(encoding="utf-8")
    return len(re.findall(r"^\s+def (test_[A-Za-z0-9_]+)", src, re.M))


MUTATIONS = [
    {
        "id": "T1",
        "desc": "删掉 model 的部分唯一 Index（uq_intervention_plans_active_per_user）",
        "file": MODEL_FILE,
        "old": """        Index(
            "uq_intervention_plans_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
""",
        "new": """        # MUTATION T1: 部分唯一索引声明被删除
""",
        "target": "test_concurrent_assessments_yield_single_active_plan",
    },
    {
        "id": "T2",
        "desc": "except SAIntegrityError 的「回查并返回」改回直接 raise",
        "file": SERVICE_FILE,
        "old": """            if existing is not None:
                record_silent_degradation(
                    "services.risk_service_warning.active_plan_conflict_recovered"
                )
                logger.info(
                    "intervention.active_plan_conflict_recovered user_id=%s "
                    "existing_plan_id=%s risk_level=%s",
                    user_id,
                    existing.id,
                    risk_level,
                )
                return existing
""",
        "new": """            raise  # MUTATION T2: 回查并返回已存在计划的分支被删除
""",
        "target": "test_second_writer_recovers_from_unique_conflict",
    },
    {
        "id": "T3",
        "desc": "upgrade 把「有冲突则中止」改成恒真通过（if conflicts → if False）",
        "file": MIGRATION_FILE,
        "old": """    conflicts = find_duplicate_active_plans(bind)
    if conflicts:
""",
        "new": """    conflicts = find_duplicate_active_plans(bind)
    if False:  # MUTATION T3: 检测结果被无视，存量重复不再中止升级
""",
        "target": "test_upgrade_aborts_on_conflicts_without_creating_index",
    },
    {
        "id": "T4",
        "desc": "升级路径 savepoint 内「无模板时撤销让位」被删（旧计划停在 cancelled）",
        "file": SERVICE_FILE,
        "old": """                    if new_plan is None:
                        existing_plan.status = "active"
                        await self.db.flush()
""",
        "new": """                    if new_plan is None:
                        pass  # MUTATION T4: 撤销让位被删，旧计划停在 cancelled
""",
        "target": "test_level_elevation_without_template_keeps_old_plan",
    },
]


def main() -> int:
    log(f"# ROUND_23a（M13）变异见证 — {GATE}")
    log(f"# 用例函数数 {gate_count()}（含参数化展开后以 [final] 行为准）")
    log("")

    green = run_gate()
    log(f"[baseline] returncode={green.returncode}")
    log(green.stdout.strip().splitlines()[-1] if green.stdout.strip() else "")
    if green.returncode != 0:
        log("[baseline] ❌ 基线非绿，终止（先修实现再变异）")
        LOG_PATH.write_text("\n".join(_log_lines) + "\n", encoding="utf-8")
        return 1

    red_ok = 0
    residual_clean = True
    for m in MUTATIONS:
        path = m["file"]
        original = path.read_bytes()
        try:
            text = path.read_text(encoding="utf-8")
            count = text.count(m["old"])
            if count != 1:
                log(f"[{m['id']}] ❌ 锚点命中 {count} 次（应恰 1 次），跳过")
                residual_clean = False
                continue
            path.write_text(text.replace(m["old"], m["new"]), encoding="utf-8")
            proc = run_gate()
            out = proc.stdout + proc.stderr
            target_hit = m["target"] in out
            if proc.returncode != 0 and target_hit:
                red_ok += 1
                log(f"[{m['id']}] RED-OK 指名用例 {m['target']} 变红")
                for line in out.splitlines():
                    if line.startswith("FAILED"):
                        log(f"  {line}")
            else:
                log(
                    f"[{m['id']}] ❌ WRONG-TARGET returncode={proc.returncode} "
                    f"target_hit={target_hit}（指名 {m['target']}）"
                )
                for line in out.splitlines()[-25:]:
                    log(f"  | {line}")
        finally:
            path.write_bytes(original)

    final = run_gate()
    log("")
    log(f"[final] returncode={final.returncode}")
    log(final.stdout.strip().splitlines()[-1] if final.stdout.strip() else "")
    log(
        f"[summary] {red_ok}/{len(MUTATIONS)} RED-OK; "
        f"residual_clean={residual_clean}; final_green={final.returncode == 0}"
    )
    if final.returncode != 0:
        for line in (final.stdout + final.stderr).splitlines()[-30:]:
            log(f"  | {line}")

    LOG_PATH.write_text("\n".join(_log_lines) + "\n", encoding="utf-8")
    ok = red_ok == len(MUTATIONS) and residual_clean and final.returncode == 0
    log(f"[exit] {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
