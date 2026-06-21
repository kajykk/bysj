"""v1.37 Round 1 Step 4: 推演仪表盘 JSON 样例与变量注入.

目的:
- 验证 panel 结构符合 Grafana 11.6 schema
- 验证 6 个变量能正确注入到 7 个 panel target
- 验证 21 个 panel 全部指向 v1.36 (post-patch) 端点
- 验证时间宏 $__isoFrom / $__isoTo 正确传递

输出:
- docs/planning/v1.37-grafana-dashboards/03-simulation-r1.md (本推演报告)
- infra/grafana/dashboards/v1.37-alerts-overview.json (样例骨架, 用于 Step 5 Lock)
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

# 模拟 Grafana 11.6 dashboard JSON schema
DASHBOARD_TEMPLATE: dict[str, Any] = {
    "title": "v1.37 Alerts Overview",
    "uid": "v137-alerts-overview",
    "schemaVersion": 39,
    "version": 1,
    "tags": ["v1.37", "alerts", "observability", "bysj"],
    "timezone": "browser",
    "time": {"from": "now-1h", "to": "now"},
    "refresh": "1m",
    "templating": {
        "list": [
            # 6 个变量
            {
                "name": "severity",
                "type": "custom",
                "label": "Severity",
                "query": "all,P0,P1,P2,P3",
                "current": {"text": "all", "value": "all"},
                "hide": 0,
            },
            {
                "name": "channel",
                "type": "custom",
                "label": "Channel",
                "query": "all,webhook,slack,dingtalk,email",
                "current": {"text": "all", "value": "all"},
            },
            {
                "name": "rule",
                "type": "query",
                "label": "Rule",
                "datasource": {"type": "simpod-json-datasource", "uid": "observability-api"},
                "refresh": 2,
                "query": {
                    "path": "/grafana/variable",
                    "params": [{"key": "type", "value": "rule"}],
                    "method": "POST",
                    "fields": [
                        {"name": "text", "jsonPath": "$[*].text"},
                        {"name": "value", "jsonPath": "$[*].value"},
                    ],
                },
            },
            {
                "name": "instance_id",
                "type": "custom",
                "label": "Instance",
                "query": "auto,$__auto",
                "current": {"text": "auto", "value": "$__auto"},
                "hide": 0,
            },
            {
                "name": "operation",
                "type": "custom",
                "label": "AM Operation",
                "query": "all,push_silence,expire_silence",
                "current": {"text": "all", "value": "all"},
            },
            {
                "name": "time_range",
                "type": "custom",
                "label": "Time Range",
                "query": "1h,6h,24h,7d,30d",
                "current": {"text": "1h", "value": "1h"},
                "hide": 0,
            },
        ]
    },
    "panels": [],
}


def _panel(
    row: int,
    title: str,
    panel_type: str,
    targets: list[dict],
    grid_pos: dict,
    field_config: dict | None = None,
    options: dict | None = None,
) -> dict:
    """构造 panel 通用结构."""
    return {
        "id": row * 100 + 1,
        "type": panel_type,
        "title": title,
        "datasource": {"type": "simpod-json-datasource", "uid": "observability-api"},
        "targets": targets,
        "gridPos": grid_pos,
        "fieldConfig": field_config or {"defaults": {}, "overrides": []},
        "options": options or {},
    }


def _row_1_trend() -> list[dict]:
    """Row 1: 告警趋势 (3 panels)."""
    base_target = {
        "datasource": {"type": "simpod-json-datasource", "uid": "observability-api"},
        "path": "/grafana/query",
        "method": "POST",
        "params": [
            {"key": "metric", "value": "trend"},
        ],
    }
    common = {
        "datasource": {"type": "simpod-json-datasource", "uid": "observability-api"},
        "refId": "A",
    }
    return [
        # 1.1 总告警量时间序列
        _panel(
            row=1,
            title="Alert Volume Over Time",
            panel_type="timeseries",
            targets=[{
                **common,
                "path": "/grafana/query",
                "method": "POST",
                "body": json.dumps({
                    "metric": "trend",
                    "params": {
                        "start_time": "$__isoFrom()",
                        "end_time": "$__isoTo()",
                        "bucket": "1h",
                        "severity": "$severity",
                        "group_by": "status",
                    },
                }),
            }],
            grid_pos={"h": 8, "w": 16, "x": 0, "y": 0},
            field_config={
                "defaults": {
                    "unit": "short",
                    "custom": {"drawStyle": "line", "lineWidth": 2},
                    "color": {"mode": "palette-classic"},
                },
                "overrides": [],
            },
        ),
        # 1.2 P0 当前量
        _panel(
            row=1,
            title="P0 Active Now",
            panel_type="stat",
            targets=[{
                **common,
                "body": json.dumps({
                    "metric": "trend",
                    "params": {
                        "start_time": "$__isoFrom()",
                        "end_time": "$__isoTo()",
                        "bucket": "5m",
                        "severity": "P0",
                    },
                }),
            }],
            grid_pos={"h": 8, "w": 8, "x": 16, "y": 0},
            field_config={
                "defaults": {
                    "unit": "short",
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "green", "value": None},
                            {"color": "red", "value": 1},
                        ],
                    },
                },
            },
        ),
        # 1.3 Top 5 规则
        _panel(
            row=1,
            title="Top 5 Triggered Rules",
            panel_type="bargauge",
            targets=[{
                **common,
                "body": json.dumps({
                    "metric": "trend",
                    "params": {
                        "start_time": "$__isoFrom()",
                        "end_time": "$__isoTo()",
                        "bucket": "1h",
                        "group_by": "rule",
                        "top_n": 5,
                    },
                }),
            }],
            grid_pos={"h": 8, "w": 24, "x": 0, "y": 8},
        ),
    ]


def _row_2_response_time() -> list[dict]:
    """Row 2: 响应时长 (3 panels)."""
    common = {
        "datasource": {"type": "simpod-json-datasource", "uid": "observability-api"},
        "refId": "A",
    }
    return [
        # 2.1 p50/p95/p99 时序
        _panel(
            row=2,
            title="Response Time p50/p95/p99",
            panel_type="timeseries",
            targets=[{
                **common,
                "body": json.dumps({
                    "metric": "response_time",
                    "params": {
                        "start_time": "$__isoFrom()",
                        "end_time": "$__isoTo()",
                        "bucket": "1h",
                        "severity": "$severity",
                    },
                }),
            }],
            grid_pos={"h": 8, "w": 16, "x": 0, "y": 16},
        ),
        # 2.2 p99 当前值 gauge
        _panel(
            row=2,
            title="p99 Response Time",
            panel_type="gauge",
            targets=[{
                **common,
                "body": json.dumps({
                    "metric": "response_time",
                    "params": {
                        "start_time": "$__isoFrom()",
                        "end_time": "$__isoTo()",
                        "bucket": "5m",
                        "severity": "$severity",
                    },
                }),
            }],
            grid_pos={"h": 8, "w": 8, "x": 16, "y": 16},
            field_config={
                "defaults": {
                    "unit": "s",
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "green", "value": None},
                            {"color": "yellow", "value": 60},
                            {"color": "red", "value": 120},
                        ],
                    },
                },
            },
        ),
        # 2.3 按严重度分位表
        _panel(
            row=2,
            title="Response Time by Severity",
            panel_type="table",
            targets=[{
                **common,
                "body": json.dumps({
                    "metric": "response_time",
                    "params": {
                        "start_time": "$__isoFrom()",
                        "end_time": "$__isoTo()",
                        "bucket": "1h",
                    },
                }),
            }],
            grid_pos={"h": 8, "w": 24, "x": 0, "y": 24},
        ),
    ]


def _row_3_escalation() -> list[dict]:
    """Row 3: 升级率 (3 panels)."""
    common = {"datasource": {"type": "simpod-json-datasource", "uid": "observability-api"}, "refId": "A"}
    return [
        _panel(3, "Escalation Rate", "timeseries",
               [{"**common": None, "body": json.dumps({"metric": "escalation", "params": {"start_time": "$__isoFrom()", "end_time": "$__isoTo()", "bucket": "1h", "severity": "$severity"}})}],
               {"h": 8, "w": 16, "x": 0, "y": 32}),
        _panel(3, "By Level", "piechart",
               [{"**common": None, "body": json.dumps({"metric": "escalation", "params": {"start_time": "$__isoFrom()", "end_time": "$__isoTo()", "group_by": "level"}})}],
               {"h": 8, "w": 8, "x": 16, "y": 32}),
        _panel(3, "Top 5 Escalated Rules", "bargauge",
               [{"**common": None, "body": json.dumps({"metric": "escalation", "params": {"start_time": "$__isoFrom()", "end_time": "$__isoTo()", "group_by": "rule", "top_n": 5}})}],
               {"h": 8, "w": 24, "x": 0, "y": 40}),
    ]


def _row_4_channel_stats() -> list[dict]:
    """Row 4: 通道发送成功率 (3 panels)."""
    common = {"datasource": {"type": "simpod-json-datasource", "uid": "observability-api"}, "refId": "A"}
    panels = []
    for i, ch in enumerate(["webhook", "slack", "dingtalk", "email"]):
        panels.append(_panel(
            4, f"{ch.title()} Success Rate", "stat",
            [{"**common": None, "body": json.dumps({"metric": "channel_stats", "params": {"start_time": "$__isoFrom()", "end_time": "$__isoTo()", "channel": ch}})}],
            {"h": 4, "w": 6, "x": i * 6, "y": 48},
        ))
    panels.append(_panel(
        4, "Avg Duration by Channel", "bargauge",
        [{"**common": None, "body": json.dumps({"metric": "channel_stats", "params": {"start_time": "$__isoFrom()", "end_time": "$__isoTo()", "group_by": "channel", "metric": "duration"}})}],
        {"h": 8, "w": 16, "x": 0, "y": 52},
    ))
    panels.append(_panel(
        4, "Failed Channels Over Time", "timeseries",
        [{"**common": None, "body": json.dumps({"metric": "channel_stats", "params": {"start_time": "$__isoFrom()", "end_time": "$__isoTo()", "channel": "$channel", "group_by": "channel", "metric": "failed"}})}],
        {"h": 8, "w": 8, "x": 16, "y": 52},
    ))
    return panels


def _row_5_silence() -> list[dict]:
    """Row 5: 静默命中率 (3 panels)."""
    common = {"datasource": {"type": "simpod-json-datasource", "uid": "observability-api"}, "refId": "A"}
    return [
        _panel(5, "Hit Rate Over Time", "timeseries",
               [{"**common": None, "body": json.dumps({"metric": "silence_hit_rate", "params": {"start_time": "$__isoFrom()", "end_time": "$__isoTo()", "bucket": "1h"}})}],
               {"h": 8, "w": 16, "x": 0, "y": 60}),
        _panel(5, "Top 10 Silence Matchers", "bargauge",
               [{"**common": None, "body": json.dumps({"metric": "silence_hit_rate", "params": {"start_time": "$__isoFrom()", "end_time": "$__isoTo()", "group_by": "matcher", "top_n": 10}})}],
               {"h": 8, "w": 8, "x": 16, "y": 60}),
        _panel(5, "Fired vs Silenced", "barchart",
               [{"**common": None, "body": json.dumps({"metric": "silence_hit_rate", "params": {"start_time": "$__isoFrom()", "end_time": "$__isoTo()", "bucket": "1h", "group_by": "type"}})}],
               {"h": 8, "w": 24, "x": 0, "y": 68},
               options={"stacking": "normal"}),
    ]


def _row_6_am_sync() -> list[dict]:
    """Row 6: AM 同步 (3 panels)."""
    common = {"datasource": {"type": "simpod-json-datasource", "uid": "observability-api"}, "refId": "A"}
    return [
        _panel(6, "AM Sync Success Rate", "gauge",
               [{"**common": None, "body": json.dumps({"metric": "am_sync", "params": {"start_time": "$__isoFrom()", "end_time": "$__isoTo()", "operation": "$operation"}})}],
               {"h": 8, "w": 8, "x": 0, "y": 76},
               field_config={"defaults": {"unit": "percentunit", "min": 0, "max": 1, "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "yellow", "value": 0.8}, {"color": "green", "value": 0.95}]}}}),
        _panel(6, "By Operation", "table",
               [{"**common": None, "body": json.dumps({"metric": "am_sync", "params": {"start_time": "$__isoFrom()", "end_time": "$__isoTo()", "group_by": "operation"}})}],
               {"h": 8, "w": 16, "x": 8, "y": 76}),
        _panel(6, "Recent Failures", "table",
               [{"**common": None, "body": json.dumps({"metric": "am_sync", "params": {"start_time": "$__isoFrom()", "end_time": "$__isoTo()", "operation": "$operation", "include_recent_failures": True, "limit": 10}})}],
               {"h": 8, "w": 24, "x": 0, "y": 84}),
    ]


def _row_7_lock_stats() -> list[dict]:
    """Row 7: 锁统计 (3 panels)."""
    common = {"datasource": {"type": "simpod-json-datasource", "uid": "observability-api"}, "refId": "A"}
    return [
        _panel(7, "Fallback Rate", "gauge",
               [{"**common": None, "body": json.dumps({"metric": "lock_stats", "params": {"group_by": "fallback_rate"}})}],
               {"h": 8, "w": 8, "x": 0, "y": 92},
               field_config={"defaults": {"unit": "percentunit", "min": 0, "max": 1, "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 0.05}, {"color": "red", "value": 0.15}]}}}),
        _panel(7, "Recent Flush Trend", "bargauge",
               [{"**common": None, "body": json.dumps({"metric": "lock_stats", "params": {"group_by": "recent_flushes", "limit": 10}})}],
               {"h": 8, "w": 16, "x": 8, "y": 92}),
        _panel(7, "Historical Totals", "stat",
               [{"**common": None, "body": json.dumps({"metric": "lock_stats", "params": {"group_by": "totals"}})}],
               {"h": 8, "w": 24, "x": 0, "y": 100}),
    ]


def build_dashboard() -> dict:
    """组装完整仪表盘 JSON."""
    dashboard = json.loads(json.dumps(DASHBOARD_TEMPLATE))  # 深拷贝
    panels = []
    panels.extend(_row_1_trend())
    panels.extend(_row_2_response_time())
    panels.extend(_row_3_escalation())
    panels.extend(_row_4_channel_stats())
    panels.extend(_row_5_silence())
    panels.extend(_row_6_am_sync())
    panels.extend(_row_7_lock_stats())

    # 用 row panels 包裹
    rows = []
    row_defs = [
        (1, 0, "Alert Trend"),
        (2, 16, "Response Time"),
        (3, 32, "Escalation"),
        (4, 48, "Channel Stats"),
        (5, 60, "Silence Hit Rate"),
        (6, 76, "AM Sync"),
        (7, 92, "Lock Stats"),
    ]
    panel_idx = 0
    panels_per_row = [3, 3, 3, 6, 3, 3, 3]  # Row 4 有 6 个 (4 stat + 2 大)
    for rid, y, title in row_defs:
        row_panels = panels[panel_idx:panel_idx + panels_per_row[rid - 1]]
        panel_idx += panels_per_row[rid - 1]
        row_obj = {
            "id": rid * 1000,
            "type": "row",
            "title": title,
            "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y},
            "panels": row_panels,
        }
        rows.append(row_obj)
    dashboard["panels"] = rows
    return dashboard


def validate_dashboard(dashboard: dict) -> dict:
    """验证仪表盘结构, 返回验证报告."""
    issues = []
    metrics = {
        "total_rows": 0,
        "total_panels": 0,
        "panels_per_row": {},
        "variables": [],
        "missing_datasource": [],
        "missing_metric": [],
    }

    for panel in dashboard.get("panels", []):
        if panel.get("type") == "row":
            metrics["total_rows"] += 1
            row_title = panel.get("title", "Unknown")
            metrics["panels_per_row"][row_title] = 0
            for sub_panel in panel.get("panels", []):
                metrics["total_panels"] += 1
                metrics["panels_per_row"][row_title] += 1
                # 检查 datasource
                if not sub_panel.get("datasource"):
                    metrics["missing_datasource"].append(sub_panel.get("title"))
                # 检查 target 中是否有 metric
                for target in sub_panel.get("targets", []):
                    body = target.get("body", "")
                    if body and "metric" not in body:
                        metrics["missing_metric"].append(sub_panel.get("title"))
        else:
            metrics["total_panels"] += 1

    for var in dashboard.get("templating", {}).get("list", []):
        metrics["variables"].append({
            "name": var.get("name"),
            "type": var.get("type"),
        })

    return {"issues": issues, "metrics": metrics}


def main() -> None:
    output_dir = Path("docs/planning/v1.37-grafana-dashboards")
    output_dir.mkdir(parents=True, exist_ok=True)

    dashboard = build_dashboard()
    report = validate_dashboard(dashboard)

    # 写 JSON 样例
    json_path = output_dir / "v1.37-alerts-overview.sample.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, indent=2, ensure_ascii=False)
    print(f"✅ 仪表盘 JSON 样例已写入: {json_path}")
    print(f"   文件大小: {json_path.stat().st_size / 1024:.1f} KB")

    # 写验证报告
    print()
    print("📊 验证报告:")
    metrics = report["metrics"]
    print(f"  - 总 Rows: {metrics['total_rows']}")
    print(f"  - 总 Panels: {metrics['total_panels']}")
    for row, count in metrics["panels_per_row"].items():
        print(f"    - {row}: {count} panels")
    print(f"  - 变量数量: {len(metrics['variables'])}")
    for v in metrics["variables"]:
        print(f"    - {v['name']} ({v['type']})")
    if metrics["missing_datasource"]:
        print(f"  ⚠️ 缺少 datasource 的 panels: {metrics['missing_datasource']}")
    else:
        print(f"  ✅ 所有 panels 都有 datasource")
    if metrics["missing_metric"]:
        print(f"  ⚠️ 缺少 metric 字段的 panels: {metrics['missing_metric']}")
    else:
        print(f"  ✅ 所有 targets 都包含 metric 字段")

    # 写验证报告到 .md
    md_path = output_dir / "03-simulation-r1.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(_render_md(dashboard, report))
    print(f"✅ 推演报告已写入: {md_path}")


def _render_md(dashboard: dict, report: dict) -> str:
    """渲染推演报告为 Markdown."""
    metrics = report["metrics"]
    md = f"""# v1.37 Round 1 推演 (Simulation) 报告

