"""GDPR 合规服务 (v1.27 P1 任务 #11).

实现用户的"数据可携权"(导出) 与 "被遗忘权"(删除).

设计原则:
- 软删除优先: 用户的 PII 字段被脱敏而非物理删除，以保留审计链
- 匿名化: 用户名/邮箱/手机号/紧急联系人等替换为占位符
- 关键业务数据保留: 风险评估/预警/危机事件保留(用于法律合规与系统安全)
- 完整审计: 每次 GDPR 操作写入 OperationLog
- 二次确认: 删除操作要求用户重新输入密码

安全注意:
- 导出数据不能明文存储 (临时文件, 下载后 24h 自动清理)
- 删除操作需管理员复核 (大操作, 防误删)

MAINT-P2-001: 原 812 行单文件拆分为 3 文件, 每文件 ≤500 行。
拆分结构:
- 本文件: 模块级常量、辅助函数、GDPRService 装配
- gdpr_service_export.py: 数据导出 (ExportMixin)
- gdpr_service_anonymize.py: 数据匿名化/删除 (AnonymizeMixin)
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pii_crypto import (
    ENCRYPTED_PREFIX,
    ENCRYPTED_PREFIX_V2,
    decrypt_field,
)
from app.models.admin import OperationLog
from app.models.intervention import InterventionPlan, InterventionTask
from app.models.review import CrisisEvent
from app.models.risk import RiskAssessment, WarningNotification
from app.models.user import EmergencyContact, UserCounselorBinding, UserProfile
from app.services.gdpr_service_anonymize import AnonymizeMixin
from app.services.gdpr_service_export import ExportMixin

logger = logging.getLogger(__name__)

# 匿名化占位符
ANON_USERNAME_PREFIX = "anon_"
ANON_EMAIL_DOMAIN = "@deleted.local"
ANON_PHONE = "00000000000"
ANON_NAME = "[已删除]"
# C-Svc-8 修复：自由文本字段匿名化占位符（NOT NULL 字段必须用占位符，不能置 None）
ANON_TEXT = "[ANONYMIZED]"

# 关键保留期 (天) - 用于合规审计的最低保留
LEGAL_RETENTION_DAYS = 365 * 3  # 3年 (符合医疗数据一般要求)


class GDPRService(ExportMixin, AnonymizeMixin):
    """GDPR 数据导出与删除服务.

    通过 Mixin 多继承组合以下功能模块:
    - ExportMixin: 数据导出 (一次性导出 + 流式迭代器), 覆盖 Article 15/20
    - AnonymizeMixin: 数据匿名化/删除 (Article 17 被遗忘权)

    本类仅保留 `__init__` 以及模块级工具:
    - `logger`: 模块级日志器
    - `ANON_*` / `LEGAL_RETENTION_DAYS`: 匿名化占位符与保留期常量 (AnonymizeMixin 通过延迟导入引用)
    - `_safe_decrypt` / `_profile_to_dict` / `_contact_to_dict` / `_binding_to_dict` /
      `_risk_to_dict` / `_warning_to_dict` / `_crisis_to_dict` / `_plan_to_dict` /
      `_task_to_dict` / `_log_to_dict`: 模型序列化辅助函数 (ExportMixin 通过延迟导入引用)
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db


# ── 辅助函数 ─────────────────────────────────────────────────────────


def _safe_decrypt(value: str | None, field: str) -> str | None:
    """安全解密 (失败返回 mask).

    SEC-P2-004: 支持 v1 (Fernet) 和 v2 (AES-256-GCM) 双前缀检测.
    """
    if not value:
        return value
    # SEC-P2-004: 检测 v1 (enc:v1:) 或 v2 (enc:v2:) 前缀
    if value.startswith(ENCRYPTED_PREFIX) or value.startswith(ENCRYPTED_PREFIX_V2):
        try:
            return decrypt_field(value, field)
        except ValueError:
            return "[DECRYPT_FAILED]"
    return value


def _profile_to_dict(p: UserProfile) -> dict:
    return {
        "nickname": p.nickname,
        "gender": p.gender,
        "age": p.age,
        "language": p.language,
        "theme": p.theme,
        "reminder_freq": p.reminder_freq,
    }


def _contact_to_dict(c: EmergencyContact) -> dict:
    return {
        "name": c.name,
        "relationship": c.relationship,
        "phone": c.phone,
    }


def _binding_to_dict(b: UserCounselorBinding) -> dict:
    return {
        "counselor_id": b.counselor_id,
        "status": b.status,
        # UserCounselorBinding 实际使用 bound_at 而非 created_at (v1.27 模型修正)
        "created_at": b.bound_at.isoformat() if b.bound_at else None,
    }


def _risk_to_dict(r: RiskAssessment) -> dict:
    return {
        "id": r.id,
        "assessment_type": r.assessment_type,
        "risk_level": r.risk_level,
        "risk_score": r.risk_score,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _warning_to_dict(w: WarningNotification) -> dict:
    return {
        "id": w.id,
        "level": w.current_level,
        "previous_level": w.previous_level,
        "message": w.trigger_reason,
        "status": "handled" if w.is_handled else ("read" if w.is_read else "pending"),
        "is_read": w.is_read,
        "is_handled": w.is_handled,
        "handle_action": w.handle_action,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


def _crisis_to_dict(c: CrisisEvent) -> dict:
    return {
        "id": c.id,
        "trigger_source": c.trigger_source,
        "crisis_score": c.crisis_score,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _plan_to_dict(p: InterventionPlan) -> dict:
    return {
        "id": p.id,
        "status": p.status,
        "risk_level": p.risk_level,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _task_to_dict(t: InterventionTask) -> dict:
    return {
        "id": t.id,
        "plan_id": t.plan_id,
        "task_name": t.task_name,
        "task_type": t.task_type,
        "description": t.description,
        "schedule": t.schedule,
        "duration_minutes": t.duration_minutes,
        "sort_order": t.sort_order,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _log_to_dict(o: OperationLog) -> dict:
    return {
        "action": o.action_type,
        "resource_type": o.target_type,
        "resource_id": o.target_id,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }
