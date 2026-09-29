"""v1.39 任务 A: 完整 mutation API 测试 + user token 验证.

覆盖:
  A1: user_none token 重新跑 user 端点 (消除 403)
  A2: POST/PUT/DELETE mutation 测试
"""
import json
import os
import secrets
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE = "http://127.0.0.1:8000"
results = []


def req(method, path, *, headers=None, body=None, timeout=15):
    h = {"Accept": "application/json"}
    if headers:
        h.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    r = Request(BASE + path, data=data, method=method, headers=h)
    try:
        with urlopen(r, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace"), resp.getcode()
    except HTTPError as e:
        return e.read().decode("utf-8", errors="replace"), e.code
    except URLError as e:
        return None, 0


def call(name, method, path, **kw):
    raw, code = req(method, path, **kw)
    ok = 200 <= code < 300 or code in (201, 204)
    status = "PASS" if ok else f"HTTP {code}"
    results.append((name, status, code, raw))
    icon = "[OK]  " if ok else "[FAIL]"
    summary = (raw or "")[:80].replace("\n", " ")
    print(f"  {icon} {name} ({method} {path}): {status} | {summary}")
    return raw, code


def login(username, password):
    raw, code = req("POST", "/api/v1/auth/login",
                    body={"username": username, "password": password})
    if code != 200:
        return None
    payload = json.loads(raw)
    inner = payload.get("data", payload)
    return inner.get("access_token")


def main():
    print("=" * 78)
    print("A 任务: user token + mutation API 完整验证")
    print("=" * 78)

    # 登录 3 种角色
    print("\n[A0] 3 角色登录")
    admin_tok = login("admin", "***REMOVED***")
    user_tok = login("user_none", "***REMOVED***")
    counselor_tok = login("dr_wang", "***REMOVED***")
    print(f"  admin token: {bool(admin_tok)} ({len(admin_tok) if admin_tok else 0} chars)")
    print(f"  user token:  {bool(user_tok)} ({len(user_tok) if user_tok else 0} chars)")
    print(f"  counselor:   {bool(counselor_tok)} ({len(counselor_tok) if counselor_tok else 0} chars)")

    admin = {"Authorization": f"Bearer {admin_tok}"} if admin_tok else {}
    user = {"Authorization": f"Bearer {user_tok}"} if user_tok else {}
    counselor = {"Authorization": f"Bearer {counselor_tok}"} if counselor_tok else {}

    # A1: user token 验证之前 403 的端点
    print("\n[A1] user 角色端点 (之前 admin 403)")
    call("user/risk/report (user)", "GET", "/api/v1/user/risk/report", headers=user)
    call("user/risk/trend (user)", "GET", "/api/v1/user/risk/trend", headers=user)
    call("user/risk/export (user)", "GET", "/api/v1/user/risk/export", headers=user)
    call("user/gdpr/export (user)", "GET", "/api/v1/user/gdpr/export", headers=user)
    call("user/data/history (user)", "GET", "/api/v1/user/data/history", headers=user)
    call("user/warnings (user)", "GET", "/api/v1/user/warnings", headers=user)

    # A2: POST mutation - draft
    print("\n[A2] POST mutations - user data")
    call("POST user/data/draft", "POST", "/api/v1/user/data/draft", headers=user,
         body={"draft_type": "unified",
               "data_payload": {"mood_score": 5, "sleep_hours": 7.5, "emotion_tags": ["calm"]}})
    call("GET user/data/draft/unified", "GET", "/api/v1/user/data/draft/unified", headers=user)
    call("POST user/data/text/analyze", "POST", "/api/v1/user/data/text/analyze", headers=user,
         body={"entry_type": "diary", "content": "最近睡不好, 心情低落",
               "emotion_tags": ["sad", "anxious"], "mood_score": 4})
    call("POST user/data/physiological", "POST", "/api/v1/user/data/physiological/record", headers=user,
         body={"source": "manual", "heart_rate": 72, "sleep_hours": 7.0,
               "steps": 8000, "sleep_quality": 4, "data_payload": {"screen_time": 2.0}})

    # A2: POST collect (评估数据)
    print("\n[A2] POST mutations - assessment")
    call("POST user/data/collect", "POST", "/api/v1/user/data/collect", headers=user,
         body={
             "assessment_type": "PHQ-9",
             "data_payload": {"answers": [1, 2, 1, 2, 1, 1, 0, 2, 1],
                              "risk_score": 11, "risk_level": 2},
         })

    # A2: POST content favorite
    print("\n[A2] POST mutations - content")
    raw, code = call("POST user/content/{id}/favorite", "POST", "/api/v1/user/content/1/favorite", headers=user)
    # A2: POST meditation log
    call("POST user/content/meditation/log", "POST", "/api/v1/user/content/meditation/log", headers=user,
         body={"content_id": 1, "duration_seconds": 300, "rating": 4})

    # A2: PUT mutations
    print("\n[A2] PUT mutations")
    call("PUT user/warning-settings", "PUT", "/api/v1/user/warning-settings", headers=user,
         body={"threshold_level": 2, "notification_enabled": True})
    call("PUT auth/profile", "PUT", "/api/v1/auth/profile", headers=user,
         body={"nickname": "Updated User", "email": "user_updated@example.com"})

    # A2: POST alert silence
    print("\n[A2] POST/PUT/DELETE - alerts")
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    end = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=1)).isoformat()
    raw, code = call("POST alerts/silences", "POST", "/api/v1/alerts/silences", headers=admin,
                     body={"name": "smoke_test_silence",
                           "matcher": {"alertname": "test_alert"},
                           "starts_at": now, "ends_at": end,
                           "comment": "Test silence by API smoke"})
    silence_id = None
    if raw and code in (200, 201):
        try:
            payload = json.loads(raw)
            inner = payload.get("data", payload)
            silence_id = inner.get("id") or inner.get("silence_id")
            print(f"    -> silence_id={silence_id}")
        except Exception:
            pass
    if silence_id:
        call(f"DELETE alerts/silences/{silence_id}", "DELETE", f"/api/v1/alerts/silences/{silence_id}", headers=admin)

    # A2: POST counselor bind-code refresh
    call("POST counselor/bind-code/refresh", "POST", "/api/v1/counselor/bind-code/refresh", headers=counselor)

    # A2: POST validation run
    print("\n[A2] POST validations")
    call("POST validation/run", "POST", "/api/v1/validation/run", headers=admin,
         body={"model_version": "v1.32-baseline",
               "dataset_path": "./data/validation_smoke.csv",
               "baseline_version": "v1.30",
               "baseline_dataset_path": "./data/validation_baseline.csv"})

    # A2: POST auth/change-password (admin)
    print("\n[A2] auth mutations")
    # 测试注册新用户
    new_user = {
        "username": f"smoke_test_{int(__import__('time').time())}",
        "email": f"smoke{int(__import__('time').time())}@test.com",
        # AUDIT-2026-09-28: 注册测试用户使用随机口令，不硬编码
        "password": os.environ.get("E2E_USER_PASSWORD") or secrets.token_urlsafe(16),
        "role": "user",
    }
    raw, code = call("POST auth/register", "POST", "/api/v1/auth/register", body=new_user)
    if raw and code in (200, 201):
        print(f"  -> registered new user: {new_user['username']}")

    # Summary
    print("\n" + "=" * 78)
    print("A 任务汇总")
    print("=" * 78)
    pass_n = sum(1 for _, s, _, _ in results if s == "PASS")
    fail_n = sum(1 for _, s, _, _ in results if s != "PASS")
    total = len(results)
    print(f"  总计: PASS {pass_n}/{total}, FAIL {fail_n}/{total}")
    if fail_n:
        print("\n失败详情:")
        for name, s, code, body in results:
            if s != "PASS":
                print(f"  - {name}: {s} | {(body or '')[:80]}")
    print("=" * 78)
    return 0 if fail_n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
