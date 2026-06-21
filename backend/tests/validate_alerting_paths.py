"""v1.39 Grafana Alert Rules Provisioning 静态验证脚本.

T-AR-010 交付物: 验证 4 个 alerting YAML + 1 个 datasource YAML 合法.
被 TC-AT-001 调用.

Usage:
    python backend/tests/validate_alerting_paths.py
    python backend/tests/validate_alerting_paths.py --check-promql
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROVISIONING = ROOT / "infra" / "grafana" / "provisioning"
ALERTING = PROVISIONING / "alerting"
DATASOURCES = PROVISIONING / "datasources"

EXPECTED_ALERTING_FILES = [
    "rules.yaml",
    "contact-points.yaml",
    "policies.yaml",
    "mute-timings.yaml",
]
EXPECTED_DATASOURCE_FILES = [
    "observability-api.yaml",
    "prometheus.yaml",
]
PROMETHEUS_DS_UID = "PB0F7F7A2A1B0E0FA"


def _check_paths() -> list[str]:
    """验证 5 个 YAML 文件存在性."""
    errors = []
    for f in EXPECTED_ALERTING_FILES:
        p = ALERTING / f
        if not p.exists():
            errors.append(f"missing: {p.relative_to(ROOT)}")
    for f in EXPECTED_DATASOURCE_FILES:
        p = DATASOURCES / f
        if not p.exists():
            errors.append(f"missing: {p.relative_to(ROOT)}")
    return errors


def _check_yaml_valid() -> list[str]:
    """验证所有 YAML 解析合法."""
    errors = []
    files = [(ALERTING, f) for f in EXPECTED_ALERTING_FILES]
    files += [(DATASOURCES, f) for f in EXPECTED_DATASOURCE_FILES]
    for d, f in files:
        p = d / f
        try:
            yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"YAML parse error in {p.relative_to(ROOT)}: {e}")
    return errors


def _check_rules_count() -> list[str]:
    """验证 rules.yaml 包含 10 条规则."""
    errors = []
    rules_yaml = ALERTING / "rules.yaml"
    data = yaml.safe_load(rules_yaml.read_text(encoding="utf-8"))
    rules = data["groups"][0]["rules"]
    if len(rules) != 10:
        errors.append(f"rules count={len(rules)}, expected 10 (R1-R8 + R10 + R11)")
    return errors


def _check_contact_points() -> list[str]:
    """验证 contact-points.yaml 包含 3 个渠道."""
    errors = []
    cp_yaml = ALERTING / "contact-points.yaml"
    data = yaml.safe_load(cp_yaml.read_text(encoding="utf-8"))
    cps = data["contactPoints"]
    if len(cps) != 3:
        errors.append(f"contact points count={len(cps)}, expected 3")
    return errors


def _check_policies() -> list[str]:
    """验证 policies.yaml 包含 3 个 routes (P0/P1/P2)."""
    errors = []
    p_yaml = ALERTING / "policies.yaml"
    data = yaml.safe_load(p_yaml.read_text(encoding="utf-8"))
    routes = data["policies"][0]["routes"]
    if len(routes) != 3:
        errors.append(f"routes count={len(routes)}, expected 3")
    severities = set()
    for r in routes:
        for m in r.get("object_matchers", []):
            if m[0] == "severity":
                severities.add(m[2])
    if severities != {"P0", "P1", "P2"}:
        errors.append(f"severities={severities}, expected {{P0, P1, P2}}")
    return errors


def _check_mute_timings() -> list[str]:
    """验证 mute-timings.yaml 包含 1 个静音."""
    errors = []
    mt_yaml = ALERTING / "mute-timings.yaml"
    data = yaml.safe_load(mt_yaml.read_text(encoding="utf-8"))
    intervals = data["muteTimeIntervals"]
    if len(intervals) != 1:
        errors.append(f"mute count={len(intervals)}, expected 1")
    return errors


def _check_datasource_uid() -> list[str]:
    """验证 prometheus.yaml 与 rules.yaml UID 一致."""
    errors = []
    ds_yaml = DATASOURCES / "prometheus.yaml"
    ds_data = yaml.safe_load(ds_yaml.read_text(encoding="utf-8"))
    if ds_data["datasources"][0]["uid"] != PROMETHEUS_DS_UID:
        errors.append(f"prometheus uid mismatch: {ds_data['datasources'][0]['uid']}")

    rules_data = yaml.safe_load((ALERTING / "rules.yaml").read_text(encoding="utf-8"))
    for r in rules_data["groups"][0]["rules"]:
        for d in r["data"]:
            if d["datasourceUid"] not in (PROMETHEUS_DS_UID, "__expr__"):
                errors.append(f"rule {r['uid']} uses unexpected datasourceUid: {d['datasourceUid']}")
    return errors


def _check_promql_validity() -> list[str]:
    """验证 10 条规则的 expr 字段是合法 PromQL (粗略)."""
    errors = []
    rules_data = yaml.safe_load((ALERTING / "rules.yaml").read_text(encoding="utf-8"))
    for r in rules_data["groups"][0]["rules"]:
        for d in r["data"]:
            if d["datasourceUid"] == "__expr__":
                continue
            expr = d.get("model", {}).get("expr", "")
            if not expr:
                errors.append(f"rule {r['uid']} has empty expr")
                continue
            # 粗略校验: 必须以 observability_ 或 up{ 开头 (R11 meta)
            if not (expr.startswith("observability_") or expr.startswith("up{") or expr.startswith("sum(")):
                errors.append(f"rule {r['uid']} expr '{expr}' not in expected namespace")

    # GAP-1: R7 必须包含 lock_acquire_total > 0
    r7 = next(r for r in rules_data["groups"][0]["rules"] if r["uid"] == "r-lock-error-high")
    r7_expr = r7["data"][0]["model"]["expr"]
    if "lock_acquire_total > 0" not in r7_expr:
        errors.append(f"GAP-1 regression: R7 missing 'lock_acquire_total > 0'")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="v1.39 alerting static validator")
    parser.add_argument("--check-promql", action="store_true", help="validate PromQL expr namespace")
    args = parser.parse_args()

    checks = [
        ("paths", _check_paths),
        ("yaml_valid", _check_yaml_valid),
        ("rules_count", _check_rules_count),
        ("contact_points", _check_contact_points),
        ("policies", _check_policies),
        ("mute_timings", _check_mute_timings),
        ("datasource_uid", _check_datasource_uid),
    ]
    if args.check_promql:
        checks.append(("promql_validity", _check_promql_validity))

    total = 0
    failed = 0
    for name, check in checks:
        total += 1
        errors = check()
        if errors:
            failed += 1
            print(f"FAIL [{name}]:")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"PASS [{name}]")
    print(f"\n{total - failed}/{total} checks passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
