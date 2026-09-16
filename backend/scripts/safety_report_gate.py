#!/usr/bin/env python3
"""safety 报告门禁 / 汇总器。

用法::

    python scripts/safety_report_gate.py safety-report.json [--blocking]

为什么需要这个脚本 (2026-09-16 定位)
====================================

`dependency-scan.yml` 的 safety-scan job 此前直接依赖 `safety check` 的退出码,
实测该退出码在这套仓库配置下不构成可靠信号, 有两个各自独立的缺陷:

1. **假门禁 (空扫描即通过)**。safety 2.x 只检查"已钉死版本"的条目。
   本仓库的 `requirements.txt` 全为 `>=` 下限约束, 于是
   `report_meta.packages_found == 0` —— 一个包都没扫, 退出码 0, 门禁"通过"。
   证据: 2026-09-15T06:42Z 与 2026-09-14T07:30Z 两次 main 分支运行的
   safety 报告产物均为 `packages_found: 0` / `scanned_packages: {}`。
   改为扫 `requirements.lock`(全为钉死, 与部署实际安装的集合一致)后,
   同一命令在同一环境得到 `packages_found: 123`。

2. **免费档不返回修复版本**。无 SAFETY_API_KEY 时走 2.x 免费档, 其
   `fixed_versions` 恒为空列表 —— 连 `cryptography 46.0.3` 这种
   `vulnerable_spec` 明确写着 `<46.0.5`(即修复版本存在)的条目也是空。
   因此"是否有漏洞"与"能否修复"无法区分, 退出码无法直接当阻塞信号用。

于是本脚本的规则:

* `packages_found == 0` -> **失败**。这是"声称在扫描但其实什么都没扫"的
  状态, 必须显式暴露, 不允许再以绿灯形式存在。
* 报告缺失/无法解析 -> 只在摘要里告警, 不阻塞 (可能是上游 API 抖动,
  无漏洞可报, 且硬失败会把外部抖动变成红 CI)。
* 有 findings 时:
    - `--blocking` (配置了 SAFETY_API_KEY, 走 3.x 付费档, 修复版本可用)
      -> 退出码 1, 阻塞合并。
    - 否则 -> 退出码 0, 但把逐条结论写进 job summary 并打 `::warning::`
      注解, 让"降级为咨询性"这件事可见, 而不是静默通过。

退出码: 0 通过 / 1 失败。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

LOCK = Path("requirements.lock")
SUMMARY_LIMIT = 40


def pinned_count(lock: Path) -> int | None:
    """统计 lock 文件中 `name==version` 形式的条目数, 作为扫描分母的参照。"""
    if not lock.is_file():
        return None
    n = 0
    for line in lock.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith((" ", "\t", "#")):
            continue
        if re.match(r"^[A-Za-z0-9._-]+(\[[^\]]*\])?==", line.strip()):
            n += 1
    return n


def emit(line: str = "") -> None:
    print(line)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        try:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass


def annotate(level: str, msg: str) -> None:
    # GitHub Actions 注解; 单行, 换行会截断注解正文
    print(f"::{level}::{msg.replace(chr(10), ' ')}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("report", nargs="?", default="safety-report.json")
    ap.add_argument(
        "--blocking",
        action="store_true",
        help="有 findings 即失败 (配置了 SAFETY_API_KEY / 3.x 付费档时使用)",
    )
    args = ap.parse_args()

    expected = pinned_count(LOCK)
    emit("## Safety 扫描 (Cross-check)")
    emit()
    emit("- 扫描目标: `requirements.lock` (部署实际安装的钉死集合)")
    if expected is not None:
        emit(f"- lock 中钉死条目数: {expected}")
    emit(f"- 模式: {'阻塞 (3.x + API key)' if args.blocking else '咨询性 (2.x 免费档)'}")
    emit()

    report = Path(args.report)
    if not report.is_file():
        annotate(
            "warning",
            f"safety 报告 {report} 不存在 —— 无法评估 (上游 API 抖动或命令异常)。不阻塞。",
        )
        emit("- 结果: **无法评估** (报告缺失), 未阻塞。")
        return 0

    try:
        data = json.loads(report.read_text(encoding="utf-8", errors="replace") or "{}")
    except json.JSONDecodeError as exc:
        annotate("warning", f"safety 报告 {report} 无法解析: {exc}。不阻塞。")
        emit("- 结果: **无法评估** (JSON 解析失败), 未阻塞。")
        return 0

    if not isinstance(data, dict) or not data:
        annotate("warning", f"safety 报告 {report} 为空。不阻塞。")
        emit("- 结果: **无法评估** (空报告), 未阻塞。")
        return 0

    meta = data.get("report_meta") or {}
    found = meta.get("packages_found")
    vulns = data.get("vulnerabilities") or []
    scanned = data.get("scanned_packages") or {}

    emit(f"- 实际扫描包数: `{found}` (scanned_packages: {len(scanned)})")
    emit(f"- 命中条数: {len(vulns)}")
    emit()

    # 规则 1: 空扫描是一等缺陷, 必须失败 —— 这正是本 job 曾经的"假绿灯"成因。
    if not found:
        annotate(
            "error",
            "safety 扫描到 0 个包 —— 门禁失效 (假绿灯)。"
            "检查扫描目标是否为钉死文件 (requirements.lock) 及 safety 版本分支。",
        )
        emit("- 结果: **失败** —— 扫描分母为 0, 该门禁没有在检查任何东西。")
        return 1

    if expected and len(scanned) < expected:
        annotate(
            "warning",
            f"扫描覆盖 {len(scanned)} < lock 钉死条目 {expected}, " "可能有条目未被评估。",
        )
        emit(f"- 覆盖告警: 扫描 {len(scanned)} < 预期 {expected}")

    if not vulns:
        emit("- 结果: **干净** —— 未命中任何公告。")
        return 0

    # 规则 2 / 3: 区分"有修复版本"与"无修复版本"。
    fixable = [v for v in vulns if v.get("fixed_versions")]
    unfixed = [v for v in vulns if not v.get("fixed_versions")]

    emit(f"- 可修复 (fixed_versions 非空): {len(fixable)}")
    emit(f"- 无修复版本: {len(unfixed)}")
    emit()
    emit("| 包 | 版本 | 公告 | 修复版本 |")
    emit("|---|---|---|---|")
    for v in vulns[:SUMMARY_LIMIT]:
        fixes = v.get("fixed_versions") or []
        emit(
            "| {pkg} | {ver} | {cve} | {fix} |".format(
                pkg=v.get("package_name", "?"),
                ver=v.get("analyzed_version", "?"),
                cve=v.get("CVE") or v.get("vulnerability_id") or "-",
                fix=", ".join(str(f) for f in fixes) if fixes else "_无_",
            )
        )
    if len(vulns) > SUMMARY_LIMIT:
        emit(f"| ... | | 其余 {len(vulns) - SUMMARY_LIMIT} 条见 artifact | |")
    emit()

    if args.blocking:
        annotate("error", f"safety 命中 {len(vulns)} 条公告 (阻塞模式)。")
        emit("- 结果: **失败** —— 阻塞模式下存在命中项。")
        return 1

    annotate(
        "warning",
        f"safety 命中 {len(vulns)} 条公告, 但当前无 SAFETY_API_KEY "
        "(2.x 免费档不返回修复版本), 本 job 降级为咨询性, 不阻塞合并。"
        "逐条见 job summary / safety-report artifact。",
    )
    emit(
        "- 结果: **咨询性告警** —— 免费档不提供修复版本, 无法区分可修/不可修, "
        "故不作为阻塞信号。配置 `SAFETY_API_KEY` 后本 job 恢复为阻塞模式。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
