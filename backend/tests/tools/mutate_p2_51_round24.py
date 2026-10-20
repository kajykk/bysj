#!/usr/bin/env python
"""ROUND_24（分页排序确定性）变异见证：五组，各自指名一条必须变红/必须放行的用例。

T1  去掉 intervention_service.get_history 的 `id.desc()` 次级键
    → 闸门 test_no_unlisted_violations 红（结构见证）
    → 顺带跑行为测试：test_intervention_history_pages_are_disjoint 也红
      （证明本机 SQLite 上「并列组内 id 降序」这半边断言确有区分力）
T2  白名单里塞一条指向不存在文件的伪造条目
    → 防腐烂 test_whitelist_entries_are_real 红（"腐烂条目"）
T3  同一处（get_history）**同时**去掉次级键与 offset/limit
    → 站点退化为"无分页子句" ⇒ 闸门**放行**（绿）
      反向证明 T1 的红来自"分页+无次级键"，而不是"改了这个文件就红"
T4  user_data_service.get_history 的 `StructuredAssessment.id.desc()` 被删
    → 闸门红：验证 **变量拆分形态**（order_by 与 offset 分两行）的检出能力
T5  给白名单站点 content_governance.get_content_history 接上 `.offset(0)`
    → 防腐烂 test_whitelist_entries_are_real 红（"已接 offset"）
      证明白名单不能被用来豁免真分页

纪律（继承 ROUND_23a）：
- 只翻转实现、不翻转断言真值空间的变异不上场；
- 字节快照 + try/finally 还原；末尾 residual-clean + 还原后全绿（final-green）；
- 变异与测试**禁并发**（SQLite 争用会造假失败）。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
GATE = "tests/test_p2_51_round24_pagination_order_gate.py"
BEHAVIOR = "tests/test_p2_51_round24_pagination_behavior.py"
PYTHON = sys.executable

INTERVENTION = BACKEND / "app" / "services" / "intervention_service.py"
USER_DATA = BACKEND / "app" / "services" / "user_data_service.py"
CONTENT_GOV = BACKEND / "app" / "api" / "v1" / "content_governance.py"
GATE_FILE = BACKEND / GATE

LOG_PATH = Path(__file__).with_name("mutate_p2_51_round24_result.log")
_log_lines: list[str] = []


def log(msg: str = "") -> None:
    print(msg)
    _log_lines.append(msg)


def run_tests(*targets: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            PYTHON,
            "-m",
            "pytest",
            *targets,
            "-o",
            "addopts=--strict-markers --import-mode=importlib",
            "-p",
            "no:cacheprovider",
            "-q",
        ],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=900,
    )


def test_count(path: Path) -> int:
    src = path.read_text(encoding="utf-8")
    return len(re.findall(r"^\s+(?:async )?def (test_[A-Za-z0-9_]+)", src, re.M))


MUTATIONS = [
    {
        "id": "T1",
        "desc": "去掉 get_history 的 id.desc() 次级键（分页仍在）",
        "file": INTERVENTION,
        "old": (
            "            .order_by(InterventionPlan.created_at.desc(), "
            "InterventionPlan.id.desc())\n"
            "            .offset(offset)\n"
        ),
        "new": (
            "            .order_by(InterventionPlan.created_at.desc())  "
            "# MUTATION T1\n"
            "            .offset(offset)\n"
        ),
        "expect": "red",
        "test": GATE,
        "target": "test_no_unlisted_violations",
    },
    {
        "id": "T2",
        "desc": "白名单塞入指向不存在文件的伪造条目",
        "file": GATE_FILE,
        "old": 'PAGING_WHITELIST: dict[tuple[str, str, tuple[str, ...]], tuple[int, str]] = {\n',
        "new": (
            'PAGING_WHITELIST: dict[tuple[str, str, tuple[str, ...]], tuple[int, str]] = {\n'
            '    ("services/renamed_away.py", "renamed_func", ("created_at",)): '
            '(1, "MUTATION T2 伪造条目"),\n'
        ),
        "expect": "red",
        "test": GATE,
        "target": "test_whitelist_entries_are_real",
        "expect_msg": "腐烂条目",
    },
    {
        "id": "T3",
        "desc": "同处同时去掉次级键与 offset/limit（退化为无分页）",
        "file": INTERVENTION,
        "old": (
            "            .order_by(InterventionPlan.created_at.desc(), "
            "InterventionPlan.id.desc())\n"
            "            .offset(offset)\n"
            "            .limit(page_size)\n"
        ),
        "new": (
            "            .order_by(InterventionPlan.created_at.desc())  "
            "# MUTATION T3: 无分页子句\n"
        ),
        "expect": "green",
        "test": GATE,
        "target": "",
    },
    {
        "id": "T4",
        "desc": "user_data_service 变量拆分形态去次级键",
        "file": USER_DATA,
        "old": (
            "                .order_by(\n"
            "                    StructuredAssessment.created_at.desc(),\n"
            "                    StructuredAssessment.id.desc(),\n"
            "                )\n"
        ),
        "new": (
            "                .order_by(\n"
            "                    StructuredAssessment.created_at.desc(),\n"
            "                )  # MUTATION T4\n"
        ),
        "expect": "red",
        "test": GATE,
        "target": "test_no_unlisted_violations",
    },
    {
        "id": "T5",
        "desc": "白名单站点接上 offset（单页变真分页）",
        "file": CONTENT_GOV,
        "old": (
            "                .order_by(OperationLog.created_at.desc())\n"
            "                .limit(100)\n"
        ),
        "new": (
            "                .order_by(OperationLog.created_at.desc())  # MUTATION T5\n"
            "                .offset(0)\n"
            "                .limit(100)\n"
        ),
        "expect": "red",
        "test": GATE,
        "target": "test_whitelist_entries_are_real",
        "expect_msg": "已接 offset",
    },
]


def main() -> int:
    log(f"# ROUND_24 变异见证 — {GATE}")
    log(f"# 闸门用例数 {test_count(GATE_FILE)}；行为用例数 {test_count(BACKEND / BEHAVIOR)}")
    log("")

    baseline = run_tests(GATE)
    log(f"[baseline] returncode={baseline.returncode}")
    if baseline.stdout.strip():
        log(baseline.stdout.strip().splitlines()[-1])
    if baseline.returncode != 0:
        log("[baseline] ❌ 基线非绿，终止（先修实现再变异）")
        LOG_PATH.write_text("\n".join(_log_lines) + "\n", encoding="utf-8")
        return 1

    red_ok = 0
    green_ok = 0
    residual_clean = True

    for m in MUTATIONS:
        path: Path = m["file"]
        original = path.read_bytes()
        try:
            text = path.read_text(encoding="utf-8")
            hits = text.count(m["old"])
            if hits != 1:
                log(f"[{m['id']}] ❌ 锚点命中 {hits} 次（应恰 1 次），跳过：{m['desc']}")
                residual_clean = False
                continue
            path.write_text(text.replace(m["old"], m["new"]), encoding="utf-8")
            proc = run_tests(m["test"])
            out = proc.stdout + proc.stderr
            last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""

            if m["expect"] == "red":
                target_hit = m["target"] in out
                msg_hit = ("expect_msg" not in m) or (m["expect_msg"] in out)
                if proc.returncode != 0 and target_hit and msg_hit:
                    red_ok += 1
                    log(f"[{m['id']}] RED-OK  {m['desc']}")
                    log(f"       指名用例 {m['target']} 变红；{last}")
                else:
                    log(
                        f"[{m['id']}] ❌ WRONG-TARGET returncode={proc.returncode} "
                        f"target_hit={target_hit} msg_hit={msg_hit}"
                    )
                    for line in out.splitlines()[-20:]:
                        log(f"  | {line}")
            else:
                if proc.returncode == 0:
                    green_ok += 1
                    log(f"[{m['id']}] GREEN-OK 放行臂成立（无分页 ⇒ 不判违规）：{m['desc']}")
                    log(f"       {last}")
                else:
                    log(f"[{m['id']}] ❌ 放行臂失效（应绿却红）：{m['desc']}")
                    for line in out.splitlines()[-20:]:
                        log(f"  | {line}")
        finally:
            path.write_bytes(original)

    # T1 的附带读数：行为断言在同一变异下是否也红（诚实记录区分力）
    original = INTERVENTION.read_bytes()
    try:
        text = INTERVENTION.read_text(encoding="utf-8")
        t1 = MUTATIONS[0]
        if text.count(t1["old"]) == 1:
            INTERVENTION.write_text(text.replace(t1["old"], t1["new"]), encoding="utf-8")
            beh = run_tests(BEHAVIOR)
            hit = "test_intervention_history_pages_are_disjoint" in (beh.stdout + beh.stderr)
            log("")
            log(
                f"[T1-behavior] returncode={beh.returncode} target_hit={hit}"
                "（行为断言对并列组内 id 降序有区分力）"
            )
            for line in beh.stdout.splitlines():
                if line.startswith("FAILED"):
                    log(f"  {line}")
    finally:
        INTERVENTION.write_bytes(original)

    final = run_tests(GATE, BEHAVIOR)
    log("")
    log(f"[final] returncode={final.returncode}")
    if final.stdout.strip():
        log(final.stdout.strip().splitlines()[-1])

    residual = []
    for p in {m["file"] for m in MUTATIONS}:
        if "MUTATION" in p.read_text(encoding="utf-8"):
            residual.append(str(p))
    residual_clean = residual_clean and not residual
    log(f"[residual] {'CLEAN' if not residual else residual}")

    log(
        f"[summary] {red_ok} RED-OK + {green_ok} GREEN-OK / {len(MUTATIONS)}；"
        f"residual_clean={residual_clean}; final_green={final.returncode == 0}"
    )
    ok = (
        red_ok == sum(1 for m in MUTATIONS if m["expect"] == "red")
        and green_ok == sum(1 for m in MUTATIONS if m["expect"] == "green")
        and residual_clean
        and final.returncode == 0
    )
    log(f"[exit] {'PASS' if ok else 'FAIL'}")
    LOG_PATH.write_text("\n".join(_log_lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
