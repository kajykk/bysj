"""阶段三续: 触发推理流量, 验证金丝雀路由和 M4 stacking 模型可用性 (容器内执行).

通过 HTTP API 触发 fusion 推理请求, 金丝雀路由会将 5% 流量分发到 M4 stacking.
"""
import json
import sys
import urllib.request


API = "http://localhost:8000/api/v1"
USERNAME = "admin"
PASSWORD = "Admin@Canary2026"


def login() -> str:
    body = json.dumps({"username": USERNAME, "password": PASSWORD}).encode()
    req = urllib.request.Request(
        f"{API}/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    r = urllib.request.urlopen(req, timeout=10)
    data = json.loads(r.read().decode())
    token = data.get("data", {}).get("access_token")
    if not token:
        print(f"ERROR: 登录失败: {data}")
        sys.exit(1)
    return token


def trigger_fusion(token: str, count: int = 20) -> None:
    """触发 fusion 推理, 5% 流量应路由到 M4 stacking."""
    print(f"\n触发 {count} 次 fusion 推理请求 (5% 应路由到 M4)...")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # 多样化的测试输入
    test_cases = [
        {
            "features": {"age": 22, "gender": 1, "study_year": 3, "cgpa": 3.2, "stress_level": 7, "sleep_duration": 5.0, "social_support": 2, "financial_pressure": 3, "family_history": 0, "academic_pressure": 4, "exercise_frequency": 1, "anxiety": 1, "panic_attack": 0, "treatment_seeking": 0},
            "text": "最近总是失眠,什么都提不起兴趣,觉得活着没意思。",
            "physiological": {"heart_rate": 95, "hrv": 25, "steps": 1500, "sleep_efficiency": 0.65, "activity_variance": 0.3},
        },
        {
            "features": {"age": 20, "gender": 0, "study_year": 2, "cgpa": 3.8, "stress_level": 3, "sleep_duration": 7.5, "social_support": 4, "financial_pressure": 1, "family_history": 0, "academic_pressure": 2, "exercise_frequency": 4, "anxiety": 0, "panic_attack": 0, "treatment_seeking": 0},
            "text": "今天天气真好,和朋友一起出去玩,心情很愉快。",
            "physiological": {"heart_rate": 72, "hrv": 55, "steps": 8000, "sleep_efficiency": 0.88, "activity_variance": 0.7},
        },
        {
            "features": {"age": 24, "gender": 1, "study_year": 4, "cgpa": 2.8, "stress_level": 9, "sleep_duration": 4.0, "social_support": 1, "financial_pressure": 5, "family_history": 1, "academic_pressure": 5, "exercise_frequency": 0, "anxiety": 1, "panic_attack": 1, "treatment_seeking": 1},
            "text": "我撑不下去了,想结束这一切,每天都很痛苦。",
            "physiological": {"heart_rate": 110, "hrv": 15, "steps": 500, "sleep_efficiency": 0.45, "activity_variance": 0.2},
        },
    ]

    success = 0
    canary_count = 0
    for i in range(count):
        case = test_cases[i % len(test_cases)]
        body = json.dumps(case).encode()
        req = urllib.request.Request(
            f"{API}/model/predict/fusion",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            r = urllib.request.urlopen(req, timeout=30)
            data = json.loads(r.read().decode())
            pred = data.get("data", {}).get("prediction", "?")
            risk = data.get("data", {}).get("risk_level", "?")
            model = data.get("data", {}).get("model_used", "?")
            canary = data.get("data", {}).get("canary_routed", False)
            canary_ver = data.get("data", {}).get("canary_version", "-")
            if canary:
                canary_count += 1
            if i < 5 or i >= count - 3 or canary:  # 打印前5, 后3, 和所有金丝雀
                print(f"  [{i+1:2d}] pred={pred} risk={risk} canary={canary} ver={canary_ver}")
            success += 1
        except Exception as exc:
            print(f"  [{i+1:2d}] ERROR: {exc}")

    print(f"\n总计: {success}/{count} 成功, 金丝雀路由: {canary_count}")
    print(f"期望金丝雀路由: ~{int(count * 0.05)} 次 (5% 流量, admin hash=19)")


def main() -> int:
    print("=" * 60)
    print("触发金丝雀推理流量")
    print("=" * 60)

    token = login()
    print(f"✅ 登录成功")

    trigger_fusion(token, count=20)

    print("\n" + "=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
