"""R-F4: verify_grafana_* 共享 Grafana API client.

从 verify_grafana_datasource.py / verify_grafana_prometheus.py 抽取的公共逻辑：
- Basic Auth header 构造
- 通过 Grafana datasource proxy 查询 Prometheus (GET / POST 两种方式)

行为与原脚本保持一致：HTTP/网络异常降级为含 "error" 字段的 dict（调用方检查
`"error" in result` 即可）。
"""

from __future__ import annotations

import os
import base64
import json
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_GRAFANA_URL = "http://localhost:3000"
DEFAULT_ADMIN_USER = "admin"


def require_admin_password() -> str:
    """读取 Grafana admin 口令。缺失即抛错, **不提供默认值**。

    AUDIT-2026-10-07 (S-2): 原DEFAULT_ADMIN_PASSWORD 为硬编码字面量且扩散到 5 个文件。
    硬编码默认值 = 默认可用凭据: 任何漏改的脚本都会静默回落到同一个弱口令。
    故此处 fail-fast, 迫使部署方显式设置 GRAFANA_ADMIN_PASSWORD。

    惰性读取: 不在模块导入期执行, 避免 `import grafana_client` 直接抛错
    (那会让所有引用方在 import 阶段崩溃, 而非在实际用到凭据时)。
    """
    value = os.environ.get("GRAFANA_ADMIN_PASSWORD", "").strip()
    if not value:
        raise RuntimeError(
            "GRAFANA_ADMIN_PASSWORD 未设置。请配置环境变量后再运行本脚本, "
            "或在 docker-compose 的 .env 中设置 (禁止使用默认值)。"
        )
    return value


def make_basic_auth_header(
    user: str = DEFAULT_ADMIN_USER,
    password: str | None = None,
) -> dict:
    """构造 Grafana Basic Auth 请求头.

    password 为 None 时从环境变量读取(推荐); 显式传入仅用于测试。
    """
    if password is None:
        password = require_admin_password()
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
