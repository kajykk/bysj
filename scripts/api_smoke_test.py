"""v1.39 R3 全量 API 验证 - 基于真实 OpenAPI 路由.

覆盖全部 22 个 tag 的关键 GET 端点 + 几个 POST/PUT.
"""
import json
import os
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE = "http://127.0.0.1:8000"
results = []


def req(method, path, *, headers=None, body=None, timeout=15):
    url = BASE + path
    data = None
    h = {"Accept": "application/json"}
    if headers:
        h.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    r = Request(url, data=data, method=method, headers=h)
    try:
        with urlopen(r, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace"), resp.getcode(), None
    except HTTPError as e:
        return e.read().decode("utf-8", errors="replace"), e.code, None
    except URLError as e:
        return None, 0, str(e.reason)


def call(name, method, path, **kw):
    raw, code, err = req(method, path, **kw)
    if err:
        results.append((name, "CONN_FAIL", code, err[:80]))
        print(f"  [CONN] {name} ({method} {path})")
        return None
    summary = (raw or "")[:100].replace("\n", " ")
    ok = 200 <= code < 300 or code in (201, 204)
    status = "PASS" if ok else f"HTTP {code}"
    results.append((name, status, code, summary))
    icon = "[OK]  " if ok else "[FAIL]"
    print(f"  {icon} {name} ({method} {path}): {status}")
    return raw


def get_token(username, password):
    raw, code, _ = req("POST", "/api/v1/auth/login",
                       body={"username": username, "password": password})
    if code != 200:
        return None, None
    payload = json.loads(raw)
    inner = payload.get("data", payload)
    return inner.get("access_token"), inner.get("refresh_token")


def main():
    print("=" * 78)
    print("v1.39 R3 全量 API 验证 (基于真实 OpenAPI 路由)")
    print("=" * 78)

    # 0. 健康 / OpenAPI
    print("\n[0] 基础")
    call("/health", "GET", "/health")
    call("/health/ready", "GET", "/health/ready")
    call("/health/seed", "GET", "/health/seed")
    call("version", "GET", "/api/v1/version")
    call("metrics (v1.39)", "GET", "/api/v1/metrics")
    call("OpenAPI", "GET", "/openapi.json")

    # 1. 认证
    print("\n[1] auth")
    # AUDIT-2026-09-28: 口令不得硬编码入库，改从环境变量读取
    _admin_pw = os.environ.get("E2E_ADMIN_PASSWORD")
    if not _admin_pw:
        raise SystemExit("请设置环境变量 E2E_ADMIN_PASSWORD（禁止在源码中硬编码口令）")
    raw = call("auth/login admin", "POST", "/api/v1/auth/login",
               body={"username": "admin", "password": _admin_pw})
    payload = json.loads(raw) if raw else {}
    inner = payload.get("data", payload)
    token = inner.get("access_token")
    auth = {"Authorization": f"Bearer {token}"} if token else {}
    print(f"  -> token acquired: {bool(token)}")

    # 2. user-data (普通用户)
    print("\n[2] user-data (匿名)")
    call("user/data/binding GET", "GET", "/api/v1/user/data/binding", headers=auth)
    call("user/data/history GET", "GET", "/api/v1/user/data/history", headers=auth)
    call("user/data/draft/unified GET", "GET", "/api/v1/user/data/draft/unified", headers=auth)

    # 3. user-risk
    print("\n[3] user-risk")
    call("user/risk/report GET", "GET", "/api/v1/user/risk/report", headers=auth)
    call("user/risk/trend GET", "GET", "/api/v1/user/risk/trend", headers=auth)

    # 4. user-warning
    print("\n[4] user-warning")
    call("user/warnings GET", "GET", "/api/v1/user/warnings", headers=auth)
    call("user/warning-settings GET", "GET", "/api/v1/user/warning-settings", headers=auth)

    # 5. user-content
    print("\n[5] user-content")
    call("user/content/ GET", "GET", "/api/v1/user/content/", headers=auth)
    call("user/content/recommendations", "GET", "/api/v1/user/content/recommendations", headers=auth)
    call("user/content/favorites", "GET", "/api/v1/user/content/favorites/list", headers=auth)

    # 6. user-intervention
    print("\n[6] user-intervention")
    call("user/intervention/active", "GET", "/api/v1/user/intervention/active", headers=auth)
    call("user/intervention/history", "GET", "/api/v1/user/intervention/history", headers=auth)

    # 7. alerts (admin)
    print("\n[7] alerts")
    call("alerts/history", "GET", "/api/v1/alerts/history", headers=auth)
    call("alerts/archive", "GET", "/api/v1/alerts/archive", headers=auth)
    call("alerts/silences", "GET", "/api/v1/alerts/silences", headers=auth)
    call("alerts/silences/active", "GET", "/api/v1/alerts/silences/active", headers=auth)

    # 8. observability (v1.39 R3 关键)
    print("\n[8] observability (v1.39 核心)")
    call("observability/health", "GET", "/api/v1/alerts/observability/health", headers=auth)
    call("observability/trend", "GET", "/api/v1/alerts/observability/trend", headers=auth)
    call("observability/response-time", "GET", "/api/v1/alerts/observability/response-time", headers=auth)
    call("observability/escalation", "GET", "/api/v1/alerts/observability/escalation", headers=auth)
    call("observability/channel-stats", "GET", "/api/v1/alerts/observability/channel-stats", headers=auth)
    call("observability/silence-hit-rate", "GET", "/api/v1/alerts/observability/silence-hit-rate", headers=auth)
    call("observability/am-sync", "GET", "/api/v1/alerts/observability/am-sync", headers=auth)
    call("observability/lock-stats", "GET", "/api/v1/alerts/observability/lock-stats", headers=auth)

    # 9. grafana-adapter
    print("\n[9] grafana-adapter (v1.39 R3)")
    call("grafana/health", "GET", "/api/v1/alerts/observability/grafana/health", headers=auth)
    call("grafana/ (root)", "GET", "/api/v1/alerts/observability/grafana/", headers=auth)

    # 10. monitoring
    print("\n[10] monitoring")
    call("monitoring/model-success-rate", "GET", "/api/v1/monitoring/model-success-rate", headers=auth)
    call("monitoring/fallback-stats", "GET", "/api/v1/monitoring/fallback-stats", headers=auth)
    call("monitoring/drift-alerts", "GET", "/api/v1/monitoring/drift-alerts", headers=auth)
    call("monitoring/dashboard-summary", "GET", "/api/v1/monitoring/dashboard-summary", headers=auth)
    call("monitoring/engine-snapshot", "GET", "/api/v1/monitoring/engine-snapshot", headers=auth)

    # 11. reviews
    print("\n[11] reviews")
    call("reviews", "GET", "/api/v1/reviews", headers=auth)
    call("reviews/stats", "GET", "/api/v1/reviews/stats", headers=auth)
    call("reviews/crisis-events", "GET", "/api/v1/reviews/crisis-events", headers=auth)

    # 12. counselor
    print("\n[12] counselor")
    call("counselor/warnings", "GET", "/api/v1/counselor/warnings", headers=auth)
    call("counselor/users", "GET", "/api/v1/counselor/users", headers=auth)
    call("counselor/groups", "GET", "/api/v1/counselor/groups", headers=auth)
    call("counselor/bind-code", "GET", "/api/v1/counselor/bind-code", headers=auth)

    # 13. canary
    print("\n[13] canary")
    call("canary/deployments", "GET", "/api/v1/canary/deployments", headers=auth)
    call("canary/traffic-percentages", "GET", "/api/v1/canary/traffic-percentages", headers=auth)

    # 14. model
    print("\n[14] model")
    call("model/status", "GET", "/api/v1/model/status", headers=auth)
    call("model/debug/performance", "GET", "/api/v1/model/debug/performance", headers=auth)
    call("model/training/jobs", "GET", "/api/v1/model/training/jobs", headers=auth)

    # 15. validation
    print("\n[15] validation")
    call("validation/jobs", "GET", "/api/v1/validation/jobs", headers=auth)

    # 16. reports
    print("\n[16] reports")
    call("reports/templates", "GET", "/api/v1/reports/templates", headers=auth)

    # 17. admin (admin only)
    print("\n[17] admin")
    call("admin/dashboard", "GET", "/api/v1/admin/dashboard", headers=auth)
    call("admin/stats", "GET", "/api/v1/admin/stats", headers=auth)
    call("admin/audit-logs", "GET", "/api/v1/admin/audit-logs", headers=auth)
    call("admin/operation-logs", "GET", "/api/v1/admin/operation-logs", headers=auth)
    call("admin/models", "GET", "/api/v1/admin/models", headers=auth)
    call("admin/templates", "GET", "/api/v1/admin/templates", headers=auth)
    call("admin/thresholds", "GET", "/api/v1/admin/thresholds", headers=auth)
    call("admin/metrics-summary", "GET", "/api/v1/admin/metrics-summary", headers=auth)

    # 18. GDPR
    print("\n[18] GDPR")
    call("user/gdpr/export", "GET", "/api/v1/user/gdpr/export", headers=auth)

    # Summary
    print("\n" + "=" * 78)
    print("汇总")
    print("=" * 78)
    by_tag = {}
    for name, status, code, body in results:
        first = name.split(" ")[0].split("/")[0]
        by_tag.setdefault(first, []).append((name, status, code, body))

    pass_n = sum(1 for _, s, _, _ in results if s == "PASS")
    fail_n = sum(1 for _, s, _, _ in results if s != "PASS")
    total = len(results)
    print(f"\n  总计: PASS {pass_n}/{total}, FAIL {fail_n}/{total}")
    for tag, items in sorted(by_tag.items()):
        p = sum(1 for _, s, _, _ in items if s == "PASS")
        f = sum(1 for _, s, _, _ in items if s != "PASS")
        print(f"  [{tag:15}] PASS {p}/{len(items)}  FAIL {f}/{len(items)}")

    if fail_n:
        print("\n失败详情 (前 20):")
        c = 0
        for name, s, code, body in results:
            if s != "PASS" and c < 20:
                print(f"  - {name}: {s} | {body[:80]}")
                c += 1
    print("=" * 78)
    return 0 if fail_n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
