"""P1-5 + T-301: Locust 压测基线 - 关键接口吞吐/延迟 + 模型推理场景.

使用方法:
    # 安装 locust (已在 requirements-dev.txt)
    pip install locust

    # 启动后端 (确保 DB 已 seed, Redis 可选)
    cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000

    # 运行压测 (Web UI: http://localhost:8089)
    cd backend && locust -f load_tests/locustfile.py --host=http://localhost:8000

    # 无头模式 (CI 友好): 50 并发用户, 每秒增长 10, 运行 60s
    locust -f load_tests/locustfile.py --host=http://localhost:8000 \
        --headless -u 50 -r 10 -t 60s --only-summary

    # 测试特定场景 (anonymous / admin / user / inference)
    locust -f load_tests/locustfile.py --host=http://localhost:8000 \
        --headless -u 100 -r 10 -t 60s --tags admin

    # T-301: 峰值压力测试 (高并发, 短时间)
    locust -f load_tests/locustfile.py --host=http://localhost:8000 \
        --headless -u 200 -r 20 -t 120s --only-summary

    # T-301: 持久压力测试 (中等并发, 长时间, 检测内存泄漏)
    locust -f load_tests/locustfile.py --host=http://localhost:8000 \
        --headless -u 50 -r 5 -t 600s --only-summary

    # T-301: 模型推理专项压测 (需 user 角色 token)
    locust -f load_tests/locustfile.py --host=http://localhost:8000 \
        --headless -u 20 -r 5 -t 120s --tags inference

基线目标 (单实例, SQLite, 无 Redis):
    /health/live     : P99 < 30ms,  > 1000 RPS
    /health/ready    : P99 < 50ms,  > 500 RPS
    /reports/templates: P99 < 200ms, > 100 RPS
    /observability/trend (cached): P99 < 100ms, > 200 RPS
    /model/predict/tabular  : P99 < 500ms, 12 RPS (异步推理, 限流 20/min/user)
    /model/predict/text     : P99 < 800ms, 10 RPS (BERT 推理较重)
    /model/predict/fusion   : P99 < 1200ms, 8 RPS (三模态融合最重)

注意:
    - 首次 /observability/* 请求会 cache miss (计算), 后续命中缓存 (5min TTL)
    - /reports/user-risk/pdf/async 会创建后台任务, 避免高频调用
    - /model/predict/* 端点有 20/min 限流, inference user 等待时间设为 5-10s 避免触发 429
    - 认证使用 seed 的 admin 账号 (admin/TestAdminPwd-2024-Secure!)
"""
from __future__ import annotations

import os
import random

from locust import HttpUser, between, task, tag

