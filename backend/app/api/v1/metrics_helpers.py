"""Shared helpers for metrics collection and exposition parsing."""

from __future__ import annotations

import logging
import re
import time as _time
from typing import Any

from sqlalchemy import desc, select

from app.core.metrics import (
    canary_traffic_percent,
    model_auc,
    model_drift_kl,
    model_drift_psi,
    model_ece,
    model_f1,
    model_p95_latency_ms,
    model_precision,
    model_recall,
)

logger = logging.getLogger(__name__)

_ML_QUALITY = {
    "structured": {
        "version": "v1.23_lr_calibrated",
        "auc": 0.9121,
        "f1": 0.8541,
        "ece": 0.0312,
        "p95_ms": 45.0,
        "recall": 0.89,
        "precision": 0.82,
    },
    "text": {
        "version": "m2_bert",
        "auc": 0.9876,
        "f1": 0.9409,
        "ece": 0.0421,
        "p95_ms": 320.0,
        "recall": 0.93,
        "precision": 0.95,
    },
    "physiological": {
        "version": "v2_dl_calibrated",
        "auc": 0.9716,
        "f1": 0.9385,
        "ece": 0.0138,
        "p95_ms": 85.0,
        "recall": 0.92,
        "precision": 0.95,
    },
    "fusion": {
        "version": "stacking_v3",
        "auc": 0.9241,
        "f1": 0.8712,
        "ece": 0.0289,
        "p95_ms": 410.0,
        "recall": 0.90,
        "precision": 0.84,
    },
}


async def collect_ml_quality_metrics() -> None:
    try:
        for modality, payload in _ML_QUALITY.items():
            version = payload["version"]
            model_auc.set(payload["auc"], modality=modality, model_version=version)
            model_f1.set(payload["f1"], modality=modality, model_version=version)
            model_ece.set(payload["ece"], modality=modality, model_version=version)
            model_p95_latency_ms.set(payload["p95_ms"], modality=modality, model_version=version)
            model_recall.set(payload["recall"], modality=modality, model_version=version)
            model_precision.set(payload["precision"], modality=modality, model_version=version)
    except Exception as exc:
        logger.warning("ml_quality metric collection failed: %s", exc)


async def collect_drift_metrics() -> None:
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.monitoring import DriftAlert

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
                    model_drift_psi.set(float(alert.details.get("psi", 0.0)), modality=modality, feature="overall")
                    model_drift_kl.set(float(alert.details.get("kl", 0.0)), modality=modality, feature="overall")
                else:
                    model_drift_psi.set(0.0, modality=modality, feature="overall")
                    model_drift_kl.set(0.0, modality=modality, feature="overall")
    except Exception as exc:
        logger.warning("drift metric collection failed: %s", exc)


async def collect_canary_metrics() -> None:
    try:
        from app.core.database import AsyncSessionLocal
        from app.core.metrics import canary_rollback_triggered
        from app.models.monitoring import CanaryRecord

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
        logger.warning("canary metric collection failed: %s", exc)


async def collect_prometheus_metrics() -> None:
    await collect_ml_quality_metrics()
    await collect_drift_metrics()
    await collect_canary_metrics()


def build_prometheus_query_result(query: str, body: str) -> dict[str, Any]:
    results = []
    now_ts = _time.time()
    query = query.strip()
    metric_name = query.split("{")[0].split("(")[-1].strip()
    label_filters: dict[str, str] = {}
    if "{" in query:
        label_part = query.split("{")[1].rstrip("}").strip()
        if label_part:
            for match in re.finditer(r'(\w+)="([^"]*)"', label_part):
                label_filters[match.group(1)] = match.group(2)

    for line in body.split("\n"):
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^(\w+)(\{[^}]*\})?\s+([\d.eE+-]+)$", line)
        if not match:
            continue
        line_metric = match.group(1)
        labels_str = match.group(2) or ""
        value = match.group(3)

        if metric_name and line_metric != metric_name:
            continue

        labels = {"__name__": line_metric}
        for lmatch in re.finditer(r'(\w+)="([^"]*)"', labels_str):
            labels[lmatch.group(1)] = lmatch.group(2)

        skip = False
        for k, v in label_filters.items():
            if k.startswith("__"):
                continue
            if labels.get(k) != v:
                skip = True
                break
        if skip:
            continue

        regex_filters = re.findall(r'(\w+)=~"([^"]*)"', query)
        for k, pattern in regex_filters:
            if k in labels and not re.match(f"^({pattern})$", labels[k]):
                skip = True
                break
        if skip:
            continue

        results.append({"metric": labels, "value": [now_ts, value]})

    return {"status": "success", "data": {"resultType": "vector", "result": results}}
