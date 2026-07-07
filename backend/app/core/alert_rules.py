"""STAB-P1-014 修复：核心告警规则集中定义 (v1.40)

原问题: 5xx 错误率/P99/CPU/DB 连接池等告警阈值仅存在于文档中，
未代码化，无法被 CI 校验或被 Prometheus/Grafana 自动接入。

本模块集中定义所有告警阈值，作为代码化的单一事实来源。
配套 `monitoring/alert_rules.yml` 提供 Prometheus/Grafana 接入规则。

设计原则:
- 阈值集中: 所有告警阈值在一个文件中定义, 避免散落
- 环境感知: 区分 production/staging/development 阈值
- 严重程度分级: critical (立即处理) / warning (24h 内处理) / info (记录即可)
- 可被 CI 校验: 阈值变更必须通过 PR Review
- 可被 Prometheus 接入: 配套 alert_rules.yml 自动同步

关联问题:
- STAB-P1-014: 核心告警规则未在代码中定义
- STAB-P1-015: DB 连接池使用率无指标 (本模块定义阈值, 指标在 metrics.py)
- STAB-P1-016: Redis 熔断状态无指标 (本模块定义阈值, 指标在 metrics.py)
- STAB-P1-017: 模型 fallback 率无全局告警 (本模块定义阈值, 指标在 metrics.py)
- STAB-P1-018: Celery 任务失败无告警 (本模块定义阈值, 指标在 metrics.py)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final


class Severity(str, Enum):
    """告警严重程度."""

    CRITICAL = "critical"  # 立即处理 (PagerDuty/电话)
    WARNING = "warning"  # 24h 内处理 (Slack/邮件)
    INFO = "info"  # 记录即可 (仅日志)


@dataclass(frozen=True)
class AlertRule:
    """单条告警规则定义.

    Attributes:
        id: 规则 ID (e.g. "AR-001")
        name: 规则名称 (e.g. "high_5xx_error_rate")
        metric: 监控指标名 (e.g. "http_requests_total")
        description: 人类可读说明
        severity: 严重程度
        threshold: 阈值
        comparison: 比较运算符 (gt/lt/gte/lte/eq)
        duration_seconds: 持续时长 (秒), 0 表示瞬时
        runbook_url: Runbook 链接
        labels: 附加标签 (用于路由/过滤)
    """

    id: str
    name: str
    metric: str
    description: str
    severity: Severity
    threshold: float
    comparison: str = "gt"
    duration_seconds: int = 300  # 5 分钟
    runbook_url: str = ""
    labels: tuple[tuple[str, str], ...] = field(default_factory=tuple)


# ── 告警规则定义 (单一事实来源) ──
# 顺序: AR-001~099 性能 / AR-100~199 资源 / AR-200~299 稳定性 / AR-300~399 安全 / AR-400+ 可维护性

ALERT_RULES: Final[tuple[AlertRule, ...]] = (
    # ── 性能 (AR-001~099) ──
    AlertRule(
        id="AR-001",
        name="high_p95_latency",
        metric="http_request_duration_seconds_bucket",
        description="核心接口 P95 响应时间 > 2s 持续 5 分钟",
        severity=Severity.WARNING,
        threshold=2.0,
        comparison="gt",
        duration_seconds=300,
        runbook_url="docs/runbooks/high_latency.md",
        labels=(("category", "performance"), ("impact", "user_experience")),
    ),
    AlertRule(
        id="AR-002",
        name="high_p99_latency",
        metric="http_request_duration_seconds_bucket",
        description="核心接口 P99 响应时间 > 5s 持续 5 分钟",
        severity=Severity.CRITICAL,
        threshold=5.0,
        comparison="gt",
        duration_seconds=300,
        runbook_url="docs/runbooks/high_latency.md",
        labels=(("category", "performance"), ("impact", "user_experience")),
    ),
    AlertRule(
        id="AR-003",
        name="high_5xx_error_rate",
        metric="http_requests_total",
        description="5xx 错误率 > 0.1% 持续 5 分钟",
        severity=Severity.CRITICAL,
        threshold=0.001,  # 0.1%
        comparison="gt",
        duration_seconds=300,
        runbook_url="docs/runbooks/5xx_errors.md",
        labels=(("category", "stability"), ("impact", "user_facing")),
    ),
    # ── 资源 (AR-100~199) ──
    AlertRule(
        id="AR-101",
        name="high_cpu_usage",
        metric="process_cpu_usage",
        description="CPU 使用率 > 80% 持续 10 分钟",
        severity=Severity.WARNING,
        threshold=0.8,
        comparison="gt",
        duration_seconds=600,
        runbook_url="docs/runbooks/high_cpu.md",
        labels=(("category", "resource"), ("impact", "performance")),
    ),
    AlertRule(
        id="AR-102",
        name="high_memory_usage",
        metric="process_resident_memory_bytes",
        description="内存使用率 > 75% 持续 10 分钟",
        severity=Severity.WARNING,
        threshold=0.75,
        comparison="gt",
        duration_seconds=600,
        runbook_url="docs/runbooks/high_memory.md",
        labels=(("category", "resource"), ("impact", "performance")),
    ),
    AlertRule(
        id="AR-103",
        name="db_pool_exhaustion",
        metric="db_pool_size",
        description="DB 连接池使用率 > 80% 持续 5 分钟",
        severity=Severity.CRITICAL,
        threshold=0.8,
        comparison="gt",
        duration_seconds=300,
        runbook_url="docs/runbooks/db_pool.md",
        labels=(("category", "resource"), ("impact", "availability")),
    ),
    # ── 稳定性 (AR-200~299) ──
    AlertRule(
        id="AR-201",
        name="db_circuit_open",
        metric="db_circuit_failure_count",
        description="DB 熔断器处于 OPEN 状态 (失败计数 >= 阈值)",
        severity=Severity.CRITICAL,
        threshold=5.0,
        comparison="gte",
        duration_seconds=0,  # 立即触发
        runbook_url="docs/runbooks/db_circuit_open.md",
        labels=(("category", "stability"), ("impact", "availability")),
    ),
    AlertRule(
        id="AR-202",
        name="redis_unavailable",
        metric="redis_circuit_state",
        description="Redis 熔断器状态 != CLOSED (降级中)",
        severity=Severity.WARNING,
        threshold=0.0,  # 0=closed, 1=half_open, 2=open
        comparison="gt",
        duration_seconds=60,
        runbook_url="docs/runbooks/redis_unavailable.md",
        labels=(("category", "stability"), ("impact", "degradation")),
    ),
    AlertRule(
        id="AR-203",
        name="high_model_fallback_rate",
        metric="model_fallback_rate",
        description="模型 fallback 率 > 30% 持续 10 分钟 (非金丝雀期间)",
        severity=Severity.WARNING,
        threshold=0.3,
        comparison="gt",
        duration_seconds=600,
        runbook_url="docs/runbooks/model_fallback.md",
        labels=(("category", "stability"), ("impact", "model_quality")),
    ),
    AlertRule(
        id="AR-204",
        name="celery_task_failure_spike",
        metric="celery_task_failures_total",
        description="Celery 任务失败 5 分钟内 > 10 次",
        severity=Severity.WARNING,
        threshold=10.0,
        comparison="gt",
        duration_seconds=300,
        runbook_url="docs/runbooks/celery_failures.md",
        labels=(("category", "stability"), ("impact", "background_jobs")),
    ),
    AlertRule(
        id="AR-205",
        name="celery_no_heartbeat",
        metric="celery_worker_heartbeat",
        description="Celery worker 无心跳持续 2 分钟",
        severity=Severity.CRITICAL,
        threshold=0.0,
        comparison="eq",
        duration_seconds=120,
        runbook_url="docs/runbooks/celery_dead.md",
        labels=(("category", "stability"), ("impact", "scheduled_jobs")),
    ),
    AlertRule(
        id="AR-206",
        name="high_mttr",
        metric="alert_mttr_seconds",
        description="MTTR (平均故障恢复时长) > 300 秒 (5 分钟) 持续 10 分钟",
        severity=Severity.WARNING,
        threshold=300.0,
        comparison="gt",
        duration_seconds=600,
        runbook_url="docs/runbooks/high_mttr.md",
        labels=(("category", "stability"), ("impact", "recovery_slow")),
    ),
    AlertRule(
        id="AR-207",
        name="unresolved_alerts",
        metric="alert_unresolved_count",
        description="存在未恢复告警持续 1 小时 (有 fired 但无 resolved)",
        severity=Severity.WARNING,
        threshold=0.0,
        comparison="gt",
        duration_seconds=3600,
        runbook_url="docs/runbooks/unresolved_alerts.md",
        labels=(("category", "stability"), ("impact", "unresolved_incidents")),
    ),
    # ── 安全 (AR-300~399) ──
    AlertRule(
        id="AR-301",
        name="auth_failure_spike",
        metric="http_requests_total",
        description="401/403 错误 5 分钟内 > 100 次 (可能暴力破解)",
        severity=Severity.WARNING,
        threshold=100.0,
        comparison="gt",
        duration_seconds=300,
        runbook_url="docs/runbooks/auth_failure.md",
        labels=(("category", "security"), ("impact", "potential_attack")),
    ),
    AlertRule(
        id="AR-302",
        name="audit_log_write_failure",
        metric="audit_log_write_failures_total",
        description="审计日志写入失败 (合规风险)",
        severity=Severity.CRITICAL,
        threshold=0.0,
        comparison="gt",
        duration_seconds=0,
        runbook_url="docs/runbooks/audit_log_failure.md",
        labels=(("category", "security"), ("impact", "compliance")),
    ),
    # ── SEC-P1-005: 异常访问检测 (AR-303~306) ──
    # 数据源: tasks/anomaly_detection.py 周期扫描 OperationLog
    # 指标源: metrics.py anomaly_access_detected_total{type=...}
    AlertRule(
        id="AR-303",
        name="high_frequency_access",
        metric="anomaly_access_detected_total",
        description="同一用户 5 分钟内操作数 > 100 (可能撞库/爬虫)",
        severity=Severity.WARNING,
        threshold=0.0,
        comparison="gt",
        duration_seconds=0,
        runbook_url="docs/runbooks/high_frequency_access.md",
        labels=(
            ("category", "security"),
            ("impact", "potential_attack"),
            ("anomaly_type", "high_frequency"),
        ),
    ),
    AlertRule(
        id="AR-304",
        name="off_hours_access",
        metric="anomaly_access_detected_total",
        description="22:00~06:00 (UTC) 非工作时间管理员/咨询师操作 (潜在数据外泄)",
        severity=Severity.WARNING,
        threshold=0.0,
        comparison="gt",
        duration_seconds=0,
        runbook_url="docs/runbooks/off_hours_access.md",
        labels=(
            ("category", "security"),
            ("impact", "data_exfiltration"),
            ("anomaly_type", "off_hours"),
        ),
    ),
    AlertRule(
        id="AR-305",
        name="cross_region_access",
        metric="anomaly_access_detected_total",
        description="同一用户 24 小时内访问 IP 数量 > 3 (可能账号被盗)",
        severity=Severity.WARNING,
        threshold=0.0,
        comparison="gt",
        duration_seconds=0,
        runbook_url="docs/runbooks/cross_region_access.md",
        labels=(
            ("category", "security"),
            ("impact", "account_takeover"),
            ("anomaly_type", "cross_region"),
        ),
    ),
    AlertRule(
        id="AR-306",
        name="lateral_access_anomaly",
        metric="anomaly_access_detected_total",
        description="同一用户 30 分钟内访问 > 5 种 target_type (横向越权迹象)",
        severity=Severity.WARNING,
        threshold=0.0,
        comparison="gt",
        duration_seconds=0,
        runbook_url="docs/runbooks/lateral_access.md",
        labels=(
            ("category", "security"),
            ("impact", "privilege_escalation"),
            ("anomaly_type", "lateral"),
        ),
    ),
    # ── 可维护性 (AR-400+) ──
    AlertRule(
        id="AR-401",
        name="test_coverage_drop",
        metric="test_coverage_percent",
        description="测试覆盖率 < 60% (CI 阻断)",
        severity=Severity.WARNING,
        threshold=60.0,
        comparison="lt",
        duration_seconds=0,
        runbook_url="docs/runbooks/low_coverage.md",
        labels=(("category", "maintainability"), ("impact", "quality")),
    ),
    AlertRule(
        id="AR-402",
        name="circular_dependency",
        metric="circular_dependencies_count",
        description="循环依赖数量 > 0",
        severity=Severity.WARNING,
        threshold=0.0,
        comparison="gt",
        duration_seconds=0,
        runbook_url="docs/runbooks/circular_dep.md",
        labels=(("category", "maintainability"), ("impact", "architecture")),
    ),
    # ── 可观测性 (AR-208) ──
    # R-005 修复: fire-and-forget 任务失败率告警
    # 指标: fire_forget_tasks_total{task_type, status="failed"} 5 分钟内增量
    # 阈值: 5 分钟内失败 > 5 次 (覆盖 assessment_save / review_task_create /
    #   warning_intervention / validation_job / pdf_generation 5 类任务)
    # 严重程度: WARNING (24h 内处理) — 失败可能导致评估结果丢失、告警未触发等
    AlertRule(
        id="AR-208",
        name="fire_forget_task_failure_spike",
        metric="fire_forget_tasks_total",
        description="fire-and-forget 任务失败 5 分钟内 > 5 次 (评估保存/复核/告警/PDF 等)",
        severity=Severity.WARNING,
        threshold=5.0,
        comparison="gt",
        duration_seconds=300,
        runbook_url="docs/runbooks/fire_forget_failures.md",
        labels=(("category", "observability"), ("impact", "background_tasks")),
    ),
    # ── 可观测性 (AR-209) ──
    # R-006 修复: 启动组件失败告警
    # 指标: startup_component_failures_total{component, fatal}
    # 阈值: 任一启动组件失败 > 0 (覆盖 init_db / seed_database / ensure_pii_key /
    #   model_preload / sentry / observability_exporter / health_monitor /
    #   ws_pubsub / canary_fallback 9 类组件)
    # 严重程度: WARNING — 致命失败 lifespan 会中止，此处捕获非致命降级失败
    AlertRule(
        id="AR-209",
        name="startup_component_failure",
        metric="startup_component_failures_total",
        description="启动组件失败 (非致命降级运行，需排查 model_preload/sentry/observability 等)",
        severity=Severity.WARNING,
        threshold=0.0,
        comparison="gt",
        duration_seconds=0,
        runbook_url="docs/runbooks/startup_failures.md",
        labels=(("category", "observability"), ("impact", "degraded_startup")),
    ),
)


# ── 阈值索引 (快速查找) ──
ALERT_RULES_BY_ID: Final[dict[str, AlertRule]] = {rule.id: rule for rule in ALERT_RULES}
ALERT_RULES_BY_NAME: Final[dict[str, AlertRule]] = {
    rule.name: rule for rule in ALERT_RULES
}


def get_rules_by_severity(severity: Severity) -> tuple[AlertRule, ...]:
    """按严重程度过滤规则."""
    return tuple(rule for rule in ALERT_RULES if rule.severity == severity)


def get_rules_by_label(key: str, value: str) -> tuple[AlertRule, ...]:
    """按标签过滤规则 (e.g. category=stability)."""
    return tuple(rule for rule in ALERT_RULES if (key, value) in rule.labels)


def validate_rules() -> list[str]:
    """校验规则完整性 (CI 中调用).

    Returns:
        错误信息列表, 空列表表示通过
    """
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()

    for rule in ALERT_RULES:
        # ID 唯一性
        if rule.id in seen_ids:
            errors.append(f"Duplicate rule ID: {rule.id}")
        seen_ids.add(rule.id)

        # 名称唯一性
        if rule.name in seen_names:
            errors.append(f"Duplicate rule name: {rule.name}")
        seen_names.add(rule.name)

        # 比较运算符合法性
        if rule.comparison not in {"gt", "lt", "gte", "lte", "eq"}:
            errors.append(f"Rule {rule.id}: invalid comparison {rule.comparison!r}")

        # 持续时长非负
        if rule.duration_seconds < 0:
            errors.append(f"Rule {rule.id}: duration_seconds must be >= 0")

        # Runbook URL 非空 (critical 必须)
        if rule.severity == Severity.CRITICAL and not rule.runbook_url:
            errors.append(f"Rule {rule.id}: critical rule must have runbook_url")

    return errors


def render_prometheus_rules() -> str:
    """渲染为 Prometheus alerting rules YAML 格式 (供 alert_rules.yml 同步)."""
    lines: list[str] = [
        "# Auto-generated from app/core/alert_rules.py",
        "# DO NOT EDIT - modify source instead",
        "",
    ]
    lines.append("groups:")
    lines.append("  - name: bysj-alerts")
    lines.append("    rules:")

    for rule in ALERT_RULES:
        lines.append(f"      # {rule.id}: {rule.description}")
        lines.append(f"      - alert: {rule.name}")
        lines.append(f"        expr: {rule.metric} {rule.comparison} {rule.threshold}")
        lines.append(
            f"        for: {rule.duration_seconds}s"
            if rule.duration_seconds > 0
            else "        for: 0s"
        )
        lines.append("        labels:")
        lines.append(f"          severity: {rule.severity.value}")
        for k, v in rule.labels:
            lines.append(f"          {k}: {v}")
        lines.append("        annotations:")
        lines.append(f'          summary: "{rule.description}"')
        lines.append(f'          runbook_url: "{rule.runbook_url}"')
        lines.append("")

    return "\n".join(lines)


__all__ = [
    "AlertRule",
    "Severity",
    "ALERT_RULES",
    "ALERT_RULES_BY_ID",
    "ALERT_RULES_BY_NAME",
    "get_rules_by_severity",
    "get_rules_by_label",
    "validate_rules",
    "render_prometheus_rules",
]