# 从环境变量读取测试账号 (与 seed_database 一致)
ADMIN_USERNAME = os.getenv("LOCUST_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("LOCUST_ADMIN_PASS", "TestAdminPwd-2024-Secure!")
USER_USERNAME = os.getenv("LOCUST_USER_USER", "user_none")
USER_PASSWORD = os.getenv("LOCUST_USER_PASS", "TestUserPwd-2024-Secure!")


class AnonymousUser(HttpUser):
    """匿名用户: 仅访问公开健康检查端点.

    模拟 k8s 探针 + 监控系统的频繁健康检查.
    等待时间短 (0.1-0.5s), 模拟高频探针.
    """

    wait_time = between(0.1, 0.5)
    weight = 3  # 占比 30% (探针频率高但负载低)

    @tag("anonymous")
    @task(10)
    def health_live(self) -> None:
        """P0-1.1: 存活探针 (无 I/O, 目标 < 5ms)."""
        with self.client.get("/health/live", name="/health/live", catch_response=True) as resp:
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                resp.success()
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")

    @tag("anonymous")
    @task(5)
    def health_ready(self) -> None:
        """P0-1.1: 就绪探针 (非阻塞, 目标 < 5ms)."""
        with self.client.get("/health/ready", name="/health/ready", catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")

    @tag("anonymous")
    @task(1)
    def health_startup(self) -> None:
        """P0-1.1: 启动探针."""
        self.client.get("/health/startup", name="/health/startup")


class AdminUser(HttpUser):
    """管理员用户: 访问需认证的管理端点.

    模拟管理员查看报告/观测数据.
    等待时间中等 (1-3s), 模拟人类操作间隔.
    """

    wait_time = between(1.0, 3.0)
    weight = 1  # 占比 10%

    def on_start(self) -> None:
        """登录获取 token."""
        with self.client.post(
            "/api/v1/auth/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            name="/auth/login",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                # 兼容 ApiResponse 包装: {code, message, data: {access_token, ...}}
                token_data = data.get("data", data)
                token = token_data.get("access_token") or token_data.get("token")
                if token:
                    self.auth_headers = {"Authorization": f"Bearer {token}"}
                    return
                resp.failure("Login response missing access_token")
            else:
                resp.failure(f"Login failed: {resp.status_code}")
        # 登录失败时使用空 header (后续请求会被 401 拒绝, 但不阻止测试)
        self.auth_headers = {}

    @tag("admin")
    @task(5)
    def list_report_templates(self) -> None:
        """列出报告模板 (无 DB 查询, 纯内存)."""
        self.client.get(
            "/api/v1/reports/templates",
            headers=self.auth_headers,
            name="/reports/templates",
        )

    @tag("admin")
    @task(3)
    def observability_trend(self) -> None:
        """观测趋势 (首次 cache miss, 后续 cache hit 5min)."""
        self.client.get(
            "/api/v1/alerts/observability/trend?days=30",
            headers=self.auth_headers,
            name="/observability/trend",
        )

    @tag("admin")
    @task(2)
    def observability_response_time(self) -> None:
        """响应时间观测 (cached)."""
        self.client.get(
            "/api/v1/alerts/observability/response-time?days=7",
            headers=self.auth_headers,
            name="/observability/response-time",
        )

    @tag("admin")
    @task(1)
    def list_pdf_jobs(self) -> None:
        """P1-4: 列出 PDF 任务."""
        self.client.get(
            "/api/v1/reports/pdf/jobs",
            headers=self.auth_headers,
            name="/reports/pdf/jobs",
        )

    @tag("admin", "heavy")
    @task(1)
    def async_pdf_generation(self) -> None:
        """P1-4: 异步 PDF 生成 (低频, 避免堆积)."""
        payload = {
            "user_id": random.randint(1, 10),
            "user_name": f"loadtest_user_{random.randint(1, 100)}",
            "risk_level": random.choice(["low", "moderate", "high", "critical"]),
            "risk_trend": [
                {"date": "2026-06-01", "score": random.uniform(20, 80), "level": "moderate"}
            ],
            "recommendations": ["Increase exercise", "Improve sleep"],
        }
        self.client.post(
            "/api/v1/reports/user-risk/pdf/async",
            json=payload,
            headers=self.auth_headers,
            name="/reports/user-risk/pdf/async",
        )


class RegularUser(HttpUser):
    """普通用户: 访问用户级端点.

    模拟学生用户查看自身风险评估.
    等待时间较长 (2-5s), 模拟浏览行为.
    """

    wait_time = between(2.0, 5.0)
    weight = 2  # 占比 20%

    def on_start(self) -> None:
        """登录获取 token."""
        with self.client.post(
            "/api/v1/auth/login",
            json={"username": USER_USERNAME, "password": USER_PASSWORD},
            name="/auth/login",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                token_data = data.get("data", data)
                token = token_data.get("access_token") or token_data.get("token")
                if token:
                    self.auth_headers = {"Authorization": f"Bearer {token}"}
                    return
                resp.failure("Login response missing access_token")
            else:
                resp.failure(f"Login failed: {resp.status_code}")
        self.auth_headers = {}

    @tag("user")
    @task(3)
    def view_own_risk_report(self) -> None:
        """查看自身风险报告结构."""
        self.client.get(
            "/api/v1/user/risk/report",
            headers=self.auth_headers,
            name="/user/risk/report",
        )

    @tag("user")
    @task(2)
    def health_check(self) -> None:
        """普通用户也检查健康状态."""
        self.client.get("/health", name="/health")

    @tag("user")
    @task(1)
    def export_risk_json(self) -> None:
        """导出风险数据 (JSON 格式, 轻量)."""
        self.client.get(
            "/api/v1/user/risk/export?format=json&days=30",
            headers=self.auth_headers,
            name="/user/risk/export?format=json",
        )


# T-301: 模型推理测试数据 (符合 schema 校验范围)
_TABULAR_FEATURES = {
    "age": random.randint(18, 65),
    "gender": random.choice([0, 1]),
    "sleep_hours": round(random.uniform(4, 9), 1),
    "exercise_minutes": random.randint(0, 120),
    "stress_level": random.randint(1, 10),
    "mood_score": random.randint(1, 10),
    "social_support": random.randint(1, 5),
}

_SAMPLE_TEXTS = [
    "最近感觉还不错，生活很充实，每天都很开心。",
    "有时候会感到有些压力，但总体能应对，睡眠一般。",
    "最近总是睡不好，感觉很焦虑，不知道该怎么办才好。",
    "今天和朋友一起出去散步了，心情好多了。",
    "工作压力很大，经常加班到很晚，感觉很疲惫。",
]

_PHYSIOLOGICAL_DATA = {
    "sleep_hours": round(random.uniform(5, 8), 1),
    "sleep_quality": random.randint(3, 8),
    "exercise_minutes": random.randint(10, 60),
    "heart_rate": random.randint(60, 100),
    "systolic_bp": random.randint(100, 140),
    "diastolic_bp": random.randint(60, 90),
    "steps": random.randint(2000, 12000),
}


class ModelInferenceUser(HttpUser):
    """T-301: 模型推理压测用户.

    模拟用户调用风险评估模型推理端点 (tabular/text/physiological/fusion).
    这些是 CPU 密集型端点, P1 已通过 asyncio.to_thread 异步化.

    等待时间较长 (5-10s): 端点有 20/min 限流, 高频请求会触发 429.
    weight=1: 推理负载重, 占比低避免压垮单实例.
    """

    wait_time = between(5.0, 10.0)
    weight = 1  # 占比 10% (推理负载重)

    def on_start(self) -> None:
        """登录获取 token (使用普通用户账号)."""
        with self.client.post(
            "/api/v1/auth/login",
            json={"username": USER_USERNAME, "password": USER_PASSWORD},
            name="/auth/login",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                token_data = data.get("data", data)
                token = token_data.get("access_token") or token_data.get("token")
                if token:
                    self.auth_headers = {"Authorization": f"Bearer {token}"}
                    return
                resp.failure("Login response missing access_token")
            else:
                resp.failure(f"Login failed: {resp.status_code}")
        self.auth_headers = {}

    @tag("inference")
    @task(4)
    def predict_tabular(self) -> None:
        """表格模型推理 (异步, P1 已优化)."""
        features = {**_TABULAR_FEATURES, "age": random.randint(18, 65)}
        with self.client.post(
            "/api/v1/model/predict/tabular",
            json={"features": features},
            headers=self.auth_headers,
            name="/model/predict/tabular",
            catch_response=True,
        ) as resp:
            # 429 限流是预期行为 (20/min), 不计为失败
            if resp.status_code == 429:
                resp.success()
            elif resp.status_code == 200:
                resp.success()
            elif resp.status_code == 503:
                resp.failure("Model service unavailable (503)")
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")

    @tag("inference")
    @task(3)
    def predict_text(self) -> None:
        """文本模型推理 (BERT, 最重的 CPU 负载)."""
        text = random.choice(_SAMPLE_TEXTS)
        with self.client.post(
            "/api/v1/model/predict/text",
            json={"text": text},
            headers=self.auth_headers,
            name="/model/predict/text",
            catch_response=True,
        ) as resp:
            if resp.status_code == 429:
                resp.success()
            elif resp.status_code == 200:
                resp.success()
            elif resp.status_code == 503:
                resp.failure("Model service unavailable (503)")
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")

    @tag("inference")
    @task(2)
    def predict_physiological(self) -> None:
        """生理模型推理."""
        physio = {**_PHYSIOLOGICAL_DATA, "heart_rate": random.randint(60, 100)}
        with self.client.post(
            "/api/v1/model/predict/physiological",
            json={"physiological": physio},
            headers=self.auth_headers,
            name="/model/predict/physiological",
            catch_response=True,
        ) as resp:
            if resp.status_code == 429:
                resp.success()
            elif resp.status_code == 200:
                resp.success()
            elif resp.status_code == 503:
                resp.failure("Model service unavailable (503)")
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")

    @tag("inference", "heavy")
    @task(1)
    def predict_fusion(self) -> None:
        """融合推理 (三模态, 最重负载)."""
        payload = {
            "features": {**_TABULAR_FEATURES},
            "text": random.choice(_SAMPLE_TEXTS),
            "physiological": {**_PHYSIOLOGICAL_DATA},
        }
        with self.client.post(
            "/api/v1/model/predict/fusion",
            json=payload,
            headers=self.auth_headers,
            name="/model/predict/fusion",
            catch_response=True,
        ) as resp:
            if resp.status_code == 429:
                resp.success()
            elif resp.status_code == 200:
                resp.success()
            elif resp.status_code == 503:
                resp.failure("Model service unavailable (503)")
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")