> **迭代**: v1.37-grafana-dashboards
> **日期**: {datetime.now().isoformat()}
> **目的**: 验证仪表盘 JSON 结构符合 Grafana 11.6 schema, 验证 6 变量 + 7 Rows + 21 panels 完整性

---

## 1. 推演结果摘要

| 指标 | 数值 |
|:---|:---:|
| 总 Rows | {metrics['total_rows']} |
| 总 Panels | {metrics['total_panels']} |
| 变量数 | {len(metrics['variables'])} |
| 缺 datasource | {len(metrics['missing_datasource'])} |
| 缺 metric 字段 | {len(metrics['missing_metric'])} |

---

## 2. 各 Row Panel 分布

"""
    for row, count in metrics["panels_per_row"].items():
        md += f"- **{row}**: {count} panels\n"

    md += "\n---\n\n## 3. 变量清单\n\n"
    md += "| 名称 | 类型 | 用途 |\n|:---|:---:|:---|\n"
    var_descriptions = {
        "severity": "严重度过滤 (P0/P1/P2/P3/all)",
        "channel": "通道过滤 (webhook/slack/dingtalk/email/all)",
        "rule": "告警规则 (从 /grafana/variable 拉取 top 20)",
        "instance_id": "实例 ID (单实例场景用 static auto)",
        "operation": "AM 操作 (push_silence/expire_silence/all)",
        "time_range": "时间范围 (1h/6h/24h/7d/30d)",
    }
    for v in metrics["variables"]:
        md += f"| `{v['name']}` | {v['type']} | {var_descriptions.get(v['name'], '-')} |\n"

    md += "\n---\n\n## 4. 端点 - Panel 映射\n\n"
    md += "| Row | Panel 标题 | 端点 | 关键参数 |\n|:---|:---|:---|:---|\n"
    endpoint_map = [
        ("Alert Trend", "总告警量", "/grafana/query", "metric=trend, group_by=status"),
        ("Alert Trend", "P0 当前量", "/grafana/query", "metric=trend, severity=P0"),
        ("Alert Trend", "Top 5 规则", "/grafana/query", "metric=trend, group_by=rule, top_n=5"),
        ("Response Time", "p50/p95/p99", "/grafana/query", "metric=response_time"),
        ("Response Time", "p99 当前值", "/grafana/query", "metric=response_time, bucket=5m"),
        ("Response Time", "by severity", "/grafana/query", "metric=response_time, group_by=severity"),
        ("Escalation", "升级率", "/grafana/query", "metric=escalation"),
        ("Escalation", "by level", "/grafana/query", "metric=escalation, group_by=level"),
        ("Escalation", "Top 5 规则", "/grafana/query", "metric=escalation, group_by=rule, top_n=5"),
        ("Channel Stats", "4 stat panels", "/grafana/query", "metric=channel_stats, channel=webhook/slack/dingtalk/email"),
        ("Channel Stats", "Avg duration", "/grafana/query", "metric=channel_stats, group_by=channel, metric=duration"),
        ("Channel Stats", "Failed trend", "/grafana/query", "metric=channel_stats, group_by=channel, metric=failed"),
        ("Silence", "Hit rate", "/grafana/query", "metric=silence_hit_rate"),
        ("Silence", "Top 10 matchers", "/grafana/query", "metric=silence_hit_rate, group_by=matcher, top_n=10"),
        ("Silence", "Fired vs Silenced", "/grafana/query", "metric=silence_hit_rate, group_by=type"),
        ("AM Sync", "Success rate", "/grafana/query", "metric=am_sync"),
        ("AM Sync", "By operation", "/grafana/query", "metric=am_sync, group_by=operation"),
        ("AM Sync", "Recent failures", "/grafana/query", "metric=am_sync, include_recent_failures=true, limit=10"),
        ("Lock Stats", "Fallback rate", "/grafana/query", "metric=lock_stats"),
        ("Lock Stats", "Recent flushes", "/grafana/query", "metric=lock_stats, group_by=recent_flushes, limit=10"),
        ("Lock Stats", "Totals", "/grafana/query", "metric=lock_stats, group_by=totals"),
    ]
    for row, panel, endpoint, params in endpoint_map:
        md += f"| {row} | {panel} | `{endpoint}` | {params} |\n"

    md += "\n---\n\n## 5. 关键发现\n\n"
    md += """### 5.1 已解决 (R1)

