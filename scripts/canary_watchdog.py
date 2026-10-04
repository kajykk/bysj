#!/usr/bin/env python3
"""金丝雀看门狗 (v4.1-s01-s05): 定时检查 + 到期自动推进 + 超阈值自动回滚.

每轮自动重新登录换 token (ACCESS_TOKEN_EXPIRE_MINUTES=60, 不能复用静态 token).
阈值来自 scripts/canary_release.py AUTO_ROLLBACK_THRESHOLDS.

用法 (Windows 计划任务, 每 15 分钟):
    schtasks /create /tn dws-canary-watchdog ^
      /tr "python E:\\code\\bysj\\scripts\\canary_watchdog.py --once" ^
      /sc minute /mo 15
    python scripts/canary_watchdog.py --once   # 手动跑一次
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_URL = "http://127.0.0.1:8001"
ADMIN_USER = "canary_admin"
ADMIN_PASSWORD = "Canary!Admin123456"
CANARY_ID = 4  # id=2 被探针误杀回滚后重启; id=3 是回滚 API 冒烟测试占位
STAGE_MIN_SECONDS = 24 * 3600  # 每级 ≥24h
NEXT_TRAFFIC = {5: 25, 25: 100}

MAX_ERROR_RATE_PCT = 10.0
MAX_AVG_LATENCY_MS = 500.0
MAX_FALLBACK_RATE_PCT = 5.0
MAX_DRIFT_ALERTS = 10
# 延迟/回退率需连续 N 轮超标才回滚, 容忍冷启动/GC/同机抢资源等单轮毛刺.
# 教训 2026-10-02: 单轮 712ms spike 误杀 id=2; 前后轮均 40~50ms.
CONSECUTIVE_BEFORE_ROLLBACK = 2

# 跨轮状态: 记录连续超标轮数 (持久化进 state 文件)
_consecutive_cache: dict[str, int] = {}

LOG_FILE = Path(__file__).with_name("canary_watchdog.log")
STATE_FILE = Path(__file__).with_name("canary_watchdog.state.json")

# 轻量探针: 2×tabular + 2×text, 测延迟/错误率/回退率.
# 2026-10-02: text 曾触发 BERT 加载 (镜像无 transformers) 误杀 id=2;
# BERT 分支已下线，主路径为双语 TF-IDF (text ~14ms)，恢复 text 覆盖。
PROBE_PAYLOADS = [
    ("POST", "/api/v1/model/predict/tabular",
     {"features": {"age": 20, "gender": 1, "study_year": 2, "cgpa": 3.5,
                   "stress_level": 3, "sleep_duration": 6.0, "social_support": 2,
                   "financial_pressure": 3, "family_history": 0,
                   "academic_pressure": 3, "exercise_frequency": 2,
                   "anxiety": 1, "panic_attack": 0, "treatment_seeking": 0}}),
    ("POST", "/api/v1/model/predict/text", {"text": "最近总是睡不好，感觉很累"}),
    ("POST", "/api/v1/model/predict/text", {"text": "今天心情不错"}),
    ("POST", "/api/v1/model/predict/tabular",
     {"features": {"age": 22, "gender": 0, "study_year": 4, "cgpa": 3.8,
                   "stress_level": 4, "sleep_duration": 5.0, "social_support": 1,
                   "financial_pressure": 4, "family_history": 1,
                   "academic_pressure": 4, "exercise_frequency": 1,
                   "anxiety": 1, "panic_attack": 1, "treatment_seeking": 0}}),
]


def probe_traffic(token: str) -> dict:
    """发轻量探针流量, 返回错误率/平均延迟/回退率."""
    import time as _time

    lat, errors, fallbacks = [], 0, 0
    for method, path, payload in PROBE_PAYLOADS:
        t0 = _time.perf_counter()
        try:
            r = api(method, path, token, payload, timeout=30)
            dt = (_time.perf_counter() - t0) * 1000
            lat.append(dt)
            if r["http"] != 200:
                errors += 1
                continue
            # 结构化判断回退: fallback_used=true 或 model_used 含 fallback/heuristic
            body = r["body"] if isinstance(r["body"], dict) else {}
            data = body.get("data") or {}
            fb = data.get("fallback_used")
            if fb is True:
                fallbacks += 1
                continue
            mu = str(data.get("model_used", ""))
            if "fallback" in mu.lower() or "heuristic" in mu.lower():
                fallbacks += 1
        except Exception:  # noqa: BLE001 - 探针异常计为一次错误
            lat.append((_time.perf_counter() - t0) * 1000)
            errors += 1
    n = len(PROBE_PAYLOADS)
    return {
        "total": n, "errors": errors,
        "error_rate_pct": round(errors / n * 100, 2),
        "avg_latency_ms": round(sum(lat) / len(lat), 1) if lat else 0,
        "fallback_rate_pct": round(fallbacks / n * 100, 2),
    }


def log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S UTC}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def api(method: str, path: str, token: str | None = None,
        payload: dict | None = None, timeout: int = 30) -> dict:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{API_URL}{path}", data=data,
                                 headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"http": resp.status,
                    "body": json.loads(resp.read().decode() or "{}")}
    except urllib.error.HTTPError as e:
        return {"http": e.code, "body": e.read().decode()[:500]}
    except Exception as e:  # noqa: BLE001 - 后端不可达即视为检查失败
        return {"http": -1, "body": str(e)}


def login() -> str:
    r = api("POST", "/api/v1/auth/login",
            payload={"username": ADMIN_USER, "password": ADMIN_PASSWORD})
    if r["http"] != 200:
        log(f"ERROR 登录失败 http={r['http']} body={r['body']}")
        sys.exit(1)
    tok = r["body"].get("data", {}).get("access_token")
    if not tok:
        log(f"ERROR 登录响应无 token: {r['body']}")
        sys.exit(1)
    return tok


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true")
    p.parse_args()

    token = login()
    r = api("GET", f"/api/v1/canary/deployments/{CANARY_ID}", token)
    if r["http"] != 200:
        log(f"ERROR 获取金丝雀状态失败 http={r['http']} body={r['body']}")
        sys.exit(1)
    c = r["body"].get("data", r["body"])
    status, traffic = c.get("status"), c.get("traffic_percent")
    started = datetime.fromisoformat(c["started_at"])
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    log(f"canary id={CANARY_ID} status={status} traffic={traffic}% "
        f"elapsed={elapsed/3600:.2f}h/24h")

    if status != "running":
        log(f"INFO 非 running 状态, 不操作 (status={status}).")
        STATE_FILE.write_text(json.dumps(
            {"ts": datetime.now(timezone.utc).isoformat(), "status": status,
             "action": "none"}, ensure_ascii=False))
        return

    # 健康 + 漂移指标
    h = api("GET", "/health", timeout=10)
    healthy = h["http"] == 200
    d = api("GET", "/api/v1/monitoring/drift-alerts?limit=100", token)
    drift_n = -1
    if d["http"] == 200 and isinstance(d["body"], dict):
        drift_n = len(d["body"].get("data", {}).get("alerts", []))
    log(f"health http={h['http']} drift_alerts={drift_n}")

    violations = []
    if not healthy:
        violations.append("backend unhealthy")
    if drift_n >= 0 and drift_n >= MAX_DRIFT_ALERTS:
        violations.append(f"drift_alerts={drift_n}>=10")

    # 轻量探针: 错误率 / 延迟 / 回退率 (runbook 剩余 3 项阈值)
    probe = probe_traffic(token)
    log(f"probe errors={probe['errors']}/{probe['total']} "
        f"err={probe['error_rate_pct']}% avg_lat={probe['avg_latency_ms']}ms "
        f"fallback={probe['fallback_rate_pct']}%")
    if probe["error_rate_pct"] >= MAX_ERROR_RATE_PCT:
        violations.append(f"error_rate={probe['error_rate_pct']}%>=10%")
    if probe["avg_latency_ms"] >= MAX_AVG_LATENCY_MS:
        violations.append(f"avg_latency={probe['avg_latency_ms']}ms>=500ms")
    if probe["fallback_rate_pct"] >= MAX_FALLBACK_RATE_PCT:
        violations.append(f"fallback_rate={probe['fallback_rate_pct']}%>=5%")
    if not violations:
        # 指标正常, 清零跨轮超标计数, 确保只连续超标才回滚
        try:
            prev = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            prev = {}
        if prev.get("_streak"):
            prev = {k: v for k, v in prev.items() if k != "_streak"}
            STATE_FILE.write_text(json.dumps(prev, ensure_ascii=False))
    immediate = [v for v in violations
                 if not (v.startswith("avg_latency=") or v.startswith("fallback_rate="))]
    streakable = [v for v in violations
                  if v.startswith("avg_latency=") or v.startswith("fallback_rate=")]
    if immediate:
        log(f"WARN 硬阈值命中立即回滚: {immediate}")
        rb = api("POST", f"/api/v1/canary/deployments/{CANARY_ID}/rollback",
                 token, {"reason": "; ".join(immediate + streakable)})
        log(f"rollback http={rb['http']} body={json.dumps(rb['body'], ensure_ascii=False)[:300]}")
        STATE_FILE.write_text(json.dumps(
            {"ts": datetime.now(timezone.utc).isoformat(), "action": "rollback",
             "reason": "; ".join(immediate + streakable)}, ensure_ascii=False))
        return
    if streakable:
        # 连续 N 轮超标才回滚: 读上次 state, 累加本轮的持久化超标键.
        # 单轮 spike 自动清零, 不误杀 (对齐 CONSECUTIVE_BEFORE_ROLLBACK)
        try:
            prev = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            prev = {}
        streak_key = "_streak"
        prev_streak = prev.get(streak_key, 0)
        new_streak = prev_streak + 1
        log(f"WARN 命中阈值 {streakable} (连续 {new_streak}/{CONSECUTIVE_BEFORE_ROLLBACK} 轮).")
        if new_streak < CONSECUTIVE_BEFORE_ROLLBACK:
            log("INFO 未达连续轮数, 本轮只记录不回滚 (单轮毛刺容忍).")
            STATE_FILE.write_text(json.dumps(
                {"ts": datetime.now(timezone.utc).isoformat(), "action": "pending",
                 "violations": streakable, streak_key: new_streak},
                ensure_ascii=False))
            return
        log(f"WARN 连续 {CONSECUTIVE_BEFORE_ROLLBACK} 轮超标, 触发回滚: {streakable}")
        rb = api("POST", f"/api/v1/canary/deployments/{CANARY_ID}/rollback",
                 token, {"reason": "; ".join(streakable)})
        log(f"rollback http={rb['http']} body={json.dumps(rb['body'], ensure_ascii=False)[:300]}")
        STATE_FILE.write_text(json.dumps(
            {"ts": datetime.now(timezone.utc).isoformat(), "action": "rollback",
             "reason": "; ".join(streakable)}, ensure_ascii=False))
        return

    if elapsed >= STAGE_MIN_SECONDS and traffic in NEXT_TRAFFIC:
        nxt = NEXT_TRAFFIC[traffic]
        log(f"INFO 24h 观察期满, 推进 {traffic}% → {nxt}%")
        pr = api("PATCH", f"/api/v1/canary/deployments/{CANARY_ID}/traffic",
                 token, {"traffic_percent": nxt})
        log(f"promote http={pr['http']} body={json.dumps(pr['body'], ensure_ascii=False)[:300]}")
        STATE_FILE.write_text(json.dumps(
            {"ts": datetime.now(timezone.utc).isoformat(), "action": f"promote→{nxt}"},
            ensure_ascii=False))
        return

    remain = (STAGE_MIN_SECONDS - elapsed) / 3600
    log(f"OK 指标正常, 距下一级还剩 {remain:.2f}h, 不操作.")
    STATE_FILE.write_text(json.dumps(
        {"ts": datetime.now(timezone.utc).isoformat(), "action": "none",
         "remaining_h": round(remain, 2)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
