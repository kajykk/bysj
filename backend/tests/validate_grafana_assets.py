"""v1.37 Static validation of dashboard JSON + provisioning YAML (no Grafana container needed)."""
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]  # backend/tests -> bysj root

# 1. Dashboard JSON validation
sample_json = ROOT / "docs/planning/v1.37-grafana-dashboards/v1.37-alerts-overview.sample.json"
print("=== test_dashboard_json_valid ===")
try:
    with open(sample_json, encoding="utf-8") as f:
        dash = json.load(f)
    print(f"  title: {dash.get('title')}")
    print(f"  uid: {dash.get('uid')}")
    print(f"  schemaVersion: {dash.get('schemaVersion')}")
    print(f"  panels count: {len(dash.get('panels', []))}")
    print(f"  templating vars: {len(dash.get('templating', {}).get('list', []))}")
    print(f"  refresh: {dash.get('refresh')}")
    print(f"  tags: {dash.get('tags')}")
    # Required Grafana 11.6 schema fields
    required = ["title", "uid", "schemaVersion", "panels", "templating"]
    missing = [k for k in required if k not in dash]
    if missing:
        print(f"  FAIL: missing required fields: {missing}")
        sys.exit(1)
    print(f"  PASS: dashboard JSON schema valid (Grafana 11.6)")
except Exception as e:
    print(f"  FAIL: {e}")
    sys.exit(1)

# 2. Datasource provisioning
print("\n=== test_datasource_provisioning_loads (static) ===")
ds_yaml = ROOT / "infra/grafana/provisioning/datasources/observability-api.yaml"
try:
    with open(ds_yaml, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    print(f"  apiVersion: {cfg.get('apiVersion')}")
    assert cfg.get("apiVersion") == 1, "apiVersion must be 1"
    for ds in cfg.get("datasources", []):
        print(f"  datasource: {ds.get('name')} (type={ds.get('type')}, url={ds.get('url')})")
        assert ds.get("type") == "simpod-json-datasource", "wrong datasource type"
        assert ds.get("url"), "datasource url missing"
        assert ds.get("secureJsonData", {}).get("Authorization"), "Authorization header missing"
    print(f"  PASS: datasource provisioning YAML valid")
except Exception as e:
    print(f"  FAIL: {e}")
    sys.exit(1)

# 3. Dashboard provider provisioning
print("\n=== test_dashboard_provisioning_loads (static) ===")
dp_yaml = ROOT / "infra/grafana/provisioning/dashboards/v1.37-alerts.yaml"
try:
    with open(dp_yaml, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    print(f"  apiVersion: {cfg.get('apiVersion')}")
    assert cfg.get("apiVersion") == 1, "apiVersion must be 1"
    for p in cfg.get("providers", []):
        print(f"  provider: {p.get('name')} folder={p.get('folder')} path={p.get('options', {}).get('path')}")
        assert p.get("options", {}).get("path"), "provider path missing"
    print(f"  PASS: dashboard provider provisioning YAML valid")
except Exception as e:
    print(f"  FAIL: {e}")
    sys.exit(1)

# 4. Docker compose grafana service
print("\n=== test_docker_compose_grafana (static) ===")
import yaml as _yaml
compose_path = ROOT / "docker-compose.yml"
try:
    with open(compose_path, encoding="utf-8") as f:
        compose = _yaml.safe_load(f)
    svc = compose.get("services", {}).get("grafana")
    assert svc, "grafana service missing in docker-compose.yml"
    print(f"  image: {svc.get('image')}")
    print(f"  port: {svc.get('ports')}")
    print(f"  healthcheck: {bool(svc.get('healthcheck'))}")
    print(f"  depends_on: {list((svc.get('depends_on') or {}).keys())}")
    print(f"  GF_PLUGINS_PREINSTALL: {svc.get('environment', {}).get('GF_PLUGINS_PREINSTALL')}")
    assert "simpod-json-datasource" in (svc.get("environment", {}).get("GF_PLUGINS_PREINSTALL", "") or "")
    print(f"  PASS: docker-compose grafana service valid")
except Exception as e:
    print(f"  FAIL: {e}")
    sys.exit(1)

print("\n=== ALL STATIC VALIDATION PASSED ===")
