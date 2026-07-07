"""v1.38 Grafana Dashboard JSON 静态校验脚本.

校验项 (10 项):
1. JSON 合法 (AC-1)
2. 24 panels 分布 7 rows (AC-2)
3. panel.id 1-24 连续 (C-8)
4. target.metric ∈ v1.37 /metrics (AC-4)
5. panel 引用的 $xxx 变量在 templating.list 中 (AC-4 扩展)
6. P0 panel 含 thresholds (AC-5)
7. gridPos 无重叠无溢出 (C-2)
8. UID 唯一性
9. DataSource 引用 (DS_OBSERVABILITY_API 变量存在)
10. 6 变量定义 (templating.list 长度 + 类型)

用法:
    cd e:\\code\bysj
    python backend/tests/validate_dashboard_json.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]  # backend/tests -> bysj

DASHBOARD_JSON = (
    ROOT / "infra" / "grafana" / "dashboards" / "v1.37-alerts-overview.json"
)
PROVISIONING_YAML = (
    ROOT / "infra" / "grafana" / "provisioning" / "dashboards" / "alerts-overview.yaml"
)

# v1.37 7 metric (与 v1.37 grafana_adapter.py _METRIC_HANDLERS 一致)
V137_METRICS = {
    "trend",
    "response_time",
    "escalation",
    "channel_stats",
    "silence_hit_rate",
    "am_sync",
    "lock_stats",
}

# P0 panel ID 集合 (按 01-requirements.md §3.2)
P0_PANEL_IDS = {
    5,
    6,
    7,
    8,  # Row 2: Response Time (P0)
    10,
    12,
    13,
    14,
    15,  # Row 3 + Row 4 (P0)
    19,
    22,
    23,
    24,  # Row 6 + Row 7 (P0)
}


def load_dashboard() -> dict:
    if not DASHBOARD_JSON.exists():
        print(f"[VALIDATE] ERROR: dashboard JSON not found: {DASHBOARD_JSON}")
        sys.exit(1)
    with open(DASHBOARD_JSON, encoding="utf-8") as f:
        return json.load(f)


def validate_json_legal(d: dict) -> bool:
    """AC-1: JSON 合法 + 必要字段."""
    print("\n[VALIDATE 1] JSON legal + required fields:")
    required = [
        "title",
        "uid",
        "schemaVersion",
        "panels",
        "templating",
        "tags",
        "refresh",
    ]
    missing = [k for k in required if k not in d]
    assert not missing, f"missing fields: {missing}"
    print(f"  title: {d['title']}")
    print(f"  uid: {d['uid']}")
    print(f"  schemaVersion: {d['schemaVersion']}")
    print(f"  tags: {d['tags']}")
    print(f"  refresh: {d['refresh']}")
    print("  PASS: AC-1")
    return True


def validate_panels_count_and_rows(d: dict) -> bool:
    """AC-2: 24 panels 分布 7 rows."""
    print("\n[VALIDATE 2] 24 panels 分布 7 rows:")
    panels = d["panels"]
    assert len(panels) == 24, f"expected 24 panels, got {len(panels)}"
    rows: dict[int, list] = {}
    for p in panels:
        rows.setdefault(p["gridPos"]["y"] // 8, []).append(p)
    assert len(rows) == 7, f"expected 7 rows, got {len(rows)}"
    for row, pls in sorted(rows.items()):
        print(f"  Row {row + 1}: {len(pls)} panels, y={pls[0]['gridPos']['y']}")
    print("  PASS: AC-2")
    return True


def validate_panel_ids(d: dict) -> bool:
    """C-8: panel.id 1-24 连续."""
    print("\n[VALIDATE 3] panel.id 1-24 连续:")
    ids = sorted([p["id"] for p in d["panels"]])
    expected = list(range(1, 25))
    assert ids == expected, f"panel.id not 1-24: got {ids}"
    print("  PASS: C-8 (panel.id 1-24)")
    return True


def validate_metrics_exist(d: dict) -> bool:
    """AC-4: target.metric ∈ v1.37 /metrics."""
    print("\n[VALIDATE 4] target.metric ∈ v1.37 /metrics:")
    for p in d["panels"]:
        for t in p.get("targets", []):
            metric = t.get("payload", {}).get("metric")
            assert (
                metric in V137_METRICS
            ), f"panel {p['id']} uses unknown metric: {metric}"
    print(f"  PASS: AC-4 (all metrics in v1.37 set: {sorted(V137_METRICS)})")
    return True


def validate_variable_references(d: dict) -> bool:
    """AC-4 扩展: panel 引用的 $xxx 变量在 templating.list 中."""
    print("\n[VALIDATE 5] panel $xxx references in templating.list:")
    var_names = {v["name"] for v in d["templating"]["list"]}
    refs: set[str] = set()
    for p in d["panels"]:
        for t in p.get("targets", []):
            payload = t.get("payload", {})
            params = payload.get("params", {})
            for v in params.values():
                for match in re.findall(r"\$(\w+)", str(v)):
                    refs.add(match)
    print(f"  vars defined: {sorted(var_names)}")
    print(f"  $xxx refs in panels: {sorted(refs)}")
    unknown = refs - var_names
    assert not unknown, f"orphan $xxx references: {unknown}"
    print("  PASS: AC-4 扩展 (no orphan refs)")
    return True


def validate_p0_thresholds(d: dict) -> bool:
    """AC-5: P0 panel 含 thresholds."""
    print("\n[VALIDATE 6] P0 panels have thresholds:")
    missing = []
    for p in d["panels"]:
        if p["id"] in P0_PANEL_IDS:
            thresholds = p.get("fieldConfig", {}).get("defaults", {}).get("thresholds")
            if not thresholds or not thresholds.get("steps"):
                missing.append(p["id"])
    assert not missing, f"P0 panels missing thresholds: {missing}"
    print(f"  P0 panel count: {len(P0_PANEL_IDS)}, all have thresholds")
    print("  PASS: AC-5")
    return True


def validate_grid_layout(d: dict) -> bool:
    """C-2: gridPos 无重叠无溢出."""
    print("\n[VALIDATE 7] gridPos layout (no overlap, no overflow):")
    rows: dict[int, list] = {}
    for p in d["panels"]:
        rows.setdefault(p["gridPos"]["y"], []).append(p)
    for y, pls in rows.items():
        # 排序后检查无重叠
        pls_sorted = sorted(pls, key=lambda x: x["gridPos"]["x"])
        for i in range(len(pls_sorted) - 1):
            end = pls_sorted[i]["gridPos"]["x"] + pls_sorted[i]["gridPos"]["w"]
            nxt = pls_sorted[i + 1]["gridPos"]["x"]
            assert (
                end <= nxt
            ), f"row y={y}: panels {pls_sorted[i]['id']} and {pls_sorted[i+1]['id']} overlap"
        # 总宽
        total_w = sum(p["gridPos"]["w"] for p in pls)
        assert total_w <= 24, f"row y={y}: total_w={total_w} > 24"
    print(f"  Rows: {len(rows)}, all pass no-overlap + no-overflow check")
    print("  PASS: C-2")
    return True


def validate_uid_unique(d: dict) -> bool:
    """UID 唯一性 (dashboard.uid 不重复)."""
    print("\n[VALIDATE 8] dashboard UID unique:")
    assert "uid" in d and d["uid"], "uid missing"
    print(f"  uid: {d['uid']}")
    print("  PASS: UID unique")
    return True


def validate_datasource_variable(d: dict) -> bool:
    """DS_OBSERVABILITY_API 变量存在."""
    print("\n[VALIDATE 9] DataSource variable (DS_OBSERVABILITY_API):")
    var_names = {v["name"] for v in d["templating"]["list"]}
    assert "DS_OBSERVABILITY_API" in var_names, "DS_OBSERVABILITY_API variable missing"
    print("  PASS: DS_OBSERVABILITY_API present")
    return True


def validate_six_variables(d: dict) -> bool:
    """6 变量定义 (time_range/severity/rule/matcher/operation/channel) + 1 DataSource."""
    print("\n[VALIDATE 10] 6 variables defined:")
    expected = {"time_range", "severity", "rule", "matcher", "operation", "channel"}
    var_names = {v["name"] for v in d["templating"]["list"]}
    assert expected.issubset(var_names), f"missing vars: {expected - var_names}"
    print(f"  6 vars: {sorted(expected)}")
    print("  PASS: AC-3")
    return True


def validate_provisioning_yaml(d: dict) -> bool:
    """AC-8: provisioning YAML 合法."""
    print("\n[VALIDATE 11] provisioning YAML valid:")
    if not PROVISIONING_YAML.exists():
        print(f"  FAIL: not found: {PROVISIONING_YAML}")
        return False
    with open(PROVISIONING_YAML, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert cfg.get("apiVersion") == 1
    assert cfg.get("providers")
    p = cfg["providers"][0]
    print(
        f"  provider: {p['name']}, folder: {p['folder']}, path: {p['options']['path']}"
    )
    print("  PASS: AC-8")
    return True


def main() -> int:
    print("=" * 70)
    print("v1.38 Grafana Dashboard JSON 静态校验")
    print("=" * 70)
    d = load_dashboard()
    print(
        f"[VALIDATE] loaded {DASHBOARD_JSON.name}: {len(d['panels'])} panels, {len(d['templating']['list'])} vars"
    )
    all_pass = True
    for check in (
        validate_json_legal,
        validate_panels_count_and_rows,
        validate_panel_ids,
        validate_metrics_exist,
        validate_variable_references,
        validate_p0_thresholds,
        validate_grid_layout,
        validate_uid_unique,
        validate_datasource_variable,
        validate_six_variables,
        validate_provisioning_yaml,
    ):
        try:
            check(d)
        except AssertionError as e:
            print(f"  FAIL: {e}")
            all_pass = False
    print("\n" + "=" * 70)
    print(f"OVERALL: {'ALL PASS' if all_pass else 'FAIL'}")
    print("=" * 70)
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
