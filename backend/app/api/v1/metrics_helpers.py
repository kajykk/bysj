"""Shared helpers for metrics collection and exposition parsing."""

from __future__ import annotations

import json
import logging
import re
import time as _time
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select

from app.core.degradation import record_silent_degradation

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

# P0-FIX-2026-10-11: 原实现在本模块硬编码了一张 ``_ML_QUALITY`` 表
# （auc=0.9121 / f1=0.8541 / …）并直接 set 到 Prometheus。问题有三层：
#   1. 这些数字**不对应任何一次真实实验**，却和真指标共用同一组 Gauge 暴露给
#      Grafana —— 看板看起来"有数据"，实际无法区分"模型退化"与"没测"；
#   2. 结构化模态真实产物 ``models/artifacts/depression_tabular/metrics.json``
#      里 test roc_auc = 0.9203，与硬编码的 0.9121 不符；
#   3. 没有真实来源的指标（如 fusion 的 recall/precision、全部模态的 p95_ms）
#      被凭空补齐，**凭空补齐本身就是编造**。
#
# 现改为：只从真实实验产物读取，读不到的指标**不上报**（Prometheus 里该序列
# 不存在 = "未知"，这是诚实语义；上报 0 会被误读为"指标为 0"，同样有害）。
# 数据源与 scripts/p3_push_ml_metrics.py 保持同源，避免两套口径。
_MODALITY_METRIC_SOURCES: dict[str, tuple[str, ...]] = {
    # (模态名, 相对 model_dir 的候选路径, 按优先级)
    "structured": (
        "artifacts/depression_tabular/metrics.json",
        "artifacts/structured_v1.20/metrics.json",
    ),
    "text": ("artifacts/text_m2_bert/metrics.json",),
    "physiological": (
        "artifacts/physiological_optimized/metrics.json",
        "artifacts/physiological_m3/metrics.json",
        "artifacts/physiological/metrics.json",
    ),
    "fusion": ("artifacts/fusion_m4/metrics.json",),
}

# 校准产物单独提供 ECE（其余指标不提供）
_ECE_SOURCE = "artifacts/calibration_m5/metrics.json"
# M5 的 modality 名 → 本模块口径
_M5_MODALITY_MAP = {
    "structured_gbdt": "structured",
    "structured_lr": "structured",
    "physiological_mlp": "physiological",
    "text_bert": "text",
    "text_tfidf": "text",
    "fusion_stacking_gbdt": "fusion",
}

_METRIC_GAUGE_BY_KEY = {
    "auc": model_auc,
    "f1": model_f1,
    "ece": model_ece,
    "p95_ms": model_p95_latency_ms,
    "recall": model_recall,
    "precision": model_precision,
}


