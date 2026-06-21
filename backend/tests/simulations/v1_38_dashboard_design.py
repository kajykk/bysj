"""v1.38 Round 1 Step 4: Simulation 推演脚本.

模拟 24 panel 仪表盘的设计可行性:
1. 校验 panel 数量 + gridPos 排版
2. 校验 target metric 引用 (mock v1.37 /metrics 端点)
3. 校验 variable 引用 ($severity 等)
4. 校验 panel 排版无重叠
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/tests/simulations -> bysj root


# === Mock v1.37 /metrics 端点返回的 7 metric ===
V137_METRICS = {
    "trend", "response_time", "escalation", "channel_stats",
    "silence_hit_rate", "am_sync", "lock_stats",
}


# === 24 panel 设计定义 (来自 01-requirements.md §3.2) ===
PANEL_DESIGN: list[dict] = [
    # Row 1: 告警趋势 (y=0, h=8)
    {"id": 1, "row": 1, "title": "Alert P0 (Trend)", "metric": "trend", "type": "timeseries", "x": 0, "y": 0, "w": 6, "h": 8, "params": {"group_by": "severity", "severity": "P0"}},
    {"id": 2, "row": 1, "title": "Alert P1 (Trend)", "metric": "trend", "type": "timeseries", "x": 6, "y": 0, "w": 6, "h": 8, "params": {"group_by": "severity", "severity": "P1"}},
    {"id": 3, "row": 1, "title": "Alert P2/P3 (Trend)", "metric": "trend", "type": "timeseries", "x": 12, "y": 0, "w": 6, "h": 8, "params": {"group_by": "severity", "severity": "P2"}},
    {"id": 4, "row": 1, "title": "Alert Total (Stat)", "metric": "trend", "type": "stat", "x": 18, "y": 0, "w": 6, "h": 8, "params": {"group_by": "status"}},

    # Row 2: 响应时长 (y=8, h=8)
    {"id": 5, "row": 2, "title": "Response Time p99 (Stat)", "metric": "response_time", "type": "stat", "x": 0, "y": 8, "w": 6, "h": 8, "params": {}},
    {"id": 6, "row": 2, "title": "Response Time p95 (Stat)", "metric": "response_time", "type": "stat", "x": 6, "y": 8, "w": 6, "h": 8, "params": {}},
    {"id": 7, "row": 2, "title": "Response Time Mean (Stat)", "metric": "response_time", "type": "stat", "x": 12, "y": 8, "w": 6, "h": 8, "params": {}},
    {"id": 8, "row": 2, "title": "Ack Rate (Gauge)", "metric": "response_time", "type": "gauge", "x": 18, "y": 8, "w": 6, "h": 8, "params": {}},

    # Row 3: 升级率 (y=16, h=8)
    {"id": 9, "row": 3, "title": "Escalation Distribution (Pie)", "metric": "escalation", "type": "piechart", "x": 0, "y": 16, "w": 8, "h": 8, "params": {}},
    {"id": 10, "row": 3, "title": "Escalation Rate (Stat)", "metric": "escalation", "type": "stat", "x": 8, "y": 16, "w": 8, "h": 8, "params": {}},
    {"id": 11, "row": 3, "title": "Escalation by Level (BarGauge)", "metric": "escalation", "type": "bargauge", "x": 16, "y": 16, "w": 8, "h": 8, "params": {}},

    # Row 4: 通道成功率 (y=24, h=8)
    {"id": 12, "row": 4, "title": "Overall Success Rate (Stat)", "metric": "channel_stats", "type": "stat", "x": 0, "y": 24, "w": 6, "h": 8, "params": {}},
    {"id": 13, "row": 4, "title": "Webhook Success (BarGauge)", "metric": "channel_stats", "type": "bargauge", "x": 6, "y": 24, "w": 6, "h": 8, "params": {"channel": "webhook"}},
    {"id": 14, "row": 4, "title": "Slack Success (BarGauge)", "metric": "channel_stats", "type": "bargauge", "x": 12, "y": 24, "w": 6, "h": 8, "params": {"channel": "slack"}},
    {"id": 15, "row": 4, "title": "DingTalk+Email (BarGauge)", "metric": "channel_stats", "type": "bargauge", "x": 18, "y": 24, "w": 6, "h": 8, "params": {"channel": "dingtalk"}},

    # Row 5: 静默命中率 (y=32, h=8)
    {"id": 16, "row": 5, "title": "Silence Hit Rate (Stat)", "metric": "silence_hit_rate", "type": "stat", "x": 0, "y": 32, "w": 8, "h": 8, "params": {}},
    {"id": 17, "row": 5, "title": "Total Silenced (Stat)", "metric": "silence_hit_rate", "type": "stat", "x": 8, "y": 32, "w": 8, "h": 8, "params": {}},
    {"id": 18, "row": 5, "title": "Top Matchers (BarGauge)", "metric": "silence_hit_rate", "type": "bargauge", "x": 16, "y": 32, "w": 8, "h": 8, "params": {}},

    # Row 6: AM 同步 (y=40, h=8)
    {"id": 19, "row": 6, "title": "AM Sync Success Rate (Gauge)", "metric": "am_sync", "type": "gauge", "x": 0, "y": 40, "w": 8, "h": 8, "params": {}},
    {"id": 20, "row": 6, "title": "AM Sync Total (Stat)", "metric": "am_sync", "type": "stat", "x": 8, "y": 40, "w": 8, "h": 8, "params": {}},
    {"id": 21, "row": 6, "title": "AM Sync by Operation (Table)", "metric": "am_sync", "type": "table", "x": 16, "y": 40, "w": 8, "h": 8, "params": {}},

    # Row 7: 锁统计 (y=48, h=8)
    {"id": 22, "row": 7, "title": "Lock Acquire Rate (Gauge)", "metric": "lock_stats", "type": "gauge", "x": 0, "y": 48, "w": 8, "h": 8, "params": {}},
    {"id": 23, "row": 7, "title": "Lock Fallback Rate (Stat)", "metric": "lock_stats", "type": "stat", "x": 8, "y": 48, "w": 8, "h": 8, "params": {}},
    {"id": 24, "row": 7, "title": "Lock Error Rate (Stat)", "metric": "lock_stats", "type": "stat", "x": 16, "y": 48, "w": 8, "h": 8, "params": {}},
]


def validate_panel_count() -> bool:
    """AC-2: 24 panels."""
    print(f"[SIM] panel count: {len(PANEL_DESIGN)}")
    assert len(PANEL_DESIGN) == 24, f"expected 24, got {len(PANEL_DESIGN)}"
    print("  PASS: AC-2 (24 panels)")
    return True


def validate_metrics_exist() -> bool:
    """AC-4: target.metric 必须在 v1.37 /metrics 列表中."""
    print("\n[SIM] metric reference validation:")
    metrics_used = {p["metric"] for p in PANEL_DESIGN}
    print(f"  metrics used: {metrics_used}")
    missing = metrics_used - V137_METRICS
    assert not missing, f"unknown metrics: {missing}"
    print("  PASS: AC-4 (all 7 metrics exist in v1.37)")
    return True


def validate_grid_layout() -> bool:
    """C-2: 每行 panels 总宽 <= 24, 无重叠."""
    print("\n[SIM] gridPos layout validation:")
    rows: dict[int, list] = {}
    for p in PANEL_DESIGN:
        rows.setdefault(p["row"], []).append(p)

    for row, panels in rows.items():
        total_w = sum(p["w"] for p in panels)
        xs = [(p["x"], p["x"] + p["w"]) for p in panels]
        # 检查重叠
        for i, (a, b) in enumerate(xs):
            for j, (c, d) in enumerate(xs):
                if i < j and not (b <= c or d <= a):
                    print(f"  FAIL: row {row} panels {i} and {j} overlap: {a}-{b} vs {c}-{d}")
                    return False
        print(f"  Row {row}: {len(panels)} panels, total_w={total_w}, OK")
        assert total_w <= 24, f"row {row} overflow: {total_w}"
    print("  PASS: gridPos layout valid (no overlap, no overflow)")
    return True


def validate_panel_ids() -> bool:
    """C-8: panel.id 1-24 连续."""
    print("\n[SIM] panel.id uniqueness:")
    ids = [p["id"] for p in PANEL_DESIGN]
    assert sorted(ids) == list(range(1, 25)), f"ids not 1-24: {sorted(ids)}"
    print("  PASS: C-8 (panel.id 1-24 连续)")
    return True


def validate_metric_coverage() -> bool:
    """完整性: 7 metric 全部被 panel 引用."""
    print("\n[SIM] metric coverage (all 7 v1.37 metrics used?):")
    for m in sorted(V137_METRICS):
        count = sum(1 for p in PANEL_DESIGN if p["metric"] == m)
        print(f"  {m}: {count} panels")
        assert count > 0, f"metric {m} unused"
    print("  PASS: all 7 metrics covered")
    return True


def simulate_user_flows() -> bool:
    """推演用户场景."""
    print("\n[SIM] user flow simulation:")

    # 场景 1: SRE 故障定位 (3 秒判断)
    print("  场景 1: SRE 故障定位")
    critical_panels = [p for p in PANEL_DESIGN if p["id"] in (12, 19, 22)]  # channel/AM/lock
    print(f"    critical panels (3 sec 判断): {[(p['id'], p['title']) for p in critical_panels]}")

    # 场景 2: PM 周报截图
    print("  场景 2: PM 周报截图")
    weekly_panels = [p for p in PANEL_DESIGN if p["id"] in (1, 2, 3, 12)]  # 趋势 + 通道
    print(f"    weekly panels: {[(p['id'], p['title']) for p in weekly_panels]}")

    # 场景 3: 变量切换 (severity=P0)
    print("  场景 3: severity=P0 变量切换")
    severity_panels = [p for p in PANEL_DESIGN if "severity" in p["params"]]
    print(f"    panels affected by $severity: {[(p['id'], p['title']) for p in severity_panels]}")
    return True


def main() -> int:
    print("=" * 60)
    print("v1.38 R1 Simulation: 24-Panel Dashboard Design")
    print("=" * 60)
    all_pass = True
    for check in (
        validate_panel_count,
        validate_metrics_exist,
        validate_grid_layout,
        validate_panel_ids,
        validate_metric_coverage,
        simulate_user_flows,
    ):
        try:
            check()
        except AssertionError as e:
            print(f"  FAIL: {e}")
            all_pass = False
    print("\n" + "=" * 60)
    print("OVERALL: " + ("ALL PASS" if all_pass else "FAIL"))
    print("=" * 60)
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
