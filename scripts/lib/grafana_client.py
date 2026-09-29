"""R-F4: verify_grafana_* 共享 Grafana API client.

从 verify_grafana_datasource.py / verify_grafana_prometheus.py 抽取的公共逻辑：
- Basic Auth header 构造
- 通过 Grafana datasource proxy 查询 Prometheus (GET / POST 两种方式)

行为与原脚本保持一致：HTTP/网络异常降级为含 "error" 字段的 dict（调用方检查
`"error" in result` 即可）。
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_GRAFANA_URL = "http://localhost:3000"
DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASSWORD = "CkF14AETkpmIHNq8"


def make_basic_auth_header(
    user: str = DEFAULT_ADMIN_USER,
    password: str = DEFAULT_ADMIN_PASSWORD,
) -> dict:
    """构造 Grafana Basic Auth 请求头."""
    credentials = f"{user}:{password}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}", "Content-Type": "application/json"}


def query_prometheus(
    expr: str,
    *,
    grafana_url: str = DEFAULT_GRAFANA_URL,
    datasource_uid: str,
    method: str = "GET",
    timeout: int = 15,
) -> dict:
    """通过 Grafana 数据源代理查询 Prometheus.

    GET : /api/datasources/proxy/uid/{uid}/api/v1/query?query={expr}
    POST: /api/datasources/proxy/uid/{uid}/api/v1/query (JSON {"expr", "instant"})

    Returns:
        成功: Prometheus 响应 dict; 失败: 含 "error" 字段的 dict。
    """
    base_url = (
        f"{grafana_url}/api/datasources/proxy/uid/{datasource_uid}/api/v1/query"
    )
    headers = make_basic_auth_header()
    try:
        if method.upper() == "POST":
            body = json.dumps({"expr": expr, "instant": True}).encode()
            req = urllib.request.Request(
                base_url, data=body, headers=headers, method="POST"
            )
        else:
            url = f"{base_url}?query={urllib.parse.quote(expr)}"
            req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return {
            "status": "error",
            "errorType": "HTTP",
            "error": f"HTTP {exc.code}",
            "body": exc.read().decode()[:300],
        }
    except Exception as exc:
        return {"status": "error", "errorType": "Exception", "error": str(exc)}