def _model_roots() -> list[Path]:
    """候选模型根目录：settings.model_dir 优先，其次仓库根 models/。

    生产/CI 里 ``settings.model_dir`` 指向已随镜像 COPY 的 ``backend/models``；
    本地开发常从仓库根启动，产物在 ``<repo>/models``。两者都试，找不到就
    返回空 —— 由调用方决定「不上报」，而不是回退到假数据。
    """
    from app.core.config import settings

    roots: list[Path] = []
    raw = getattr(settings, "model_dir", None)
    if raw:
        roots.append(Path(raw))
    # app/api/v1/metrics_helpers.py -> app/api/v1 -> app/api -> app -> backend
    backend_root = Path(__file__).resolve().parents[3]
    roots.append(backend_root.parent / "models")
    # 去重（保序）
    seen: set[str] = set()
    unique: list[Path] = []
    for r in roots:
        key = str(r)
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def _load_json(relative: str) -> dict[str, Any] | None:
    """从候选根目录里读第一个存在的 JSON；都不存在则返回 None。"""
    for root in _model_roots():
        path = root / relative
        try:
            if path.is_file():
                with path.open(encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    return data
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取指标产物失败: %s error=%s", path, exc)
            # P2-35：产物**存在但读不出来**（损坏 / 权限 / 训练过程中被并发读到
            # 半截文件）与「产物根本没部署」在 `_load_json` 这里返回的是同一个
            # 值 None —— 调用方 `_extract_*` 拿到空 dict，Prometheus 里该模态的
            # 序列直接消失。Grafana 上「指标极差/没数据」与「产物损坏」完全无法
            # 区分，调用方从返回值看不出 ⇒ 属真降级，必须留痕。
            # 与同文件 collect_ml_quality/drift/canary 三处的处理保持同族
            # （都是「真实产物读不到 ⇒ 指标序列消失」）。
            record_silent_degradation("api.metrics_helpers.load_json")
    return None


def _first_numeric(source: dict[str, Any], *keys: str) -> float | None:
    """按 keys 顺序取第一个可转 float 的值（非数值/缺失返回 None）。"""
    for key in keys:
        value = source.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _extract_ece() -> dict[str, float]:
    """从校准实验产物提取每模态的 ECE（取 raw_metrics，calibration 前的真实值）。"""
    out: dict[str, float] = {}
    data = _load_json(_ECE_SOURCE)
    if not data:
        return out
    for entry in data.get("modalities") or []:
        if not isinstance(entry, dict):
            continue
        modality = _M5_MODALITY_MAP.get(entry.get("modality", ""))
        if modality is None or modality in out:
            continue
        calibration = entry.get("calibration") or {}
        raw = calibration.get("raw_metrics") or {}
        ece = _first_numeric(raw, "ece")
        if ece is not None:
            out[modality] = ece
    return out


def _extract_modality_metrics(modality: str) -> dict[str, float]:
    """从该模态的真实产物提取指标；只返回确实存在的键。"""
    metrics: dict[str, float] = {}
    for relative in _MODALITY_METRIC_SOURCES.get(modality, ()):  # 优先级顺序
        data = _load_json(relative)
        if data is None:
            continue
        # 依次尝试 test → val → cv 汇总，优先"测试集"口径
        sections: list[dict[str, Any]] = []
        for key in ("test_metrics", "val_metrics", "cv_results", "best_metrics"):
            section = data.get(key)
            if isinstance(section, dict):
                sections.append(section)
        if isinstance(data.get("cv_results"), list):  # fusion 的 cv_results 是数组
            for item in data["cv_results"]:
                if isinstance(item, dict):
                    sections.append(item)
        for section in sections:
            for key, aliases in (
                ("auc", ("roc_auc", "auc", "auc_mean")),
                ("f1", ("f1", "f1_mean")),
                ("recall", ("recall", "recall_mean")),
                ("precision", ("precision", "precision_mean")),
            ):
                if key in metrics:
                    continue
                value = _first_numeric(section, *aliases)
                if value is not None:
                    metrics[key] = value
        if metrics:
            break
    return metrics


async def collect_ml_quality_metrics() -> None:
    """把**真实**实验产物中的模型质量指标写入 Prometheus。

    P0-FIX-2026-10-11: 读不到真实来源的指标一律不上报（而不是填默认值）。
    上报 0 或填占位数都会让看板把"没数据"误读成"指标极差"或"指标正常"。
    """
    try:
        ece_by_modality = _extract_ece()
        reported = 0
        for modality in _MODALITY_METRIC_SOURCES:
            metrics = _extract_modality_metrics(modality)
            if ece_by_modality.get(modality) is not None:
                metrics["ece"] = ece_by_modality[modality]
            if not metrics:
                logger.info(
                    "ml_quality: 无真实产物可读，跳过模态 %s（不上报占位值）", modality
                )
                continue
            # model_version 标签用真实产物所在目录名，避免声称一个无法追溯的版本号
            source_name = _MODALITY_METRIC_SOURCES[modality][0].split("/")[-2]
            version = f"{modality}:{source_name}"
            for key, value in metrics.items():
                gauge = _METRIC_GAUGE_BY_KEY.get(key)
                if gauge is None:
                    continue
                gauge.set(float(value), modality=modality, model_version=version)
                reported += 1
            logger.info(
                "ml_quality: modality=%s version=%s metrics=%s",
                modality,
                version,
                sorted(metrics),
            )
        if reported == 0:
            logger.warning(
                "ml_quality: 未上报任何模型质量指标（真实产物不可读）"
            )
    except Exception as exc:
        logger.warning("ml_quality metric collection failed: %s", exc)
        record_silent_degradation("api.metrics_helpers.collect_ml_quality")


async def collect_drift_metrics() -> None:
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.monitoring import DriftAlert

        async with AsyncSessionLocal() as drift_session:
            for modality in ("structured", "text", "physiological", "fusion"):
                stmt = (
                    select(DriftAlert)
                    .where(DriftAlert.details["modality"].as_string() == modality)
                    # ROUND_25 (B 摊): created_at 非唯一 ⇒ 同秒并列时 gauge 读数不确定；补 id 次级键
                    .order_by(desc(DriftAlert.created_at), desc(DriftAlert.id))
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
        record_silent_degradation("api.metrics_helpers.collect_drift")


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
        record_silent_degradation("api.metrics_helpers.collect_canary")


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
