"""v1.37 Grafana Dashboard JSON 生成脚本.

功能:
1. 加载 `infra/grafana/dashboards/v1.37-alerts-overview.yaml`
2. 为每个 panel 渲染对应类型的 Jinja2 模板
3. 组合为最终 dashboard JSON
4. 输出到 `infra/grafana/dashboards/v1.37-alerts-overview.json`

用法:
    cd e:\code\bysj
    python infra/grafana/scripts/build_dashboard.py
    # 或带参数:
    python infra/grafana/scripts/build_dashboard.py --config .../v1.37-alerts-overview.yaml --output .../v1.37-alerts-overview.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

# 项目根目录 (bysj/)
ROOT = Path(__file__).resolve().parents[3]  # infra/grafana/scripts -> bysj
DEFAULT_CONFIG = ROOT / "infra" / "grafana" / "dashboards" / "v1.37-alerts-overview.yaml"
DEFAULT_OUTPUT = ROOT / "infra" / "grafana" / "dashboards" / "v1.37-alerts-overview.json"
DEFAULT_TEMPLATES = ROOT / "infra" / "grafana" / "dashboards" / "templates"


def render_panel(env: Environment, panel: dict) -> dict:
    """根据 panel.type 渲染对应 Jinja2 模板, 返回 panel JSON 字典."""
    template_name = f"panel_{panel['type']}.json.j2"
    template = env.get_template(template_name)
    rendered = template.render(panel=panel)
    return json.loads(rendered)


def build_dashboard(config_path: Path, output_path: Path, templates_dir: Path) -> int:
    """主构建流程."""
    print(f"[BUILD] 加载配置: {config_path}")
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    print(f"[BUILD] 加载模板目录: {templates_dir}")
    env = Environment(loader=FileSystemLoader(str(templates_dir)))

    # 校验 panel 类型都有对应模板
    valid_types = {"stat", "timeseries", "gauge", "bargauge", "piechart", "table"}
    panel_types = {p["type"] for p in config["panels"]}
    unknown = panel_types - valid_types
    if unknown:
        print(f"[BUILD] ERROR: unknown panel types: {unknown}")
        return 1

    # 渲染每个 panel
    rendered_panels = []
    for panel in config["panels"]:
        try:
            rendered = render_panel(env, panel)
            rendered_panels.append(rendered)
        except Exception as e:
            print(f"[BUILD] ERROR: rendering panel {panel.get('id', '?')} ({panel.get('type')}): {e}")
            return 1

    # 组合 dashboard
    dashboard = {
        "title": config["dashboard"]["title"],
        "uid": config["dashboard"]["uid"],
        "schemaVersion": config["dashboard"]["schemaVersion"],
        "version": config["dashboard"]["version"],
        "tags": config["dashboard"]["tags"],
        "timezone": config["dashboard"]["timezone"],
        "time": config["dashboard"]["time"],
        "refresh": config["dashboard"]["refresh"],
        "templating": config["templating"],
        "panels": rendered_panels,
    }

    # 写入输出
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=2)

    print(f"[BUILD] ✅ 生成完成: {output_path}")
    print(f"[BUILD] panels: {len(rendered_panels)}, vars: {len(config['templating']['list'])}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build v1.37 Grafana dashboard JSON")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="YAML 配置文件路径")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="输出 JSON 路径")
    parser.add_argument("--templates", type=Path, default=DEFAULT_TEMPLATES, help="Jinja2 模板目录")
    args = parser.parse_args()

    if not args.config.exists():
        print(f"[BUILD] ERROR: config not found: {args.config}")
        return 1
    if not args.templates.exists():
        print(f"[BUILD] ERROR: templates dir not found: {args.templates}")
        return 1

    return build_dashboard(args.config, args.output, args.templates)


if __name__ == "__main__":
    raise SystemExit(main())
