"""阶段四: 触发融合推理 (含金丝雀路由) 生成 model_inference_total/duration 指标.

L13 修复（ROUND_23）：口令从环境变量 `BYSJ_ADMIN_PASSWORD` 读取
（用户名由 `BYSJ_ADMIN_USERNAME` 提供，默认 admin）。修前模块级硬编码
PASSWORD 常量——同一形态的凭据散落在多个脚本里，改一处漏一处。
缺失即报错退出（退出码 2），不回落默认值。
"""
import json
import os
import sys
import urllib.request

API = "http://localhost:8000/api/v1"
USERNAME = os.environ.get("BYSJ_ADMIN_USERNAME") or "admin"
PASSWORD = os.environ.get("BYSJ_ADMIN_PASSWORD")

if not PASSWORD:
    print(
        "ERROR: 缺少环境变量 BYSJ_ADMIN_PASSWORD。\n"
        "本脚本不再内置任何口令（L13 修复）：请显式提供后再运行。",
        file=sys.stderr,
    )
    sys.exit(2)


def login() -> str:
    body = json.dumps({"username": USERNAME, "password": PASSWORD}).encode()
    req = urllib.request.Request(
        f"{API}/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())["data"]["access_token"]


def trigger_fusion(token: str) -> None:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    cases = [
        {"features": {"age": 22, "gender": 1, "study_year": 3, "cgpa": 3.2, "stress_level": 7, "sleep_duration": 5.0, "social_support": 2, "financial_pressure": 3, "family_history": 0, "academic_pressure": 4, "exercise_frequency": 1, "anxiety": 1, "panic_attack": 0, "treatment_seeking": 0},
         "text": "最近总是失眠,什么都提不起兴趣,觉得活着没意思。",
         "physiological": {"heart_rate": 95, "hrv": 25, "steps": 1500, "sleep_efficiency": 0.65, "activity_variance": 0.3}},
        {"features": {"age": 21, "gender": 0, "study_year": 2, "cgpa": 3.6, "stress_level": 3, "sleep_duration": 7.0, "social_support": 4, "financial_pressure": 1, "family_history": 0, "academic_pressure": 2, "exercise_frequency": 3, "anxiety": 0, "panic_attack": 0, "treatment_seeking": 0},
         "text": "今天心情不错,和朋友一起吃了饭,看了部电影。",
         "physiological": {"heart_rate": 72, "hrv": 60, "steps": 8000, "sleep_efficiency": 0.9, "activity_variance": 0.7}},
    ]
    print(f"触发 {len(cases)} 个融合推理请求...")
    for i, case in enumerate(cases):
        body = json.dumps(case).encode()
        req = urllib.request.Request(
            f"{API}/model/predict/fusion",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode()).get("data", {})
                canary = data.get("canary_routed", False)
                ver = data.get("canary_version", "-")
                pred = data.get("prediction", "?")
                prob = data.get("probability", 0)
                model = data.get("model_used", "?")
                print(f"  [{i+1}] pred={pred} prob={prob:.3f} model={model} canary={canary} ver={ver}")
        except Exception as exc:
            print(f"  [{i+1}] ERROR: {exc}")


def main() -> None:
    print("=" * 60)
    print("触发融合推理 (生成 model_inference + canary 指标)")
    print("=" * 60)
    try:
        token = login()
        print(f"OK 登录成功")
        trigger_fusion(token)
    except Exception as exc:
        print(f"ERROR: {exc}")
        raise
    print("=" * 60)


if __name__ == "__main__":
    main()
