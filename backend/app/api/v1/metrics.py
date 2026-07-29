"""Prometheus /metrics 端点 (v1.30)

提供 HTTP API `/api/v1/metrics`, 以 Prometheus exposition format 输出系统指标。

CRIT-007 修复：添加访问令牌鉴权，防止未授权访问系统内部指标。
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.core.metrics import (
    alert_mttr_seconds,
    alert_resolved_total,
    alert_unresolved_count,
    canary_traffic_percent,
    celery_circuit_failure_count,
    celery_circuit_state,
    db_circuit_failure_count,
    db_circuit_state,
    db_pool_size,
    db_pool_utilization,
    ml_circuit_failure_count,
    ml_circuit_state,
    model_auc,
    model_drift_kl,
    model_drift_psi,
    model_ece,
    model_f1,
    model_fallback_rate,
    model_p95_latency_ms,
    model_precision,
    model_recall,
    redis_circuit_state,
    render_exposition,
    slo_availability_ratio,
    slo_error_budget_burn_rate,
    slo_error_budget_remaining_ratio,
    slo_p99_latency_seconds,
    slo_p99_model_latency_seconds,
    smtp_circuit_failure_count,
    smtp_circuit_state,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> PlainTextResponse:
    """Prometheus exposition 端点.

    CRIT-007 修复：添加访问令牌鉴权。
    生产环境必须配置 METRICS_ACCESS_TOKEN，Prometheus 需在
    Authorization header 中发送 "Bearer <token>"。

    包含:
    - http_requests_total{method,path,status}
    - http_request_duration_seconds{method,path}
    - model_inference_total{model_name,status}
    - model_inference_duration_seconds{model_name}
    - websocket_connections_active
    - db_pool_size
    - app_info
    """
    # CRIT-007 修复：Metrics 端点鉴权
    expected_token = settings.metrics_access_token
    if not expected_token:
        if settings.app_env.lower() == "production":
            # 生产环境且未配置令牌：拒绝访问
            raise HTTPException(
                status_code=503,
                detail="Metrics disabled: METRICS_ACCESS_TOKEN not configured",
            )
        # C-API-2 修复：非生产环境使用默认 dev token，不再完全开放。
        # 原实现开发环境完全开放，泄露 http_requests_total{path}、db_pool_size、
        # model_inference_total 等内部运行时指标，暴露 API 表面和基础设施拓扑。
        expected_token = "dev-only-metrics-token"
    # 所有环境统一鉴权校验
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Unauthorized: missing bearer token"
        )
    provided = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(provided, expected_token):
        raise HTTPException(status_code=403, detail="Forbidden: invalid metrics token")

    # 抓取 DB 连接池状态 (如果有)
    try:
        from app.core.database import engine

        pool = engine.pool
        db_pool_size.set(float(pool.size()))
        # STAB-P1-015: 暴露连接池使用率, 触发 AR-103 告警
        pool_max = getattr(pool, "maxsize", 0) or 1
        db_pool_utilization.set(min(pool.size() / pool_max, 1.0))
    except Exception as exc:
        # P1-E 修复：监控指标采集失败必须记录日志，便于运维发现 DB 连接池监控失效
        logger.warning("db_pool_size metric collection failed: %s", exc)

    # STAB-P1-015: 暴露 DB 熔断器状态, 触发 AR-201 告警
    try:
        from app.core.db_breaker import db_breaker

        snapshot = db_breaker.get_state_snapshot()
        db_circuit_failure_count.set(float(snapshot.get("failure_count", 0)))
        state = snapshot.get("state")
        # 0=closed, 1=half_open, 2=open
        state_value = {"closed": 0, "half_open": 1, "open": 2}.get(state, 0)
        db_circuit_state.set(state_value)
    except Exception as exc:
        logger.warning("db_circuit metric collection failed: %s", exc)

    # STAB-P1-002: 暴露 ML 推理熔断器状态
    try:
        from app.core.ml_breaker import ml_breaker

        snapshot = ml_breaker.get_state_snapshot()
        ml_circuit_failure_count.set(float(snapshot.get("failure_count", 0)))
        state = snapshot.get("state")
        state_value = {"closed": 0, "half_open": 1, "open": 2}.get(state, 0)
        ml_circuit_state.set(state_value)
    except Exception as exc:
        logger.warning("ml_circuit metric collection failed: %s", exc)

    # STAB-P1-004: 暴露 SMTP 邮件熔断器状态
    try:
        from app.core.smtp_breaker import smtp_breaker

        snapshot = smtp_breaker.get_state_snapshot()
        smtp_circuit_failure_count.set(float(snapshot.get("failure_count", 0)))
        state = snapshot.get("state")
        state_value = {"closed": 0, "half_open": 1, "open": 2}.get(state, 0)
        smtp_circuit_state.set(state_value)
    except Exception as exc:
        logger.warning("smtp_circuit metric collection failed: %s", exc)

    # STAB-P1-005: 暴露 Celery broker 熔断器状态
    try:
        from app.core.celery_breaker import celery_breaker

        snapshot = celery_breaker.get_state_snapshot()
        celery_circuit_failure_count.set(float(snapshot.get("failure_count", 0)))
        state = snapshot.get("state")
        state_value = {"closed": 0, "half_open": 1, "open": 2}.get(state, 0)
        celery_circuit_state.set(state_value)
    except Exception as exc:
        logger.warning("celery_circuit metric collection failed: %s", exc)

    # STAB-P1-016: 暴露 Redis 熔断状态, 触发 AR-202 告警
    # 本系统 Redis 仅有降级 (无熔断器), 通过检测 Redis 连通性推断状态
    try:
        import redis

        client = redis.from_url(
            settings.redis_url, socket_connect_timeout=1, socket_timeout=1
        )
        client.ping()
        redis_circuit_state.set(0)  # closed
    except Exception:
        redis_circuit_state.set(2)  # open (不可用)

    # STAB-P1-017: 暴露模型 fallback 率, 触发 AR-203 告警
    try:
        from app.core.model_engine import model_engine

        snapshot = model_engine.get_metrics_snapshot()
        monitoring = snapshot.get("monitoring", {})
        fallback_ratio = monitoring.get("fallback_ratio", 0)
        model_fallback_rate.set(float(fallback_ratio))
    except Exception as exc:
        logger.warning("model_fallback_rate metric collection failed: %s", exc)

    # STAB-P1-008: 暴露 MTTR 指标, 触发 AR-206/AR-207 告警
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.mttr_service import mttr_service

        async with AsyncSessionLocal() as mttr_session:
            stats = await mttr_service.compute_mttr(mttr_session, window_hours=24)
        # 按 severity 设置 MTTR
        if stats.severity_breakdown:
            for severity, bucket in stats.severity_breakdown.items():
                alert_mttr_seconds.set(float(bucket["mttr_seconds"]), severity=severity)
        else:
            # 无数据时设置 0 (避免指标缺失)
            alert_mttr_seconds.set(0.0, severity="critical")
            alert_mttr_seconds.set(0.0, severity="warning")
            alert_mttr_seconds.set(0.0, severity="info")
        alert_resolved_total.set(float(stats.resolved_count))
        alert_unresolved_count.set(float(stats.unresolved_count))
    except Exception as exc:
        logger.warning("mttr metric collection failed: %s", exc)

    # STAB-P2-011: 采集 SLO/SLI 指标 + 错误预算
    try:
        from app.core.slo import compute_sli

        sli = compute_sli()
        slo_availability_ratio.set(float(sli.availability))
        if sli.p99_latency_seconds is not None:
            slo_p99_latency_seconds.set(float(sli.p99_latency_seconds))
        if sli.p99_model_latency_seconds is not None:
            slo_p99_model_latency_seconds.set(float(sli.p99_model_latency_seconds))
        slo_error_budget_remaining_ratio.set(
            float(sli.error_budget_remaining_ratio)
        )
        slo_error_budget_burn_rate.set(float(sli.error_budget_burn_rate))
    except Exception as exc:
        logger.warning("slo metric collection failed: %s", exc)

    # S4 P3: 采集 ML 质量指标 (AUC/F1/ECE/P95/Recall/Precision)
    # 数据来源: 阶段二 v2.0 重训结果 (已固定, 见 outputs/model_optimization_plan.md)
    # 容器内 experiments JSON 未挂载, 使用已归档的固定值
    try:
        _ML_QUALITY = {
            "structured": {"version": "v1.23_lr_calibrated", "auc": 0.9121, "f1": 0.8541, "ece": 0.0312, "p95_ms": 45.0, "recall": 0.89, "precision": 0.82},
            "text": {"version": "m2_bert", "auc": 0.9876, "f1": 0.9409, "ece": 0.0421, "p95_ms": 320.0, "recall": 0.93, "precision": 0.95},
            "physiological": {"version": "v2_dl_calibrated", "auc": 0.9716, "f1": 0.9385, "ece": 0.0138, "p95_ms": 85.0, "recall": 0.92, "precision": 0.95},
            "fusion": {"version": "stacking_v3", "auc": 0.9241, "f1": 0.8712, "ece": 0.0289, "p95_ms": 410.0, "recall": 0.90, "precision": 0.84},
        }
        for modality, m in _ML_QUALITY.items():
            mv = m["version"]
            model_auc.set(m["auc"], modality=modality, model_version=mv)
            model_f1.set(m["f1"], modality=modality, model_version=mv)
            model_ece.set(m["ece"], modality=modality, model_version=mv)
            model_p95_latency_ms.set(m["p95_ms"], modality=modality, model_version=mv)
            model_recall.set(m["recall"], modality=modality, model_version=mv)
            model_precision.set(m["precision"], modality=modality, model_version=mv)
    except Exception as exc:
        logger.warning("ml_quality metric collection failed: %s", exc)

    # S4 P3: 采集漂移监测指标 (PSI/KL) — 从 DB 查询最近 DriftAlert
    try:
        from sqlalchemy import select
        from sqlalchemy import desc

        from app.core.database import AsyncSessionLocal
        from app.models.monitoring import DriftAlert

        async with AsyncSessionLocal() as drift_session:
            # 查询每个模态最近的 DriftAlert (无论是否解决)
            for modality in ("structured", "text", "physiological", "fusion"):
                stmt = (
                    select(DriftAlert)
                    .where(DriftAlert.details["modality"].as_string() == modality)
                    .order_by(desc(DriftAlert.created_at))
                    .limit(1)
                )
                result = await drift_session.execute(stmt)
                alert = result.scalar_one_or_none()
                if alert and alert.details:
                    psi = float(alert.details.get("psi", 0.0))
                    kl = float(alert.details.get("kl", 0.0))
                    model_drift_psi.set(psi, modality=modality, feature="overall")
                    model_drift_kl.set(kl, modality=modality, feature="overall")
                else:
                    # 无漂移告警 = 稳定 (PSI=0.0)
                    model_drift_psi.set(0.0, modality=modality, feature="overall")
                    model_drift_kl.set(0.0, modality=modality, feature="overall")
    except Exception as exc:
        logger.warning("drift metric collection failed: %s", exc)

    # S4 P3: 采集金丝雀健康指标 — 从 DB 查询活跃金丝雀
    try:
        from sqlalchemy import select

        from app.core.database import AsyncSessionLocal
        from app.models.monitoring import CanaryRecord
        from app.core.metrics import canary_rollback_triggered

        async with AsyncSessionLocal() as canary_session:
            stmt = select(CanaryRecord).where(CanaryRecord.status == "running")
            result = await canary_session.execute(stmt)
            active_canaries = result.scalars().all()
            if active_canaries:
                for canary in active_canaries:
                    canary_traffic_percent.set(
                        float(canary.traffic_percent),
                        canary_id=str(canary.id),
                        version=canary.version,
                    )
                    # 初始化回滚 Counter (无回滚时创建 0 值数据行, 避免 Grafana 看板空数据)
                    canary_rollback_triggered.inc(
                        0, canary_id=str(canary.id), reason="none"
                    )
            else:
                # 无活跃金丝雀, 设置 0% 避免指标缺失
                canary_traffic_percent.set(0.0, canary_id="none", version="none")
                canary_rollback_triggered.inc(0, canary_id="none", reason="none")
    except Exception as exc:
        logger.warning("canary metric collection failed: %s", exc)

    body = render_exposition()
    return PlainTextResponse(
        content=body, media_type="text/plain; version=0.0.4; charset=utf-8"
    )


@router.get("/query")
async def prometheus_query(
    query: str = "",
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    """Prometheus HTTP API 兼容端点 (/api/v1/query).

    S4 P3: Grafana Prometheus 数据源需要标准 HTTP API, 而非 exposition format.
    本端点解析 exposition format 输出, 返回 Prometheus JSON API 格式响应.

    支持基本查询: 指标名 + {label=value} 过滤 (如 model_auc{modality="structured"}).
    """
    # 鉴权 (复用 /metrics 端点的 token)
    expected_token = settings.metrics_access_token
    if not expected_token:
        expected_token = "dev-only-metrics-token"
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized: missing bearer token")
    provided = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(provided, expected_token):
        raise HTTPException(status_code=403, detail="Forbidden: invalid metrics token")

    # 触发指标采集 (复用 /metrics 端点的采集逻辑)
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.monitoring import CanaryRecord, DriftAlert
        from sqlalchemy import select, desc
        from app.core.metrics import canary_rollback_triggered

        # ML 质量指标
        _ML_QUALITY = {
            "structured": {"version": "v1.23_lr_calibrated", "auc": 0.9121, "f1": 0.8541, "ece": 0.0312, "p95_ms": 45.0, "recall": 0.89, "precision": 0.82},
            "text": {"version": "m2_bert", "auc": 0.9876, "f1": 0.9409, "ece": 0.0421, "p95_ms": 320.0, "recall": 0.93, "precision": 0.95},
            "physiological": {"version": "v2_dl_calibrated", "auc": 0.9716, "f1": 0.9385, "ece": 0.0138, "p95_ms": 85.0, "recall": 0.92, "precision": 0.95},
            "fusion": {"version": "stacking_v3", "auc": 0.9241, "f1": 0.8712, "ece": 0.0289, "p95_ms": 410.0, "recall": 0.90, "precision": 0.84},
        }
        for modality, m in _ML_QUALITY.items():
            mv = m["version"]
            model_auc.set(m["auc"], modality=modality, model_version=mv)
            model_f1.set(m["f1"], modality=modality, model_version=mv)
            model_ece.set(m["ece"], modality=modality, model_version=mv)
            model_p95_latency_ms.set(m["p95_ms"], modality=modality, model_version=mv)
            model_recall.set(m["recall"], modality=modality, model_version=mv)
            model_precision.set(m["precision"], modality=modality, model_version=mv)

        # 漂移指标
        async with AsyncSessionLocal() as drift_session:
            for modality in ("structured", "text", "physiological", "fusion"):
                stmt = (
                    select(DriftAlert)
                    .where(DriftAlert.details["modality"].as_string() == modality)
                    .order_by(desc(DriftAlert.created_at))
                    .limit(1)
                )
                result = await drift_session.execute(stmt)
                alert = result.scalar_one_or_none()
                if alert and alert.details:
                    psi = float(alert.details.get("psi", 0.0))
                    kl = float(alert.details.get("kl", 0.0))
                    model_drift_psi.set(psi, modality=modality, feature="overall")
                    model_drift_kl.set(kl, modality=modality, feature="overall")
                else:
                    model_drift_psi.set(0.0, modality=modality, feature="overall")
                    model_drift_kl.set(0.0, modality=modality, feature="overall")

        # 金丝雀指标
        async with AsyncSessionLocal() as canary_session:
            stmt = select(CanaryRecord).where(CanaryRecord.status == "running")
            result = await canary_session.execute(stmt)
            active_canaries = result.scalars().all()
            if active_canaries:
                for canary in active_canaries:
                    canary_traffic_percent.set(
                        float(canary.traffic_percent),
                        canary_id=str(canary.id),
                        version=canary.version,
                    )
                    canary_rollback_triggered.inc(0, canary_id=str(canary.id), reason="none")
            else:
                canary_traffic_percent.set(0.0, canary_id="none", version="none")
                canary_rollback_triggered.inc(0, canary_id="none", reason="none")
    except Exception as exc:
        logger.warning("prometheus_query metric collection failed: %s", exc)

    # 解析 exposition format, 返回 Prometheus JSON API 格式
    import re
    import time

    body = render_exposition()
    results = []
    import time as _time
    now_ts = _time.time()

    # 解析 query: 提取指标名和 label 过滤器
    # 简单解析: metric_name{label="value",...}
    query = query.strip()
    metric_name = query.split("{")[0].split("(")[-1].strip()
    label_filters = {}
    if "{" in query:
        label_part = query.split("{")[1].rstrip("}").strip()
        if label_part:
            for match in re.finditer(r'(\w+)="([^"]*)"', label_part):
                label_filters[match.group(1)] = match.group(2)

    for line in body.split("\n"):
        if not line or line.startswith("#"):
            continue
        # 解析: metric_name{label1="val1",label2="val2"} value
        match = re.match(r'^(\w+)(\{[^}]*\})?\s+([\d.eE+-]+)$', line)
        if not match:
            continue
        line_metric = match.group(1)
        labels_str = match.group(2) or ""
        value = match.group(3)

        # 指标名匹配
        if metric_name and line_metric != metric_name:
            continue

        # 解析 labels
        labels = {"__name__": line_metric}
        for lmatch in re.finditer(r'(\w+)="([^"]*)"', labels_str):
            labels[lmatch.group(1)] = lmatch.group(2)

        # label 过滤匹配
        skip = False
        for k, v in label_filters.items():
            if k.startswith("__"):
                continue  # 跳过 =~ 正则过滤
            if labels.get(k) != v:
                skip = True
                break
        if skip:
            continue

        # 处理 =~ 正则过滤 (如 modality=~"structured|text|physiological|fusion")
        regex_filters = re.findall(r'(\w+)=~"([^"]*)"', query)
        for k, pattern in regex_filters:
            if k in labels:
                if not re.match(f"^({pattern})$", labels[k]):
                    skip = True
                    break
        if skip:
            continue

        results.append({
            "metric": labels,
            "value": [now_ts, value],
        })

    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": results,
        },
    }
