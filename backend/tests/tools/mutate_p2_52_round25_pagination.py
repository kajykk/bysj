#!/usr/bin/env python
"""ROUND_25（B 摊：分页排序判据扩展）变异见证：五组。

BM1  去掉 review_service.get_reviews 新补的 `desc(ReviewTask.id)` 次级键
     → 闸门 test_no_unlisted_violations 红（证明本轮 14 处修复是承重墙）
BM2  从 NON_UNIQUE_SORT_COLUMNS 删掉 "status"
     → 自证 test_detects_business_column 红（业务列判据失效）
BM3  阉割 `_at` 时间戳结构判据（is_non_unique_sort_column 去掉后缀规则）
     → 自证 test_detects_timestamp_suffix_pattern 红 + 站点数哨兵红
BM4  让函数形态 desc(Model.col) 重新不可见（_col_of_sort_arg 返回 None）
     → 自证 test_detects_function_form 红 + 站点数哨兵红（58→45 < 50）
     证明 ROUND_24 的形态覆盖缺口不会再悄悄复发
BM5  反向（放行臂）：review_service 同时去掉次级键与 offset/limit
     → 闸门**放行**（绿）——证明 BM1 的红来自"分页+无次级键"，
       而不是"碰过这个文件就红"

纪律（继承 ROUND_23a / ROUND_24 / ROUND_25 A 摊）：
- 只翻转实现/判据、没翻转断言真值空间的变异不上场；
- 字节快照 + try/finally 还原；末尾 residual-clean + 还原后全绿（final-green）；
- 变异与测试**禁并发**（SQLite 争用会造假失败）——单独跑本脚本；
- pytest 必须带 --basetemp，且**每次 run 用全新目录**（复用固定目录会触发
  Windows tmp_path 的 `<name>current` copytree 竞争，非确定性 setup ERROR
  会把环境抖动伪装成闸门红绿——2026-10-22 实测教训）；产生的 basetemp
  目录由人工分批清理（环境防护按 turn 累计拦截 >50 文件的删除）。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
GATE = "tests/test_p2_51_round24_pagination_order_gate.py"
PYTHON = sys.executable
BASETEMP_PREFIX = "r25_mut_bt"

REVIEW = BACKEND / "app" / "services" / "review_service.py"
LINT = BACKEND / "tests" / "tools" / "pagination_order_lint.py"

LOG_PATH = Path(__file__).with_name("mutate_p2_52_round25_pagination_result.log")
_log_lines: list[str] = []
_created_basetemps: list[Path] = []
_run_counter = 0


def log(msg: str = "") -> None:
    print(msg)
    _log_lines.append(msg)


def run_tests() -> subprocess.CompletedProcess:
    """每次 pytest 用**全新 basetemp**。

    实测教训（2026-10-22）：复用同一个 basetemp 时，pytest 的 tmp_path
    在 Windows 上要为每个用例维护 `<name>current` 目录（无 symlink 权限时
    退化为 copytree），与 basetemp 下累积的既有目录竞争 ⇒ 非确定性的
    setup ERROR（15 个自证用例集体红，与变异内容无关）。固定 basetemp 复用
    会把环境抖动伪装成闸门红/绿，故每轮一新目录，目录保留待人工清理。
    """
    global _run_counter
    _run_counter += 1
    basetemp = BACKEND / f"{BASETEMP_PREFIX}_{_run_counter}"
    _created_basetemps.append(basetemp)
    return subprocess.run(
        [
            PYTHON,
            "-m",
            "pytest",
            GATE,
            "-o",
            "addopts=--strict-markers --import-mode=importlib",
            "-p",
            "no:cacheprovider",
            "-q",
            "--basetemp",
            str(basetemp),
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
        "id": "BM1",
        "desc": "去掉 review_service.get_reviews 新补的 id 次级键（分页仍在）",
        "file": REVIEW,
        "old": (
            "        query = query.order_by(desc(ReviewTask.created_at), desc(ReviewTask.id))\n"
            "        query = query.offset((filter_data.page - 1) * filter_data.page_size)\n"
            "        query = query.limit(filter_data.page_size)\n"
        ),
        "new": (
            "        query = query.order_by(desc(ReviewTask.created_at))  # MUTATION BM1\n"
            "        query = query.offset((filter_data.page - 1) * filter_data.page_size)\n"
            "        query = query.limit(filter_data.page_size)\n"
        ),
        "expect": "red",
        "target": "test_no_unlisted_violations",
    },
    {
        "id": "BM2",
        "desc": "从 NON_UNIQUE_SORT_COLUMNS 删掉 status（业务列判据缺员）",
        "file": LINT,
        "old": 'NON_UNIQUE_SORT_COLUMNS: frozenset[str] = frozenset({"status", "role", "level", "category"})',
        "new": 'NON_UNIQUE_SORT_COLUMNS: frozenset[str] = frozenset({"role", "level", "category"})  # MUTATION BM2',
        "expect": "red",
        "target": "test_detects_business_column",
    },
    {
        "id": "BM3",
        "desc": "阉割 _at 时间戳结构判据",
        "file": LINT,
        "old": "    return col in NON_UNIQUE_SORT_COLUMNS or col.endswith(TIMESTAMP_COLUMN_SUFFIX)",
        "new": "    return col in NON_UNIQUE_SORT_COLUMNS  # MUTATION BM3: 后缀规则被阉割",
        "expect": "red",
        "target": "test_detects_timestamp_suffix_pattern",
    },
    {
        "id": "BM4",
        "desc": "函数形态 desc(Model.col) 重新不可见（ROUND_24 覆盖缺口复发）",
        "file": LINT,
        "old": (
            "    if isinstance(func, ast.Name) and func.id in DIRECTIONS:\n"
            "        if arg.args and isinstance(arg.args[0], ast.Attribute):\n"
            "            return arg.args[0].attr  # 函数形态 desc(Model.col)\n"
        ),
        "new": (
            "    if isinstance(func, ast.Name) and func.id in DIRECTIONS:\n"
            "        return None  # MUTATION BM4: 函数形态不可见\n"
        ),
        "expect": "red",
        "target": "test_detects_function_form",
    },
    {
        "id": "BM5",
        "desc": "反向（放行臂）：review_service 同时去掉次级键与 offset/limit",
        "file": REVIEW,
        "old": (
            "        query = query.order_by(desc(ReviewTask.created_at), desc(ReviewTask.id))\n"
            "        query = query.offset((filter_data.page - 1) * filter_data.page_size)\n"
            "        query = query.limit(filter_data.page_size)\n"
        ),
        "new": (
            "        query = query.order_by(desc(ReviewTask.created_at))  # MUTATION BM5: 无分页\n"
        ),
        "expect": "green",
        "target": "",
    },
]


def main() -> int:
    log(f"# ROUND_25 B 摊变异见证 — {GATE}")
    log(f"# 闸门 collected 用例数（含自证与哨兵）: {test_count(BACKEND / GATE)}")
    log("")

    baseline = run_tests()
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
            proc = run_tests()
            out = proc.stdout + proc.stderr
            last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""

            # ERROR（setup/teardown）是环境抖动，不是判据红：
            # 指名用例必须**真的 FAILED** 才算 RED；出现 ERROR 先重跑一次。
            if re.search(r"^ERROR ", out, re.M):
                log(f"[{m['id']}] WARN 出现 ERROR（环境抖动），原样重跑一次再判")
                proc = run_tests()
                out = proc.stdout + proc.stderr
                last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""

            if m["expect"] == "red":
                target_failed = bool(
                    re.search(rf"^FAILED .*{re.escape(m['target'])}(\s|$)", out, re.M)
                )
                if proc.returncode != 0 and target_failed:
                    red_ok += 1
                    log(f"[{m['id']}] RED-OK  {m['desc']}")
                    log(f"       指名用例 {m['target']} 变红；{last}")
                else:
                    log(
                        f"[{m['id']}] ❌ WRONG-TARGET returncode={proc.returncode} "
                        f"target_failed={target_failed}"
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

    final = run_tests()
    log("")
    log(f"[final] returncode={final.returncode}")
    if final.stdout.strip():
        log(final.stdout.strip().splitlines()[-1])

    log(
        f"[basetemp] {len(_created_basetemps)} fresh dirs kept for manual cleanup: "
        + ", ".join(p.name for p in _created_basetemps)
        + "（环境防护按 turn 累计拦截 >50 文件的删除，故不在脚本内 rmtree）"
    )

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
