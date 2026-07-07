"""v1.38 Grafana Dashboard Template 单元测试 (7 tests).

被测资产:
- infra/grafana/dashboards/v1.37-alerts-overview.yaml
- infra/grafana/dashboards/templates/*.json.j2
- infra/grafana/scripts/build_dashboard.py
- infra/grafana/dashboards/v1.37-alerts-overview.json (生成产物)

合计: 7 测试 (1 meta + 6 功能)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]  # backend/tests -> bysj
YAML_CONFIG = ROOT / "infra" / "grafana" / "dashboards" / "v1.37-alerts-overview.yaml"
TEMPLATES_DIR = ROOT / "infra" / "grafana" / "dashboards" / "templates"
DASHBOARD_JSON = (
    ROOT / "infra" / "grafana" / "dashboards" / "v1.37-alerts-overview.json"
)
BUILD_SCRIPT = ROOT / "infra" / "grafana" / "scripts" / "build_dashboard.py"

V137_METRICS = {
    "trend",
    "response_time",
    "escalation",
    "channel_stats",
    "silence_hit_rate",
    "am_sync",
    "lock_stats",
}

P0_PANEL_IDS = {5, 6, 7, 8, 10, 12, 13, 14, 15, 19, 22, 23, 24}


# ==================== Fixtures ====================


@pytest.fixture(scope="module")
def yaml_config() -> dict:
    with open(YAML_CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def dashboard_json() -> dict:
    with open(DASHBOARD_JSON, encoding="utf-8") as f:
        return json.load(f)


# ==================== 1. Meta Test ====================


def test_meta_test_count():
    """meta-test: 验证本文件包含 6 个功能测试 (不计算本 meta-test 自身)."""
    test_file = Path(__file__)
    content = test_file.read_text(encoding="utf-8")
    # 匹配 def test_xxx (排除 test_meta_xxx)
    funcs = re.findall(r"^def (test_\w+)\(", content, re.MULTILINE)
    funcs = [f for f in funcs if not f.startswith("test_meta_")]
    assert len(funcs) == 6, f"expected 6 functional tests, got {len(funcs)}: {funcs}"


# ==================== 2. Functional Tests ====================


def test_yaml_config_loads(yaml_config):
    """T-GRAF-001: YAML 配置可被 yaml.safe_load 解析, 24 panels + 7 vars."""
    assert "panels" in yaml_config
    assert len(yaml_config["panels"]) == 24
    assert len(yaml_config["templating"]["list"]) == 7


def test_jinja2_templates_render():
    """T-GRAF-002: 6 个 .json.j2 模板可被 Jinja2 解析."""
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    types = ["stat", "timeseries", "gauge", "bargauge", "piechart", "table"]
    for t in types:
        template_path = TEMPLATES_DIR / f"panel_{t}.json.j2"
        assert template_path.exists(), f"template missing: {template_path}"
        # 解析模板 (不渲染, 仅验证语法)
        env.parse(template_path.read_text(encoding="utf-8"))


def test_generated_json_has_24_panels(dashboard_json):
    """T-GRAF-003 + T-GRAF-004: 生成的 JSON 含 24 panels."""
    assert "panels" in dashboard_json
    assert len(dashboard_json["panels"]) == 24


def test_panel_metrics_exist_in_v137(dashboard_json):
    """AC-4: panel 引用的 metric 全部在 v1.37 7 metric 集合中."""
    for panel in dashboard_json["panels"]:
        for target in panel.get("targets", []):
            metric = target.get("payload", {}).get("metric")
            assert (
                metric in V137_METRICS
            ), f"panel {panel['id']} uses unknown metric: {metric}"


def test_panel_variable_references(dashboard_json):
    """AC-4 扩展: panel 引用的 $xxx 变量必须在 templating.list 中."""
    var_names = {v["name"] for v in dashboard_json["templating"]["list"]}
    refs: set[str] = set()
    for panel in dashboard_json["panels"]:
        for target in panel.get("targets", []):
            params = target.get("payload", {}).get("params", {})
            for v in params.values():
                for match in re.findall(r"\$(\w+)", str(v)):
                    refs.add(match)
    assert refs.issubset(var_names), f"orphan $xxx refs: {refs - var_names}"


def test_p0_panels_have_thresholds(dashboard_json):
    """AC-5: P0 panel 含 fieldConfig.defaults.thresholds."""
    missing = []
    for panel in dashboard_json["panels"]:
        if panel["id"] in P0_PANEL_IDS:
            thresholds = (
                panel.get("fieldConfig", {}).get("defaults", {}).get("thresholds")
            )
            if not thresholds or not thresholds.get("steps"):
                missing.append(panel["id"])
    assert not missing, f"P0 panels missing thresholds: {missing}"
