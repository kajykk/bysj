"""阶段四: 通过 HTTP API 触发推理 + 推送指标到服务进程 (容器内执行).

在 dws-backend 服务进程内生成指标数据:
  1. 重置 admin 密码 (确保可登录)
  2. 通过 HTTP API 登录获取 token
  3. 触发推理请求 (生成 model_inference_total / duration)
  4. 查询 metrics 端点验证四类指标

Usage:
    docker cp scripts/trigger_grafana_data.py dws-backend:/tmp/t.py
    docker exec dws-backend python /tmp/t.py
"""
import asyncio
import urllib.request
import json
import sys

BASE = "http://localhost:8000"
API = f"{BASE}/api/v1"


async def reset_admin_password() -> str:
    """重置 admin 密码并返回新密码."""
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    from app.services.auth_service import AuthService

    new_password = "Admin@Canary2026"
    async with AsyncSessionLocal() as db:
        svc = AuthService(db)
        try:
            await svc.reset_password_by_admin("admin", new_password)
            await db.commit()
            print(f"OK admin 密码已重置")
            return new_password
        except Exception as exc:
            print(f"WARN 重置密码失败: {exc}, 尝试直接更新")
            from app.core.security import get_password_hash
            r = await db.execute(text("SELECT id FROM users WHERE username=:u"), {"u": "admin"})
            row = r.fetchone()
            if not row:
                print("ERROR admin 用户不存在")
                sys.exit(1)
            await db.execute(
                text("UPDATE users SET password_hash=:h WHERE id=:id"),
                {"h": get_password_hash(new_password), "id": row[0]},
            )
            await db.commit()
            print(f"OK admin 密码已直接更新")
            return new_password


def http_post(url: str, data: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        print(f"  HTTP {exc.code}: {exc.read().decode()[:200]}")
        return {}
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return {}


def login(password: str) -> str | None:
    resp = http_post(f"{API}/auth/login", {"username": "admin", "password": password})
    data = resp.get("data", {})
    token = data.get("access_token")
    if token:
        print(f"OK 登录成功")
    else:
        print(f"ERROR 登录失败: {resp}")
    return token


def trigger_inference(token: str) -> None:
    """触发文本和结构化推理请求."""
    print("\n触发推理请求...")
    texts = [
        "今天天气真好,和朋友一起出去玩,心情很愉快。",
        "最近总是失眠,什么都提不起兴趣,觉得活着没意思。",
        "我撑不下去了,想结束这一切,每天都很痛苦。",
    ]
    for i, text in enumerate(texts):
        resp = http_post(f"{API}/model/predict/text", {"text": text}, token=token)
        pred = resp.get("data", {}).get("prediction", "?")
        model = resp.get("data", {}).get("model_used", "?")
        print(f"  [{i+1}] model={model} pred={pred}")

    # 结构化推理 (tabular)
    struct_features = {
        "age": 22, "gender": 1, "study_year": 3, "cgpa": 3.2,
        "stress_level": 7, "sleep_duration": 5.0, "social_support": 2,
        "financial_pressure": 3, "family_history": 0,
        "academic_pressure": 4, "exercise_frequency": 1,
        "anxiety": 1, "panic_attack": 0, "treatment_seeking": 0,
    }
    resp = http_post(f"{API}/model/predict/tabular", {"features": struct_features}, token=token)
    pred = resp.get("data", {}).get("prediction", "?")
    print(f"  [structured] pred={pred}")


def verify_metrics() -> None:
    """验证 metrics 端点输出四类指标."""
    from app.core.config import settings
    token = settings.metrics_access_token or "dev-only-metrics-token"
    req = urllib.request.Request(
        f"{API}/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    r = urllib.request.urlopen(req, timeout=10)
    data = r.read().decode()
    lines = [l for l in data.split("\n") if l and not l.startswith("#")]

    categories = {
        "模型质量": ["model_inference_total", "model_inference_duration"],
        "推理延迟": ["http_request_duration", "model_inference_duration"],
    }
    print(f"\nmetrics 总行数: {len(lines)}")
    for cat, keywords in categories.items():
        found = [l for l in lines for k in keywords if k in l]
        print(f"  [{('OK' if found else 'MISSING')}] {cat}: {len(found)} 行")
        for f in found[:2]:
            print(f"    {f[:100]}")

    # 检查 model_inference
    inference_lines = [l for l in lines if "model_inference" in l]
    print(f"\nmodel_inference 指标 ({len(inference_lines)} 行):")
    for l in inference_lines[:5]:
        print(f"  {l[:120]}")


async def main() -> None:
    print("=" * 60)
    print("阶段四: 触发推理 + 验证 metrics")
    print("=" * 60)

    # 1. 重置密码
    password = await reset_admin_password()

    # 2. 登录
    token = login(password)
    if not token:
        print("ERROR 无法登录, 跳过推理触发")
    else:
        # 3. 触发推理
        trigger_inference(token)

    # 4. 验证 metrics
    verify_metrics()

    print("\n" + "=" * 60)
    print("验证完成!")
    print("=" * 60)


asyncio.run(main())