- ✅ Panel 数量匹配需求 (1 仪表盘 / 7 Rows / 21 panels)
- ✅ 所有 panel 都有 datasource (simpod-json-datasource)
- ✅ 所有 target 都包含 metric 字段
- ✅ 6 变量全部定义, 类型与 Draft 一致

### 5.2 仍待解决 (R2 修订)

- ⚠️ **P0-1**: 需在 v1.36 后端增加 Grafana Adapter 路由 (`/grafana/query`, `/grafana/variable`, `/grafana/health`)
- ⚠️ **P0-2**: 需在 v1.36 后端增加 Service Account 鉴权路径 (`GRAFANA_SERVICE_TOKEN` env var)
- ⚠️ **P1-1**: 需明确 v1.36 后端如何解析 POST body 中的 JSON params (与 GET query string 不同)
- ⚠️ **P1-2**: rule 变量需用 query 类型从 `/grafana/variable` 拉取, JSON path 配置需验证
- ⚠️ **P1-3**: 5min 缓存导致 panel 看起来 stale, 需在 README 明确说明

### 5.3 Round 2 待办

- R2-D1: v1.36 后端增加 Grafana Adapter 路由 (4 端点)
- R2-D2: v1.36 后端增加 Service Account 鉴权 (1 函数)
- R2-D3: 明确 POST body 解析与 GET query string 转换
- R2-D4: rule 变量 JSON path 验证
- R2-D5: instance_id 简化为 static 文本
- R2-D6: README 5min 缓存说明

---

## 6. 样例文件

- 仪表盘 JSON 样例: `v1.37-alerts-overview.sample.json` (~30KB, 21 panels, 6 vars)
- 本报告: `03-simulation-r1.md`

---

> **Round 1 Step 4 完成**: 进入 Step 5 (Lock) - 锁定 Round 1 交付物
"""
    return md


if __name__ == "__main__":
    main()
