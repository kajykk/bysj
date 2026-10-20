"""ROUND_19 M 批 2 变异见证：改坏一处实现，对应用例必须指名变红。

判据不是"变红就算过"——而是**红在正确的地方**：每条变异都指名一条
ROUND_19 测试（M10–M16 六条修复各至少一处），失败输出里必须出现该用例名，
否则说明是靠别的用例连带报红。

七处变异与六条修复的对应：
- M11：绕过完成率钳制 + silent_degradation 记账 ⇒ 越界用例红；
- M12a：threshold_level 不再被消费（回落写死默认值）⇒ 阈值=1 用例红；
- M12b：`_NOT_EFFECTIVE_KEYS` 被掏空 ⇒ "不生效"声明用例红；
- M14：事件改为提交前即发布 ⇒ after-commit 计数用例红；
- M15：total_users 不再排除匿名化用户 ⇒ 前后对比用例红；
- M16：导出移除一个 section ⇒ 覆盖面对齐用例红；
- M10：end 不再扩张到当天结束 ⇒ 边界用例红。

每处变异都先存字节快照，``finally`` 还原；收尾比对字节一致、再跑一次全绿。
日志同时写 stdout 与 ``mutate_p2_47_round19_result.log``。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent

INTERVENTION = BACKEND / "app" / "services" / "intervention_service.py"
RISK_WARNING = BACKEND / "app" / "services" / "risk_service_warning.py"
WARNING_SERVICE = BACKEND / "app" / "services" / "warning_service.py"
PENDING_EVENTS = BACKEND / "app" / "core" / "pending_events.py"
ADMIN_STATS = BACKEND / "app" / "services" / "admin_service_stats.py"
GDPR_EXPORT = BACKEND / "app" / "services" / "gdpr_service_export.py"
DATETIME_PARAMS = BACKEND / "app" / "core" / "datetime_params.py"
LOG = Path(__file__).resolve().parent / "mutate_p2_47_round19_result.log"

SUITE = "tests/test_p2_47_round19_m_batch2.py"

CASES = (
    {
        "cid": "M11",
        "path": INTERVENTION,
        "old": "        if rate < 0 or rate > 100:\n",
        "new": "        if False:  # MUTATION: 钳制与记账被绕过\n",
        "target": f"{SUITE}::TestM11CompletionRate::test_out_of_range_is_clamped_and_counted",
        "expect": "test_out_of_range_is_clamped_and_counted",
        "why": "完成率钳制 + record_silent_degradation 是 M11 的纵深防御，绕过它必须红",
    },
    {
        "cid": "M12a",
        "path": RISK_WARNING,
        "old": (
            "        threshold = (\n"
            "            setting.threshold_level\n"
            "            if setting and setting.threshold_level is not None\n"
            "            else DEFAULT_WARNING_THRESHOLD\n"
            "        )\n"
        ),
        "new": (
            "        threshold = (\n"
            "            DEFAULT_WARNING_THRESHOLD\n"
            "            if setting and setting.threshold_level is not None\n"
            "            else DEFAULT_WARNING_THRESHOLD\n"
            "        )\n"
        ),
        "target": f"{SUITE}::TestM12ThresholdLevelEffective::test_threshold_1_warns_at_level_1",
        "expect": "test_threshold_1_warns_at_level_1",
        "why": "threshold_level 是 M12 的核心：写死默认值=配置项重新变成死配置，必须红",
    },
    {
        "cid": "M12b",
        "path": WARNING_SERVICE,
        "old": (
            '_NOT_EFFECTIVE_KEYS: frozenset[str] = frozenset(\n'
            '    {"quiet_hours_start", "quiet_hours_end", "notify_channels"}\n'
            ")\n"
        ),
        "new": (
            "_NOT_EFFECTIVE_KEYS: frozenset[str] = frozenset(\n"
            "    set()  # MUTATION: 声明集合被掏空\n"
            ")\n"
        ),
        "target": f"{SUITE}::TestM12NotEffectiveDeclared::test_update_warns_and_audits_not_effective",
        "expect": "test_update_warns_and_audits_not_effective",
        "why": "免打扰/渠道三项的显式不生效声明是 M12 的交付物，掏空必须红",
    },
    {
        "cid": "M14",
        "path": PENDING_EVENTS,
        "old": "    _PENDING.setdefault(sync_session, []).append((event_type, data))\n",
        "new": "    event_bus.publish_sync(event_type, data)  # MUTATION: 提交前即发布\n",
        "target": f"{SUITE}::TestM14EventAfterCommit::test_event_published_only_after_commit",
        "expect": "test_event_published_only_after_commit",
        "why": "M14 的判据是事件计数：提交前发布=事务失败也会带出事件，必须红",
    },
    {
        "cid": "M15",
        "path": ADMIN_STATS,
        "old": (
            "            .where(User.status != USER_STATUS_DELETED)\n"
            "            .scalar_subquery()\n"
            '            .label("total_users"),\n'
        ),
        "new": (
            "            .scalar_subquery()\n"
            '            .label("total_users"),\n'
        ),
        "target": f"{SUITE}::TestM15StatsExcludeAnonymized::test_anonymized_user_drops_out_of_totals",
        "expect": "test_anonymized_user_drops_out_of_totals",
        "why": "匿名化用户必须同步退出统计口径，去掉过滤必须红",
    },
    {
        "cid": "M16",
        "path": GDPR_EXPORT,
        "old": '            "text_entries": [_text_entry_to_dict(t) for t in text_entries],\n',
        "new": "            # MUTATION: text_entries section 被移除\n",
        "target": f"{SUITE}::TestM16GdprExportCoverage::test_export_contains_previously_missing_sections",
        "expect": "test_export_contains_previously_missing_sections",
        "why": "导出清单与匿名化覆盖面对齐是 M16 的判据，少一个 section 必须红",
    },
    {
        "cid": "M10",
        "path": DATETIME_PARAMS,
        "old": "        parse_datetime_param(end_value, field=end_field, inclusive_end=True),\n",
        "new": "        parse_datetime_param(end_value, field=end_field, inclusive_end=False),\n",
        "target": f"{SUITE}::TestM10EndDateInclusive::test_date_only_end_expands_to_end_of_day",
        "expect": "test_date_only_end_expands_to_end_of_day",
        "why": "date-only 的 end 必须扩张到当天 23:59:59.999999，否则当日数据被整体排除",
    },
)

_lines: list[str] = []


def log(msg: str = "") -> None:
    print(msg, flush=True)
    _lines.append(msg)


def run_gate(target: str) -> tuple[int, str]:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=--strict-markers --import-mode=importlib --ignore=functional_test.py",
            "-p",
            "no:cacheprovider",
            "-q",
            "--tb=short",
            target,
        ],
        cwd=str(BACKEND),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    log("=" * 72)
    log("ROUND_19 M 批 2 —— 真实变异验证（M10–M16 六条修复）")
    log(f"套件：{SUITE}")
    log("=" * 72)

    snapshots = {case["path"]: case["path"].read_bytes() for case in CASES}
    results: dict[str, str] = {}

    try:
        for case in CASES:
            cid = case["cid"]
            path = case["path"]
            old = case["old"]
            new = case["new"]
            log()
            log(f"[{cid}] {path.name}：{old.strip()!r} → {new.strip()!r}")
            log(f"     强度：强（{case['why']}）")

            # 用 read_text 而不是 snapshot.decode：前者做换行归一化（CRLF→\n），
            # 否则带换行的锚点在本机 autocrlf 检出下永远匹配不到。
            text = path.read_text(encoding="utf-8")
            if text.count(old) != 1:
                log(f"[{cid}] ✗ 锚点不唯一（出现 {text.count(old)} 次），变异无效")
                results[cid] = "ANCHOR-BAD"
                continue

            try:
                path.write_text(text.replace(old, new), encoding="utf-8")
                code, out = run_gate(case["target"])
                failed = [
                    line.split(" - ")[0].strip()
                    for line in out.splitlines()
                    if line.startswith("FAILED ")
                ]
                targeted = case["expect"] in out
                if code == 0:
                    log(f"[{cid}] ✗ 假绿：改坏了实现，闸门仍然通过")
                    results[cid] = "FALSE-GREEN"
                elif not targeted:
                    log(f"[{cid}] ✗ 红了但不是这一条（没出现 {case['expect']}），判据过弱")
                    results[cid] = "WRONG-TARGET"
                else:
                    log(f"[{cid}] ✓ 变异后变红，且指名 {case['expect']}")
                    results[cid] = "RED-OK"
                if failed:
                    log(f"     实际失败用例：{failed}")
            finally:
                path.write_bytes(snapshots[path])
                log(f"[{cid}] ✓ 还原（字节一致={path.read_bytes() == snapshots[path]}）")
    finally:
        for path, blob in snapshots.items():
            if path.read_bytes() != blob:  # pragma: no cover - 兜底
                path.write_bytes(blob)

    residual = [str(p.relative_to(REPO)) for p, blob in snapshots.items() if p.read_bytes() != blob]
    log()
    log(f"[residual] 残留文件: {'无' if not residual else residual}")

    final_code, final_out = run_gate(SUITE)
    tail = [line for line in final_out.splitlines() if " passed" in line or " failed" in line]
    log(f"[final] 还原后 returncode={final_code}（0=全绿）")
    log(f"[final] {tail[-1].strip() if tail else '<无结论行>'}")

    log()
    log("[summary] " + " | ".join(f"{cid}={res}" for cid, res in results.items()))
    all_red_ok = all(res == "RED-OK" for res in results.values())
    log(f"[summary] residual_clean={not residual} final_green={final_code == 0} all_red_ok={all_red_ok}")

    LOG.write_text("\n".join(_lines) + "\n", encoding="utf-8")
    print(f"\n日志已写入 {LOG.relative_to(REPO)}")
    return 0 if (all_red_ok and not residual and final_code == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
